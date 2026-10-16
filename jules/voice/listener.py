"""Voice audio capture, VAD (Voice Activity Detection), Push-to-Talk and Barge-in.

Provides AudioListener for 16kHz mono audio capture via sounddevice,
with integrated VAD energy/RMS + zero-crossing analysis, Push-to-Talk (PTT),
and low-latency (< 50ms) Barge-in interruption when Jules is speaking.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
import inspect
import io
import logging
import threading
import time
from typing import Any, Callable
import wave

import numpy as np

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None  # type: ignore

from jules.daemon.state import DaemonState, StatePublisher

logger = logging.getLogger(__name__)


class AudioHardwareUnavailableError(RuntimeError):
    """Raised when audio capture hardware is not available or PortAudio fails."""


@dataclass(slots=True)
class BargeInEvent:
    """Event emitted when user speech interrupts Jules while speaking."""

    timestamp: float = field(default_factory=time.time)
    audio_frame: bytes | None = None
    interrupted_state: DaemonState = DaemonState.SPEAKING


# Alias for explicit naming
BargeInDetected = BargeInEvent
BargeInCallback = Callable[[BargeInEvent], Any]


class VADDetector:
    """Lightweight energy/RMS and zero-crossing voice activity detector.

    Designed for 16kHz mono audio in 30ms frames (480 samples).
    Detects speech activity and tracks utterance completion after continuous silence.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        speech_threshold: float = 0.04,
        silence_timeout_ms: float = 600.0,
        min_zcr: float = 0.005,
        max_zcr: float = 0.8,
        min_speech_frames: int = 1,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_samples = int(self.sample_rate * (self.frame_duration_ms / 1000.0))
        self.speech_threshold = speech_threshold
        self.silence_timeout_ms = silence_timeout_ms
        self.min_zcr = min_zcr
        self.max_zcr = max_zcr
        self.min_speech_frames = min_speech_frames

        self.has_speech_started: bool = False
        self.silence_accumulated_ms: float = 0.0
        self.is_utterance_complete: bool = False
        self.total_speech_frames: int = 0

    def _to_float_samples(self, frame: bytes | np.ndarray) -> np.ndarray:
        """Convert input frame (bytes, int16, or float32) into normalized [-1.0, 1.0] float32."""
        if isinstance(frame, bytes):
            samples_int = np.frombuffer(frame, dtype=np.int16)
            return samples_int.astype(np.float32) / 32768.0

        if isinstance(frame, np.ndarray):
            if frame.dtype == np.int16:
                return frame.astype(np.float32) / 32768.0
            if np.issubdtype(frame.dtype, np.floating):
                return frame.astype(np.float32)

        return np.array([], dtype=np.float32)

    def calculate_rms(self, frame: bytes | np.ndarray) -> float:
        """Calculate Root Mean Square (RMS) energy normalized to [0.0, 1.0]."""
        samples = self._to_float_samples(frame)
        if len(samples) == 0:
            return 0.0
        return float(np.sqrt(np.mean(samples**2)))

    def calculate_zcr(self, frame: bytes | np.ndarray) -> float:
        """Calculate Zero Crossing Rate (ZCR) of the audio frame."""
        samples = self._to_float_samples(frame)
        if len(samples) < 2:
            return 0.0
        signs = samples >= 0
        crossings = np.count_nonzero(signs[1:] != signs[:-1])
        return float(crossings / len(samples))

    def is_speech(self, frame: bytes | np.ndarray) -> bool:
        """Determine whether the 30ms audio frame contains speech."""
        rms = self.calculate_rms(frame)
        zcr = self.calculate_zcr(frame)

        # Speech frame criteria:
        # RMS energy exceeds speech_threshold and ZCR is within human vocal/speech bounds
        # Rejecting pure DC offset (where ZCR is zero) or extreme high-freq interference
        if rms >= self.speech_threshold and (self.min_zcr <= zcr <= self.max_zcr):
            return True
        return False

    def process_frame(self, frame: bytes | np.ndarray) -> tuple[bool, bool]:
        """Process a 30ms frame through the utterance state machine.

        Returns:
            (is_speech: bool, is_utterance_complete: bool)
        """
        speech = self.is_speech(frame)

        if speech:
            self.has_speech_started = True
            self.silence_accumulated_ms = 0.0
            self.total_speech_frames += 1
            return True, False

        # Silence detected
        if self.has_speech_started and not self.is_utterance_complete:
            self.silence_accumulated_ms += self.frame_duration_ms
            if self.silence_accumulated_ms >= self.silence_timeout_ms:
                if self.total_speech_frames >= self.min_speech_frames:
                    self.is_utterance_complete = True
                    return False, True
                self.reset()
                return False, False

        return False, self.is_utterance_complete

    def reset(self) -> None:
        """Reset the VAD state machine for a new utterance."""
        self.has_speech_started = False
        self.silence_accumulated_ms = 0.0
        self.is_utterance_complete = False
        self.total_speech_frames = 0


class AudioListener:
    """Captures 16kHz mono audio, runs VAD, handles PTT and triggers Barge-in."""

    def __init__(
        self,
        state_publisher: StatePublisher | None = None,
        vad: VADDetector | None = None,
        barge_in_callback: BargeInCallback | None = None,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        device: int | str | None = None,
        stream_factory: Callable[..., Any] | None = None,
        strict_hardware: bool = False,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.state_publisher = state_publisher
        self.vad = vad or VADDetector(
            sample_rate=sample_rate,
            frame_duration_ms=frame_duration_ms,
        )
        self.barge_in_callback = barge_in_callback
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_samples = int(self.sample_rate * (self.frame_duration_ms / 1000.0))
        self.frame_bytes_len = self.frame_samples * 2  # 16-bit PCM = 2 bytes/sample

        self.device = device
        self.strict_hardware = strict_hardware
        self._loop = loop
        self._lock = threading.RLock()

        self.is_recording: bool = False
        self.is_available: bool = False
        self._current_recording_buffer = bytearray()
        self._incoming_buffer = bytearray()
        self._active_queues: list[asyncio.Queue[bytes]] = []

        self._stream: Any = None
        self._init_stream(stream_factory)

    def _init_stream(self, stream_factory: Callable[..., Any] | None) -> None:
        """Initialize sounddevice InputStream with graceful headless fallback."""
        try:
            if stream_factory is not None:
                self._stream = stream_factory(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.frame_samples,
                    device=self.device,
                    callback=self._audio_callback,
                )
                self.is_available = True
            elif sd is not None:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.frame_samples,
                    device=self.device,
                    callback=self._audio_callback,
                )
                self.is_available = True
            else:
                if self.strict_hardware:
                    raise AudioHardwareUnavailableError("sounddevice package is not available.")
                self.is_available = False
        except Exception as exc:
            if self.strict_hardware:
                raise AudioHardwareUnavailableError(f"Audio capture hardware unavailable: {exc}") from exc
            logger.warning("Audio capture device not available (%s). Running in headless/mock mode.", exc)
            self.is_available = False
            self._stream = None

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        """Real-time sounddevice stream callback running on PortAudio thread."""
        if status:
            logger.debug("sounddevice stream status: %s", status)
        data_bytes = indata.tobytes()
        self.feed_audio(data_bytes)

    def _trigger_barge_in(self, event: BargeInEvent) -> None:
        """Dispatch Barge-in event immediately to halt speaker playback."""
        if self.barge_in_callback is not None:
            try:
                res = self.barge_in_callback(event)
                if inspect.iscoroutine(res):
                    loop = self._get_loop()
                    if loop and loop.is_running():
                        try:
                            current_loop = asyncio.get_running_loop()
                            if current_loop is loop:
                                loop.create_task(res)
                            else:
                                asyncio.run_coroutine_threadsafe(res, loop)
                        except RuntimeError:
                            asyncio.run_coroutine_threadsafe(res, loop)
            except Exception as exc:
                logger.error("Error executing barge_in_callback: %s", exc)

    def _get_loop(self) -> asyncio.AbstractEventLoop | None:
        """Retrieve active asyncio event loop if running."""
        if self._loop is not None and not self._loop.is_closed():
            return self._loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None

    def process_frame(self, frame: bytes | np.ndarray) -> tuple[bool, bool]:
        """Process a single 30ms audio frame.

        Evaluates Barge-in if Jules is speaking, checks VAD activity,
        and accumulates recording data.
        """
        frame_bytes = frame if isinstance(frame, bytes) else frame.tobytes()

        # 1. Barge-in check: If Jules is speaking and user speech is detected
        if self.state_publisher is not None:
            current_state = self.state_publisher.get_current_state().state
            if current_state == DaemonState.SPEAKING:
                if self.vad.is_speech(frame):
                    event = BargeInDetected(
                        timestamp=time.time(),
                        audio_frame=frame_bytes,
                        interrupted_state=DaemonState.SPEAKING,
                    )
                    self._trigger_barge_in(event)

        # 2. Recording buffer accumulation
        with self._lock:
            if self.is_recording:
                self._current_recording_buffer.extend(frame_bytes)

        # 3. VAD analysis
        is_speech, is_complete = self.vad.process_frame(frame)

        # 4. Dispatch to any active async phrase queues
        if self._active_queues:
            loop = self._get_loop()
            for q in list(self._active_queues):
                if loop and loop.is_running():
                    loop.call_soon_threadsafe(q.put_nowait, frame_bytes)
                else:
                    try:
                        q.put_nowait(frame_bytes)
                    except asyncio.QueueFull:
                        pass

        return is_speech, is_complete

    def feed_audio(self, chunk: bytes | np.ndarray) -> None:
        """Feed arbitrary audio chunks into the listener, slicing into 30ms frames."""
        data_bytes = chunk if isinstance(chunk, bytes) else chunk.tobytes()

        with self._lock:
            self._incoming_buffer.extend(data_bytes)
            while len(self._incoming_buffer) >= self.frame_bytes_len:
                frame = bytes(self._incoming_buffer[: self.frame_bytes_len])
                del self._incoming_buffer[: self.frame_bytes_len]
                self.process_frame(frame)

    def start_recording(self) -> None:
        """Start recording audio stream and update state to LISTENING."""
        with self._lock:
            self._current_recording_buffer.clear()
            self._incoming_buffer.clear()
            self.vad.reset()
            self.is_recording = True

        if self._stream is not None:
            try:
                self._stream.start()
            except Exception as exc:
                logger.warning("Failed to start audio stream: %s", exc)

        if self.state_publisher is not None:
            self.state_publisher.update(
                state=DaemonState.LISTENING,
                last_event="ptt_start",
            )

    def stop_recording(self) -> bytes:
        """Stop recording, return collected PCM audio bytes, and set state to IDLE."""
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception as exc:
                logger.warning("Failed to stop audio stream: %s", exc)

        with self._lock:
            self.is_recording = False
            result = bytes(self._current_recording_buffer)

        if self.state_publisher is not None:
            self.state_publisher.update(
                state=DaemonState.IDLE,
                last_event="ptt_stop",
            )

        return result

    def toggle_ptt(self) -> bool:
        """Toggle Push-to-Talk recording state.

        Returns:
            True if recording started, False if stopped.
        """
        if self.is_recording:
            self.stop_recording()
            return False
        self.start_recording()
        return True

    async def handle_ipc_command(
        self,
        op: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Handle IPC commands such as voice_ptt_toggle and voice_barge_in."""
        if op == "voice_ptt_toggle":
            is_active = self.toggle_ptt()
            state_val = (
                self.state_publisher.get_current_state().state.value
                if self.state_publisher
                else (DaemonState.LISTENING.value if is_active else DaemonState.IDLE.value)
            )
            return {
                "status": "ok",
                "ptt": "active" if is_active else "inactive",
                "state": state_val,
            }

        if op == "voice_barge_in":
            if self.state_publisher:
                self.state_publisher.update(
                    state=DaemonState.IDLE,
                    last_event="voice_barge_in",
                )
            return {"status": "ok", "barge_in": True, "state": DaemonState.IDLE.value}

        return {"status": "error", "error": f"Unknown voice operation: {op}"}

    def record_phrase(
        self,
        timeout: float | None = 10.0,
        silence_timeout_ms: float | None = None,
    ) -> asyncio.Future[bytes]:
        """Record an utterance until silence is detected by VAD.

        Returns an asyncio.Future/Task resolving to 16kHz 16-bit mono PCM bytes.
        """
        self.start_recording()
        loop = self._get_loop() or asyncio.get_event_loop()
        return loop.create_task(
            self._record_phrase_coro(timeout=timeout, silence_timeout_ms=silence_timeout_ms)
        )

    async def _record_phrase_coro(
        self,
        timeout: float | None = 10.0,
        silence_timeout_ms: float | None = None,
    ) -> bytes:
        """Coroutine capturing audio until VAD signals utterance completion."""
        original_timeout = self.vad.silence_timeout_ms
        if silence_timeout_ms is not None:
            self.vad.silence_timeout_ms = silence_timeout_ms

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._active_queues.append(queue)
        collected_frames: list[bytes] = []

        start_time = time.time()
        try:
            while True:
                if timeout is not None and (time.time() - start_time) > timeout:
                    break

                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                collected_frames.append(frame)
                if self.vad.is_utterance_complete:
                    break

            return b"".join(collected_frames)
        finally:
            self.vad.silence_timeout_ms = original_timeout
            if queue in self._active_queues:
                self._active_queues.remove(queue)
            self.stop_recording()

    async def record_phrase_stream(
        self,
        timeout: float | None = 10.0,
        silence_timeout_ms: float | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """Async generator yielding 30ms PCM audio frames until utterance completion."""
        original_timeout = self.vad.silence_timeout_ms
        if silence_timeout_ms is not None:
            self.vad.silence_timeout_ms = silence_timeout_ms

        queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._active_queues.append(queue)

        self.start_recording()
        start_time = time.time()
        try:
            while True:
                if timeout is not None and (time.time() - start_time) > timeout:
                    break

                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                yield frame
                if self.vad.is_utterance_complete:
                    break
        finally:
            self.vad.silence_timeout_ms = original_timeout
            if queue in self._active_queues:
                self._active_queues.remove(queue)
            self.stop_recording()

    def to_wav_bytes(self, pcm_data: bytes) -> bytes:
        """Package raw 16kHz mono 16-bit PCM bytes into a standard RIFF WAV format."""
        bio = io.BytesIO()
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM = 2 bytes
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)
        return bio.getvalue()

    def to_numpy(self, pcm_data: bytes) -> np.ndarray:
        """Convert raw 16-bit PCM bytes into normalized float32 NumPy array [-1.0, 1.0]."""
        samples_int = np.frombuffer(pcm_data, dtype=np.int16)
        return samples_int.astype(np.float32) / 32768.0

    def close(self) -> None:
        """Close sounddevice stream and release resources."""
        with self._lock:
            self.is_recording = False
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception as exc:
                    logger.debug("Error closing stream: %s", exc)
                self._stream = None
