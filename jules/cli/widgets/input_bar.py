"""Input widget for chat messages and slash commands."""

from __future__ import annotations

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.message import Message  # type: ignore[import-not-found]
from textual.widget import Widget  # type: ignore[import-not-found]
from textual.widgets import Input, OptionList  # type: ignore[import-not-found]

from jules.cli.commands import SlashCommand, parse_slash_command  # type: ignore[import-not-found]


class _ChatInput(Input):
    """Input that forwards up/down/escape to the overlay when it is visible."""

    def _overlay(self) -> OptionList | None:
        try:
            overlay = self.screen.query_one("#cmd-overlay", OptionList)
            return overlay if overlay.display else None
        except Exception:
            return None

    def on_key(self, event) -> None:  # type: ignore[override]
        overlay = self._overlay()
        if overlay is None:
            return
        if event.key == "escape":
            overlay.display = False
            event.prevent_default()
            event.stop()
        elif event.key in ("up", "down"):
            count = overlay.option_count
            if count == 0:
                return
            current = overlay.highlighted or 0
            if event.key == "up":
                overlay.highlighted = (current - 1) % count
            else:
                overlay.highlighted = (current + 1) % count
            event.prevent_default()
            event.stop()


class InputBar(Widget):
    """Single-line input wrapper for PR2; multiline growth lands later."""

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    class CommandSubmitted(Message):
        def __init__(self, command: SlashCommand) -> None:
            super().__init__()
            self.command = command

    def compose(self) -> ComposeResult:
        yield _ChatInput(placeholder="> Escribe tu mensaje o usa / para comandos...", id="chat-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        event.input.value = ""
        if not value:
            return
        command = parse_slash_command(value)
        if command is not None:
            self.post_message(self.CommandSubmitted(command))
            return
        self.post_message(self.Submitted(value))

    def disable(self) -> None:
        inp = self.query_one("#chat-input", Input)
        inp.placeholder = "● generando..."
        inp.disabled = True

    def enable(self) -> None:
        inp = self.query_one("#chat-input", Input)
        inp.placeholder = "> Escribe tu mensaje o usa / para comandos..."
        inp.disabled = False
        inp.focus()
