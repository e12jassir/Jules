"""Active model panel."""

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.reactive import reactive  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Static  # type: ignore[import-not-found]


class ModelPanel(Widget):
    context_size: reactive[str] = reactive("---")

    _last_model: str = "---"
    _last_provider: str = "---"
    _last_state: str = "online"

    def compose(self) -> ComposeResult:
        yield Static("MODELO ACTIVO", classes="panel-header")
        yield Static("---        ● online\n--- ∨", id="model-status", classes="panel-section online")

    def update_model(self, model: str, provider: str, online: bool = True) -> None:
        state = "online" if online else "offline"
        dot = "●"
        self._last_model = model
        self._last_provider = provider
        self._last_state = state
        self.query_one("#model-status", Static).update(f"{provider}        {dot} {state}\n{model} ∨")

    def set_context_size(self, size: str) -> None:
        self.context_size = size
        self._refresh_display()

    def _refresh_display(self) -> None:
        try:
            dot = "●"
            self.query_one("#model-status", Static).update(
                f"{self._last_provider}        {dot} {self._last_state}\n{self._last_model} ∨"
            )
        except Exception:  # noqa: BLE001
            pass
