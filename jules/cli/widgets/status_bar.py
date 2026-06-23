"""Minimal status bar — provider:model left, cursor/writing right."""

from __future__ import annotations

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.containers import Horizontal  # type: ignore[import-not-found]
from textual.message import Message  # type: ignore[import-not-found]
from textual.reactive import reactive  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Static  # type: ignore[import-not-found]


class StatusBar(Widget):
    """Minimal status bar — provider:model left, cursor/writing right."""

    class DoctorResult(Message):
        def __init__(self, issues: list[str]) -> None:
            super().__init__()
            self.issues = issues

    active_model = reactive("---")
    is_streaming = reactive(False)
    input_focused = reactive(False)

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(id="status-left", classes="status-left")
            yield Static(id="status-right", classes="status-right")

    def on_mount(self) -> None:
        self._refresh_labels()

    def set_generating(self, generating: bool) -> None:
        self.is_streaming = generating
        self._refresh_labels()

    def set_active_model(self, model: str) -> None:
        self.active_model = model
        self._refresh_labels()

    def on_status_bar_doctor_result(self, message: DoctorResult) -> None:
        self._refresh_labels()

    def watch_active_model(self, _value: str) -> None:
        self._refresh_labels()

    def watch_is_streaming(self, _value: bool) -> None:
        self._refresh_labels()

    def watch_input_focused(self, _value: bool) -> None:
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#status-left", Static).update(self.active_model)
        if self.is_streaming:
            right = "● escribiendo…"
        elif self.input_focused:
            right = "▎ cursor"
        else:
            right = ""
        self.query_one("#status-right", Static).update(right)
