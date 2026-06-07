"""Session statistics panel."""

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Static  # type: ignore[import-not-found]


class StatsPanel(Widget):
    def compose(self) -> ComposeResult:
        yield Static("ESTADÍSTICAS", classes="panel-header")
        yield Static("Tokens usados   0\nCosto sesión    ---\nTiempo sesión   00:00:00", id="stats-status", classes="panel-section")

    def update_stats(self, tokens: int, cost: float | None, session_time: str) -> None:
        cost_text = "---" if cost is None else f"${cost:.4f}"
        self.query_one("#stats-status", Static).update(
            f"Tokens usados   {tokens:,}\nCosto sesión    {cost_text}\nTiempo sesión   {session_time}"
        )
