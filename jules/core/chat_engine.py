"""Headless chat engine — the same request/response/streaming logic used by
the Textual TUI (`jules.cli.app.JulesApp._stream_response`), extracted so it
can be driven by any frontend (Textual, the Rust `jules-tui` prototype, or
tests) without depending on Textual widgets.

This module owns no UI state. Callers hold a `ChatEngineState` instance
across turns (active provider/model, chat history) and call
`stream_turn(state, message)` per user message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from jules.auth.base import OAuthError
from jules.cli.app import (  # noqa: F401 — reuse existing module-level helpers
    _compose_prompt,
    _persist_episode_background,
    _retrieve_memory_references,
    _sanitize_message,
)
from jules.providers.base import ContentEvent, ProviderError, StreamEvent, ThoughtEvent


@dataclass
class ChatEngineState:
    """Per-session state carried between turns. Frontend-agnostic."""

    active_provider: str = "opencode"
    active_model: str = "opencode/deepseek-v4-flash-free"
    user_model_override: str | None = None
    chat_history: list[tuple[str, str]] = field(default_factory=list)


async def stream_turn(state: ChatEngineState, message: str) -> AsyncIterator[StreamEvent]:
    """Stream one turn's events for `message`, updating `state` in place.

    Mirrors `JulesApp._stream_response` + the history/model bookkeeping in
    `JulesApp.process_message`, minus anything Textual-specific (widgets,
    `self.screen.query_one`, notifications). Sanitization happens here too,
    so callers get a single `ContentEvent` with the block reason instead of
    having to replicate that check themselves.
    """
    from jules.core.context import ContextEngine
    from jules.core.router import TaskType, route, stream_with_fallback
    from jules.core.session import SessionContext as CoreSessionContext
    from jules.memory.models import SessionContext as MemorySessionContext
    from jules.personality.loader import MasterPersonalityMissingError, PersonalityLoader

    safe, reason = _sanitize_message(message)
    if not safe:
        yield ContentEvent(content=f"Mensaje bloqueado por sanitizador: {reason}")
        return

    core_context = CoreSessionContext(cwd=str(Path.cwd()))
    built = await ContextEngine.build(core_context, message)
    memory_context = MemorySessionContext(
        project=Path(built.project_root).name if built.project_root else None,
        directory=core_context.cwd,
        active_files=[],
        inferred_intent=built.intent,
        time_of_day=str(built.time_of_day),
        shell=built.shell,
    )

    provider, model = await route(TaskType.QUICK, user_override=state.user_model_override)
    state.active_provider = provider.name
    state.active_model = model
    memory_refs = await _retrieve_memory_references(message)

    try:
        import asyncio

        personality = await asyncio.to_thread(PersonalityLoader().load, provider.name)
    except MasterPersonalityMissingError:
        yield ContentEvent(
            content=(
                "Archivo de personalidad master (~/.jules/personality/master.md) "
                "no encontrado. Es obligatorio para operar."
            )
        )
        return

    prompt = _compose_prompt(personality, message, memory_refs, list(state.chat_history))

    response_parts: list[str] = []

    async def _drain(event) -> StreamEvent:
        # `stream_with_fallback` can yield either a typed StreamEvent (when
        # the fallback provider implements `stream_events`) or a raw string
        # token (when it only implements the older `stream()` API, e.g.
        # OpenCode — see jules/providers/opencode.py). Normalize both to
        # ContentEvent so downstream consumers (protocol.py, Textual's
        # ChatLog) only ever handle typed events.
        if isinstance(event, str):
            event = ContentEvent(content=event)
        if isinstance(event, ContentEvent):
            response_parts.append(event.content)
        return event

    try:
        if hasattr(provider, "stream_events"):
            async for event in provider.stream_events(prompt, memory_context, model):
                yield await _drain(event)
        else:
            async for token in provider.stream(prompt, memory_context, model):
                yield await _drain(ContentEvent(content=token))
    except (NotImplementedError, ProviderError, OAuthError):
        async for event, fallback_model, fallback_provider in stream_with_fallback(
            prompt, memory_context, TaskType.QUICK, user_override=state.user_model_override
        ):
            if fallback_model != state.active_model or fallback_provider != state.active_provider:
                state.active_provider = fallback_provider
                state.active_model = fallback_model
            yield await _drain(event)

    response = "".join(response_parts)
    state.chat_history.append(("user", message))
    state.chat_history.append(("jules", response))

    try:
        await _persist_episode_background(message, response, state.active_model, state.active_provider)
    except Exception:  # noqa: BLE001 - persistence must never break a turn
        pass


__all__ = ["ChatEngineState", "stream_turn", "ThoughtEvent", "ContentEvent"]
