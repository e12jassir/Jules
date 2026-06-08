"""Integration tests for the Jules IPC server — spawns subprocess, exchanges JSON."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
PYTHON = sys.executable
TIMEOUT = 15


def _spawn_server() -> subprocess.Popen:
    return subprocess.Popen(
        [PYTHON, "-m", "jules.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(PROJECT_ROOT),
    )


def _send(proc: subprocess.Popen, msg: dict) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(msg) + "\n").encode())
    proc.stdin.flush()


def _recv(proc: subprocess.Popen, timeout: float = TIMEOUT) -> dict:
    """Read one JSON line from server stdout."""
    assert proc.stdout is not None
    import select

    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        raise TimeoutError("No response from server within timeout")
    line = proc.stdout.readline()
    if not line:
        raise EOFError("Server closed stdout")
    return json.loads(line.decode())


def _recv_until_type(proc: subprocess.Popen, target_type: str, timeout: float = TIMEOUT) -> list[dict]:
    """Read lines until we see target_type or timeout."""
    messages: list[dict] = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msg = _recv(proc, timeout=deadline - time.time())
            messages.append(msg)
            if msg.get("type") == target_type:
                return messages
        except (TimeoutError, EOFError):
            break
    return messages


class TestServerIpc:
    def test_message_produces_tokens_and_done(self):
        """Send message → receive at least one token or error event → then done."""
        proc = _spawn_server()
        try:
            _send(proc, {"type": "message", "content": "hello"})
            messages = _recv_until_type(proc, "done")
            types = [m["type"] for m in messages]

            assert "done" in types, f"Expected 'done' event, got: {types}"
            # Must have received at least one substantive event before done
            pre_done = types[: types.index("done")]
            assert any(t in pre_done for t in ("token", "thought", "error")), (
                f"Expected token/thought/error before 'done', got: {pre_done}"
            )
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_model_list_returns_models(self):
        """Send model_list → receive model_list with non-empty models list."""
        proc = _spawn_server()
        try:
            _send(proc, {"type": "model_list"})
            resp = _recv(proc)
            assert resp["type"] == "model_list"
            assert isinstance(resp["models"], list)
            assert len(resp["models"]) > 0
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_quit_exits_cleanly(self):
        """Send quit → process exits with code 0."""
        proc = _spawn_server()
        try:
            _send(proc, {"type": "quit"})
            exit_code = proc.wait(timeout=5)
            assert exit_code == 0
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)

    def test_malformed_json_returns_error_server_stays_alive(self):
        """Send malformed JSON → receive error event, server stays alive."""
        proc = _spawn_server()
        try:
            # Send garbage
            assert proc.stdin is not None
            proc.stdin.write(b"not json at all\n")
            proc.stdin.flush()

            resp = _recv(proc)
            assert resp["type"] == "error"
            assert resp["recoverable"] is True

            # Server should still be alive — send quit to verify
            _send(proc, {"type": "quit"})
            exit_code = proc.wait(timeout=5)
            assert exit_code == 0
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
