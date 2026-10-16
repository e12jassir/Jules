"""Unit tests for EdgeTTSBackend, FallbackTTSBackend, and VoiceSpeaker auto-selection."""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from jules.daemon.state import DaemonState, StatePublisher
from jules.voice.speaker import (
    BaseTTSBackend,
    EdgeTTSBackend,
    ElevenLabsTTSBackend,
    FallbackTTSBackend,
    KokoroTTSBackend,
    MockTTSBackend,
    SentenceStreamChunker,
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


# ---------------------------------------------------------------------------
# (d) Tests for Low-Latency Pipelined Synthesis, Playback & Barge-in
# ---------------------------------------------------------------------------


class TestSentenceStreamChunkerFirstSentence:
    """Tests verifying min_first_chars accelerates initial sentence emission."""

    def test_min_first_chars_cuts_first_sentence_earlier(self) -> None:
        """First sentence cuts at >= min_first_chars, while subsequent sentences require min_chars."""
        chunker = SentenceStreamChunker(min_chars=40, min_first_chars=20)

        # 14 chars with period: not emitted because < min_first_chars (20)
        out1 = chunker.add_chunk("Hola Esteban. ")
        assert out1 == []

        # Additional 14 chars: total 28 chars >= min_first_chars (20) with delimiter
        out2 = chunker.add_chunk("¿Cómo estás? ")
        assert out2 == ["Hola Esteban. ¿Cómo estás?"]

        # Second sentence is now subject to min_chars (40)
        out3 = chunker.add_chunk("Muy bien! ")  # 10 chars < 40 -> not emitted
        assert out3 == []

        out4 = chunker.add_chunk("Aquí tienes el resumen completo del estado del sistema.")
        assert len(out4) == 1
        assert out4[0] == "Muy bien! Aquí tienes el resumen completo del estado del sistema."

    def test_chunker_reset_restores_first_sentence_threshold(self) -> None:
        """reset() restores _is_first_sentence to True for next turn."""
        chunker = SentenceStreamChunker(min_chars=50, min_first_chars=20)
        chunker.add_chunk("Primera oración de prueba completada.")
        chunker.reset()

        assert chunker._is_first_sentence is True
        emitted = chunker.add_chunk("Nueva oración rápida! ")
        assert emitted == ["Nueva oración rápida!"]


class TestVoiceSpeakerPipelining:
    """Tests verifying decoupled synthesis and playback pipelining."""

    @pytest.mark.asyncio
    async def test_pipelined_multi_sentence_stream_processes_smoothly(self) -> None:
        """Pipelined synthesis and playback processes multi-sentence stream to completion."""
        mock_stream = MagicMock()
        mock_stream.active = True
        backend = MockTTSBackend(audio_duration=0.02, simulate_delay=0.01)

        speaker = VoiceSpeaker(
            backend=backend,
            stream_factory=lambda **_: mock_stream,
        )

        sentences = [
            "Primera oración sintetizada y lista.",
            "Segunda oración mientras la primera suena.",
            "Tercera oración cerrando el flujo con cero latencia.",
        ]

        await speaker.speak_stream(sentences)

        assert backend.history == sentences
        assert speaker.queue_size == 0
        assert not speaker.is_speaking
        assert mock_stream.write.call_count >= len(sentences)

        speaker.close()

    @pytest.mark.asyncio
    async def test_pipelining_concurrency_synthesis_ahead_of_playback(self) -> None:
        """Synthesis of subsequent sentences happens concurrently while playback is active."""
        mock_stream = MagicMock()
        mock_stream.active = True

        playback_started = asyncio.Event()
        synthesis_completed_for_second = asyncio.Event()

        class ConcurrencyTrackingBackend(BaseTTSBackend):
            def __init__(self) -> None:
                super().__init__(sample_rate=24000)
                self.count = 0

            def synthesize(self, text: str) -> tuple[np.ndarray, int]:
                self.count += 1
                if self.count == 2:
                    synthesis_completed_for_second.set()
                samples = np.zeros(2400, dtype=np.float32)
                return samples, 24000

        backend = ConcurrencyTrackingBackend()
        speaker = VoiceSpeaker(
            backend=backend,
            stream_factory=lambda **_: mock_stream,
        )

        def slow_write(chunk: np.ndarray) -> None:
            playback_started.set()
            time.sleep(0.04)

        mock_stream.write = slow_write

        sentences = ["Primera oración en reproducción.", "Segunda oración pipelined."]
        speak_task = asyncio.create_task(speaker.speak_stream(sentences))

        await asyncio.wait_for(playback_started.wait(), timeout=1.0)
        # Sentence 2 must synthesize even while sentence 1 write is ongoing
        await asyncio.wait_for(synthesis_completed_for_second.wait(), timeout=1.0)

        await speak_task
        assert backend.count == 2
        speaker.close()


class TestVoiceSpeakerPipelinedBargeIn:
    """Tests verifying sub-50ms barge-in interruption across decoupled queues."""

    @pytest.mark.asyncio
    async def test_instant_barge_in_drains_both_queues_under_50ms(
        self, tmp_path: Path
    ) -> None:
        """Interruption immediately clears both sentence and audio queues and stops stream in <50ms."""
        mock_stream = MagicMock()
        mock_stream.active = True

        state_file = tmp_path / "jules_pipelined_bargein.state"
        publisher = StatePublisher(target_path=state_file, initial_state=DaemonState.IDLE)

        backend = MockTTSBackend(audio_duration=0.5, simulate_delay=0.05)
        speaker = VoiceSpeaker(
            backend=backend,
            state_publisher=publisher,
            stream_factory=lambda **_: mock_stream,
        )

        sentences = [f"Oración en cola con índice {i} para barge-in." for i in range(10)]
        speak_task = asyncio.create_task(speaker.speak_stream(sentences))

        # Allow synthesis/playback to start
        await asyncio.sleep(0.03)
        assert speaker.is_speaking
        assert publisher.get_current_state().state == DaemonState.SPEAKING

        # Instant barge-in stop
        t_start = time.perf_counter()
        speaker.stop()
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        assert elapsed_ms < 50.0, f"stop() took {elapsed_ms:.2f}ms, expected < 50ms"
        assert speaker._sentence_queue.empty()
        assert speaker._audio_queue.empty()
        assert speaker.queue_size == 0
        assert not speaker.is_speaking
        assert publisher.get_current_state().state == DaemonState.IDLE
        assert mock_stream.abort.called or mock_stream.stop.called

        await asyncio.wait_for(speak_task, timeout=0.3)
        speaker.close()

