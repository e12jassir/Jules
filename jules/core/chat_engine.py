"""Decoupled core chat engine for Jules.

Coordinates prompt assembly, memory retrieval, streaming turn execution,
sanitization, and zero-latency background persistence without depending on
any terminal or graphical UI components.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator
from uuid import uuid4

from jules.core.context import BuiltContext, ContextEngine
from jules.core.router import CognitiveRouter, TaskType
from jules.core.session import SessionContext as CoreSessionContext
from jules.memory.engine import MemoryEngine
from jules.memory.models import Episode, SessionContext as MemorySessionContext
from jules.personality.loader import MasterPersonalityMissingError, PersonalityLoader
from jules.providers.base import ContentEvent, StreamEvent, ThoughtEvent
from jules.sanitizer.sanitizer import Sanitizer

if TYPE_CHECKING:
    from jules.core.permissions import PermissionGate

logger = logging.getLogger(__name__)


def compose_prompt(
    personality: str,
    message: str,
    memory_refs: list[str] | None = None,
    chat_history: list[tuple[str, str]] | None = None,
    history_limit: int = 20,
    facts: list[str] | None = None,
) -> str:
    """Assemble system personality, project facts, memory references and history."""
    parts = []
    if personality:
        parts.append(personality)
    if facts:
        clean_facts = [f.strip() for f in facts if f and f.strip()]
        if clean_facts:
            parts.append("Project facts:\n- " + "\n- ".join(clean_facts))
    if memory_refs:
        clean_refs = [ref.strip() for ref in memory_refs if ref and ref.strip()]
        if clean_refs:
            parts.append("Relevant past context:\n- " + "\n- ".join(clean_refs))
    if chat_history:
        recent = chat_history[-history_limit:]
        history_block = "\n".join(f"{role.capitalize()}: {content}" for role, content in recent)
        parts.append(f"Conversation so far:\n{history_block}")
    parts.append(f"User: {message}")
    return "\n\n".join(parts)


@dataclass
class ChatEngineState:
    """Per-session state carried between turns for headless protocols."""

    active_provider: str = "opencode"
    active_model: str = "opencode/deepseek-v4-flash-free"
    user_model_override: str | None = None
    chat_history: list[tuple[str, str]] = field(default_factory=list)


class ChatEngine:
    """Central cognitive brain decoupled from Textual and OS frontends."""

    def __init__(
        self,
        router: CognitiveRouter,
        memory_engine: MemoryEngine,
        personality_loader: PersonalityLoader,
        sanitizer: type[Sanitizer] = Sanitizer,
        permission_gate: PermissionGate | None = None,
    ) -> None:
        self.router = router
        self.memory_engine = memory_engine
        self.personality_loader = personality_loader
        self.sanitizer = sanitizer
        self.permission_gate = permission_gate
        self.last_provider: str | None = None
        self.last_model: str | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def stream_turn(
        self,
        user_input: str,
        session_id: str,
        session_ctx: CoreSessionContext,
        chat_history: list[tuple[str, str]],
        user_override: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Execute one complete conversational turn with zero latency overhead.

        Lifecycle:
        1. Sanitizer.check(user_input): abort immediately if unsafe.
        2. memory_engine.start_active_query(): cancel competing Ollama background tasks.
        3. Parallel execution of ContextEngine.build & memory_engine.retrieve_async (<150ms timeout).
        4. Personality and prompt assembly.
        5. Streaming from router.stream_with_fallback.
        6. Finally: memory_engine.end_active_query() and background persistence dispatch.
        """
        # Step 1: Sanitizer check
        sanitize_result = self.sanitizer.check(user_input)
        if not sanitize_result.is_safe:
            yield ContentEvent(content=f"Mensaje bloqueado por sanitizador: {sanitize_result.reason}")
            return

        # Step 2: Signal active query to memory engine
        self.memory_engine.start_active_query()

        built_context: BuiltContext | None = None
        response_parts: list[str] = []
        turn_success = False

        try:
            # Step 3: Parallel context building and bounded memory retrieval (<150ms)
            async def _safe_retrieve() -> list[Episode]:
                try:
                    return await asyncio.wait_for(
                        self.memory_engine.retrieve_async(user_input, limit=3),
                        timeout=0.15,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Memory retrieval timed out or failed: %s", exc)
                    return []

            built_context, episodes = await asyncio.gather(
                ContextEngine.build(session_ctx, user_input),
                _safe_retrieve(),
            )

            # Step 4: Resolve provider and model, then assemble prompt
            provider, model = await self.router.route(TaskType.QUICK, user_override=user_override)
            self.last_provider = provider.name
            self.last_model = model

            memory_refs = [
                f"{ep.problem[:80] if ep.problem else ep.solution[:80] if ep.solution else ''}"
                for ep in episodes
            ]

            try:
                personality = await asyncio.to_thread(self.personality_loader.load, provider.name)
            except MasterPersonalityMissingError:
                yield ContentEvent(
                    content=(
                        "Archivo de personalidad master (~/.jules/personality/master.md) "
                        "no encontrado. Es obligatorio para operar."
                    )
                )
                return

            if session_id == "voice_session" or session_id.startswith("voice"):
                personality += (
                    "\n\n[MODO CONVERSACIÓN POR VOZ EN TIEMPO REAL]\n"
                    "- Estás conversando verbalmente por voz con Esteban.\n"
                    "- Responde de forma concisa, fluida y directa: máximo 1 a 2 oraciones naturales (3 sólo si es estrictamente necesario).\n"
                    "- Prohibido usar viñetas, listas, tablas, asteriscos, código o formato markdown.\n"
                    "- Tono natural, inteligente, cómplice y fresco de tú a tú, sin rodeos ni formalismos de bot."
                )

            prompt = compose_prompt(
                personality=personality,
                message=user_input,
                memory_refs=memory_refs,
                chat_history=chat_history,
            )

            memory_context = MemorySessionContext(
                project=Path(built_context.project_root).name if built_context.project_root else None,
                directory=session_ctx.cwd,
                active_files=[],
                inferred_intent=built_context.intent,
                time_of_day=str(built_context.time_of_day),
                shell=built_context.shell,
            )

            # Step 5: Streaming from router with fallback support
            async for item in self.router.stream_with_fallback(
                prompt,
                memory_context,  # type: ignore[arg-type]
                TaskType.QUICK,
                user_override=user_override,
            ):
                if isinstance(item, tuple) and len(item) == 3:
                    event_raw, stream_model, stream_provider = item
                    self.last_model = stream_model
                    self.last_provider = stream_provider
                else:
                    event_raw = item

                if isinstance(event_raw, str):
                    event: StreamEvent = ContentEvent(content=event_raw)
                else:
                    event = event_raw

                if isinstance(event, ContentEvent):
                    response_parts.append(event.content)

                yield event

            turn_success = True

        finally:
            # Step 6: Query lifecycle teardown & zero-latency background persistence
            self.memory_engine.end_active_query()

            full_response = "".join(response_parts)
            if turn_success and full_response:
                if isinstance(chat_history, list):
                    chat_history.append(("user", user_input))
                    chat_history.append(("jules", full_response))

                safe_response = self.sanitizer.check(full_response)
                if safe_response.is_safe:
                    bg_task = asyncio.create_task(
                        self._persist_turn_background(
                            user_input=user_input,
                            response=full_response,
                            session_id=session_id,
                            session_ctx=session_ctx,
                            built_ctx=built_context,
                            model=self.last_model or "unknown",
                            provider_name=self.last_provider or "unknown",
                        )
                    )
                    self._background_tasks.add(bg_task)
                    bg_task.add_done_callback(self._background_tasks.discard)
                else:
                    logger.warning(
                        "Response contains sensitive patterns, suppressed from memory persistence: %s",
                        safe_response.reason,
                    )

    async def _persist_turn_background(
        self,
        user_input: str,
        response: str,
        session_id: str,
        session_ctx: CoreSessionContext,
        built_ctx: BuiltContext | None,
        model: str,
        provider_name: str,
    ) -> None:
        """Background task for SQLite and LanceDB persistence."""
        try:
            context = MemorySessionContext(
                project=Path(built_ctx.project_root).name if (built_ctx and built_ctx.project_root) else Path(session_ctx.cwd).name,
                directory=session_ctx.cwd,
                active_files=[],
                inferred_intent=built_ctx.intent if built_ctx else "chat",
                time_of_day=str(built_ctx.time_of_day if built_ctx else datetime.now(timezone.utc).hour),
                shell=built_ctx.shell if built_ctx else "unknown",
            )
            episode = Episode(
                id=str(uuid4()),
                timestamp=datetime.now(timezone.utc),
                context=context,
                problem=user_input,
                process=None,
                solution=response,
                duration_seconds=None,
                friction_score=0.0,
                tags=["chat", f"provider:{provider_name}"],
                model_used=model,
                provider_used=provider_name,
            )
            if hasattr(self.memory_engine, "persist_async"):
                await self.memory_engine.persist_async(episode)

            persistent = getattr(self.memory_engine, "persistent", None)
            if persistent and hasattr(persistent, "save_chat_history"):
                await persistent.save_chat_history(session_id, user_input, response)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Background memory persistence failed: %s", exc)

    @classmethod
    async def create_default(cls) -> ChatEngine:
        """Factory for initializing ChatEngine with standard dependencies."""
        from jules.core.config import load_config
        from jules.core.permissions import PermissionGate
        from jules.core.router import _get_router
        from jules.memory.episodic import EpisodicMemory
        from jules.memory.persistent import PersistentMemory

        router = await _get_router()
        persistent = PersistentMemory()
        episodic = EpisodicMemory(Path.home() / ".jules" / "lancedb")

        try:
            scoring_provider, _ = await router.route(TaskType.MEMORY_SCORING)
        except Exception:
            scoring_provider = None

        class _ScoringAdapter:
            def __init__(self, prov: Any, model: str = "llama3.2:1b") -> None:
                self.provider = prov
                self.model = model

            async def generate_text(self, prompt: str) -> str:
                if hasattr(self.provider, "ask"):
                    return await self.provider.ask(prompt, [], self.model)
                return "SCORE: 0.5"

        class _NoopScoringProvider:
            async def generate_text(self, prompt: str) -> str:
                del prompt
                return "SCORE: 0.5"

        scoring_adapter = _ScoringAdapter(scoring_provider) if scoring_provider else _NoopScoringProvider()
        embedding_prov = scoring_provider if hasattr(scoring_provider, "embed") else None

        memory_engine = MemoryEngine(
            persistent=persistent,
            episodic=episodic,
            provider=scoring_adapter,
            embedding_provider=embedding_prov,
        )
        config = load_config()
        gate = PermissionGate(config.permissions)

        rebuild_task = asyncio.create_task(memory_engine.rebuild_vector_index_if_needed())
        memory_engine._background_tasks.add(rebuild_task)
        rebuild_task.add_done_callback(memory_engine._background_tasks.discard)

        return cls(
            router=router,
            memory_engine=memory_engine,
            personality_loader=PersonalityLoader(),
            sanitizer=Sanitizer,
            permission_gate=gate,
        )


_default_engine_instance: ChatEngine | None = None


async def stream_turn(state: ChatEngineState, message: str) -> AsyncIterator[StreamEvent]:
    """Compatibility wrapper for headless protocol callers."""
    global _default_engine_instance
    if _default_engine_instance is None:
        _default_engine_instance = await ChatEngine.create_default()

    core_ctx = CoreSessionContext(cwd=str(Path.cwd()))
    async for event in _default_engine_instance.stream_turn(
        user_input=message,
        session_id=str(uuid4()),
        session_ctx=core_ctx,
        chat_history=state.chat_history,
        user_override=state.user_model_override,
    ):
        if _default_engine_instance.last_provider:
            state.active_provider = _default_engine_instance.last_provider
        if _default_engine_instance.last_model:
            state.active_model = _default_engine_instance.last_model
        yield event


__all__ = [
    "ChatEngine",
    "ChatEngineState",
    "compose_prompt",
    "stream_turn",
]
