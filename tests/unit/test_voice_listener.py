"""Unit tests for voice audio capture, VAD, Push-to-Talk and Barge-in."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jules.daemon.state import DaemonState, StatePublisher
from jules.voice.listener import (
    AudioHardwareUnavailableError,
    AudioListener,
    BargeInDetected,
    BargeInEvent,
    VADDetector,
)


def _generate_frame(
    duration_ms: int = 30,
    sample_rate: int = 16000,
    amplitude: float = 0.0,
    freq: float = 400.0,
) -> bytes:
    """Helper to generate a PCM 16-bit mono audio frame."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    if amplitude == 0.0:
        samples = np.zeros(num_samples, dtype=np.int16)
    else:
        t = np.linspace(0, duration_ms / 1000.0, num_samples, endpoint=False)
        wave = amplitude * np.sin(2 * np.pi * freq * t)
        samples = np.clip(wave, -32768, 32767).astype(np.int16)
    return samples.tobytes()


@pytest.fixture
def publisher(tmp_path: Path) -> StatePublisher:
    """Fixture providing an isolated StatePublisher."""
    state_file = tmp_path / "jules.state"
    return StatePublisher(target_path=state_file, initial_state=DaemonState.IDLE)


@pytest.fixture(autouse=True)
def mock_sounddevice():
    """Mock sounddevice.InputStream by default so tests never block on hardware PortAudio streams."""
    mock_stream = MagicMock()
    with patch("sounddevice.InputStream", return_value=mock_stream):
        yield mock_stream


class TestVADDetector:
    """Tests for lightweight VAD energy/RMS and zero-crossing detection."""

    def test_vad_detects_silence_vs_speech(self) -> None:
        """VAD should differentiate silence and speech frames correctly."""
        vad = VADDetector(sample_rate=16000, frame_duration_ms=30, speech_threshold=0.015)

        # Pure silence
        silence_frame = _generate_frame(duration_ms=30, amplitude=0.0)
        assert vad.is_speech(silence_frame) is False

        # Ambient low-level noise (amplitude ~ 40/32768 = ~0.0012 RMS)
        noise_samples = np.random.normal(0, 30, 480).astype(np.int16).tobytes()
        assert vad.is_speech(noise_samples) is False

        # Speech frame (400Hz tone, amplitude 6000, RMS ~ 0.13)
        speech_frame = _generate_frame(duration_ms=30, amplitude=6000.0, freq=400.0)
        assert vad.is_speech(speech_frame) is True

    def test_vad_dc_offset_rejected_by_zero_crossing(self) -> None:
        """VAD should reject pure DC offset where zero-crossing rate is zero."""
        vad = VADDetector(sample_rate=16000, frame_duration_ms=30, speech_threshold=0.015, min_zcr=0.005)
        # Constant positive DC bias has no sign transitions
        dc_samples = np.full(480, 5000, dtype=np.int16).tobytes()
        assert vad.is_speech(dc_samples) is False

    def test_vad_utterance_completion_after_600ms_silence(self) -> None:
        """VAD completes utterance after speech is followed by 600ms continuous silence."""
        vad = VADDetector(
            sample_rate=16000,
            frame_duration_ms=30,
            speech_threshold=0.015,
            silence_timeout_ms=600.0,
        )

        silence_frame = _generate_frame(duration_ms=30, amplitude=0.0)
        speech_frame = _generate_frame(duration_ms=30, amplitude=6000.0, freq=400.0)

        # 1. Silence before speech does not start or complete utterance
        for _ in range(5):
            is_speech, is_complete = vad.process_frame(silence_frame)
            assert is_speech is False
            assert is_complete is False
            assert vad.has_speech_started is False

        # 2. Speech begins
        for _ in range(3):  # 90ms speech
            is_speech, is_complete = vad.process_frame(speech_frame)
            assert is_speech is True
            assert is_complete is False
            assert vad.has_speech_started is True

        # 3. Silence post-speech for 19 frames (570ms) - should NOT complete yet
        for i in range(19):
            is_speech, is_complete = vad.process_frame(silence_frame)
            assert is_speech is False
            assert is_complete is False
            assert vad.silence_accumulated_ms == pytest.approx((i + 1) * 30.0)

        # 4. 20th silence frame reaches exactly 600ms -> utterance complete!
        is_speech, is_complete = vad.process_frame(silence_frame)
        assert is_speech is False
        assert is_complete is True
        assert vad.is_utterance_complete is True

    def test_vad_speech_resets_silence_countdown(self) -> None:
        """New speech frame during silence resets the 600ms countdown timer."""
        vad = VADDetector(
            sample_rate=16000,
            frame_duration_ms=30,
            silence_timeout_ms=600.0,
        )
        silence_frame = _generate_frame(duration_ms=30, amplitude=0.0)
        speech_frame = _generate_frame(duration_ms=30, amplitude=6000.0, freq=400.0)

        # Start speech
        vad.process_frame(speech_frame)
        assert vad.has_speech_started is True

        # 10 frames silence (300ms)
        for _ in range(10):
            vad.process_frame(silence_frame)
        assert vad.silence_accumulated_ms == pytest.approx(300.0)
        assert vad.is_utterance_complete is False

        # Another speech frame arrives -> resets silence counter
        is_speech, is_complete = vad.process_frame(speech_frame)
        assert is_speech is True
        assert vad.silence_accumulated_ms == 0.0

        # Another 10 frames silence (300ms) -> still not complete
        for _ in range(10):
            vad.process_frame(silence_frame)
        assert vad.is_utterance_complete is False

        # Final 10 frames silence (reaches 600ms from 2nd speech) -> complete!
        for _ in range(9):
            vad.process_frame(silence_frame)
        assert vad.is_utterance_complete is False

        _, is_complete = vad.process_frame(silence_frame)
        assert is_complete is True

    def test_vad_reset(self) -> None:
        """vad.reset() restores state machine to initial empty state."""
        vad = VADDetector()
        speech = _generate_frame(amplitude=6000.0)
        vad.process_frame(speech)
        assert vad.has_speech_started is True

        vad.reset()
        assert vad.has_speech_started is False
        assert vad.is_utterance_complete is False
        assert vad.silence_accumulated_ms == 0.0


class TestPushToTalk:
    """Tests for manual and IPC-driven Push-to-Talk audio recording."""

    def test_ptt_manual_start_stop(self, publisher: StatePublisher) -> None:
        """Manual start_recording() and stop_recording() toggle recording and update state."""
        listener = AudioListener(state_publisher=publisher)
        assert listener.is_recording is False
        assert publisher.get_current_state().state == DaemonState.IDLE

        # Start recording
        listener.start_recording()
        assert listener.is_recording is True
        assert publisher.get_current_state().state == DaemonState.LISTENING

        # Feed some test audio data
        test_chunk = _generate_frame(amplitude=4000.0)
        listener.feed_audio(test_chunk)

        # Stop recording
        recorded_data = listener.stop_recording()
        assert listener.is_recording is False
        assert publisher.get_current_state().state == DaemonState.IDLE
        assert test_chunk in recorded_data

    def test_ptt_toggle_method(self, publisher: StatePublisher) -> None:
        """toggle_ptt() toggles recording state between active and inactive."""
        listener = AudioListener(state_publisher=publisher)

        # 1st toggle: starts recording
        active = listener.toggle_ptt()
        assert active is True
        assert listener.is_recording is True
        assert publisher.get_current_state().state == DaemonState.LISTENING

        # 2nd toggle: stops recording
        active = listener.toggle_ptt()
        assert active is False
        assert listener.is_recording is False
        assert publisher.get_current_state().state == DaemonState.IDLE

    @pytest.mark.asyncio
    async def test_ptt_ipc_operations(self, publisher: StatePublisher) -> None:
        """handle_ipc_command handles 'voice_ptt_toggle' and returns daemon-compliant response."""
        listener = AudioListener(state_publisher=publisher)

        # Toggle on via IPC
        res1 = await listener.handle_ipc_command("voice_ptt_toggle")
        assert res1["status"] == "ok"
        assert res1["ptt"] == "active"
        assert res1["state"] == DaemonState.LISTENING.value
        assert listener.is_recording is True

        # Toggle off via IPC
        res2 = await listener.handle_ipc_command("voice_ptt_toggle")
        assert res2["status"] == "ok"
        assert res2["ptt"] == "inactive"
        assert res2["state"] == DaemonState.IDLE.value
        assert listener.is_recording is False


class TestBargeIn:
    """Tests for Barge-in interrupt when daemon is in SPEAKING state."""

    def test_barge_in_fires_immediately_when_speaking(self, publisher: StatePublisher) -> None:
        """When state is SPEAKING and speech is detected, BargeInDetected fires."""
        barge_events: list[BargeInEvent] = []

        def on_barge_in(event: BargeInEvent) -> None:
            barge_events.append(event)

        listener = AudioListener(
            state_publisher=publisher,
            barge_in_callback=on_barge_in,
        )

        # Daemon is currently speaking
        publisher.update(state=DaemonState.SPEAKING)

        silence_frame = _generate_frame(amplitude=0.0)
        speech_frame = _generate_frame(amplitude=6000.0)

        # Silence should NOT trigger barge-in
        listener.process_frame(silence_frame)
        assert len(barge_events) == 0

        # Speech MUST trigger barge-in
        listener.process_frame(speech_frame)
        assert len(barge_events) == 1
        assert isinstance(barge_events[0], BargeInDetected)
        assert barge_events[0].interrupted_state == DaemonState.SPEAKING

    def test_barge_in_latency_under_50ms(self, publisher: StatePublisher) -> None:
        """Barge-in detection and callback invocation must execute in < 50ms."""
        recorded_time: float = 0.0

        def on_barge_in(event: BargeInEvent) -> None:
            nonlocal recorded_time
            recorded_time = time.perf_counter()

        listener = AudioListener(
            state_publisher=publisher,
            barge_in_callback=on_barge_in,
        )
        publisher.update(state=DaemonState.SPEAKING)
        speech_frame = _generate_frame(amplitude=6000.0)

        start_time = time.perf_counter()
        listener.process_frame(speech_frame)

        assert recorded_time > 0.0
        elapsed = recorded_time - start_time
        assert elapsed < 0.050, f"Barge-in took {elapsed * 1000:.2f}ms, expected < 50ms"

    def test_barge_in_does_not_fire_when_idle_or_listening(self, publisher: StatePublisher) -> None:
        """Barge-in should NOT trigger if state is IDLE or LISTENING."""
        barge_events: list[BargeInEvent] = []

        listener = AudioListener(
            state_publisher=publisher,
            barge_in_callback=lambda ev: barge_events.append(ev),
        )

        speech_frame = _generate_frame(amplitude=6000.0)

        # State IDLE: speech should not barge-in
        publisher.update(state=DaemonState.IDLE)
        listener.process_frame(speech_frame)
        assert len(barge_events) == 0

        # State LISTENING: speech is expected, should not barge-in
        publisher.update(state=DaemonState.LISTENING)
        listener.process_frame(speech_frame)
        assert len(barge_events) == 0


class TestStateTransitionsAndPhrase:
    """Tests for phrase capture and state transitions."""

    @pytest.mark.asyncio
    async def test_record_phrase_state_transitions(self, publisher: StatePublisher) -> None:
        """record_phrase sets state to LISTENING during recording and resets to IDLE after."""
        listener = AudioListener(state_publisher=publisher)
        assert publisher.get_current_state().state == DaemonState.IDLE

        phrase_future = listener.record_phrase(timeout=5.0)
        # Should now be LISTENING
        assert publisher.get_current_state().state == DaemonState.LISTENING

        speech_frame = _generate_frame(duration_ms=30, amplitude=6000.0)
        silence_frame = _generate_frame(duration_ms=30, amplitude=0.0)

        # Feed 3 speech frames
        for _ in range(3):
            listener.feed_audio(speech_frame)
            await asyncio.sleep(0.001)

        # Feed 20 silence frames (600ms silence to complete phrase)
        for _ in range(20):
            listener.feed_audio(silence_frame)
            await asyncio.sleep(0.001)

        result_pcm = await asyncio.wait_for(phrase_future, timeout=2.0)
        assert len(result_pcm) > 0
        assert publisher.get_current_state().state == DaemonState.IDLE

    def test_audio_conversions_ready_for_whisper(self, publisher: StatePublisher) -> None:
        """Verify PCM to WAV and NumPy float32 format conversions for Whisper STT."""
        listener = AudioListener(state_publisher=publisher)
        pcm_data = _generate_frame(duration_ms=60, amplitude=5000.0)

        # Convert to WAV
        wav_bytes = listener.to_wav_bytes(pcm_data)
        assert wav_bytes.startswith(b"RIFF")
        assert b"WAVEfmt " in wav_bytes

        # Convert to numpy float32
        arr = listener.to_numpy(pcm_data)
        assert arr.dtype == np.float32
        assert np.max(np.abs(arr)) <= 1.0


class TestHeadlessFallback:
    """Tests for safe headless operation when sound hardware is missing or mocked."""

    def test_headless_fallback_when_sounddevice_fails(self, publisher: StatePublisher) -> None:
        """Listener should initialize safely in headless mode if InputStream fails."""
        with patch("sounddevice.InputStream", side_effect=OSError("No default input device")):
            listener = AudioListener(state_publisher=publisher)
            # Does not crash, marks hardware unavailable
            assert listener.is_available is False

            # Feed audio and manual recording still work safely in memory
            listener.start_recording()
            assert listener.is_recording is True
            assert publisher.get_current_state().state == DaemonState.LISTENING

            chunk = _generate_frame(duration_ms=30, amplitude=4000.0)
            listener.feed_audio(chunk)
            data = listener.stop_recording()
            assert chunk in data
            assert publisher.get_current_state().state == DaemonState.IDLE

    def test_mocked_sounddevice_input_stream(self, publisher: StatePublisher) -> None:
        """Listener starts and stops mocked sounddevice InputStream cleanly."""
        mock_stream = MagicMock()
        with patch("sounddevice.InputStream", return_value=mock_stream):
            listener = AudioListener(state_publisher=publisher)
            assert listener.is_available is True

            listener.start_recording()
            mock_stream.start.assert_called_once()

            listener.stop_recording()
            mock_stream.stop.assert_called_once()
