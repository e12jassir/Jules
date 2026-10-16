"""Jules Voice subsystem: audio capture, VAD, transcription, and speech synthesis."""

from __future__ import annotations

from jules.voice.listener import (
    AudioHardwareUnavailableError,
    AudioListener,
    BargeInCallback,
    BargeInDetected,
    BargeInEvent,
    VADDetector,
)
from jules.voice.speaker import (
    BaseTTSBackend,
    ElevenLabsTTSBackend,
    KokoroTTSBackend,
    MockTTSBackend,
    PiperTTSBackend,
    SentenceStreamChunker,
    SpeakerError,
    TTSModelError,
    VoiceSpeaker,
    clean_markdown_for_speech,
)
from jules.voice.transcriber import (
    AudioFormatError,
    LocalTranscriber,
    ModelLoadError,
    TranscriberError,
    TranscriptionResult,
)

__all__ = [
    "AudioFormatError",
    "AudioHardwareUnavailableError",
    "AudioListener",
    "BargeInCallback",
    "BargeInDetected",
    "BargeInEvent",
    "BaseTTSBackend",
    "ElevenLabsTTSBackend",
    "KokoroTTSBackend",
    "LocalTranscriber",
    "MockTTSBackend",
    "ModelLoadError",
    "PiperTTSBackend",
    "SentenceStreamChunker",
    "SpeakerError",
    "TTSModelError",
    "TranscriberError",
    "TranscriptionResult",
    "VADDetector",
    "VoiceSpeaker",
    "clean_markdown_for_speech",
]

