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
    "LocalTranscriber",
    "ModelLoadError",
    "TranscriberError",
    "TranscriptionResult",
    "VADDetector",
]

