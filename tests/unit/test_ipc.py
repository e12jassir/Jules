"""Unit tests for UNIX domain socket IPC protocol and client/server."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from jules.daemon.ipc import (
    IPCClient,
    IPCConnectionError,
    IPCError,
    IPCServer,
    IPCTimeoutError,
    resolve_socket_path,
)
from jules.providers.base import ContentEvent, StreamEvent, ThoughtEvent
from jules.sanitizer import Sanitizer


# ---------------------------------------------------------------------------
# Path Resolution Tests
# ---------------------------------------------------------------------------


def test_resolve_socket_path_with_explicit_override(tmp_path: Path) -> None:
    """Explicit socket path override should be respected."""
    custom_sock = tmp_path / "custom.sock"
    resolved = resolve_socket_path(target_path=custom_sock)
    assert resolved == custom_sock.resolve()


def test_resolve_socket_path_with_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When XDG_RUNTIME_DIR is set and accessible, resolve to $XDG_RUNTIME_DIR/jules.sock."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    resolved = resolve_socket_path()
    assert resolved == tmp_path / "jules.sock"


def test_resolve_socket_path_fallback_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """When XDG_RUNTIME_DIR is unset, fallback to ~/.jules/run/jules.sock."""
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    resolved = resolve_socket_path()
    assert resolved == Path.home() / ".jules" / "run" / "jules.sock"


def test_resolve_socket_path_fallback_when_inaccessible(monkeypatch: pytest.MonkeyPatch) -> None:
    """When XDG_RUNTIME_DIR is not a directory or unwritable, fallback to ~/.jules/run/jules.sock."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/non/existent/runtime/dir/999999")
    resolved = resolve_socket_path()
    assert resolved == Path.home() / ".jules" / "run" / "jules.sock"


# ---------------------------------------------------------------------------
# Permissions Tests
# ---------------------------------------------------------------------------


async def test_socket_permissions_enforced(tmp_path: Path) -> None:
    """Socket file permissions must be 0o600 for single-user security."""
    sock_path = tmp_path / "jules.sock"
    server = IPCServer(socket_path=sock_path)
    await server.start()
    try:
        assert sock_path.exists()
        mode = sock_path.stat().st_mode & 0o777
        assert mode == 0o600
    finally:
        await server.stop()


# ---------------------------------------------------------------------------
# Async Communication Roundtrip Tests
# ---------------------------------------------------------------------------


async def test_ipc_server_client_roundtrip(tmp_path: Path) -> None:
    """Client and server communicate over temporary UNIX domain socket."""
    sock_path = tmp_path / "jules.sock"
    async with IPCServer(socket_path=sock_path) as server:
        client = IPCClient(socket_path=sock_path)
        status_res = await client.get_status()
        assert status_res.get("status") == "ok"
        assert status_res.get("service") == "jules-daemon"


# ---------------------------------------------------------------------------
# Operations (op) Tests
# ---------------------------------------------------------------------------


async def test_ipc_op_query_streaming(tmp_path: Path) -> None:
    """Query operation streams ThoughtEvent and ContentEvent back ending with done signal."""
    sock_path = tmp_path / "jules.sock"

    async def fake_query_handler(payload: dict[str, Any]) -> AsyncIterator[StreamEvent]:
        assert payload.get("text") == "Hello Jules"
        yield ThoughtEvent(content="Pondering...")
        yield ContentEvent(content="Hello ")
        yield ContentEvent(content="World!")

    server = IPCServer(socket_path=sock_path, query_handler=fake_query_handler)
    await server.start()
    try:
        client = IPCClient(socket_path=sock_path)
        events: list[StreamEvent] = []
        async for ev in client.stream_query("Hello Jules", session_id="test-session"):
            events.append(ev)

        assert len(events) == 3
        assert isinstance(events[0], ThoughtEvent)
        assert events[0].content == "Pondering..."
        assert isinstance(events[1], ContentEvent)
        assert events[1].content == "Hello "
        assert isinstance(events[2], ContentEvent)
        assert events[2].content == "World!"
    finally:
        await server.stop()


async def test_ipc_op_query_blocked_by_sanitizer(tmp_path: Path) -> None:
    """Query with sensitive tokens should be blocked by Sanitizer first."""
    sock_path = tmp_path / "jules.sock"
    handler_called = False

    async def fake_query_handler(payload: dict[str, Any]) -> AsyncIterator[StreamEvent]:
        nonlocal handler_called
        handler_called = True
        yield ContentEvent(content="Should not be reached")

    server = IPCServer(socket_path=sock_path, query_handler=fake_query_handler)
    await server.start()
    try:
        client = IPCClient(socket_path=sock_path)
        events: list[StreamEvent] = []
        # Pass private key format that Sanitizer flags
        async for ev in client.stream_query("My key is -----BEGIN RSA PRIVATE KEY----- secret"):
            events.append(ev)

        assert not handler_called
        assert len(events) == 1
        assert isinstance(events[0], ContentEvent)
        assert "bloqueado por sanitizador" in events[0].content.lower() or "blocked by sanitizer" in events[0].content.lower()
    finally:
        await server.stop()


async def test_ipc_op_voice_ptt_toggle(tmp_path: Path) -> None:
    """voice_ptt_toggle triggers callback and returns ok status."""
    sock_path = tmp_path / "jules.sock"
    ptt_called = False

    async def fake_ptt_handler() -> dict[str, Any]:
        nonlocal ptt_called
        ptt_called = True
        return {"status": "ok", "listening": True}

    server = IPCServer(socket_path=sock_path, ptt_handler=fake_ptt_handler)
    await server.start()
    try:
        client = IPCClient(socket_path=sock_path)
        res = await client.toggle_ptt()
        assert ptt_called is True
        assert res["status"] == "ok"
        assert res.get("listening") is True
    finally:
        await server.stop()


async def test_ipc_op_voice_barge_in(tmp_path: Path) -> None:
    """voice_barge_in triggers callback and returns ok status."""
    sock_path = tmp_path / "jules.sock"
    barge_in_called = False

    def fake_barge_in_handler() -> dict[str, Any]:
        nonlocal barge_in_called
        barge_in_called = True
        return {"status": "ok", "interrupted": True}

    server = IPCServer(socket_path=sock_path, barge_in_handler=fake_barge_in_handler)
    await server.start()
    try:
        client = IPCClient(socket_path=sock_path)
        res = await client.barge_in()
        assert barge_in_called is True
        assert res["status"] == "ok"
        assert res.get("interrupted") is True
    finally:
        await server.stop()


async def test_ipc_op_shell_event_safe(tmp_path: Path) -> None:
    """Safe shell_event triggers handler and returns ok status."""
    sock_path = tmp_path / "jules.sock"
    received_event: dict[str, Any] = {}

    async def fake_shell_handler(event: dict[str, Any]) -> dict[str, Any]:
        nonlocal received_event
        received_event = event
        return {"status": "ok", "captured": True}

    server = IPCServer(socket_path=sock_path, shell_handler=fake_shell_handler)
    await server.start()
    try:
        client = IPCClient(socket_path=sock_path)
        res = await client.send_shell_event(
            phase="preexec",
            cmd="git status",
            exit_code=0,
            cwd="/home/user/project",
            duration_ms=45.2,
        )
        assert res["status"] == "ok"
        assert res.get("captured") is True
        assert received_event["cmd"] == "git status"
        assert received_event["phase"] == "preexec"
        assert received_event["exit_code"] == 0
        assert received_event["cwd"] == "/home/user/project"
    finally:
        await server.stop()


async def test_ipc_op_shell_event_sanitizer_blocks_sensitive_cmd(tmp_path: Path) -> None:
    """Sensitive commands in shell_event must be intercepted by Sanitizer before reaching handler."""
    sock_path = tmp_path / "jules.sock"
    handler_called = False

    async def fake_shell_handler(event: dict[str, Any]) -> dict[str, Any]:
        nonlocal handler_called
        handler_called = True
        return {"status": "ok"}

    server = IPCServer(socket_path=sock_path, shell_handler=fake_shell_handler)
    await server.start()
    try:
        client = IPCClient(socket_path=sock_path)
        res = await client.send_shell_event(
            phase="preexec",
            cmd="export SECRET_KEY=supersecretvalue123",
            exit_code=0,
        )
        assert not handler_called
        assert res["status"] == "blocked"
        assert "reason" in res
    finally:
        await server.stop()


async def test_ipc_op_status(tmp_path: Path) -> None:
    """status operation returns daemon health, memory, and model status."""
    sock_path = tmp_path / "jules.sock"

    async def fake_status_handler() -> dict[str, Any]:
        return {
            "health": "healthy",
            "memory": {"episodes": 12, "facts": 5},
            "models": {"active": "llama3.2:3b", "available": ["llama3.2:3b", "qwen2.5:3b"]},
        }

    server = IPCServer(socket_path=sock_path, status_handler=fake_status_handler)
    await server.start()
    try:
        client = IPCClient(socket_path=sock_path)
        res = await client.get_status()
        assert res["status"] == "ok"
        assert res["health"] == "healthy"
        assert res["memory"]["episodes"] == 12
        assert res["models"]["active"] == "llama3.2:3b"
    finally:
        await server.stop()


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------


async def test_ipc_malformed_json_handling(tmp_path: Path) -> None:
    """Malformed JSON line should return error response without crashing server."""
    sock_path = tmp_path / "jules.sock"
    async with IPCServer(socket_path=sock_path):
        client = IPCClient(socket_path=sock_path)
        raw_res = await client.send_raw_line("not-valid-json\n")
        parsed = json.loads(raw_res)
        assert parsed["status"] == "error"
        assert "json" in parsed["error"].lower()


async def test_ipc_unknown_operation_handling(tmp_path: Path) -> None:
    """Unknown op string should return descriptive error response."""
    sock_path = tmp_path / "jules.sock"
    async with IPCServer(socket_path=sock_path):
        client = IPCClient(socket_path=sock_path)
        res = await client.send_raw({"op": "non_existent_action"})
        assert res["status"] == "error"
        assert "unknown operation" in res["error"].lower()


async def test_ipc_missing_op_handling(tmp_path: Path) -> None:
    """Payload missing 'op' field should return error response."""
    sock_path = tmp_path / "jules.sock"
    async with IPCServer(socket_path=sock_path):
        client = IPCClient(socket_path=sock_path)
        res = await client.send_raw({"foo": "bar"})
        assert res["status"] == "error"
        assert "op" in res["error"].lower()


# ---------------------------------------------------------------------------
# Shutdown, Stale Socket, and Conflict Tests
# ---------------------------------------------------------------------------


async def test_ipc_clean_shutdown(tmp_path: Path) -> None:
    """Server shutdown must close listener and unlink socket file."""
    sock_path = tmp_path / "jules.sock"
    server = IPCServer(socket_path=sock_path)
    await server.start()
    assert sock_path.exists()
    assert server.is_running

    await server.stop()
    assert not sock_path.exists()
    assert not server.is_running


async def test_ipc_stale_socket_cleanup_on_startup(tmp_path: Path) -> None:
    """Unused/stale socket file left over from crashed process should be cleaned up automatically."""
    sock_path = tmp_path / "jules.sock"
    # Create a stale file where the socket should be
    sock_path.write_text("stale data leftover from crash")
    assert sock_path.exists()

    server = IPCServer(socket_path=sock_path)
    await server.start()
    try:
        assert server.is_running
        client = IPCClient(socket_path=sock_path)
        res = await client.get_status()
        assert res["status"] == "ok"
    finally:
        await server.stop()


async def test_ipc_active_socket_conflict(tmp_path: Path) -> None:
    """Attempting to start a second server on an actively listening socket must fail."""
    sock_path = tmp_path / "jules.sock"
    server1 = IPCServer(socket_path=sock_path)
    await server1.start()
    try:
        server2 = IPCServer(socket_path=sock_path)
        with pytest.raises(RuntimeError, match="already"):
            await server2.start()
    finally:
        await server1.stop()


# ---------------------------------------------------------------------------
# Client Connection and Timeout Handling Tests
# ---------------------------------------------------------------------------


async def test_ipc_client_connection_error_when_no_server(tmp_path: Path) -> None:
    """Client raises IPCConnectionError when server is not running."""
    sock_path = tmp_path / "nonexistent.sock"
    client = IPCClient(socket_path=sock_path, timeout=0.5)
    with pytest.raises(IPCConnectionError):
        await client.get_status()


async def test_ipc_client_timeout_handling(tmp_path: Path) -> None:
    """Client raises IPCTimeoutError when server response exceeds timeout."""
    sock_path = tmp_path / "jules.sock"

    async def hanging_status_handler() -> dict[str, Any]:
        await asyncio.sleep(2.0)
        return {"status": "ok"}

    server = IPCServer(socket_path=sock_path, status_handler=hanging_status_handler)
    await server.start()
    try:
        client = IPCClient(socket_path=sock_path, timeout=0.1)
        with pytest.raises(IPCTimeoutError):
            await client.get_status()
    finally:
        await server.stop()
