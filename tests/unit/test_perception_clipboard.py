from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from jules.perception.clipboard import (
    ClipboardResult,
    get_clipboard_text,
    is_wayland_session,
    resolve_clipboard_command,
)


def test_is_wayland_session_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test WAYLAND_DISPLAY set
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    assert is_wayland_session() is True

    # Test XDG_SESSION_TYPE=wayland
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert is_wayland_session() is True

    # Test X11 session
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert is_wayland_session() is False


def test_resolve_clipboard_command_wayland_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")

    # Both wl-paste and xclip exist
    def fake_which(cmd: str) -> str | None:
        if cmd in ("wl-paste", "xclip"):
            return f"/usr/bin/{cmd}"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    assert resolve_clipboard_command() == ["wl-paste", "--no-newline"]

    # Only xclip exists on Wayland (XWayland fallback)
    def fake_which_fallback(cmd: str) -> str | None:
        if cmd == "xclip":
            return "/usr/bin/xclip"
        return None

    monkeypatch.setattr("shutil.which", fake_which_fallback)
    assert resolve_clipboard_command() == ["xclip", "-selection", "clipboard", "-o"]


def test_resolve_clipboard_command_x11_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")

    def fake_which(cmd: str) -> str | None:
        if cmd in ("xclip", "wl-paste"):
            return f"/usr/bin/{cmd}"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    assert resolve_clipboard_command() == ["xclip", "-selection", "clipboard", "-o"]

    # Only xsel exists
    def fake_which_xsel(cmd: str) -> str | None:
        if cmd == "xsel":
            return "/usr/bin/xsel"
        return None

    monkeypatch.setattr("shutil.which", fake_which_xsel)
    assert resolve_clipboard_command() == ["xsel", "--clipboard", "--output"]


def test_resolve_clipboard_command_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert resolve_clipboard_command() is None


@pytest.mark.asyncio
async def test_get_clipboard_text_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"git checkout -b feature/test\n", b""

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProc()),
    )

    result = await get_clipboard_text(command_override=["dummy-clipboard"])
    assert isinstance(result, ClipboardResult)
    assert result.is_safe is True
    assert result.text == "git checkout -b feature/test\n"
    assert result.sanitizer_reason is None
    assert result.error is None


@pytest.mark.asyncio
async def test_get_clipboard_text_mandatory_sanitizer_blocks_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. Shell export secret
    class FakeProcSecret:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"export AWS_SECRET_ACCESS_KEY=secret_key_value_12345", b""

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProcSecret()),
    )

    res = await get_clipboard_text(command_override=["dummy-clipboard"])
    assert res.is_safe is False
    assert res.sanitizer_reason == "export_secret"
    assert "[BLOCKED: Sensitive content detected (export_secret)]" in res.text
    assert "secret_key_value_12345" not in res.text

    # 2. OpenAI API Key
    class FakeProcOpenAI:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"Here is my key: sk-abcdef1234567890abcdef1234567890", b""

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProcOpenAI()),
    )

    res_openai = await get_clipboard_text(command_override=["dummy-clipboard"])
    assert res_openai.is_safe is False
    assert res_openai.sanitizer_reason == "openai_key"
    assert "[BLOCKED: Sensitive content detected (openai_key)]" in res_openai.text
    assert "sk-abcdef" not in res_openai.text


@pytest.mark.asyncio
async def test_get_clipboard_missing_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jules.perception.clipboard.resolve_clipboard_command", lambda: None)
    result = await get_clipboard_text()
    assert result.is_safe is False
    assert result.text == ""
    assert "No supported clipboard utility found" in (result.error or "")


@pytest.mark.asyncio
async def test_get_clipboard_empty_or_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcEmpty:
        returncode = 1

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"Nothing is copied\n"

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=FakeProcEmpty()),
    )

    result = await get_clipboard_text(command_override=["dummy-clipboard"])
    assert result.text == ""
    assert result.is_safe is True
    assert "Clipboard is empty or contains non-text content" in (result.error or "")


@pytest.mark.asyncio
async def test_get_clipboard_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
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

    result = await get_clipboard_text(timeout=0.01, command_override=["dummy-clipboard"])
    assert result.is_safe is False
    assert "timed out" in (result.error or "")
    assert proc.killed is True
