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

__all__ = [
    "AudioHardwareUnavailableError",
    "AudioListener",
    "BargeInCallback",
    "BargeInDetected",
    "BargeInEvent",
    "VADDetector",
]
