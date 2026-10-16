"""Tests for shell hooks, IPC emission, silent failure guarantee, and daemon context updating."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import socket
import subprocess
from typing import AsyncIterator
import pytest
import pytest_asyncio

from jules.core.context import ContextEngine
from jules.core.session import SessionContext
from jules.daemon.ipc import IPCClient, IPCServer
from jules.daemon.service import JulesDaemon
from jules.platform.shell import (
    BASH_HOOKS_BLOCK,
    FISH_HOOKS_BLOCK,
    ZSH_HOOKS_BLOCK,
)
from jules.sanitizer import Sanitizer


# ---------------------------------------------------------------------------
# Requirement 2(a): Hook script generation checks
# ---------------------------------------------------------------------------


def test_bash_hooks_block_structure() -> None:
    """Verify bash hooks include non-blocking background emission to unix socket."""
    assert "-S" in BASH_HOOKS_BLOCK
    assert "/run/user" in BASH_HOOKS_BLOCK or "XDG_RUNTIME_DIR" in BASH_HOOKS_BLOCK
    assert "jules.sock" in BASH_HOOKS_BLOCK
    assert ".jules/run/jules.sock" in BASH_HOOKS_BLOCK
    assert ">/dev/null 2>&1" in BASH_HOOKS_BLOCK
    assert "shell_event" in BASH_HOOKS_BLOCK
    assert "_jules_precmd" in BASH_HOOKS_BLOCK
    assert "_jules_preexec" in BASH_HOOKS_BLOCK
    # Ensure TODO is completely removed
    assert "TODO" not in BASH_HOOKS_BLOCK


def test_zsh_hooks_block_structure() -> None:
    """Verify zsh hooks include non-blocking background emission to unix socket."""
    assert "-S" in ZSH_HOOKS_BLOCK
    assert "/run/user" in ZSH_HOOKS_BLOCK or "XDG_RUNTIME_DIR" in ZSH_HOOKS_BLOCK
    assert "jules.sock" in ZSH_HOOKS_BLOCK
    assert ".jules/run/jules.sock" in ZSH_HOOKS_BLOCK
    assert ">/dev/null 2>&1" in ZSH_HOOKS_BLOCK
    assert "shell_event" in ZSH_HOOKS_BLOCK
    assert "_jules_precmd" in ZSH_HOOKS_BLOCK
    assert "_jules_preexec" in ZSH_HOOKS_BLOCK
    assert "TODO" not in ZSH_HOOKS_BLOCK


def test_fish_hooks_block_structure() -> None:
    """Verify fish hooks include non-blocking background emission to unix socket."""
    assert "test -S" in FISH_HOOKS_BLOCK or "-S" in FISH_HOOKS_BLOCK
    assert "/run/user" in FISH_HOOKS_BLOCK or "XDG_RUNTIME_DIR" in FISH_HOOKS_BLOCK
    assert "jules.sock" in FISH_HOOKS_BLOCK
    assert ".jules/run/jules.sock" in FISH_HOOKS_BLOCK
    assert ">/dev/null 2>&1" in FISH_HOOKS_BLOCK
    assert "shell_event" in FISH_HOOKS_BLOCK
    assert "_jules_precmd" in FISH_HOOKS_BLOCK
    assert "_jules_preexec" in FISH_HOOKS_BLOCK
    assert "TODO" not in FISH_HOOKS_BLOCK


# ---------------------------------------------------------------------------
# Requirement 2(b): Silent failure / zero-overhead guarantee
# ---------------------------------------------------------------------------


def test_silent_failure_when_daemon_offline_bash(tmp_path: Path) -> None:
    """When socket does not exist, executing bash hooks returns 0 and produces no output."""
    nonexistent_dir = tmp_path / "nonexistent"
    env = {
        **os.environ,
        "XDG_RUNTIME_DIR": str(nonexistent_dir),
        "HOME": str(tmp_path / "home"),
    }
    snippet = f"""
{BASH_HOOKS_BLOCK}
_jules_preexec "ls -la"
(exit 42)
_jules_precmd
"""
    proc = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
        env=env,
        timeout=2,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
def test_silent_failure_when_daemon_offline_zsh(tmp_path: Path) -> None:
    """When socket does not exist, executing zsh hooks returns 0 and produces no output."""
    nonexistent_dir = tmp_path / "nonexistent"
    env = {
        **os.environ,
        "XDG_RUNTIME_DIR": str(nonexistent_dir),
        "HOME": str(tmp_path / "home"),
    }
    snippet = f"""
{ZSH_HOOKS_BLOCK}
_jules_preexec "ls -la"
(exit 42)
_jules_precmd
"""
    proc = subprocess.run(
        ["zsh", "-c", snippet],
        capture_output=True,
        text=True,
        env=env,
        timeout=2,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""


@pytest.mark.skipif(not shutil.which("fish"), reason="fish not installed")
def test_silent_failure_when_daemon_offline_fish(tmp_path: Path) -> None:
    """When socket does not exist, executing fish hooks returns 0 and produces no output."""
    nonexistent_dir = tmp_path / "nonexistent"
    env = {
        **os.environ,
        "XDG_RUNTIME_DIR": str(nonexistent_dir),
        "HOME": str(tmp_path / "home"),
    }
    snippet = f"""
{FISH_HOOKS_BLOCK}
_jules_preexec "ls -la"
_jules_precmd
"""
    proc = subprocess.run(
        ["fish", "-c", snippet],
        capture_output=True,
        text=True,
        env=env,
        timeout=2,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""


def test_silent_failure_when_socket_file_is_stale(tmp_path: Path) -> None:
    """When socket file exists but nobody is listening, hooks exit 0 with no stdout/stderr."""
    sock_path = tmp_path / "jules.sock"
    # Create dead socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(str(sock_path))
    s.close()

    env = {
        **os.environ,
        "XDG_RUNTIME_DIR": str(tmp_path),
        "HOME": str(tmp_path),
    }
    snippet = f"""
{BASH_HOOKS_BLOCK}
_jules_preexec "test command"
_jules_precmd
"""
    proc = subprocess.run(
        ["bash", "-c", snippet],
        capture_output=True,
        text=True,
        env=env,
        timeout=2,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""


# ---------------------------------------------------------------------------
# Requirement 2(c): Daemon event processing & session context update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daemon_shell_event_updates_session_context(tmp_path: Path) -> None:
    """Shell events sent over IPC update cwd, last_exit_code, and recent_commands."""
    sock_path = tmp_path / "jules.sock"
    state_path = tmp_path / "jules.state"

    daemon = JulesDaemon(
        socket_path=sock_path,
        state_path=state_path,
        current_directory="/initial/dir",
    )
    await daemon.start()

    try:
        client = IPCClient(socket_path=sock_path)

        # 1. Send preexec event for a build command
        res1 = await client.send_shell_event(
            phase="preexec",
            cmd="cargo build --release",
            cwd="/workspace/project",
        )
        assert res1["status"] == "ok"
        assert daemon.session_context.cwd == "/workspace/project"
        assert "cargo build --release" in daemon.session_context.recent_commands

        # 2. Send precmd event with error exit code
        res2 = await client.send_shell_event(
            phase="precmd",
            cmd="",
            exit_code=101,
            cwd="/workspace/project",
        )
        assert res2["status"] == "ok"
        assert daemon.session_context.last_exit_code == 101

        # Check intent inference reflects failure (debugging)
        assert ContextEngine._infer_intent(daemon.session_context) == "debugging"

        # 3. Send successful learning command
        await client.send_shell_event(
            phase="preexec",
            cmd="man cargo",
            cwd="/workspace/project",
        )
        await client.send_shell_event(
            phase="precmd",
            cmd="",
            exit_code=0,
            cwd="/workspace/project",
        )
        assert daemon.session_context.last_exit_code == 0
        assert ContextEngine._infer_intent(daemon.session_context) == "learning"

    finally:
        await daemon.stop()


# ---------------------------------------------------------------------------
# Requirement 2(d): Security - sensitive command stripped / blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daemon_shell_event_blocks_sensitive_commands(tmp_path: Path) -> None:
    """Commands containing secrets are blocked by Sanitizer and never stored in session context."""
    sock_path = tmp_path / "jules.sock"
    state_path = tmp_path / "jules.state"

    daemon = JulesDaemon(
        socket_path=sock_path,
        state_path=state_path,
    )
    await daemon.start()

    try:
        client = IPCClient(socket_path=sock_path)

        sensitive_commands = [
            "export OPENAI_API_KEY=sk-abcdef1234567890abcdef1234567890",
            "curl -H 'Authorization: Bearer secret_token_xyz123' https://api.service.com",
            "git clone https://username:password123@github.com/repo.git",
        ]

        for secret_cmd in sensitive_commands:
            res = await client.send_shell_event(
                phase="preexec",
                cmd=secret_cmd,
                cwd="/safe/dir",
            )
            assert res.get("status") == "blocked"
            assert res.get("blocked") is True
            # Must NOT be in recent_commands
            assert secret_cmd not in daemon.session_context.recent_commands

        # Send a normal safe command
        safe_res = await client.send_shell_event(
            phase="preexec",
            cmd="pytest tests/",
            cwd="/safe/dir",
        )
        assert safe_res.get("status") == "ok"
        assert "pytest tests/" in daemon.session_context.recent_commands
        assert len(daemon.session_context.recent_commands) == 1

    finally:
        await daemon.stop()


# ---------------------------------------------------------------------------
# Live shell script execution emitting to daemon
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_bash_hooks_emit_to_daemon(tmp_path: Path) -> None:
    """Executing actual bash hooks sends events to a live JulesDaemon."""
    sock_path = tmp_path / "jules.sock"
    state_path = tmp_path / "jules.state"

    daemon = JulesDaemon(
        socket_path=sock_path,
        state_path=state_path,
        current_directory=str(tmp_path),
    )
    await daemon.start()

    try:
        env = {
            **os.environ,
            "XDG_RUNTIME_DIR": str(tmp_path),
            "HOME": str(tmp_path),
        }
        snippet = f"""
{BASH_HOOKS_BLOCK}
_jules_preexec "pytest -v"
(exit 1)
_jules_precmd
"""
        proc = subprocess.run(
            ["bash", "-c", snippet],
            capture_output=True,
            text=True,
            env=env,
            timeout=3,
        )
        assert proc.returncode == 0

        # Wait for background non-blocking emission to arrive
        for _ in range(20):
            if "pytest -v" in daemon.session_context.recent_commands:
                break
            await asyncio.sleep(0.1)

        assert "pytest -v" in daemon.session_context.recent_commands
        assert daemon.session_context.last_exit_code == 1
        assert ContextEngine._infer_intent(daemon.session_context) == "debugging"

    finally:
        await daemon.stop()


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh not installed")
@pytest.mark.asyncio
async def test_live_zsh_hooks_emit_to_daemon(tmp_path: Path) -> None:
    """Executing actual zsh hooks sends events to a live JulesDaemon."""
    sock_path = tmp_path / "jules.sock"
    state_path = tmp_path / "jules.state"

    daemon = JulesDaemon(
        socket_path=sock_path,
        state_path=state_path,
        current_directory=str(tmp_path),
    )
    await daemon.start()

    try:
        env = {
            **os.environ,
            "XDG_RUNTIME_DIR": str(tmp_path),
            "HOME": str(tmp_path),
        }
        snippet = f"""
{ZSH_HOOKS_BLOCK}
_jules_preexec "npm test"
(exit 2)
_jules_precmd
"""
        proc = subprocess.run(
            ["zsh", "-c", snippet],
            capture_output=True,
            text=True,
            env=env,
            timeout=3,
        )
        assert proc.returncode == 0

        for _ in range(20):
            if "npm test" in daemon.session_context.recent_commands:
                break
            await asyncio.sleep(0.1)

        assert "npm test" in daemon.session_context.recent_commands
        assert daemon.session_context.last_exit_code == 2
        assert ContextEngine._infer_intent(daemon.session_context) == "debugging"

    finally:
        await daemon.stop()


@pytest.mark.skipif(not shutil.which("fish"), reason="fish not installed")
@pytest.mark.asyncio
async def test_live_fish_hooks_emit_to_daemon(tmp_path: Path) -> None:
    """Executing actual fish hooks sends events to a live JulesDaemon."""
    sock_path = tmp_path / "jules.sock"
    state_path = tmp_path / "jules.state"

    daemon = JulesDaemon(
        socket_path=sock_path,
        state_path=state_path,
        current_directory=str(tmp_path),
    )
    await daemon.start()

    try:
        env = {
            **os.environ,
            "XDG_RUNTIME_DIR": str(tmp_path),
            "HOME": str(tmp_path),
        }
        snippet = f"""
{FISH_HOOKS_BLOCK}
_jules_preexec "cargo test"
_jules_precmd
"""
        proc = subprocess.run(
            ["fish", "-c", snippet],
            capture_output=True,
            text=True,
            env=env,
            timeout=3,
        )
        assert proc.returncode == 0

        for _ in range(20):
            if "cargo test" in daemon.session_context.recent_commands:
                break
            await asyncio.sleep(0.1)

        assert "cargo test" in daemon.session_context.recent_commands
        assert daemon.session_context.last_exit_code == 0

    finally:
        await daemon.stop()


@pytest.mark.asyncio
async def test_daemon_direct_shell_event_sanitizer() -> None:
    """Direct call to JulesDaemon._handle_shell_event enforces Sanitizer check."""
    daemon = JulesDaemon()
    res = await daemon._handle_shell_event({
        "cmd": "export SECRET_TOKEN=supersecretvalue123",
        "phase": "preexec",
    })
    assert res["status"] == "blocked"
    assert res["blocked"] is True
    assert "export SECRET_TOKEN=supersecretvalue123" not in daemon.session_context.recent_commands

