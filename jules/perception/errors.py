from __future__ import annotations


class PerceptionError(Exception):
    """Base exception for all perception subsystem errors."""


class ToolNotFoundError(PerceptionError):
    """Raised when a required CLI tool (e.g. grim, maim, wl-paste, xclip) is not found."""


class CaptureTimeoutError(PerceptionError):
    """Raised when a screen capture operation exceeds the timeout limit."""


class CaptureFailedError(PerceptionError):
    """Raised when a screen capture command fails or produces invalid data."""
