"""Modal model picker — navigate with arrows, select with Enter."""

from __future__ import annotations

from collections.abc import Sequence

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.screen import ModalScreen  # type: ignore[import-not-found]
from textual.widgets import Input, OptionList, Static  # type: ignore[import-not-found]
from textual.widgets.option_list import Option  # type: ignore[import-not-found]

_PROVIDER_ICONS = {
    "ollama": "🦙",
    "openai_oauth": "✦",
    "google": "◈",
    "openrouter": "⌁",
    "opencode": "⌥",
    "antigravity": "⊕",
    "codex": "⊞",
}


class _PickerInput(Input):
    """Input that forwards up/down/enter/escape to the picker screen."""

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key in ("up", "down", "enter", "escape"):
            # Let the ModalScreen.on_key handle these
            event.prevent_default()
            # Re-post to screen by NOT stopping — let it bubble up
            # Actually we need to call screen directly since Input eats these
            self.screen.on_key(event)  # type: ignore[attr-defined]
            event.stop()


class ModelPickerScreen(ModalScreen[tuple[str, str] | None]):
    """Full-screen modal to pick a provider:model. Returns (provider, model) or None."""

    DEFAULT_CSS = """
    ModelPickerScreen {
        align: center middle;
    }
    #picker-box {
        width: 72;
        height: auto;
        max-height: 36;
        background: $surface;
        border: round $accent;
        padding: 0;
    }
    #picker-header {
        background: $accent 20%;
        color: $accent;
        text-align: center;
        padding: 1 2;
        text-style: bold;
    }
    #picker-search {
        margin: 1 2 0 2;
        border: tall $panel;
    }
    #section-label {
        color: $text-muted;
        margin: 1 2 0 2;
        text-style: italic;
    }
    #model-list {
        margin: 0 1;
        height: auto;
        max-height: 22;
        border: none;
        background: transparent;
        scrollbar-size: 1 1;
        scrollbar-size-vertical: 1;
    }
    #picker-footer {
        color: $text-muted;
        text-align: center;
        padding: 0 2 1 2;
    }
    """

    def __init__(
        self,
        models: tuple[tuple[str, str], ...],
        current: str = "",
        recents: list[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__()
        self._all_models = models
        self._current = current
        self._recents = recents or []
        self._filtered = list(models)

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical  # type: ignore[import-not-found]

        with Vertical(id="picker-box"):
            yield Static("  Seleccionar modelo", id="picker-header")
            yield _PickerInput(placeholder="  Buscar modelo...", id="picker-search")
            yield Static("", id="section-label")
            yield OptionList(*self._build_options(self._all_models), id="model-list")
            yield Static("↑↓ navegar   Enter seleccionar   Esc cancelar", id="picker-footer")

    def on_mount(self) -> None:
        self._refresh_list(list(self._all_models))
        self.query_one("#picker-search", Input).focus()
        if self._current:
            lst = self.query_one("#model-list", OptionList)
            for i in range(lst.option_count):
                opt = lst.get_option_at_index(i)
                oid = getattr(opt, "id", None) or ""
                key = oid[2:] if oid.startswith("r:") else oid
                if key == self._current:
                    lst.highlighted = i
                    break

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.lower().strip()
        if not query:
            filtered = list(self._all_models)
            self.query_one("#section-label", Static).update("")
        else:
            filtered = [(p, m) for p, m in self._all_models if query in m.lower() or query in p.lower()]
            self.query_one("#section-label", Static).update(f"  {len(filtered)} resultado(s)")
        self._refresh_list(filtered)

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key == "escape":
            self.dismiss(None)
            event.stop()
        elif event.key in ("down", "up"):
            lst = self.query_one("#model-list", OptionList)
            count = lst.option_count
            if count == 0:
                return
            current = lst.highlighted if lst.highlighted is not None else -1
            if event.key == "down":
                # Skip disabled options
                idx = current + 1
                while idx < count:
                    opt = lst.get_option_at_index(idx)
                    if not getattr(opt, "disabled", False):
                        break
                    idx += 1
                if idx < count:
                    lst.highlighted = idx
            else:
                idx = (current - 1) if current > 0 else count - 1
                while idx >= 0:
                    opt = lst.get_option_at_index(idx)
                    if not getattr(opt, "disabled", False):
                        break
                    idx -= 1
                if idx >= 0:
                    lst.highlighted = idx
            event.prevent_default()
            event.stop()
        elif event.key == "enter":
            lst = self.query_one("#model-list", OptionList)
            hi = lst.highlighted
            if hi is not None:
                opt = lst.get_option_at_index(hi)
                self._select(getattr(opt, "id", None))
            event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._select(getattr(event.option, "id", None))

    def _select(self, option_id: str | None) -> None:
        if not option_id or option_id.startswith("__"):
            return
        key = option_id[2:] if option_id.startswith("r:") else option_id
        if ":" in key:
            provider, model = key.split(":", 1)
            self.dismiss((provider, model))

    def _refresh_list(self, models: Sequence[tuple[str, str]]) -> None:
        lst = self.query_one("#model-list", OptionList)
        lst.clear_options()
        for opt in self._build_options(models):
            lst.add_option(opt)

    def _build_options(self, models: Sequence[tuple[str, str]]) -> list[Option]:
        options: list[Option] = []
        model_set = {(p, m) for p, m in models}

        # Recents section
        recents_filtered = [(p, m) for p, m in self._recents if (p, m) in model_set]
        if recents_filtered:
            options.append(Option("[dim]  RECIENTES[/dim]", disabled=True, id="__hdr_recent__"))
            for provider, model in recents_filtered:
                icon = _PROVIDER_ICONS.get(provider, "○")
                marker = " [green]●[/green]" if f"{provider}:{model}" == self._current else ""
                options.append(Option(
                    f"  {icon} [bold]{model}[/bold]{marker}  [dim]{provider}[/dim]",
                    id=f"r:{provider}:{model}",
                ))
            options.append(Option("[dim]  ──────────────────────────────[/dim]", disabled=True, id="__sep_recent__"))

        # Sort by provider to keep same-provider models together
        _PROVIDER_ORDER = ["ollama", "openai_oauth", "google", "openrouter", "opencode", "antigravity", "codex"]
        sorted_models = sorted(models, key=lambda pm: (_PROVIDER_ORDER.index(pm[0]) if pm[0] in _PROVIDER_ORDER else 99, pm[1]))

        # Grouped by provider
        last_provider = ""
        hdr_idx = 0
        for provider, model in sorted_models:
            if provider != last_provider:
                icon = _PROVIDER_ICONS.get(provider, "○")
                options.append(Option(
                    f"[dim]  {icon} {provider.upper()}[/dim]",
                    disabled=True,
                    id=f"__hdr_{provider}_{hdr_idx}__",
                ))
                hdr_idx += 1
                last_provider = provider
            marker = " [green]●[/green]" if f"{provider}:{model}" == self._current else ""
            options.append(Option(f"    {model}{marker}", id=f"{provider}:{model}"))

        return options
