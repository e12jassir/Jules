"""Unit tests for LocalTranscriber with faster-whisper INT8 and Sanitizer integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import io
from pathlib import Path
import time
from typing import Any
from unittest.mock import MagicMock, patch
import wave

import numpy as np
import pytest

from jules.voice.transcriber import (
    AudioFormatError,
    LocalTranscriber,
    ModelLoadError,
    TranscriberError,
    TranscriptionResult,
)


@dataclass
class DummySegment:
    """Mock segment matching faster-whisper Segment interface."""
    text: str
    start: float = 0.0
    end: float = 2.0


@dataclass
class DummyTranscriptionInfo:
    """Mock info matching faster-whisper TranscriptionInfo interface."""
    language: str = "es"
    language_probability: float = 0.98
    duration: float = 3.0


def _create_dummy_wav(duration_s: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Create in-memory RIFF WAV bytes with a sine wave."""
    num_samples = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    samples = (np.sin(2 * np.pi * 440.0 * t) * 10000).astype(np.int16)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return bio.getvalue()


def _create_dummy_pcm(duration_s: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Create raw 16-bit PCM bytes (no WAV header)."""
    num_samples = int(duration_s * sample_rate)
    samples = np.full(num_samples, 2000, dtype=np.int16)
    return samples.tobytes()


@pytest.fixture
def mock_whisper_model():
    """Mock faster-whisper WhisperModel to prevent model downloads or GPU execution in CI."""
    with patch("faster_whisper.WhisperModel") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance

        def set_transcribe_result(text: str = "Hola mundo", language: str = "es", duration: float = 2.5):
            def transcribe_impl(*args, **kwargs):
                return iter([DummySegment(text=text)]), DummyTranscriptionInfo(language=language, duration=duration)
            instance.transcribe.side_effect = transcribe_impl

        set_transcribe_result("Hola mundo")
        instance.set_transcribe_result = set_transcribe_result

        yield mock_cls, instance


class TestLocalTranscriberInitialization:
    """Tests for initialization, default configurations, and preloading behaviors."""

    def test_eager_model_preloading_by_default(self, mock_whisper_model) -> None:
        """LocalTranscriber should pre-load faster-whisper model eagerly on init by default."""
        mock_cls, mock_instance = mock_whisper_model

        transcriber = LocalTranscriber(
            model_size="base",
            device="cpu",
            compute_type="int8",
            beam_size=1,
            vad_filter=True,
        )

        assert transcriber.is_loaded is True
        mock_cls.assert_called_once_with(
            "base",
            device="cpu",
            compute_type="int8",
        )
        assert transcriber.beam_size == 1
        assert transcriber.vad_filter is True
        assert transcriber.compute_type == "int8"
        assert transcriber.model_size == "base"
        assert transcriber.device == "cpu"

    def test_lazy_loading_option(self, mock_whisper_model) -> None:
        """When lazy_load=True, model is not loaded until explicitly requested or transcribed."""
        mock_cls, _ = mock_whisper_model

        transcriber = LocalTranscriber(lazy_load=True)
        assert transcriber.is_loaded is False
        mock_cls.assert_not_called()

        # Explicit load
        transcriber.load_model()
        assert transcriber.is_loaded is True
        mock_cls.assert_called_once()

    def test_unload_model(self, mock_whisper_model) -> None:
        """unload_model releases model from memory."""
        _, _ = mock_whisper_model
        transcriber = LocalTranscriber()
        assert transcriber.is_loaded is True

        transcriber.unload_model()
        assert transcriber.is_loaded is False

        # Multiple unloads should be safe
        transcriber.unload_model()
        assert transcriber.is_loaded is False

    def test_load_model_failure_raises_model_load_error(self) -> None:
        """Model loading errors should raise ModelLoadError without crashing."""
        with patch("faster_whisper.WhisperModel", side_effect=RuntimeError("Out of memory")):
            with pytest.raises(ModelLoadError, match="Failed to load speech transcription model"):
                LocalTranscriber(lazy_load=False)


class TestLocalTranscriberAudioFormats:
    """Tests for transcribing various audio formats (WAV bytes, raw PCM, numpy array, BytesIO, Path)."""

    @pytest.mark.asyncio
    async def test_transcribe_wav_bytes(self, mock_whisper_model) -> None:
        """Transcribing RIFF WAV bytes should produce TranscriptionResult."""
        _, mock_instance = mock_whisper_model
        mock_instance.set_transcribe_result("muéstrame el estado de la batería", duration=3.0)

        transcriber = LocalTranscriber()
        wav_data = _create_dummy_wav(duration_s=3.0)

        result = await transcriber.transcribe(wav_data)

        assert isinstance(result, TranscriptionResult)
        assert result.text == "muéstrame el estado de la batería"
        assert result.sanitized_text == "muéstrame el estado de la batería"
        assert result.is_safe is True
        assert result.reason is None
        assert result.language == "es"
        assert result.duration == 3.0
        assert result.latency_ms >= 0.0

        # Verify transcribe was called with beam_size=1 and vad_filter=True
        mock_instance.transcribe.assert_called_once()
        _, kwargs = mock_instance.transcribe.call_args
        assert kwargs.get("beam_size") == 1
        assert kwargs.get("vad_filter") is True

    @pytest.mark.asyncio
    async def test_transcribe_raw_pcm_bytes(self, mock_whisper_model) -> None:
        """Transcribing raw 16-bit PCM bytes (from AudioListener) should work properly."""
        _, mock_instance = mock_whisper_model
        mock_instance.set_transcribe_result("abrir terminal", duration=1.0)

        transcriber = LocalTranscriber()
        raw_pcm = _create_dummy_pcm(duration_s=1.0)

        result = await transcriber.transcribe(raw_pcm)

        assert result.text == "abrir terminal"
        assert result.is_safe is True

        # Ensure the audio passed to model.transcribe is a normalized float32 numpy array
        args, _ = mock_instance.transcribe.call_args
        audio_arg = args[0]
        assert isinstance(audio_arg, np.ndarray)
        assert audio_arg.dtype == np.float32

    @pytest.mark.asyncio
    async def test_transcribe_numpy_array(self, mock_whisper_model) -> None:
        """Transcribing float32 NumPy array should pass directly to whisper."""
        _, mock_instance = mock_whisper_model
        mock_instance.set_transcribe_result("probando audio", duration=1.5)

        transcriber = LocalTranscriber()
        arr = np.linspace(-0.5, 0.5, 24000, dtype=np.float32)

        result = await transcriber.transcribe(arr)

        assert result.text == "probando audio"
        assert result.is_safe is True

    @pytest.mark.asyncio
    async def test_transcribe_bytes_io_and_file_path(self, mock_whisper_model, tmp_path: Path) -> None:
        """Transcribing io.BytesIO and Path / str file paths."""
        _, mock_instance = mock_whisper_model
        mock_instance.set_transcribe_result("audio desde archivo", duration=1.0)

        transcriber = LocalTranscriber()
        wav_data = _create_dummy_wav(duration_s=1.0)

        # 1. io.BytesIO
        bio = io.BytesIO(wav_data)
        res_bio = await transcriber.transcribe(bio)
        assert res_bio.text == "audio desde archivo"

        # 2. File Path
        file_path = tmp_path / "test.wav"
        file_path.write_bytes(wav_data)

        res_path = await transcriber.transcribe(file_path)
        assert res_path.text == "audio desde archivo"

        # 3. String path
        res_str = await transcriber.transcribe(str(file_path))
        assert res_str.text == "audio desde archivo"


class TestSanitizerIntegration:
    """Tests verifying Sanitizer security check on transcription results."""

    @pytest.mark.asyncio
    async def test_clean_speech_is_safe(self, mock_whisper_model) -> None:
        """Clean speech should return is_safe=True and unaltered sanitized_text."""
        _, mock_instance = mock_whisper_model
        clean_text = "muéstrame el estado de la batería y la carga de CPU"
        mock_instance.set_transcribe_result(clean_text, duration=2.0)

        transcriber = LocalTranscriber()
        result = await transcriber.transcribe(_create_dummy_wav())

        assert result.text == clean_text
        assert result.sanitized_text == clean_text
        assert result.is_safe is True
        assert result.reason is None

    @pytest.mark.asyncio
    async def test_sensitive_speech_export_secret_is_blocked(self, mock_whisper_model) -> None:
        """Speech containing export API_KEY is rejected by Sanitizer."""
        _, mock_instance = mock_whisper_model
        sensitive_text = "export API_KEY=sk-abcdef1234567890123456"
        mock_instance.set_transcribe_result(sensitive_text, language="en", duration=2.0)

        transcriber = LocalTranscriber()
        result = await transcriber.transcribe(_create_dummy_wav())

        assert result.text == sensitive_text
        assert result.is_safe is False
        assert result.reason == "export_secret"
        assert result.sanitized_text == ""  # Redacted / empty for security

    @pytest.mark.asyncio
    async def test_sensitive_speech_openai_key_is_blocked(self, mock_whisper_model) -> None:
        """Speech containing bare openai key prefix is rejected by Sanitizer."""
        _, mock_instance = mock_whisper_model
        sensitive_text = "mi clave secreta es sk-abcdef1234567890123456"
        mock_instance.set_transcribe_result(sensitive_text, language="es", duration=2.0)

        transcriber = LocalTranscriber()
        result = await transcriber.transcribe(_create_dummy_wav())

        assert result.text == sensitive_text
        assert result.is_safe is False
        assert result.reason == "openai_key"
        assert result.sanitized_text == ""

    @pytest.mark.asyncio
    async def test_sensitive_speech_assignment_secret_is_blocked(self, mock_whisper_model) -> None:
        """Speech containing password=secret is rejected by Sanitizer."""
        _, mock_instance = mock_whisper_model
        sensitive_text = "conectar con password=mySuperSecretPassword123"
        mock_instance.set_transcribe_result(sensitive_text, language="es", duration=2.0)

        transcriber = LocalTranscriber()
        result = await transcriber.transcribe(_create_dummy_wav())

        assert result.is_safe is False
        assert result.reason == "assignment_secret"
        assert result.sanitized_text == ""


class TestNonBlockingAsyncExecution:
    """Tests verifying asyncio event loop remains non-blocked during transcription."""

    @pytest.mark.asyncio
    async def test_transcribe_runs_in_background_thread(self, mock_whisper_model) -> None:
        """Inference should execute via asyncio.to_thread, keeping the loop responsive."""
        _, mock_instance = mock_whisper_model

        # Simulate a 80ms blocking inference in faster-whisper
        def blocking_transcribe(*args, **kwargs):
            time.sleep(0.08)
            return iter([DummySegment(text="operación no bloqueante")]), DummyTranscriptionInfo()

        mock_instance.transcribe.side_effect = blocking_transcribe

        transcriber = LocalTranscriber()

        # Concurrently run a periodic task on the event loop
        ticks = 0

        async def ticker():
            nonlocal ticks
            for _ in range(6):
                await asyncio.sleep(0.01)
                ticks += 1

        # Run both concurrently
        ticker_task = asyncio.create_task(ticker())
        transcribe_task = asyncio.create_task(transcriber.transcribe(_create_dummy_wav()))

        result, _ = await asyncio.gather(transcribe_task, ticker_task)

        assert result.text == "operación no bloqueante"
        # The ticker should have ticked multiple times while transcription was happening
        assert ticks >= 3, f"Event loop was blocked! Ticks: {ticks}"


class TestErrorHandling:
    """Tests handling empty or invalid audio data, or inference failures."""

    @pytest.mark.asyncio
    async def test_empty_audio_raises_audio_format_error(self, mock_whisper_model) -> None:
        """Empty audio bytes or array should raise AudioFormatError without crashing."""
        _, _ = mock_whisper_model
        transcriber = LocalTranscriber()

        with pytest.raises(AudioFormatError, match="Empty audio"):
            await transcriber.transcribe(b"")

        with pytest.raises(AudioFormatError, match="Empty audio"):
            await transcriber.transcribe(np.array([], dtype=np.float32))

        with pytest.raises(AudioFormatError, match="Empty audio"):
            await transcriber.transcribe(io.BytesIO(b""))

    @pytest.mark.asyncio
    async def test_nonexistent_audio_path_raises_audio_format_error(self, mock_whisper_model) -> None:
        """Passing nonexistent file path raises AudioFormatError."""
        _, _ = mock_whisper_model
        transcriber = LocalTranscriber()

        with pytest.raises(AudioFormatError, match="not found"):
            await transcriber.transcribe(Path("/tmp/nonexistent_audio_file_12345.wav"))

    @pytest.mark.asyncio
    async def test_inference_exception_raises_transcriber_error(self, mock_whisper_model) -> None:
        """Inference runtime errors raise TranscriberError without crashing the process."""
        _, mock_instance = mock_whisper_model
        mock_instance.transcribe.side_effect = RuntimeError("Whisper CTranslate2 execution failed")

        transcriber = LocalTranscriber()

        with pytest.raises(TranscriberError, match="Transcription failed"):
            await transcriber.transcribe(_create_dummy_wav())
