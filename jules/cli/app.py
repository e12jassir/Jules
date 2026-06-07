"""Textual application shell for Jules."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, cast
from uuid import uuid4

from textual.app import App, ComposeResult  # type: ignore[import-not-found]
from textual import work  # type: ignore[import-not-found]
from textual.reactive import reactive  # type: ignore[import-not-found]

from jules.cli.screens.welcome import WelcomeScreen  # type: ignore[import-not-found]
from jules.cli.widgets.chat_log import ChatLog  # type: ignore[import-not-found]
from jules.cli.widgets.input_bar import InputBar  # type: ignore[import-not-found]
from jules.cli.widgets.memory_panel import MemoryPanel  # type: ignore[import-not-found]
from jules.cli.widgets.model_panel import ModelPanel  # type: ignore[import-not-found]
from jules.cli.widgets.stats_panel import StatsPanel  # type: ignore[import-not-found]
from jules.cli.widgets.status_bar import StatusBar  # type: ignore[import-not-found]


def _resolve_theme_css() -> str:
    """Return the TCSS filename based on [cli].theme in config.toml."""
    try:
        import tomllib
        for candidate in (Path.cwd() / "config.toml", Path.home() / ".jules" / "config.toml"):
            if candidate.exists():
                with candidate.open("rb") as f:
                    raw = tomllib.load(f)
                if raw.get("cli", {}).get("theme") == "terminal":
                    return "theme_terminal.tcss"
                break
    except Exception:
        pass
    return "theme.tcss"


_TERMINAL_PALETTE_CACHE: dict[str, str] | None = None
_TERMINAL_PALETTE_CACHED = False

def _read_terminal_palette() -> dict[str, str] | None:
    """Read colors from Ghostty config and map to semantic variables."""
    global _TERMINAL_PALETTE_CACHE, _TERMINAL_PALETTE_CACHED
    if _TERMINAL_PALETTE_CACHED:
        return _TERMINAL_PALETTE_CACHE
    _TERMINAL_PALETTE_CACHED = True

    config_path = Path.home() / ".config" / "ghostty" / "config.ghostty"
    if not config_path.exists():
        return None
    try:
        text = config_path.read_text()
        colors: dict[str, str] = {}
        palette: dict[int, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key == "background":
                colors["background"] = value
            elif key == "foreground":
                colors["foreground"] = value
            elif key == "palette":
                idx, _, hex_val = value.partition("=")
                palette[int(idx.strip())] = hex_val.strip()
        if not colors.get("background"):
            return None
        _TERMINAL_PALETTE_CACHE = {
            "background": colors.get("background", "#000000"),
            "surface": palette.get(0, "#111111"),
            "panel": palette.get(8, "#333333"),
            "text": colors.get("foreground", "#ffffff"),
            "text-muted": palette.get(1, "#888888"),
            "accent": palette.get(6, "#00afaf"),
            "success": palette.get(2, "#00af00"),
            "warning": palette.get(3, "#afaf00"),
            "error": palette.get(1, "#af0000"),
        }
        return _TERMINAL_PALETTE_CACHE
    except Exception:
        return None


class JulesApp(App[None]):
    """Persistent Textual TUI for Jules."""

    CSS_PATH = _resolve_theme_css()
    TITLE = ""
    SUB_TITLE = ""
    from textual.binding import Binding  # type: ignore[import-not-found]

    BINDINGS = [
        Binding("tab", "cycle_model", "Modelo"),
        ("ctrl+m", "open_model_picker", "Modelos"),
        ("ctrl+p", "command_palette", "Comandos"),
        ("ctrl+h", "show_help", "Ayuda"),
        ("ctrl+c", "quit", "Salir"),
    ]

    _session_id: str = str(uuid4())
    _background_tasks: set  # set[asyncio.Task] — holds strong refs to prevent GC
    _cached_models: tuple[tuple[str, str], ...]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._background_tasks = set()

    def get_css_variables(self) -> dict[str, str]:
        variables = super().get_css_variables()
        if self.CSS_PATH == "theme_terminal.tcss":
            palette = _read_terminal_palette()
            if palette:
                variables.update(palette)
        return variables

    _model_index: int = 0

    active_model = reactive("---")
    active_provider = reactive("---")
    active_tier = reactive("---")
    tokens_used = reactive(0)
    session_cost = reactive(0.0)
    session_time = reactive("00:00:00")
    memory_episodes = reactive(0)
    memory_facts = reactive(0)
    online_status = reactive(True)

    def compose(self) -> ComposeResult:
        # Yield nothing — WelcomeScreen is pushed as a real screen in on_mount
        return
        yield  # make this a generator

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())
        self.run_worker(self._run_doctor())
        self.run_worker(self._populate_initial_model())

    async def _populate_initial_model(self) -> None:
        """Set Ollama as default model on startup; fall back to router default."""
        try:
            from jules.core.router import CognitiveRouter, TaskType

            router = await asyncio.to_thread(CognitiveRouter)
            # Always start with local Ollama — no external calls on launch
            try:
                provider_obj, model = router.route(TaskType.OFFLINE)
                provider = provider_obj.name
            except Exception:
                provider, model = await asyncio.to_thread(lambda: CognitiveRouter().current_model())
            self.active_provider = provider
            self.active_model = model
            self._user_model_override = f"{provider}:{model}"
            self._cached_models = router.available_models()
            self._update_model_panel(model, provider, True)
        except Exception:  # noqa: BLE001
            pass

    async def _run_doctor(self) -> None:
        """Run doctor checks in background and post result to StatusBar."""
        try:
            from jules.linux.doctor import run_all_checks

            report = await asyncio.to_thread(run_all_checks)
            issues = [r.message for r in report.results if r.status in ("fail", "warn")]
            self.query_one(StatusBar).post_message(StatusBar.DoctorResult(issues))
        except Exception:  # noqa: BLE001
            pass

    @work(exclusive=True)
    async def process_message(self, message: str) -> None:
        """Process one user message without blocking the TUI event loop."""
        from jules.providers.base import ContentEvent, ThoughtEvent

        chat_log = cast(ChatLog, self.screen.query_one(ChatLog))
        status_bar = cast(StatusBar, self.screen.query_one(StatusBar))
        status_bar.set_generating(True)
        safe, reason = _sanitize_message(message)
        chat_log.start_jules_message()
        if not safe:
            chat_log.append_token(f"Mensaje bloqueado por sanitizador: {reason}", cursor=False)
            chat_log.finalize_message()
            status_bar.set_generating(False)
            return
        response_parts: list[str] = []
        try:
            async for event in self._stream_response(message):
                if isinstance(event, ThoughtEvent):
                    chat_log.append_thought(event.content)
                elif isinstance(event, ContentEvent):
                    response_parts.append(event.content)
                    chat_log.append_token(event.content)
                else:
                    # Plain str fallback (legacy providers)
                    response_parts.append(event)  # type: ignore[arg-type]
                    chat_log.append_token(event)  # type: ignore[arg-type]
            response = "".join(response_parts)
            chat_log.finalize_message()
            self._record_stats(message, response)
            self._fire_background(self._persist_episode(message, response))
            self._fire_background(self._persist_chat_history(message, response))
        except Exception as exc:  # noqa: BLE001 - boundary must degrade instead of crashing TUI
            chat_log.append_token(f"Error procesando mensaje: {exc}", cursor=False)
            chat_log.finalize_message()
        finally:
            status_bar.set_generating(False)

    async def _stream_response(self, message: str) -> AsyncIterator[object]:
        from jules.core.context import ContextEngine
        from jules.core.router import TaskType, ask_with_fallback, route
        from jules.core.session import SessionContext as CoreSessionContext
        from jules.memory.models import SessionContext as MemorySessionContext
        from jules.personality.loader import MasterPersonalityMissingError, PersonalityLoader
        from jules.providers.base import ContentEvent, ProviderError, StreamEvent

        core_context = CoreSessionContext(cwd=str(Path.cwd()))
        built = await asyncio.to_thread(ContextEngine.build, core_context, message)
        memory_context = MemorySessionContext(
            project=Path(built.project_root).name if built.project_root else None,
            directory=core_context.cwd,
            active_files=[],
            inferred_intent=built.intent,
            time_of_day=str(built.time_of_day),
            shell=built.shell,
        )

        provider, model = await route(TaskType.QUICK, user_override=getattr(self, "_user_model_override", None))
        self.active_provider = provider.name
        self.active_model = model
        self._update_model_panel(model, provider.name, True)
        memory_refs = await _retrieve_memory_references(message)
        try:
            personality = await asyncio.to_thread(PersonalityLoader().load, provider.name)
        except MasterPersonalityMissingError:
            yield ContentEvent(content="Archivo de personalidad master (~/.jules/personality/master.md) no encontrado. Es obligatorio para operar.")
            return
        prompt = _compose_prompt(personality, message, memory_refs)

        try:
            # Prefer stream_events() for typed ThoughtEvent/ContentEvent
            if hasattr(provider, "stream_events"):
                async for event in provider.stream_events(prompt, memory_context, model):  # type: ignore[union-attr]
                    yield event
            else:
                async for token in provider.stream(prompt, memory_context, model):
                    yield token
        except (NotImplementedError, ProviderError):
            response, fallback_model, fallback_provider = await ask_with_fallback(prompt, memory_context, TaskType.QUICK)
            self.active_provider = fallback_provider
            self.active_model = fallback_model
            self._update_model_panel(fallback_model, fallback_provider, True)
            yield response

    def _update_model_panel(self, model: str, provider: str, online: bool) -> None:
        try:
            self.screen.query_one(ModelPanel).update_model(model, provider, online)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _record_stats(self, message: str, response: str) -> None:
        self.tokens_used += _estimate_tokens(message) + _estimate_tokens(response)
        try:
            self.screen.query_one(StatsPanel).update_stats(self.tokens_used, None, self.session_time)  # type: ignore[attr-defined]
        except Exception:
            pass

    async def _persist_episode(self, message: str, response: str) -> None:
        try:
            await _persist_episode_background(message, response, self.active_model, self.active_provider)
            self.memory_episodes += 1
            self.screen.query_one(MemoryPanel).update_counts(self.memory_episodes, self.memory_facts, 0)  # type: ignore[attr-defined]
        except Exception:
            try:
                self.screen.query_one(MemoryPanel).set_degraded("sin persistencia")  # type: ignore[attr-defined]
            except Exception:
                pass

    async def _persist_chat_history(self, message: str, response: str) -> None:
        try:
            from jules.memory.persistent import create_memory_engine, create_memory_sessionmaker
            from jules.models.chat_history import ChatHistoryEntry, ChatHistoryORM

            if not hasattr(self, "_chat_engine"):
                self._chat_engine = create_memory_engine()
                self._chat_session_factory = create_memory_sessionmaker(self._chat_engine)
            async with self._chat_session_factory() as session:
                async with session.begin():
                    session.add(ChatHistoryORM.from_entry(ChatHistoryEntry(
                        id=None, session_id=self._session_id,
                        role="user", content=message,
                        created_at=datetime.now(timezone.utc)
                    )))
                    session.add(ChatHistoryORM.from_entry(ChatHistoryEntry(
                        id=None, session_id=self._session_id,
                        role="assistant", content=response,
                        created_at=datetime.now(timezone.utc)
                    )))
        except Exception:
            pass

    def _fire_background(self, coro) -> None:
        """Schedule a coroutine as a background task with a strong reference to prevent GC."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def action_open_model_picker(self) -> None:
        """Open the interactive model picker modal."""
        from jules.cli.screens.model_picker import ModelPickerScreen
        from jules.core.router import CognitiveRouter

        if not hasattr(self, "_cached_models") or not self._cached_models:
            self._cached_models = await asyncio.to_thread(lambda: CognitiveRouter().available_models())

        current = getattr(self, "_user_model_override", "")
        # Build recents: current model first
        recents: list[tuple[str, str]] = []
        if current and ":" in current:
            p, m = current.split(":", 1)
            recents.append((p, m))

        def on_picked(result: tuple[str, str] | None) -> None:
            if result:
                provider, model = result
                self.run_worker(self._set_active_model(provider, model))

        await self.push_screen(
            ModelPickerScreen(self._cached_models, current, recents),
            on_picked,
        )

    def action_toggle_variants(self) -> None:
        self.notify("Model variants are not wired yet.", severity="information")

    def action_toggle_agents(self) -> None:
        self.notify("Agent tabs are not wired yet.", severity="information")

    async def action_cycle_model(self) -> None:
        """Cycle through available models for the CURRENT provider on TAB press."""
        from jules.core.router import CognitiveRouter

        try:
            if not hasattr(self, "_cached_models") or not self._cached_models:
                self._cached_models = await asyncio.to_thread(
                    lambda: CognitiveRouter().available_models()
                )
            if not self._cached_models:
                return

            current_provider = self.active_provider
            provider_models = [(p, m) for p, m in self._cached_models if p == current_provider]

            if not provider_models:
                return

            current_index = 0
            for i, (p, m) in enumerate(provider_models):
                if m == self.active_model:
                    current_index = i
                    break

            next_index = (current_index + 1) % len(provider_models)
            next_provider, next_model = provider_models[next_index]

            await self._set_active_model(next_provider, next_model)
        except Exception:  # noqa: BLE001
            pass

    async def _set_active_model(self, provider: str, model: str) -> None:
        """Update active model state and notify ModelPanel."""
        self.active_provider = provider
        self.active_model = model
        self._update_model_panel(model, provider, True)
        self._user_model_override = f"{provider}:{model}"
        self.notify(f"Modelo: {model} ({provider})", timeout=2)

    def action_command_palette(self) -> None:
        """Focus the chat input and type '/' to open the command overlay."""
        try:
            inp = self.screen.query_one("#chat-input")
            inp.focus()
            inp.value = "/"  # type: ignore[attr-defined]
            inp.cursor_position = 1  # type: ignore[attr-defined]
        except Exception:
            try:
                inp = self.screen.query_one("#welcome-input")
                inp.focus()
                inp.value = "/"  # type: ignore[attr-defined]
                inp.cursor_position = 1  # type: ignore[attr-defined]
            except Exception:
                self.notify("Usá / en el input para ver los comandos.", severity="information")

    def action_show_help(self) -> None:
        """Execute /help directly in the chat."""
        from jules.cli.commands import handle_help
        try:
            from jules.cli.widgets.chat_log import ChatLog
            log = self.screen.query_one(ChatLog)
            result = handle_help()
            log.start_jules_message()
            log.append_token(result, cursor=False)
            log.finalize_message()
        except Exception:
            self.notify(
                "/help /status /doctor /memory /sessions /model /clear /exit",
                severity="information",
                timeout=6,
            )


_SHARED_PERSISTENT_MEMORY = None
_SHARED_EPISODIC_MEMORY = None

async def _get_shared_memory() -> tuple:
    global _SHARED_PERSISTENT_MEMORY, _SHARED_EPISODIC_MEMORY
    if _SHARED_PERSISTENT_MEMORY is None or _SHARED_EPISODIC_MEMORY is None:
        def build():
            global _SHARED_PERSISTENT_MEMORY, _SHARED_EPISODIC_MEMORY
            from jules.memory.persistent import PersistentMemory
            from jules.memory.episodic import EpisodicMemory
            if _SHARED_PERSISTENT_MEMORY is None:
                _SHARED_PERSISTENT_MEMORY = PersistentMemory()
            if _SHARED_EPISODIC_MEMORY is None:
                _SHARED_EPISODIC_MEMORY = EpisodicMemory(Path.home() / ".jules" / "lancedb")
        await asyncio.to_thread(build)
    return _SHARED_PERSISTENT_MEMORY, _SHARED_EPISODIC_MEMORY


async def _retrieve_memory_references(message: str) -> list[str]:
    """Best-effort memory retrieval; imports and setup are bounded off-loop."""
    try:
        from jules.memory.engine import MemoryEngine

        persistent, episodic = await _get_shared_memory()
        memory = MemoryEngine(
            persistent=persistent,
            episodic=episodic,
            provider=_NoopScoringProvider(),
            embedding_provider=None,
        )
        episodes = await asyncio.wait_for(
            memory.retrieve_async(message, limit=3),
            timeout=1.5,
        )
        return [f"{ep.problem[:80] if ep.problem else ep.solution[:80] if ep.solution else ''}" for ep in episodes]
    except Exception:
        return []


def _sanitize_message(message: str) -> tuple[bool, str | None]:
    from jules.sanitizer.sanitizer import Sanitizer

    result = Sanitizer.check(message)
    return result.is_safe, result.reason


async def _persist_episode_background(message: str, response: str, model: str, provider_name: str) -> None:
    """Persist a memory episode after UI response finalization."""
    from jules.memory.engine import MemoryEngine
    from jules.memory.models import Episode, SessionContext

    context = SessionContext(
        project=Path.cwd().name,
        directory=str(Path.cwd()),
        active_files=[],
        inferred_intent="chat",
        time_of_day=str(datetime.now(timezone.utc).hour),
        shell="unknown",
    )
    episode = Episode(
        id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        context=context,
        problem=message,
        process=None,
        solution=response,
        duration_seconds=None,
        friction_score=0.0,
        tags=["tui", f"provider:{provider_name}"],
        model_used=model,
        provider_used=provider_name,
    )
    scoring_provider, scoring_model = await _local_scoring_provider()
    persistent, episodic = await _get_shared_memory()
    memory = MemoryEngine(
        persistent=persistent,
        episodic=episodic,
        provider=_ScoringAdapter(scoring_provider, scoring_model, context),
        embedding_provider=scoring_provider,
    )
    memory.persistence_delay_seconds = 0
    persisted = await memory.persist_and_wait_async(episode)
    if not persisted:
        return


def _estimate_tokens(text: str) -> int:
    """Cheap fallback token estimate until providers expose usage totals."""
    return max(1, len(text.split())) if text else 0


def calculate_cost(tokens: int, model: str, rates: dict[str, float] | None = None) -> float:
    """Return estimated cost in USD given token count, model name, and per-token rates.

    Rates are expected as cost-per-token (e.g. 0.000003 for $3/M tokens).
    Falls back to 0.0 when model is not in the rates table.
    """
    if tokens <= 0 or not rates:
        return 0.0
    rate = rates.get(model, 0.0)
    return tokens * rate


async def _local_scoring_provider():
    from jules.core.router import TaskType, route

    return await route(TaskType.MEMORY_SCORING)


class _NoopScoringProvider:
    async def generate_text(self, prompt: str) -> str:
        del prompt
        return "SCORE: 0.5"


class _ScoringAdapter:
    def __init__(self, provider, model: str, context) -> None:
        self.provider = provider
        self.model = model
        self.context = context

    async def generate_text(self, prompt: str) -> str:
        return await self.provider.ask(prompt, self.context, self.model)


def _compose_prompt(personality: str, message: str, memory_refs: list[str] | None = None) -> str:
    parts = []
    if personality:
        parts.append(personality)
    if memory_refs:
        parts.append("Relevant past context:\n- " + "\n- ".join(memory_refs))
    parts.append(f"User: {message}")
    return "\n\n".join(parts)
