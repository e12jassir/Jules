from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
import shutil

from typing import TYPE_CHECKING

from jules.sanitizer import Sanitizer

if TYPE_CHECKING:
    from jules.core.permissions import PermissionGate

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ClipboardResult:
    """Represents the outcome of a clipboard text extraction operation."""

    text: str
    is_safe: bool
    sanitizer_reason: str | None = None
    raw_text: str | None = None
    redacted_text: str | None = None
    error: str | None = None

    def __str__(self) -> str:
        return self.text


def is_wayland_session() -> bool:
    """Detect whether the current environment is running under a Wayland compositor."""
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return True
    return False


def resolve_clipboard_command() -> list[str] | None:
    """Resolve the appropriate CLI command for reading clipboard content.

    Prioritizes Wayland native utilities (`wl-paste`) under Wayland sessions,
    and X11 utilities (`xclip`, `xsel`) under X11 sessions, with mutual fallback.
    """
    wayland = is_wayland_session()

    if wayland:
        candidates = [
            ("wl-paste", ["wl-paste", "--no-newline"]),
            ("xclip", ["xclip", "-selection", "clipboard", "-o"]),
            ("xsel", ["xsel", "--clipboard", "--output"]),
        ]
    else:
        candidates = [
            ("xclip", ["xclip", "-selection", "clipboard", "-o"]),
            ("xsel", ["xsel", "--clipboard", "--output"]),
            ("wl-paste", ["wl-paste", "--no-newline"]),
        ]

    for binary_name, command in candidates:
        if shutil.which(binary_name):
            return command

    return None


async def get_clipboard_text(
    timeout: float = 3.0,
    command_override: list[str] | None = None,
    gate: PermissionGate | None = None,
) -> ClipboardResult:
    """Asynchronously retrieve clipboard text, sanitizing content for sensitive data.

    Returns a `ClipboardResult`. If sensitive keys, tokens, or credentials are found,
    `is_safe` is set to False, `text` is redacted, and `sanitizer_reason` contains
    the detected sensitive pattern category.
    """
    cmd = command_override or resolve_clipboard_command()
    if not cmd:
        return ClipboardResult(
            text="",
            is_safe=False,
            error="No supported clipboard utility found (wl-paste, xclip, xsel)",
        )

    if gate is not None:
        from jules.core.permissions import Action
        await gate.check(Action.SHELL_COMMAND, " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return ClipboardResult(
            text="",
            is_safe=False,
            error=f"Clipboard tool executable not found: {exc}",
        )
    except OSError as exc:
        return ClipboardResult(
            text="",
            is_safe=False,
            error=f"Failed to execute clipboard command: {exc}",
        )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except OSError:
            pass
        return ClipboardResult(
            text="",
            is_safe=False,
            error=f"Clipboard read timed out after {timeout} seconds",
        )

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        # Non-zero return code often occurs when clipboard is empty or holds non-text MIME types
        return ClipboardResult(
            text="",
            is_safe=True,
            raw_text="",
            error=f"Clipboard is empty or contains non-text content ({err_msg})"
            if err_msg
            else "Clipboard is empty or contains non-text content",
        )

    raw_text = stdout.decode("utf-8", errors="replace")
    if not raw_text:
        return ClipboardResult(
            text="",
            is_safe=True,
            raw_text="",
            redacted_text="",
        )

    # Mandatory Sanitizer filtering
    sanitize_res = Sanitizer.check(raw_text)
    if not sanitize_res.is_safe:
        logger.warning(
            "Clipboard content contained sensitive information: %s",
            sanitize_res.reason,
        )
        redacted = f"[BLOCKED: Sensitive content detected ({sanitize_res.reason})]"
        return ClipboardResult(
            text=redacted,
            is_safe=False,
            sanitizer_reason=sanitize_res.reason,
            raw_text=raw_text,
            redacted_text=redacted,
        )

    return ClipboardResult(
        text=raw_text,
        is_safe=True,
        raw_text=raw_text,
        redacted_text=raw_text,
    )
