"""Tool availability panel."""

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Static  # type: ignore[import-not-found]


class ToolsPanel(Widget):
    def compose(self) -> ComposeResult:
        yield Static("HERRAMIENTAS", classes="panel-header")
        yield Static("• filesystem   ✓\n• terminal     ✓\n• git          ✓\n• search       ✓\n• web          ○", classes="panel-section")
