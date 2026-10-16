"""Unit tests for EdgeTTSBackend, FallbackTTSBackend, and VoiceSpeaker auto-selection."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from jules.voice.speaker import (
    BaseTTSBackend,
    EdgeTTSBackend,
    ElevenLabsTTSBackend,
    FallbackTTSBackend,
    KokoroTTSBackend,
    MockTTSBackend,
    TTSModelError,
    VoiceSpeaker,
    _find_kokoro_model_files,
    load_configured_tts_backend,
)


# ---------------------------------------------------------------------------
# (a) Tests for EdgeTTSBackend
# ---------------------------------------------------------------------------


class TestEdgeTTSBackend:
    """Tests for EdgeTTSBackend synthesis, availability, and error handling."""

    def test_default_parameters(self) -> None:
        backend = EdgeTTSBackend()
        assert backend.voice == "es-CO-SalomeNeural"
        assert backend.rate == "+0%"
        assert backend.sample_rate == 24000

    def test_is_available_true(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            assert EdgeTTSBackend.is_available() is True

    def test_is_available_false_when_ffmpeg_missing(self) -> None:
        with patch("shutil.which", return_value=None):
            assert EdgeTTSBackend.is_available() is False

    def test_is_available_false_when_edge_tts_missing(self) -> None:
        with patch.dict("sys.modules", {"edge_tts": None}):
            assert EdgeTTSBackend.is_available() is False

    def test_synthesize_empty_or_markdown_empty(self) -> None:
        backend = EdgeTTSBackend()
        samples, sr = backend.synthesize("")
        assert len(samples) == 0
        assert sr == 24000

        samples, sr = backend.synthesize("```python\nx = 1\n```")
        assert len(samples) == 0
        assert sr == 24000

    def test_synthesize_success_sync(self) -> None:
        backend = EdgeTTSBackend()

        # Mock audio chunks from edge_tts
        mock_comm = MagicMock()

        async def fake_stream():
            yield {"type": "audio", "data": b"\xff\xfb\x90\x00"}

        mock_comm.stream = fake_stream

        # Mock ffmpeg returning 16-bit PCM bytes
        raw_pcm = (np.array([0, 16384, -16384, 0], dtype=np.int16)).tobytes()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = raw_pcm

        with patch("edge_tts.Communicate", return_value=mock_comm), patch(
            "subprocess.run", return_value=mock_proc
        ) as mock_sub:
            samples, sr = backend.synthesize("Hola Jules")
            assert sr == 24000
            assert isinstance(samples, np.ndarray)
            assert samples.dtype == np.float32
            assert len(samples) == 4
            np.testing.assert_allclose(samples, [0.0, 0.5, -0.5, 0.0], atol=1e-4)

            mock_sub.assert_called_once()
            cmd_args = mock_sub.call_args[0][0]
            assert cmd_args[0] == "ffmpeg"
            assert str(backend.sample_rate) in cmd_args

    @pytest.mark.asyncio
    async def test_synthesize_inside_running_event_loop(self) -> None:
        """EdgeTTSBackend.synthesize works seamlessly when called inside a running asyncio loop."""
        backend = EdgeTTSBackend()

        mock_comm = MagicMock()

        async def fake_stream():
            yield {"type": "audio", "data": b"mock_mp3_data"}

        mock_comm.stream = fake_stream

        raw_pcm = (np.zeros(10, dtype=np.int16)).tobytes()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = raw_pcm

        with patch("edge_tts.Communicate", return_value=mock_comm), patch(
            "subprocess.run", return_value=mock_proc
        ):
            samples, sr = backend.synthesize("Prueba asíncrona")
            assert sr == 24000
            assert len(samples) == 10

    def test_synthesize_edge_tts_failure_raises_tts_model_error(self) -> None:
        backend = EdgeTTSBackend()

        mock_comm = MagicMock()

        async def fake_failing_stream():
            raise ConnectionError("Network unreachable")
            yield  # pragma: no cover

        mock_comm.stream = fake_failing_stream

        with patch("edge_tts.Communicate", return_value=mock_comm):
            with pytest.raises(TTSModelError, match="EdgeTTS synthesis failed"):
                backend.synthesize("Hola mundo")

    def test_synthesize_ffmpeg_nonzero_exit_raises_tts_model_error(self) -> None:
        backend = EdgeTTSBackend()

        mock_comm = MagicMock()

        async def fake_stream():
            yield {"type": "audio", "data": b"bad_mp3"}

        mock_comm.stream = fake_stream

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = b"Invalid MP3 bitstream"

        with patch("edge_tts.Communicate", return_value=mock_comm), patch(
            "subprocess.run", return_value=mock_proc
        ):
            with pytest.raises(TTSModelError, match="ffmpeg decode error"):
                backend.synthesize("Hola mundo")

    def test_synthesize_ffmpeg_not_found_raises_tts_model_error(self) -> None:
        backend = EdgeTTSBackend()

        mock_comm = MagicMock()

        async def fake_stream():
            yield {"type": "audio", "data": b"data"}

        mock_comm.stream = fake_stream

        with patch("edge_tts.Communicate", return_value=mock_comm), patch(
            "subprocess.run", side_effect=FileNotFoundError("No ffmpeg")
        ):
            with pytest.raises(TTSModelError, match="ffmpeg not found"):
                backend.synthesize("Hola mundo")

    def test_synthesize_ffmpeg_timeout_raises_tts_model_error(self) -> None:
        backend = EdgeTTSBackend()

        mock_comm = MagicMock()

        async def fake_stream():
            yield {"type": "audio", "data": b"data"}

        mock_comm.stream = fake_stream

        with patch("edge_tts.Communicate", return_value=mock_comm), patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=15),
        ):
            with pytest.raises(TTSModelError, match="ffmpeg decode timed out"):
                backend.synthesize("Hola mundo")


# ---------------------------------------------------------------------------
# (b) Tests for FallbackTTSBackend
# ---------------------------------------------------------------------------


class TestFallbackTTSBackend:
    """Tests for composite FallbackTTSBackend primary/secondary dispatch."""

    def test_primary_success_bypasses_fallback(self) -> None:
        primary = MockTTSBackend(audio_duration=0.01)
        fallback = MockTTSBackend(audio_duration=0.01)

        composite = FallbackTTSBackend(primary=primary, fallback=fallback)
        samples, sr = composite.synthesize("Synthesize this")

        assert len(primary.history) == 1
        assert primary.history[0] == "Synthesize this"
        assert len(fallback.history) == 0
        assert sr == 24000

    def test_primary_failure_triggers_fallback_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        failing_primary = MagicMock(spec=BaseTTSBackend)
        failing_primary.synthesize.side_effect = TTSModelError("Edge TTS connection timeout")
        failing_primary.sample_rate = 24000

        fallback = MockTTSBackend(audio_duration=0.02)
        composite = FallbackTTSBackend(primary=failing_primary, fallback=fallback)

        with caplog.at_level("WARNING"):
            samples, sr = composite.synthesize("Emergency fallback phrase")

        assert len(fallback.history) == 1
        assert fallback.history[0] == "Emergency fallback phrase"
        assert sr == 24000
        assert "Primary TTS backend" in caplog.text
        assert "Falling back to MockTTSBackend" in caplog.text

    def test_both_primary_and_fallback_fail_raises_tts_model_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        failing_primary = MagicMock(spec=BaseTTSBackend)
        failing_primary.synthesize.side_effect = TTSModelError("Network down")
        failing_primary.sample_rate = 24000

        failing_fallback = MagicMock(spec=BaseTTSBackend)
        failing_fallback.synthesize.side_effect = RuntimeError("ONNX model corrupted")
        failing_fallback.sample_rate = 24000

        composite = FallbackTTSBackend(primary=failing_primary, fallback=failing_fallback)

        with caplog.at_level("ERROR"):
            with pytest.raises(TTSModelError, match="Both primary .* and fallback .* failed"):
                composite.synthesize("Fatal failure phrase")

        assert "Fallback TTS backend" in caplog.text

    def test_fallback_backend_sample_rate_resolution(self) -> None:
        p = MockTTSBackend(sample_rate=16000)
        f = MockTTSBackend(sample_rate=24000)
        composite = FallbackTTSBackend(primary=p, fallback=f)
        assert composite.sample_rate == 16000

        composite_custom = FallbackTTSBackend(primary=p, fallback=f, sample_rate=48000)
        assert composite_custom.sample_rate == 48000


# ---------------------------------------------------------------------------
# (c) Tests for VoiceSpeaker Priority Resolution
# ---------------------------------------------------------------------------


class TestVoiceSpeakerPriorityResolution:
    """Tests for VoiceSpeaker backend auto-selection priority hierarchy."""

    def test_priority_1_edge_tts_available_with_kokoro_model(self, tmp_path: Path) -> None:
        fake_model = tmp_path / "kokoro-v0_19.onnx"
        fake_voices = tmp_path / "voices.bin"
        fake_model.touch()
        fake_voices.touch()

        with patch("jules.voice.speaker.load_configured_tts_backend", return_value=None), patch(
            "jules.voice.speaker.EdgeTTSBackend.is_available", return_value=True
        ), patch(
            "jules.voice.speaker._find_kokoro_model_files",
            return_value=(fake_model, fake_voices),
        ):
            speaker = VoiceSpeaker(stream_factory=lambda **_: MagicMock())
            assert isinstance(speaker.backend, FallbackTTSBackend)
            assert isinstance(speaker.backend.primary, EdgeTTSBackend)
            assert isinstance(speaker.backend.fallback, KokoroTTSBackend)
            speaker.close()

    def test_priority_1_edge_tts_available_without_kokoro_model(self) -> None:
        with patch("jules.voice.speaker.load_configured_tts_backend", return_value=None), patch(
            "jules.voice.speaker.EdgeTTSBackend.is_available", return_value=True
        ), patch(
            "jules.voice.speaker._find_kokoro_model_files", return_value=None
        ):
            speaker = VoiceSpeaker(stream_factory=lambda **_: MagicMock())
            assert isinstance(speaker.backend, FallbackTTSBackend)
            assert isinstance(speaker.backend.primary, EdgeTTSBackend)
            assert isinstance(speaker.backend.fallback, MockTTSBackend)
            speaker.close()

    def test_priority_2_kokoro_when_edge_unavailable(self, tmp_path: Path) -> None:
        fake_model = tmp_path / "kokoro-v0_19.onnx"
        fake_voices = tmp_path / "voices.bin"
        fake_model.touch()
        fake_voices.touch()

        with patch("jules.voice.speaker.load_configured_tts_backend", return_value=None), patch(
            "jules.voice.speaker.EdgeTTSBackend.is_available", return_value=False
        ), patch(
            "jules.voice.speaker._find_kokoro_model_files",
            return_value=(fake_model, fake_voices),
        ):
            speaker = VoiceSpeaker(stream_factory=lambda **_: MagicMock())
            assert isinstance(speaker.backend, KokoroTTSBackend)
            speaker.close()

    def test_priority_3_mock_when_edge_and_kokoro_unavailable(self) -> None:
        with patch("jules.voice.speaker.load_configured_tts_backend", return_value=None), patch(
            "jules.voice.speaker.EdgeTTSBackend.is_available", return_value=False
        ), patch(
            "jules.voice.speaker._find_kokoro_model_files", return_value=None
        ):
            speaker = VoiceSpeaker(stream_factory=lambda **_: MagicMock())
            assert isinstance(speaker.backend, MockTTSBackend)
            speaker.close()

    def test_explicit_elevenlabs_configured_with_api_key(self) -> None:
        with patch(
            "jules.voice.speaker.load_configured_tts_backend", return_value="elevenlabs"
        ), patch(
            "jules.voice.speaker.ElevenLabsTTSBackend.load_api_key",
            return_value="sk_test_valid_key",
        ):
            speaker = VoiceSpeaker(stream_factory=lambda **_: MagicMock())
            assert isinstance(speaker.backend, ElevenLabsTTSBackend)
            assert speaker.backend.api_key == "sk_test_valid_key"
            speaker.close()

    def test_explicit_elevenlabs_configured_without_api_key_falls_back_to_mock(self) -> None:
        with patch(
            "jules.voice.speaker.load_configured_tts_backend", return_value="elevenlabs"
        ), patch(
            "jules.voice.speaker.ElevenLabsTTSBackend.load_api_key", return_value=None
        ):
            speaker = VoiceSpeaker(stream_factory=lambda **_: MagicMock())
            assert isinstance(speaker.backend, MockTTSBackend)
            speaker.close()

    def test_custom_backend_passed_directly(self) -> None:
        custom_backend = MockTTSBackend()
        speaker = VoiceSpeaker(
            backend=custom_backend,
            stream_factory=lambda **_: MagicMock(),
        )
        assert speaker.backend is custom_backend
        speaker.close()

    def test_load_configured_tts_backend_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("JULES_TTS_BACKEND", "kokoro")
        assert load_configured_tts_backend() == "kokoro"

    def test_load_configured_tts_backend_from_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("JULES_TTS_BACKEND", raising=False)
        fake_home = tmp_path / "home"
        jules_dir = fake_home / ".jules"
        jules_dir.mkdir(parents=True)
        env_file = jules_dir / ".env"
        env_file.write_text('JULES_TTS_BACKEND="elevenlabs"\n')

        with patch("pathlib.Path.home", return_value=fake_home):
            assert load_configured_tts_backend() == "elevenlabs"
