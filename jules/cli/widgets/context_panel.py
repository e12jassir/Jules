"""Project context panel."""

import asyncio
from pathlib import Path
import subprocess

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Static  # type: ignore[import-not-found]


class ContextPanel(Widget):
    def compose(self) -> ComposeResult:
        project = Path.cwd().name
        branch = "---"
        yield Static("CONTEXTO", classes="panel-header")
        yield Static(f"📁 Proyecto   ~/{project}\n⎇  Rama       {branch}\n📄 Archivos   ---", classes="panel-section")

    async def on_mount(self) -> None:
        try:
            branch = await asyncio.to_thread(_branch)
            self.query_one(".panel-section", Static).update(
                f"📁 Proyecto   ~/{Path.cwd().name}\n⎇  Rama       {branch}\n📄 Archivos   ---"
            )
        except Exception:
            pass


def _branch() -> str:
    try:
        result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, timeout=0.2)
    except (OSError, subprocess.SubprocessError):
        return "---"
    return result.stdout.strip() or "---"
