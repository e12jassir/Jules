"""Ultra-fast local speech transcription with faster-whisper INT8 and Sanitizer integration.

Provides LocalTranscriber for low-latency (< 350ms on 3s clips) speech-to-text
with pre-loaded faster-whisper model running in background threads, and immediate
Sanitizer security filtering on transcribed text.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import gc
import io
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable
import wave

import numpy as np

try:
    import faster_whisper
except ImportError:  # pragma: no cover
    faster_whisper = None  # type: ignore

try:
    import av

    _orig_av_open = av.open

    def _compat_av_open(*args: Any, **kwargs: Any) -> Any:
        # PyAV 14+ removed metadata_errors parameter from av.open
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)

    av.open = _compat_av_open
except Exception:  # pragma: no cover
    pass

from jules.sanitizer.sanitizer import Sanitizer

logger = logging.getLogger(__name__)


class TranscriberError(RuntimeError):
    """Base exception for voice transcription errors."""


class AudioFormatError(TranscriberError, ValueError):
    """Raised when audio data is empty, corrupted, or in an unsupported format."""


class ModelLoadError(TranscriberError):
    """Raised when loading the faster-whisper model fails."""


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """Result of speech transcription with security analysis and latency metrics."""

    text: str
    sanitized_text: str
    is_safe: bool
    reason: str | None
    language: str
    duration: float
    latency_ms: float


class LocalTranscriber:
    """Pre-loaded faster-whisper INT8 speech transcriber with Sanitizer integration.

    Executes inference in a background thread via asyncio.to_thread with beam_size=1
    and vad_filter=True to guarantee ultra-fast response without blocking the event loop.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 1,
        vad_filter: bool = True,
        language: str | None = "es",
        lazy_load: bool = False,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self.language = language
        self.model_factory = model_factory

        self._model: Any = None
        self._lock = threading.Lock()

        if not lazy_load:
            self.load_model()

    @property
    def is_loaded(self) -> bool:
        """Return True if faster-whisper model is currently loaded in memory."""
        return self._model is not None

    def load_model(self) -> None:
        """Load the faster-whisper model into memory."""
        with self._lock:
            if self._model is not None:
                return

            try:
                if self.model_factory is not None:
                    self._model = self.model_factory(
                        self.model_size,
                        device=self.device,
                        compute_type=self.compute_type,
                    )
                elif faster_whisper is not None:
                    self._model = faster_whisper.WhisperModel(
                        self.model_size,
                        device=self.device,
                        compute_type=self.compute_type,
                    )
                else:  # pragma: no cover
                    raise ModelLoadError("faster-whisper is not installed.")
                logger.info(
                    "Loaded faster-whisper model (%s, device=%s, compute=%s)",
                    self.model_size,
                    self.device,
                    self.compute_type,
                )
            except Exception as exc:
                self._model = None
                raise ModelLoadError(
                    f"Failed to load speech transcription model '{self.model_size}': {exc}"
                ) from exc

    def unload_model(self) -> None:
        """Unload the model and release memory."""
        with self._lock:
            self._model = None
            gc.collect()
            logger.info("Unloaded faster-whisper model.")

    def _prepare_audio(
        self,
        audio: bytes | np.ndarray | Path | str | io.BytesIO,
        sample_rate: int = 16000,
    ) -> np.ndarray:
        """Normalize audio input to 1D float32 numpy array in [-1.0, 1.0]."""
        if isinstance(audio, np.ndarray):
            if audio.size == 0:
                raise AudioFormatError("Empty audio array provided for transcription.")
            if np.issubdtype(audio.dtype, np.integer):
                samples = audio.astype(np.float32) / 32768.0
            else:
                samples = audio.astype(np.float32)
            if samples.ndim > 1:
                samples = np.mean(samples, axis=-1)
            return np.ascontiguousarray(samples.ravel())

        if isinstance(audio, io.BytesIO):
            data = audio.getvalue()
            if len(data) == 0:
                raise AudioFormatError("Empty audio stream provided for transcription.")
            return self._prepare_audio(data, sample_rate=sample_rate)

        if isinstance(audio, (str, Path)):
            path = Path(audio)
            if not path.exists():
                raise AudioFormatError(f"Audio file not found: {audio}")
            data = path.read_bytes()
            if len(data) == 0:
                raise AudioFormatError(f"Audio file is empty: {audio}")
            return self._prepare_audio(data, sample_rate=sample_rate)

        if isinstance(audio, (bytes, bytearray)):
            raw_bytes = bytes(audio)
            if len(raw_bytes) == 0:
                raise AudioFormatError("Empty audio bytes provided for transcription.")

            # Check for RIFF WAV container
            if raw_bytes.startswith(b"RIFF") and len(raw_bytes) >= 44:
                try:
                    with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                        channels = wf.getnchannels()
                        sampwidth = wf.getsampwidth()
                        nframes = wf.getnframes()
                        frames = wf.readframes(nframes)

                        if sampwidth == 2:
                            arr = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                        elif sampwidth == 1:
                            arr = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                        elif sampwidth == 4:
                            arr = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
                        else:
                            arr = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

                        if channels > 1:
                            arr = arr.reshape(-1, channels).mean(axis=1)

                        if arr.size == 0:
                            raise AudioFormatError("WAV file contains 0 audio frames.")

                        return np.ascontiguousarray(arr.astype(np.float32))
                except Exception as exc:
                    logger.debug("wave.open failed on WAV bytes (%s), attempting decode_audio fallback", exc)
                    if faster_whisper is not None:
                        try:
                            decoded = faster_whisper.audio.decode_audio(
                                io.BytesIO(raw_bytes),
                                sampling_rate=sample_rate,
                            )
                            return np.ascontiguousarray(decoded.astype(np.float32))
                        except Exception as dec_exc:
                            raise AudioFormatError(f"Failed to decode audio: {dec_exc}") from dec_exc
                    raise AudioFormatError(f"Failed to decode WAV audio: {exc}") from exc

            # Raw 16-bit PCM mono bytes (e.g. from AudioListener)
            if len(raw_bytes) % 2 != 0:
                raw_bytes = raw_bytes[: len(raw_bytes) - (len(raw_bytes) % 2)]

            if len(raw_bytes) == 0:
                raise AudioFormatError("Audio bytes too short for 16-bit PCM samples.")

            samples_int = np.frombuffer(raw_bytes, dtype=np.int16)
            samples_float = samples_int.astype(np.float32) / 32768.0
            return np.ascontiguousarray(samples_float)

        raise AudioFormatError(f"Unsupported audio type: {type(audio)}")

    def _transcribe_sync(
        self,
        audio_array: np.ndarray,
        sample_rate: int,
    ) -> tuple[str, str, float]:
        """Synchronous inference worker executed in background thread.

        Returns:
            (transcribed_text, detected_language, audio_duration_seconds)
        """
        if self._model is None:
            self.load_model()

        try:
            segments, info = self._model.transcribe(
                audio_array,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                language=self.language,
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                temperature=0.0,
            )

            # Eagerly iterate and consume all segments inside the worker thread
            chunks = [seg.text.strip() for seg in segments if getattr(seg, "text", "").strip()]
            text = " ".join(chunks).strip()

            detected_lang = getattr(info, "language", "") or self.language or "unknown"
            duration = getattr(info, "duration", 0.0)
            if duration <= 0.0:
                duration = float(len(audio_array) / float(sample_rate))

            return text, detected_lang, duration

        except Exception as exc:
            logger.error("Speech transcription inference error: %s", exc)
            raise TranscriberError(f"Transcription failed: {exc}") from exc

    async def transcribe(
        self,
        audio: bytes | np.ndarray | Path | str | io.BytesIO,
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        """Transcribe speech audio asynchronously without blocking the event loop.

        Runs inference in a worker thread, measures latency, and applies Sanitizer checks.

        Args:
            audio: WAV bytes, raw PCM bytes, NumPy array, file Path, str path, or BytesIO.
            sample_rate: Audio sampling rate in Hz (default 16000).

        Returns:
            TranscriptionResult with raw text, sanitized text, safety status, and metrics.
        """
        audio_array = self._prepare_audio(audio, sample_rate=sample_rate)
        if audio_array.size == 0:
            raise AudioFormatError("Empty audio data provided for transcription.")

        start_time = time.perf_counter()

        # Run inference in worker thread via asyncio.to_thread
        text, language, duration = await asyncio.to_thread(
            self._transcribe_sync,
            audio_array,
            sample_rate,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        # Pass through Sanitizer
        sanitized = Sanitizer.check(text)
        is_safe = sanitized.is_safe
        reason = sanitized.reason
        sanitized_text = text if is_safe else ""

        return TranscriptionResult(
            text=text,
            sanitized_text=sanitized_text,
            is_safe=is_safe,
            reason=reason,
            language=language,
            duration=duration,
            latency_ms=latency_ms,
        )


__all__ = [
    "AudioFormatError",
    "LocalTranscriber",
    "ModelLoadError",
    "TranscriberError",
    "TranscriptionResult",
]
