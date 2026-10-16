from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import os
import shutil
import struct

from jules.perception.errors import (
    CaptureFailedError,
    CaptureTimeoutError,
    PerceptionError,
    ToolNotFoundError,
)

logger = logging.getLogger(__name__)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class VisionCaptureResult:
    """Represents an in-memory screen capture."""

    data: bytes
    format: str = "png"
    width: int | None = None
    height: int | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.data)


def is_wayland_session() -> bool:
    """Detect whether the current environment is running under a Wayland compositor."""
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return True
    return False


def resolve_screen_capture_command() -> list[str] | None:
    """Resolve the appropriate CLI command for capturing screen directly to stdout bytes.

    Wayland: `grim -` (writes PNG to stdout)
    X11: `maim` (writes PNG to stdout by default)
    """
    wayland = is_wayland_session()

    if wayland:
        candidates = [
            ("grim", ["grim", "-"]),
            ("maim", ["maim"]),
        ]
    else:
        candidates = [
            ("maim", ["maim"]),
            ("grim", ["grim", "-"]),
        ]

    for binary_name, command in candidates:
        if shutil.which(binary_name):
            return command

    return None


async def capture_screen(
    timeout: float = 5.0,
    command_override: list[str] | None = None,
) -> VisionCaptureResult:
    """Capture the current screen into in-memory PNG bytes without writing files to disk.

    Raises:
        ToolNotFoundError: If neither grim nor maim is found in PATH.
        CaptureTimeoutError: If the screen capture command exceeds the timeout limit.
        CaptureFailedError: If the process fails or the output data is invalid PNG.
    """
    cmd = command_override or resolve_screen_capture_command()
    if not cmd:
        raise ToolNotFoundError(
            "No supported screen capture utility found (grim for Wayland, maim for X11)"
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise ToolNotFoundError(
            f"Screen capture tool {cmd[0]!r} not found: {exc}"
        ) from exc
    except OSError as exc:
        raise CaptureFailedError(
            f"Failed to start screen capture process {cmd[0]!r}: {exc}"
        ) from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        try:
            proc.kill()
        except OSError:
            pass
        raise CaptureTimeoutError(
            f"Screen capture timed out after {timeout} seconds"
        ) from exc

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise CaptureFailedError(
            f"Screen capture tool {cmd[0]!r} failed with exit code {proc.returncode}: {err_msg}"
        )

    if not stdout or not stdout.startswith(PNG_MAGIC):
        raise CaptureFailedError(
            "Captured data is not a valid PNG (invalid magic header)"
        )

    width: int | None = None
    height: int | None = None
    if len(stdout) >= 24:
        try:
            # Bytes 16-24 hold width and height in PNG IHDR chunk
            width, height = struct.unpack(">II", stdout[16:24])
        except struct.error:
            pass

    return VisionCaptureResult(
        data=stdout,
        format="png",
        width=width,
        height=height,
    )
