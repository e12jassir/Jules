from __future__ import annotations

from .clipboard import (
    ClipboardResult,
    get_clipboard_text,
    is_wayland_session as is_wayland_clipboard_session,
    resolve_clipboard_command,
)
from .errors import (
    CaptureFailedError,
    CaptureTimeoutError,
    PerceptionError,
    ToolNotFoundError,
)
from .vision import (
    PNG_MAGIC,
    VisionCaptureResult,
    capture_screen,
    is_wayland_session,
    resolve_screen_capture_command,
)

__all__ = [
    "CaptureFailedError",
    "CaptureTimeoutError",
    "ClipboardResult",
    "PNG_MAGIC",
    "PerceptionError",
    "ToolNotFoundError",
    "VisionCaptureResult",
    "capture_screen",
    "get_clipboard_text",
    "is_wayland_clipboard_session",
    "is_wayland_session",
    "resolve_clipboard_command",
    "resolve_screen_capture_command",
]
