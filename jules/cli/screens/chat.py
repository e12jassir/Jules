"""Main chat screen layout."""

from __future__ import annotations

from typing import cast

from textual.app import ComposeResult  # type: ignore[import-not-found]
from textual.containers import Horizontal, Vertical  # type: ignore[import-not-found]
from textual.screen import Screen  # type: ignore[import-not-found]
from textual.widgets import Input, OptionList, Static  # type: ignore[import-not-found]
from textual.widgets.option_list import Option  # type: ignore[import-not-found]

from jules.cli.commands import COMMANDS  # type: ignore[import-not-found]
from jules.cli.widgets.chat_log import ChatLog  # type: ignore[import-not-found]
from jules.cli.widgets.input_bar import InputBar  # type: ignore[import-not-found]
from jules.cli.widgets.sidebar import Sidebar  # type: ignore[import-not-found]
from jules.cli.widgets.status_bar import StatusBar  # type: ignore[import-not-found]

_PROVIDER_CATEGORIES = {
    "cli": (["opencode", "antigravity"], "CLI"),
    "oauth": (["openai", "claude"], "OAuth"),
    "api": (["openai", "anthropic", "gemini", "openrouter", "google"], "API Key"),
    "local": (["ollama"], "Local"),
}
_OAUTH_PROVIDERS = {"codex"}


def _build_overlay_options(
    overlay: OptionList,
    value: str,
    cached_models: tuple,
) -> list[str]:
    """Populate overlay with completions for `value`. Returns list of match keys."""
    overlay.clear_options()
    matches: list[str] = []
    fragment = value[1:]

    if " " not in fragment:
        frag_lower = fragment.lower()
        for name, desc in COMMANDS.items():
            if name.startswith(frag_lower):
                overlay.add_option(Option(f"/{name}  [dim]{desc}[/dim]", id=name))
                matches.append(name)
        return matches

    cmd, arg = fragment.split(" ", 1)
    cmd = cmd.lower()
    arg_lower = arg.lower()

    if cmd == "model":
        for provider, model in (cached_models or ()):
            if provider in _OAUTH_PROVIDERS:
                continue
            label = f"{provider}:{model}"
            if not arg or arg_lower in label.lower():
                overlay.add_option(Option(f"/model {label}  [dim]{provider}[/dim]", id=f"model_{provider}:{model}"))
                matches.append(label)

    elif cmd == "provider":
        parts = arg.split(" ", 1)
        cat = parts[0].lower()
        sub = parts[1].lower() if len(parts) > 1 else ""
        if " " not in arg:
            for c, (_, label) in _PROVIDER_CATEGORIES.items():
                if c.startswith(cat):
                    overlay.add_option(Option(f"/provider {c}  [dim]{label}[/dim]", id=f"provider_{c}"))
                    matches.append(c)
        else:
            if cat in _PROVIDER_CATEGORIES:
                names, label = _PROVIDER_CATEGORIES[cat]
                for n in names:
                    if n.startswith(sub):
                        overlay.add_option(Option(f"/provider {cat} {n}  [dim]{label}[/dim]", id=f"provider_{cat}_{n}"))
                        matches.append(n)

    elif cmd in ("login", "logout", "auth"):
        for p in ["openai", "claude"]:
            if p.startswith(arg_lower):
                overlay.add_option(Option(f"/{cmd} {p}  [dim]OAuth[/dim]", id=f"{cmd}_{p}"))
                matches.append(p)

    return matches


class ChatScreen(Screen[None]):
    """Two-column chat screen."""

    DEFAULT_CSS = """
    #cmd-overlay {
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

    def __init__(self, initial_message: str | None = None) -> None:
        super().__init__()
        self.initial_message = initial_message

    def compose(self) -> ComposeResult:
        with Vertical(classes="chat-shell"):
            with Horizontal(classes="chat-layout"):
                with Vertical(classes="chat-area"):
                    with Horizontal(classes="chat-header"):
                        with Horizontal(classes="chat-header-left"):
                            yield Static("🌹 jules", classes="brand-logo")
                            yield Static(" chat ", classes="tab tab-active")
                            yield Static("+", classes="tab-add")
                        yield Static("v0.1.0", classes="chat-version")
                    yield ChatLog()
                    yield InputBar()
                yield Sidebar()
            yield StatusBar()
        yield OptionList(id="cmd-overlay")

    def on_mount(self) -> None:
        self.query_one("#cmd-overlay").display = False
        if self.initial_message:
            self._submit_message(self.initial_message)

    # ------------------------------------------------------------------
    # Slash command overlay
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        overlay = self.query_one("#cmd-overlay", OptionList)
        value = event.value
        if not value.startswith("/"):
            overlay.display = False
            return
        matches = _build_overlay_options(overlay, value, getattr(self.app, "_cached_models", ()))
        overlay.display = bool(matches)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = getattr(event.option, "id", None)
        self._complete_with(option_id)

    def on_key(self, event) -> None:  # type: ignore[override]
        overlay = self.query_one("#cmd-overlay", OptionList)
        if overlay.display and event.key == "tab":
            highlighted = overlay.highlighted
            if highlighted is not None:
                option = overlay.get_option_at_index(highlighted)
                self._complete_with(option.id)
            event.stop()
        elif not overlay.display and event.key == "tab":
            inp = self.query_one("#chat-input", Input)
            if self.focused is inp or inp.has_focus:
                self.app.call_later(self.app.action_cycle_model)
                event.stop()

    def _complete_with(self, command_id: str | None) -> None:
        if not command_id:
            return
        inp = self.query_one("#chat-input", Input)

        if command_id.startswith("model_"):
            # id = "model_provider:model"
            label = command_id[len("model_"):]
            inp.value = f"/model {label} "
        elif command_id.startswith("provider_"):
            # id = "provider_cat" or "provider_cat_name"
            rest = command_id[len("provider_"):]
            parts = rest.split("_", 1)
            cat = parts[0]
            if len(parts) == 1:
                inp.value = f"/provider {cat} "
            else:
                inp.value = f"/provider {cat} {parts[1]} "
        elif "_" in command_id and command_id.split("_")[0] in ("login", "logout", "auth"):
            cmd, provider = command_id.split("_", 1)
            inp.value = f"/{cmd} {provider} "
        else:
            inp.value = f"/{command_id} "

        inp.focus()
        inp.cursor_position = len(inp.value)
        self.query_one("#cmd-overlay").display = False
        inp.focus()
        inp.cursor_position = len(inp.value)
        self.query_one("#cmd-overlay").display = False

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_input_bar_submitted(self, message: InputBar.Submitted) -> None:
        self._submit_message(message.value)

    async def on_input_bar_command_submitted(self, message: InputBar.CommandSubmitted) -> None:
        command = message.command
        log = cast(ChatLog, self.query_one(ChatLog))
        if not command.known:
            log.start_jules_message()
            log.append_token(f"Comando desconocido: /{command.name}", cursor=False)
            log.finalize_message()
            return
        if command.name == "clear":
            log.clear()
        elif command.name == "exit":
            self.app.exit()
        elif command.name == "model":
            # No args → open interactive picker
            if not command.args:
                await self.app.action_open_model_picker()
                return

            from jules.cli.commands import handle_model
            try:
                result = await handle_model(command.args)
            except Exception as exc:
                log.start_jules_message()
                log.append_token(f"Error al cambiar modelo: {exc}", cursor=False)
                log.finalize_message()
                return
            if isinstance(result, tuple):
                display, provider, model = result
                set_model = getattr(self.app, "_set_active_model", None)
                if set_model is not None:
                    await set_model(provider, model)
                log.start_jules_message()
                log.append_token(display, cursor=False)
                log.finalize_message()
            else:
                log.start_jules_message()
                log.append_token(result, cursor=False)
                log.finalize_message()
        elif command.name == "help":
            from jules.cli.commands import handle_help

            result = handle_help()
            log.start_jules_message()
            log.append_token(result, cursor=False)
            log.finalize_message()
        elif command.name == "provider":
            from jules.cli.commands import handle_provider

            # OAuth flows are long-running — run in worker
            if command.args and command.args[0].lower() == "oauth":
                provider_name = command.args[1] if len(command.args) > 1 else ""
                log.start_jules_message()
                log.append_token(f"Iniciando login OAuth para {provider_name}...", cursor=False)
                log.finalize_message()
                login_args = (provider_name, "device") if provider_name else ("openai", "device")

                def _on_done(result: str) -> None:
                    log.start_jules_message()
                    log.append_token(result, cursor=False)
                    log.finalize_message()

                self.run_worker(self._login_worker(login_args, _on_done), exclusive=False)
                return

            try:
                result = await handle_provider(command.args)
            except Exception as exc:
                result = f"Error en /provider: {exc}"
            if isinstance(result, tuple):
                display, provider, model = result
                set_model = getattr(self.app, "_set_active_model", None)
                if set_model is not None:
                    await set_model(provider, model)
                log.start_jules_message()
                log.append_token(display, cursor=False)
                log.finalize_message()
            else:
                log.start_jules_message()
                log.append_token(result, cursor=False)
                log.finalize_message()
        elif command.name in ("sessions", "memory", "status", "doctor", "login", "logout", "auth"):
            from jules.cli.commands import (
                handle_auth,
                handle_doctor,
                handle_login,
                handle_logout,
                handle_memory,
                handle_sessions,
                handle_status,
            )

            if command.name == "login":
                # login does long-running OAuth polling — run in worker to avoid freezing TUI
                log.start_jules_message()
                log.append_token("Iniciando login OAuth...", cursor=False)
                log.finalize_message()
                args = command.args

                def _do_login() -> str:
                    import asyncio
                    return asyncio.run(handle_login(args))

                def _on_login_done(result: str) -> None:
                    log.start_jules_message()
                    log.append_token(result, cursor=False)
                    log.finalize_message()

                self.run_worker(
                    self._login_worker(args, _on_login_done),
                    exclusive=False,
                )
                return

            if command.name == "sessions":
                result = await handle_sessions()
            elif command.name == "memory":
                query = " ".join(command.args) if command.args else ""
                result = await handle_memory(query)
            elif command.name == "status":
                result = await handle_status()
            elif command.name == "login":
                result = await handle_login(command.args)
            elif command.name == "logout":
                result = await handle_logout(command.args)
            elif command.name == "auth":
                result = await handle_auth(command.args)
            else:
                result = await handle_doctor()
            log.start_jules_message()
            log.append_token(result, cursor=False)
            log.finalize_message()
        else:
            log.start_jules_message()
            log.append_token(f"/{command.name} todavía no está conectado al flujo real.", cursor=False)
            log.finalize_message()

    async def _login_worker(self, args: tuple, callback) -> None:
        """Run OAuth login in a worker so the TUI stays responsive."""
        from jules.cli.commands import handle_login
        try:
            result = await handle_login(args)
        except Exception as exc:
            result = f"Error en login: {exc}"
        callback(result)

    def _submit_message(self, value: str) -> None:
        from jules.cli.commands import parse_slash_command
        command = parse_slash_command(value)
        if command is not None:
            self.post_message(InputBar.CommandSubmitted(command))
            return
        log = cast(ChatLog, self.query_one(ChatLog))
        log.add_user_message(value)
        process_message = getattr(self.app, "process_message")
        process_message(value)
