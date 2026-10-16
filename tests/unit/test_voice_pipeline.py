"""Unit tests for sentence streaming speech synthesis and barge-in interruption."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jules.daemon.state import DaemonState, StatePublisher
from jules.voice.listener import AudioHardwareUnavailableError, AudioListener, BargeInEvent
from jules.voice.speaker import (
    BaseTTSBackend,
    MockTTSBackend,
    SentenceStreamChunker,
    VoiceSpeaker,
)


@pytest.fixture
def publisher(tmp_path: Path) -> StatePublisher:
    """Fixture providing an isolated StatePublisher."""
    state_file = tmp_path / "jules.state"
    return StatePublisher(target_path=state_file, initial_state=DaemonState.IDLE)


@pytest.fixture
def mock_output_stream():
    """Mock sounddevice.OutputStream and sounddevice.stop by default."""
    mock_stream = MagicMock()
    mock_stream.active = True
    with patch("sounddevice.OutputStream", return_value=mock_stream) as mock_out, patch(
        "sounddevice.stop"
    ) as mock_sd_stop:
        yield mock_stream, mock_sd_stop


# ---------------------------------------------------------------------------
# (a) Tests for SentenceStreamChunker
# ---------------------------------------------------------------------------


class TestSentenceStreamChunker:
    """Tests for SentenceStreamChunker accumulation, splitting and flushing."""

    def test_chunker_accumulates_until_min_chars_and_delimiter(self) -> None:
        """Chunker should not emit until both min_chars threshold is met AND delimiter is found."""
        chunker = SentenceStreamChunker(min_chars=40)

        # 14 chars with period: not emitted yet because len < 40
        out1 = chunker.add_chunk("Short phrase. ")
        assert out1 == []

        # Another 18 chars: total 32 chars < 40 -> still not emitted
        out2 = chunker.add_chunk("Second phrase? ")
        assert out2 == []

        # Final chunk exceeds 40 chars and hits delimiter '.'
        out3 = chunker.add_chunk("Now this final phrase will push it well over forty characters.")
        assert len(out3) == 1
        expected = "Short phrase. Second phrase? Now this final phrase will push it well over forty characters."
        assert out3[0] == expected

    def test_chunker_splits_multiple_sentences_in_single_chunk(self) -> None:
        """A single incoming chunk with multiple >= min_chars sentences splits correctly."""
        chunker = SentenceStreamChunker(min_chars=30)
        s1 = "This is the first sentence which exceeds thirty chars!"
        s2 = "This is the second sentence which also exceeds thirty chars."
        trailing = "Trailing text"

        text = f"{s1} {s2} {trailing}"
        emitted = chunker.add_chunk(text)

        assert emitted == [s1, s2]

        # Trailing text remains in buffer until flushed
        assert chunker.flush() == [trailing]

    def test_chunker_flushes_leftover_trailing_text(self) -> None:
        """Trailing text with no delimiter is emitted when flush() is invoked."""
        chunker = SentenceStreamChunker(min_chars=40)

        out = chunker.add_chunk("Incomplete ending without punctuation")
        assert out == []

        flushed = chunker.flush()
        assert flushed == ["Incomplete ending without punctuation"]

        # Subsequent flush should be empty
        assert chunker.flush() == []

    def test_chunker_custom_min_chars(self) -> None:
        """Configurable min_chars allows smaller or larger sentence chunking."""
        chunker = SentenceStreamChunker(min_chars=10)

        out = chunker.add_chunk("Hello Jules! How are you doing today?")
        assert len(out) >= 1
        assert out[0] == "Hello Jules!"
        assert out[1] == "How are you doing today?"

    def test_chunker_various_delimiters(self) -> None:
        """Handles '.', '?', '!', ':', and '\\n' delimiters."""
        chunker = SentenceStreamChunker(min_chars=20)

        assert chunker.add_chunk("Is this question valid? ") == ["Is this question valid?"]
        assert chunker.add_chunk("Yes this is definitely valid! ") == [
            "Yes this is definitely valid!"
        ]
        assert chunker.add_chunk("Here is the key takeaway: ") == ["Here is the key takeaway:"]
        assert chunker.add_chunk("This is a line separated by newline\n") == [
            "This is a line separated by newline"
        ]

    @pytest.mark.asyncio
    async def test_chunker_async_stream(self) -> None:
        """chunker.stream() consumes an async token iterator and yields sentences."""
        chunker = SentenceStreamChunker(min_chars=35)

        tokens = [
            "Jules ",
            "is ",
            "an ",
            "autonomous ",
            "coding ",
            "daemon ",
            "built ",
            "for ",
            "Linux. ",
            "It ",
            "monitors ",
            "the ",
            "system ",
            "and ",
            "provides ",
            "full ",
            "duplex ",
            "voice ",
            "capabilities. ",
            "Final ",
            "note",
        ]

        async def token_generator() -> AsyncGenerator[str, None]:
            for token in tokens:
                yield token

        collected: list[str] = []
        async for sentence in chunker.stream(token_generator()):
            collected.append(sentence)

        assert len(collected) == 3
        assert collected[0] == "Jules is an autonomous coding daemon built for Linux."
        assert (
            collected[1]
            == "It monitors the system and provides full duplex voice capabilities."
        )
        assert collected[2] == "Final note"

    def test_chunker_reset_clears_buffer(self) -> None:
        """reset() discards all buffered text."""
        chunker = SentenceStreamChunker(min_chars=40)
        chunker.add_chunk("Some partial text")
        chunker.reset()
        assert chunker.flush() == []


# ---------------------------------------------------------------------------
# (b) Tests for VoiceSpeaker playback & sentence streaming
# ---------------------------------------------------------------------------


class TestVoiceSpeakerPlayback:
    """Tests for VoiceSpeaker sentence queueing, synthesis and state transitions."""

    @pytest.mark.asyncio
    async def test_speaker_plays_sentence_and_updates_state(
        self, publisher: StatePublisher, mock_output_stream: Any
    ) -> None:
        """VoiceSpeaker sets SPEAKING during playback and resets to IDLE when complete."""
        mock_stream, _ = mock_output_stream
        backend = MockTTSBackend(audio_duration=0.01)
        speaker = VoiceSpeaker(
            backend=backend,
            state_publisher=publisher,
            stream_factory=lambda **_: mock_stream,
        )

        assert publisher.get_current_state().state == DaemonState.IDLE
        assert not speaker.is_speaking

        sentence = "This is a single spoken sentence for Jules speech test."
        await speaker.speak(sentence)

        assert backend.history == [sentence]
        assert publisher.get_current_state().state == DaemonState.IDLE
        assert not speaker.is_speaking
        assert mock_stream.write.called

        speaker.close()

    @pytest.mark.asyncio
    async def test_speaker_speak_stream_sequential_playback(
        self, publisher: StatePublisher, mock_output_stream: Any
    ) -> None:
        """Multiple sentences in stream are played sequentially with SPEAKING state active."""
        mock_stream, _ = mock_output_stream
        backend = MockTTSBackend(audio_duration=0.01)
        speaker = VoiceSpeaker(
            backend=backend,
            state_publisher=publisher,
            stream_factory=lambda **_: mock_stream,
        )

        sentences = [
            "First sentence delivered via streaming pipeline.",
            "Second sentence synthesized while first is playing.",
            "Third sentence completing the streaming conversation turn.",
        ]

        states_observed: list[DaemonState] = []

        async def sentence_gen() -> AsyncGenerator[str, None]:
            for s in sentences:
                states_observed.append(publisher.get_current_state().state)
                yield s

        await speaker.speak_stream(sentence_gen())

        assert backend.history == sentences
        assert publisher.get_current_state().state == DaemonState.IDLE
        assert not speaker.is_speaking
        assert mock_stream.write.call_count >= len(sentences)

        speaker.close()

    @pytest.mark.asyncio
    async def test_speaker_empty_or_whitespace_text_ignored(
        self, publisher: StatePublisher, mock_output_stream: Any
    ) -> None:
        """Empty or blank sentences are safely ignored without changing state."""
        mock_stream, _ = mock_output_stream
        backend = MockTTSBackend()
        speaker = VoiceSpeaker(
            backend=backend,
            state_publisher=publisher,
            stream_factory=lambda **_: mock_stream,
        )

        await speaker.speak("")
        await speaker.speak("    ")

        assert len(backend.history) == 0
        assert publisher.get_current_state().state == DaemonState.IDLE
        speaker.close()


# ---------------------------------------------------------------------------
# (c) Tests for Barge-In Interruption (< 50ms)
# ---------------------------------------------------------------------------


class TestVoiceSpeakerBargeIn:
    """Tests for immediate Barge-in interruption and listener wiring."""

    @pytest.mark.asyncio
    async def test_barge_in_stop_clears_queue_and_resets_state(
        self, publisher: StatePublisher, mock_output_stream: Any
    ) -> None:
        """speaker.stop() immediately empties queue, cancels playback, and sets IDLE."""
        mock_stream, mock_sd_stop = mock_output_stream

        # Backend simulates slow playback so we can interrupt it mid-speech
        backend = MockTTSBackend(audio_duration=0.5, simulate_delay=0.1)
        speaker = VoiceSpeaker(
            backend=backend,
            state_publisher=publisher,
            stream_factory=lambda **_: mock_stream,
        )

        sentences = [f"Sentence number {i} for long queue test." for i in range(5)]

        # Start speaking stream in background task
        speak_task = asyncio.create_task(speaker.speak_stream(sentences))

        # Give it a brief moment to start speaking
        await asyncio.sleep(0.03)
        assert speaker.is_speaking
        assert publisher.get_current_state().state == DaemonState.SPEAKING

        # Measure stop duration
        t_start = time.perf_counter()
        speaker.stop()
        t_stop = (time.perf_counter() - t_start) * 1000.0

        # Must halt in < 50ms
        assert t_stop < 50.0, f"speaker.stop() took {t_stop:.2f}ms, expected < 50ms"

        # Queue must be cleared immediately
        assert speaker.queue_size == 0
        assert not speaker.is_speaking
        assert publisher.get_current_state().state == DaemonState.IDLE
        assert mock_stream.abort.called or mock_sd_stop.called

        # Ensure task completes cleanly without hanging
        await asyncio.wait_for(speak_task, timeout=0.2)
        speaker.close()

    @pytest.mark.asyncio
    async def test_barge_in_stop_latency_strict_timing(
        self, publisher: StatePublisher, mock_output_stream: Any
    ) -> None:
        """Strict verification that stop() executes in < 50ms even with many queued items."""
        mock_stream, _ = mock_output_stream
        backend = MockTTSBackend(audio_duration=0.2)
        speaker = VoiceSpeaker(
            backend=backend,
            state_publisher=publisher,
            stream_factory=lambda **_: mock_stream,
        )

        # Pre-fill queue with 50 sentences
        for i in range(50):
            speaker._sentence_queue.put_nowait(f"Pre-queued sentence {i}")

        speaker._is_speaking = True
        publisher.update(state=DaemonState.SPEAKING)

        t_start = time.perf_counter()
        speaker.stop()
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        assert elapsed_ms < 50.0, f"stop() took {elapsed_ms:.2f}ms (threshold 50ms)"
        assert speaker.queue_size == 0
        assert publisher.get_current_state().state == DaemonState.IDLE
        speaker.close()

    @pytest.mark.asyncio
    async def test_barge_in_automatic_wiring_with_listener(
        self, publisher: StatePublisher, mock_output_stream: Any
    ) -> None:
        """Connecting listener to speaker automatically triggers speaker.stop() on BargeInEvent."""
        mock_stream, _ = mock_output_stream
        backend = MockTTSBackend(audio_duration=0.5, simulate_delay=0.1)
        speaker = VoiceSpeaker(
            backend=backend,
            state_publisher=publisher,
            stream_factory=lambda **_: mock_stream,
        )

        # Create listener with mock factory
        listener = AudioListener(
            state_publisher=publisher,
            stream_factory=lambda **_: MagicMock(),
        )

        # Wire speaker to listener
        speaker.connect_listener(listener)
        assert listener.barge_in_callback == speaker.on_barge_in

        # Start speaking
        speak_task = asyncio.create_task(
            speaker.speak("This is a long sentence being spoken right now.")
        )
        await asyncio.sleep(0.03)
        assert speaker.is_speaking
        assert publisher.get_current_state().state == DaemonState.SPEAKING

        # Simulate user speaking -> Barge-in event triggered from listener
        barge_in_event = BargeInEvent(
            timestamp=time.time(),
            interrupted_state=DaemonState.SPEAKING,
        )
        listener._trigger_barge_in(barge_in_event)

        # Speaker should now be stopped immediately
        assert not speaker.is_speaking
        assert publisher.get_current_state().state == DaemonState.IDLE

        await asyncio.wait_for(speak_task, timeout=0.2)
        speaker.close()
        listener.close()


# ---------------------------------------------------------------------------
# (d) Tests for Headless / Mocked Fallback
# ---------------------------------------------------------------------------


class TestVoiceSpeakerHardwareFallback:
    """Tests for graceful fallback when sound hardware is unavailable."""

    def test_strict_hardware_raises_on_unavailable_device(self) -> None:
        """AudioHardwareUnavailableError is raised if strict_hardware=True and device fails."""

        def failing_factory(**_: Any) -> None:
            raise RuntimeError("PortAudio device error: Invalid device")

        with pytest.raises(AudioHardwareUnavailableError, match="hardware unavailable"):
            VoiceSpeaker(
                backend=MockTTSBackend(),
                stream_factory=failing_factory,
                strict_hardware=True,
            )

    @pytest.mark.asyncio
    async def test_headless_graceful_fallback_without_hardware(
        self, publisher: StatePublisher
    ) -> None:
        """VoiceSpeaker operates safely in headless mode when hardware is unavailable."""

        def failing_factory(**_: Any) -> None:
            raise RuntimeError("No sound output hardware found")

        speaker = VoiceSpeaker(
            backend=MockTTSBackend(audio_duration=0.01),
            state_publisher=publisher,
            stream_factory=failing_factory,
            strict_hardware=False,
        )

        assert not speaker.is_available

        # Should complete speak without raising exceptions
        await speaker.speak("Headless speech synthesis test should succeed gracefully.")
        assert publisher.get_current_state().state == DaemonState.IDLE
        speaker.close()
