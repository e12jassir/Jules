"""
Smoke tests for the Rust TUI binary.

Covers:
- Startup budget: Python IPC server must emit `ready` within 500ms (spec: backend ≤500ms).
- Degraded mode: TUI binary must exit non-zero and emit an error when the child server fails.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
PYTHON = sys.executable
TUI_BINARY = PROJECT_ROOT / "jules-tui" / "target" / "release" / "jules-tui"

BACKEND_STARTUP_BUDGET_MS = 500.0


@pytest.fixture(scope="module")
def tui_binary_exists():
    if not TUI_BINARY.exists():
        pytest.skip(f"Rust TUI binary not found at {TUI_BINARY}. Run `cargo build --release` first.")


class TestIpcServerStartupBudget:
    """Verify the Python IPC backend emits `ready` within the spec budget."""

    def test_server_ready_within_500ms(self):
        """Spec: backend ≤500ms to emit ready after receiving init."""
        proc = subprocess.Popen(
            [PYTHON, "-m", "jules.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )
        try:
            assert proc.stdin and proc.stdout
            init_msg = json.dumps({"type": "init", "protocol_version": 1}) + "\n"

            t0 = time.perf_counter()
            proc.stdin.write(init_msg.encode())
            proc.stdin.flush()

            import select
            ready_sel, _, _ = select.select([proc.stdout], [], [], BACKEND_STARTUP_BUDGET_MS / 1000)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            assert ready_sel, (
                f"Server did not respond within {BACKEND_STARTUP_BUDGET_MS}ms (elapsed: {elapsed_ms:.1f}ms)"
            )

            line = proc.stdout.readline()
            msg = json.loads(line.decode())

            assert msg["type"] == "ready", f"Expected 'ready', got: {msg}"
            assert elapsed_ms < BACKEND_STARTUP_BUDGET_MS, (
                f"Backend startup budget exceeded: {elapsed_ms:.1f}ms > {BACKEND_STARTUP_BUDGET_MS}ms"
            )
        finally:
            proc.terminate()
            proc.wait(timeout=5)


class TestTuiDegradedMode:
    """Verify the TUI binary handles a failing/absent child server gracefully."""

    @pytest.mark.xfail(
        reason=(
            "TUI calls enable_raw_mode() on startup which requires a real TTY. "
            "A proper degraded-mode assertion test needs a headless/PTY mode in the binary. "
            "The error path IS wired (ChildExited event in main.rs), but cannot be driven "
            "from a subprocess without a terminal. Track in a follow-up task."
        ),
        strict=False,
    )
    def test_degraded_mode_server_immediate_exit(self, tui_binary_exists):
        """
        Launch jules-tui with a fake server that exits immediately (code 1).
        The TUI must exit non-zero — confirming ChildExited error path fires.
        """
        fake_python = (
            f"{PYTHON} -c \"import sys; sys.exit(1)\""
        )
        proc = subprocess.Popen(
            [str(TUI_BINARY)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                **__import__("os").environ,
                "JULES_PYTHON": fake_python,
            },
        )
        try:
            exit_code = proc.wait(timeout=10)
            assert exit_code != 0, (
                "Expected TUI to exit non-zero when child server exits immediately"
            )
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("TUI did not exit within 10s when child server exited immediately")
