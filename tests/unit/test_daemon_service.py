"""Unit tests for resident JulesDaemon service, systemd generator, and CLI daemon commands."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import signal
import sys
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from jules.daemon.ipc import IPCClient, IPCConnectionError, IPCServer
from jules.daemon.service import JulesDaemon, install_systemd_user_service
from jules.daemon.state import DaemonState, StatePublisher
from jules.providers.base import ContentEvent, StreamEvent, ThoughtEvent
from jules.sanitizer import Sanitizer
import jules.cli.main as cli_main


# ---------------------------------------------------------------------------
# Fixtures and Helpers
# ---------------------------------------------------------------------------


class MockChatEngine:
    """Mock ChatEngine that yields simulated streaming events."""

    def __init__(self, responses: list[StreamEvent] | None = None) -> None:
        self.responses = responses or [
            ThoughtEvent(content="Thinking deeply..."),
            ContentEvent(content="Hello from Jules daemon!"),
        ]
        self.last_provider = "mock_provider"
        self.last_model = "mock_model"
        self.received_queries: list[dict] = []

    async def stream_turn(
        self,
        user_input: str,
        session_id: str,
        session_ctx: any,
        chat_history: list[tuple[str, str]],
        user_override: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        self.received_queries.append({
            "user_input": user_input,
            "session_id": session_id,
            "session_ctx": session_ctx,
            "chat_history": chat_history,
            "user_override": user_override,
        })
        for event in self.responses:
            yield event


def make_mock_daemon(tmp_path: Path, chat_engine: MockChatEngine | None = None) -> JulesDaemon:
    """Create a JulesDaemon configured with isolated temporary paths and mocks."""
    sock_path = tmp_path / "jules.sock"
    state_path = tmp_path / "jules.state"

    mock_router = MagicMock()
    mock_router.providers = {}
    mock_persistent = MagicMock()
    mock_episodic = MagicMock()
    mock_memory_engine = MagicMock()
    mock_memory_engine._background_tasks = set()
    mock_event_bus = MagicMock()
    mock_watcher = MagicMock()
    mock_watcher._running = False
    mock_watcher.stop = MagicMock()

    engine = chat_engine or MockChatEngine()

    return JulesDaemon(
        router=mock_router,
        persistent_memory=mock_persistent,
        episodic_memory=mock_episodic,
        memory_engine=mock_memory_engine,
        event_bus=mock_event_bus,
        platform_watcher=mock_watcher,
        chat_engine=engine,
        socket_path=sock_path,
        state_path=state_path,
        current_directory=str(tmp_path),
    )


# ---------------------------------------------------------------------------
# 1. Lifecycle and Component Initialization Tests
# ---------------------------------------------------------------------------


def test_daemon_components_initialization(tmp_path: Path) -> None:
    """Test JulesDaemon component initialization (Router, Memory, ChatEngine, Publisher, IPC)."""
    sock_path = tmp_path / "jules.sock"
    state_path = tmp_path / "jules.state"

    mock_router = MagicMock()
    mock_persistent = MagicMock()
    mock_episodic = MagicMock()
    mock_memory = MagicMock()
    mock_bus = MagicMock()
    mock_watcher = MagicMock()
    mock_chat = MockChatEngine()

    daemon = JulesDaemon(
        router=mock_router,
        persistent_memory=mock_persistent,
        episodic_memory=mock_episodic,
        memory_engine=mock_memory,
        event_bus=mock_bus,
        platform_watcher=mock_watcher,
        chat_engine=mock_chat,
        socket_path=sock_path,
        state_path=state_path,
    )

    # Verify all components are present and wired
    assert daemon.router is mock_router
    assert daemon.persistent_memory is mock_persistent
    assert daemon.episodic_memory is mock_episodic
    assert daemon.memory_engine is mock_memory
    assert daemon.event_bus is mock_bus
    assert daemon.platform_watcher is mock_watcher
    assert daemon.chat_engine is mock_chat
    assert isinstance(daemon.state_publisher, StatePublisher)
    assert isinstance(daemon.ipc_server, IPCServer)
    assert daemon.ipc_server.socket_path == sock_path.resolve()
    assert daemon.state_publisher.target_path == state_path.resolve()
    assert not daemon.is_running


async def test_daemon_lifecycle_start_and_stop(tmp_path: Path) -> None:
    """Test daemon start sets state to IDLE and listens, stop unlinks socket/state."""
    daemon = make_mock_daemon(tmp_path)
    sock_path = daemon.socket_path
    state_path = daemon.state_path

    assert not sock_path.exists()
    assert not state_path.exists()
    assert not daemon.is_running

    # Start daemon
    await daemon.start()
    try:
        assert daemon.is_running
        assert sock_path.exists()
        assert state_path.exists()

        # Check socket permissions 0o600
        mode = sock_path.stat().st_mode & 0o777
        assert mode == 0o600

        # State publisher snapshot should be IDLE
        snapshot = daemon.state_publisher.get_current_state()
        assert snapshot.state == DaemonState.IDLE

        # Connect with IPC client and verify status response
        client = IPCClient(socket_path=sock_path)
        status = await client.get_status()
        assert status.get("status") == "ok"
        assert status.get("state") == "IDLE"
        assert status.get("health") == "healthy"
    finally:
        # Stop daemon
        await daemon.stop()

    # After stop: running is False and runtime files are cleaned up
    assert not daemon.is_running
    assert not sock_path.exists()
    assert not state_path.exists()


# ---------------------------------------------------------------------------
# 2. IPC Handler Wiring Tests (query, ptt, barge_in, shell_event, status)
# ---------------------------------------------------------------------------


async def test_daemon_ipc_query_streaming(tmp_path: Path) -> None:
    """Test IPC query handler routes to ChatEngine.stream_turn and streams events."""
    chat_engine = MockChatEngine(responses=[
        ThoughtEvent(content="Pondering..."),
        ContentEvent(content="Daemon is alive!"),
    ])
    daemon = make_mock_daemon(tmp_path, chat_engine=chat_engine)

    await daemon.start()
    try:
        client = IPCClient(socket_path=daemon.socket_path)
        events = []
        async for ev in client.stream_query("Test input", session_id="test_sess"):
            events.append(ev)

        assert len(events) == 2
        assert isinstance(events[0], ThoughtEvent)
        assert events[0].content == "Pondering..."
        assert isinstance(events[1], ContentEvent)
        assert events[1].content == "Daemon is alive!"

        # Query recorded in chat engine
        assert len(chat_engine.received_queries) == 1
        assert chat_engine.received_queries[0]["user_input"] == "Test input"

        # Daemon state should return to IDLE after query completes
        assert daemon.state_publisher.get_current_state().state == DaemonState.IDLE
    finally:
        await daemon.stop()


async def test_daemon_ipc_voice_ptt_toggle(tmp_path: Path) -> None:
    """Test IPC voice_ptt_toggle toggles state between LISTENING and IDLE."""
    daemon = make_mock_daemon(tmp_path)
    await daemon.start()
    try:
        client = IPCClient(socket_path=daemon.socket_path)
        assert daemon.state_publisher.get_current_state().state == DaemonState.IDLE

        # Toggle PTT on -> LISTENING
        resp1 = await client.toggle_ptt()
        assert resp1.get("status") == "ok"
        assert daemon.state_publisher.get_current_state().state == DaemonState.LISTENING

        # Toggle PTT off -> IDLE
        resp2 = await client.toggle_ptt()
        assert resp2.get("status") == "ok"
        assert daemon.state_publisher.get_current_state().state == DaemonState.IDLE
    finally:
        await daemon.stop()


async def test_daemon_ipc_voice_barge_in(tmp_path: Path) -> None:
    """Test IPC voice_barge_in sets state back to IDLE."""
    daemon = make_mock_daemon(tmp_path)
    await daemon.start()
    try:
        client = IPCClient(socket_path=daemon.socket_path)
        daemon.state_publisher.update_state(DaemonState.SPEAKING)
        assert daemon.state_publisher.get_current_state().state == DaemonState.SPEAKING

        resp = await client.barge_in()
        assert resp.get("status") == "ok"
        assert resp.get("barge_in") is True
        assert daemon.state_publisher.get_current_state().state == DaemonState.IDLE
    finally:
        await daemon.stop()


async def test_daemon_ipc_shell_event(tmp_path: Path) -> None:
    """Test IPC shell_event updates session context and exits codes safely."""
    daemon = make_mock_daemon(tmp_path)
    await daemon.start()
    try:
        client = IPCClient(socket_path=daemon.socket_path)

        resp = await client.send_shell_event(
            phase="precmd",
            cmd="cargo build",
            exit_code=1,
            cwd=str(tmp_path),
            duration_ms=250.0,
        )
        assert resp.get("status") == "ok"
        assert resp.get("handled") is True

        assert daemon.session_context.last_exit_code == 1
        assert "cargo build" in daemon.session_context.recent_commands
    finally:
        await daemon.stop()


# ---------------------------------------------------------------------------
# 3. Signal Handling and Graceful Shutdown Tests
# ---------------------------------------------------------------------------


async def test_daemon_run_forever_signal_handling(tmp_path: Path) -> None:
    """Test run_forever exits cleanly when receiving SIGTERM/SIGINT."""
    daemon = make_mock_daemon(tmp_path)

    run_task = asyncio.create_task(daemon.run_forever())
    # Wait until daemon is running
    for _ in range(50):
        if daemon.is_running:
            break
        await asyncio.sleep(0.01)

    assert daemon.is_running

    # Trigger shutdown event via daemon.stop_requested or signal simulation
    daemon.request_stop()
    await asyncio.wait_for(run_task, timeout=2.0)

    assert not daemon.is_running
    assert not daemon.socket_path.exists()
    assert not daemon.state_path.exists()


# ---------------------------------------------------------------------------
# 4. Systemd Service Generator Tests
# ---------------------------------------------------------------------------


def test_install_systemd_user_service(tmp_path: Path) -> None:
    """Test install_systemd_user_service generates valid jules.service file."""
    service_path = install_systemd_user_service(target_dir=tmp_path)

    assert service_path == tmp_path / "jules.service"
    assert service_path.exists()

    content = service_path.read_text(encoding="utf-8")

    # Assert Unit metadata
    assert "[Unit]" in content
    assert "Description=" in content
    assert "Documentation=" in content
    assert "After=network.target" in content

    # Assert Service section
    assert "[Service]" in content
    assert "Type=simple" in content
    assert "ExecStart=" in content
    assert "daemon start" in content
    assert sys.executable in content
    assert "Restart=on-failure" in content

    # Assert Install section
    assert "[Install]" in content
    assert "WantedBy=default.target" in content

    # Assert non-systemd fallback notes (Alpine, Void)
    assert "Alpine" in content or "OpenRC" in content
    assert "Void" in content or "runit" in content


# ---------------------------------------------------------------------------
# 5. CLI Daemon Commands Tests (start, status, install, ask)
# ---------------------------------------------------------------------------


def test_cli_daemon_install(tmp_path: Path) -> None:
    """Test 'jules daemon install --path ...' writes service and outputs confirmation."""
    runner = CliRunner()
    result = runner.invoke(cli_main.cli, ["daemon", "install", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / "jules.service").exists()
    assert "systemctl --user daemon-reload" in result.output


def test_cli_daemon_status_when_offline(tmp_path: Path) -> None:
    """Test 'jules daemon status' when daemon is not running."""
    non_existent_sock = tmp_path / "nonexistent.sock"
    runner = CliRunner()

    result = runner.invoke(cli_main.cli, ["daemon", "status", "--socket", str(non_existent_sock)])
    assert result.exit_code != 0
    assert "offline" in result.output.lower() or "not running" in result.output.lower()

    # With --json
    result_json = runner.invoke(
        cli_main.cli,
        ["daemon", "status", "--socket", str(non_existent_sock), "--json"],
    )
    assert result_json.exit_code != 0
    parsed = json.loads(result_json.output)
    assert parsed.get("status") in ("offline", "stopped", "error")


class RunningDaemonContext:
    """Run a JulesDaemon concurrently in a dedicated thread to test CLI interactions."""

    def __init__(self, daemon: JulesDaemon) -> None:
        import threading
        self.daemon = daemon
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.daemon.start())
        self.loop.run_forever()

    def __enter__(self) -> JulesDaemon:
        import time
        self.thread.start()
        start_time = time.time()
        while not self.daemon.is_running:
            if time.time() - start_time > 3.0:
                raise TimeoutError("Daemon failed to start in background thread")
            time.sleep(0.01)
        return self.daemon

    def __exit__(self, exc_type: any, exc_val: any, exc_tb: any) -> None:
        future = asyncio.run_coroutine_threadsafe(self.daemon.stop(), self.loop)
        future.result(timeout=3.0)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=3.0)


def test_cli_daemon_status_when_online(tmp_path: Path) -> None:
    """Test 'jules daemon status' when daemon is running."""
    daemon = make_mock_daemon(tmp_path)

    with RunningDaemonContext(daemon):
        runner = CliRunner()

        # Human readable
        res = runner.invoke(cli_main.cli, ["daemon", "status", "--socket", str(daemon.socket_path)])
        assert res.exit_code == 0
        assert "IDLE" in res.output

        # JSON format
        res_json = runner.invoke(
            cli_main.cli,
            ["daemon", "status", "--socket", str(daemon.socket_path), "--json"],
        )
        assert res_json.exit_code == 0
        parsed = json.loads(res_json.output)
        assert parsed.get("status") == "ok"
        assert parsed.get("state") == "IDLE"


def test_cli_ask_when_online(tmp_path: Path) -> None:
    """Test 'jules ask <text>' routes via IPCClient and streams response."""
    chat_engine = MockChatEngine(responses=[
        ThoughtEvent(content="Thinking..."),
        ContentEvent(content="Hello, Esteban!"),
    ])
    daemon = make_mock_daemon(tmp_path, chat_engine=chat_engine)

    with RunningDaemonContext(daemon):
        runner = CliRunner()
        res = runner.invoke(cli_main.cli, ["ask", "Hello Jules", "--socket", str(daemon.socket_path)])
        assert res.exit_code == 0
        assert "Hello, Esteban!" in res.output


def test_cli_ask_when_offline(tmp_path: Path) -> None:
    """Test 'jules ask <text>' handles daemon offline gracefully."""
    non_existent_sock = tmp_path / "nonexistent.sock"
    runner = CliRunner()

    res = runner.invoke(cli_main.cli, ["ask", "Hello Jules", "--socket", str(non_existent_sock)])
    assert res.exit_code != 0
    assert "daemon" in res.output.lower()
    assert "start" in res.output.lower() or "offline" in res.output.lower()
