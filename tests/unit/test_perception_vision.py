from __future__ import annotations

import asyncio
import os
from pathlib import Path
import struct
from unittest.mock import AsyncMock

import pytest

from jules.perception.errors import (
    CaptureFailedError,
    CaptureTimeoutError,
    PerceptionError,
    ToolNotFoundError,
)
from jules.perception.vision import (
    PNG_MAGIC,
    VisionCaptureResult,
    capture_screen,
    is_wayland_session,
    resolve_screen_capture_command,
)


def _make_sample_png(width: int = 1920, height: int = 1080) -> bytes:
    """Generate minimal valid PNG bytes with IHDR dimensions for testing."""
    ihdr_payload = (
        struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"  # 8-bit truecolor with alpha
    )
    ihdr_chunk = (
        len(ihdr_payload).to_bytes(4, "big")
        + b"IHDR"
        + ihdr_payload
        + b"\x00\x00\x00\x00"  # dummy CRC
    )
    return PNG_MAGIC + ihdr_chunk


def test_is_wayland_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert is_wayland_session() is True

    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert is_wayland_session() is True

    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert is_wayland_session() is False


def test_resolve_screen_capture_command_wayland(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

    def fake_which(name: str) -> str | None:
        if name in ("grim", "maim"):
            return f"/usr/bin/{name}"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    assert resolve_screen_capture_command() == ["grim", "-"]

    # Fallback to maim if grim missing
    def fake_which_maim(name: str) -> str | None:
        if name == "maim":
            return "/usr/bin/maim"
        return None

    monkeypatch.setattr("shutil.which", fake_which_maim)
    assert resolve_screen_capture_command() == ["maim"]


def test_resolve_screen_capture_command_x11(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    def fake_which(name: str) -> str | None:
        if name in ("grim", "maim"):
            return f"/usr/bin/{name}"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    assert resolve_screen_capture_command() == ["maim"]


def test_resolve_screen_capture_command_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert resolve_screen_capture_command() is None


@pytest.mark.asyncio
async def test_capture_screen_in_memory_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sample_png = _make_sample_png(1920, 1080)

    class FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return sample_png, b""

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProc()),
    )

    # Monitor current working directory before and after
    files_before = set(Path.cwd().glob("*"))

    result = await capture_screen(command_override=["dummy-grim", "-"])

    # Zero files written to disk verification
    files_after = set(Path.cwd().glob("*"))
    assert files_before == files_after

    assert isinstance(result, VisionCaptureResult)
    assert result.format == "png"
    assert result.data == sample_png
    assert result.size_bytes == len(sample_png)
    assert result.width == 1920
    assert result.height == 1080


@pytest.mark.asyncio
async def test_capture_screen_missing_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jules.perception.vision.resolve_screen_capture_command", lambda: None)

    with pytest.raises(ToolNotFoundError) as exc_info:
        await capture_screen()

    assert issubclass(ToolNotFoundError, PerceptionError)
    assert "No supported screen capture utility found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_capture_screen_invalid_png_magic_header(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcCorrupted:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"NOT_A_PNG_FILE_DATA", b""

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProcCorrupted()),
    )

    with pytest.raises(CaptureFailedError) as exc_info:
        await capture_screen(command_override=["dummy-grim", "-"])

    assert issubclass(CaptureFailedError, PerceptionError)
    assert "invalid magic header" in str(exc_info.value)


@pytest.mark.asyncio
async def test_capture_screen_process_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcError:
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"grim error: failed to copy output\n"

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProcError()),
    )

    with pytest.raises(CaptureFailedError) as exc_info:
        await capture_screen(command_override=["grim", "-"])

    assert "failed with exit code 1" in str(exc_info.value)
    assert "failed to copy output" in str(exc_info.value)


@pytest.mark.asyncio
async def test_capture_screen_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcHanging:
        returncode = None
        killed = False

        async def communicate(self) -> tuple[bytes, bytes]:
            await asyncio.sleep(10)
            return b"", b""

        def kill(self) -> None:
            self.killed = True

    proc = FakeProcHanging()
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=proc),
    )

    with pytest.raises(CaptureTimeoutError) as exc_info:
        await capture_screen(timeout=0.01, command_override=["grim", "-"])

    assert issubclass(CaptureTimeoutError, PerceptionError)
    assert "timed out after 0.01 seconds" in str(exc_info.value)
    assert proc.killed is True
