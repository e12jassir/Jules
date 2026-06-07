"""Welcome screen for the Jules Textual TUI."""

from __future__ import annotations

import asyncio
import itertools

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.containers import Center, Container, Horizontal, Vertical  # type: ignore[import-not-found]
from textual.screen import Screen  # type: ignore[import-not-found]
from textual.widgets import Input, OptionList, Static  # type: ignore[import-not-found]

from jules.cli.screens.chat import ChatScreen  # type: ignore[import-not-found]
from jules.cli.widgets.input_bar import _ChatInput  # type: ignore[import-not-found]
from jules.cli.widgets.status_bar import StatusBar  # type: ignore[import-not-found]

BRAILLE_ROSE = """
     ██╗██╗   ██╗██╗     ███████╗███████╗
     ██║██║   ██║██║     ██╔════╝██╔════╝
     ██║██║   ██║██║     █████╗  ███████╗
██   ██║██║   ██║██║     ██╔══╝  ╚════██║
╚█████╔╝╚██████╔╝███████╗███████╗███████║
 ╚════╝  ╚═════╝ ╚══════╝╚══════╝╚══════╝
""".strip("\n")


def _build_model_row() -> str:
    """Build provider summary line from config — no network calls."""
    try:
        from jules.core.router import CognitiveRouter
        models = CognitiveRouter().available_models()
        providers = list(dict.fromkeys(p for p, _ in models))  # ordered, de-duped
        labels = {
            "ollama": "Ollama",
            "antigravity": "Antigravity",
            "opencode": "OpenCode",
            "codex": "Codex",
            "google": "Google AI",
            "openrouter": "OpenRouter",
            "openai_oauth": "OpenAI",
        }
        parts = [labels.get(p, p.title()) for p in providers]
        return " · ".join(parts)
    except Exception:
        return "Ollama · Antigravity · OpenCode · Google AI · OpenRouter · OpenAI"


class WelcomeScreen(Screen[None]):
    """Initial screen shown before the first chat message."""

    DEFAULT_CSS = """
    #welcome-cmd-overlay {
        display: none;
        width: 60;
        max-height: 16;
        background: $surface;
        border: tall $accent;
        layer: overlay;
        dock: bottom;
        offset-y: -5;
        margin-left: 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(classes="welcome-shell"):
            with Horizontal(classes="welcome-header"):
                yield Static(">_ Welcome to Jules", classes="welcome-title")
                yield Static("v0.1.0", classes="version")
            with Vertical(classes="welcome-screen"):
                yield Static(BRAILLE_ROSE, classes="rose-art")
                yield Static("Tu asistente de IA. Tu memoria. Tu compañera.", classes="tagline")
                with Center():
                    yield _ChatInput(placeholder="> Pregúntame cualquier cosa...", classes="welcome-input", id="welcome-input")
                yield Static("Ollama · Antigravity · OpenCode · Google AI · OpenRouter · OpenAI", classes="model-row", id="model-row")
                yield Static("ctrl+m modelos    ctrl+p comandos    ctrl+h ayuda    tab modelo    ctrl+c salir", classes="bindings-row")
                yield Static("● /doctor para ver el estado del sistema", classes="tip-row", id="tip-row")
            yield StatusBar()
        yield OptionList(id="welcome-cmd-overlay")

    async def on_mount(self) -> None:
        self.query_one("#welcome-cmd-overlay").display = False
        try:
            label = await asyncio.to_thread(_build_model_row)
            self.query_one("#model-row", Static).update(label)
        except Exception:
            pass
        self._rotate_tip()

    _TIPS = itertools.cycle([
        "● /doctor — estado del sistema y providers",
        "● /model — ver y cambiar el modelo activo",
        "● /memory — buscar en tu memoria semántica",
        "● /sessions — ver conversaciones anteriores",
        "● /status — estado de los providers",
        "● /provider local ollama — usar Ollama local",
        "● ctrl+p — abrir paleta de comandos",
    ])

    def _rotate_tip(self) -> None:
        try:
            self.query_one("#tip-row", Static).update(next(self._TIPS))
            self.set_timer(4.0, self._rotate_tip)
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        overlay = self.query_one("#welcome-cmd-overlay", OptionList)
        value = event.value
        if not value.startswith("/"):
            overlay.display = False
            return
        from jules.cli.screens.chat import _build_overlay_options
        matches = _build_overlay_options(overlay, value, getattr(self.app, "_cached_models", ()))
        overlay.display = bool(matches)

    def on_key(self, event) -> None:  # type: ignore[override]
        overlay = self.query_one("#welcome-cmd-overlay", OptionList)
        if overlay.display and event.key == "tab":
            highlighted = overlay.highlighted
            if highlighted is not None:
                option = overlay.get_option_at_index(highlighted)
                inp = self.query_one("#welcome-input", Input)
                inp.value = f"/{option.id} "
                inp.cursor_position = len(inp.value)
            overlay.display = False
            event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = getattr(event.option, "id", None)
        if option_id:
            inp = self.query_one("#welcome-input", Input)
            inp.value = f"/{option_id} "
            inp.focus()
            inp.cursor_position = len(inp.value)
            self.query_one("#welcome-cmd-overlay").display = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return
        event.input.value = ""
        self.app.push_screen(ChatScreen(message))
