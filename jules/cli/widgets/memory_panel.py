"""Memory counters panel."""

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Static  # type: ignore[import-not-found]


class MemoryPanel(Widget):
    def compose(self) -> ComposeResult:
        yield Static("MEMORIA", classes="panel-header")
        yield Static("⏱ Episodios   0\n⏱ Hechos      0\n⏱ Recuerdos   0\n> Ver memoria", id="memory-status", classes="panel-section")

    def update_counts(self, episodes: int, facts: int = 0, memories: int = 0) -> None:
        self.query_one("#memory-status", Static).update(
            f"⏱ Episodios   {episodes}\n⏱ Hechos      {facts}\n⏱ Recuerdos   {memories}\n> Ver memoria"
        )

    def set_degraded(self, reason: str) -> None:
        self.query_one("#memory-status", Static).update(f"⚠ {reason}\n> Ver memoria")
