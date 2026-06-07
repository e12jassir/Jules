"""Right sidebar composed from static PR2 panels."""

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.containers import VerticalScroll  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]

from jules.cli.widgets.context_panel import ContextPanel  # type: ignore[import-not-found]
from jules.cli.widgets.memory_panel import MemoryPanel  # type: ignore[import-not-found]
from jules.cli.widgets.model_panel import ModelPanel  # type: ignore[import-not-found]
from jules.cli.widgets.stats_panel import StatsPanel  # type: ignore[import-not-found]
from jules.cli.widgets.tools_panel import ToolsPanel  # type: ignore[import-not-found]


class Sidebar(Widget):
    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="sidebar"):
            yield ContextPanel()
            yield ModelPanel()
            yield MemoryPanel()
            yield ToolsPanel()
            yield StatsPanel()
