"""Status bar widget for the Jules Textual TUI."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import subprocess

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.containers import Horizontal  # type: ignore[import-not-found]
from textual.message import Message  # type: ignore[import-not-found]
from textual.reactive import reactive  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Static  # type: ignore[import-not-found]


class StatusBar(Widget):
    """Bottom status bar with project, branch, key bindings, and clock."""

    class DoctorResult(Message):
        """Doctor result notification used to show degraded state."""

        def __init__(self, issues: list[str]) -> None:
            super().__init__()
            self.issues = issues

    cwd = reactive(str(Path.cwd()))
    branch = reactive("---")
    status = reactive("● conectado")
    now = reactive("--:--")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(id="status-left", classes="status-left")
            yield Static("ctrl+t variantes  tab agentes  ctrl+p comandos  ctrl+h ayuda", id="status-center", classes="status-center")
            yield Static(id="status-right", classes="status-right")

    def on_mount(self) -> None:
        self._tick()
        self.set_interval(1.0, self._tick)
        self._refresh_labels()
        self.run_worker(self.refresh_branch())

    async def refresh_branch(self) -> None:
        """Re-read the git branch asynchronously and update the reactive."""
        try:
            branch = await asyncio.to_thread(_current_branch)
            self.branch = branch
        except Exception:  # noqa: BLE001
            pass

    def set_generating(self, generating: bool) -> None:
        self.status = "● generando..." if generating else "● Auto-saved"
        self._refresh_labels()

    def on_status_bar_doctor_result(self, message: DoctorResult) -> None:
        self.status = f"⚠ {len(message.issues)} problema(s)" if message.issues else "● conectado"
        self._refresh_labels()

    def watch_cwd(self, _value: str) -> None:
        self._refresh_labels()

    def watch_branch(self, _value: str) -> None:
        self._refresh_labels()

    def watch_status(self, _value: str) -> None:
        self._refresh_labels()

    def watch_now(self, _value: str) -> None:
        self._refresh_labels()

    def _tick(self) -> None:
        self.now = datetime.now().strftime("%H:%M")

    def _refresh_labels(self) -> None:
        if not self.is_mounted:
            return
        display_cwd = _short_home(self.cwd)
        self.query_one("#status-left", Static).update(f"{display_cwd}  ⎇ {self.branch}  {self.status}")
        self.query_one("#status-right", Static).update(f"{self.now}  🌹")


def _current_branch() -> str:
    try:
        result = subprocess.run(["git", "branch", "--show-current"], check=False, capture_output=True, text=True, timeout=0.2)
    except (OSError, subprocess.SubprocessError):
        return "---"
    return result.stdout.strip() or "---"


def _short_home(path: str) -> str:
    home = str(Path.home())
    return path.replace(home, "~", 1) if path.startswith(home) else path
