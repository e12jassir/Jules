"""IPC server handlers — bridge protocol messages to Jules subsystems."""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections.abc import AsyncGenerator
from typing import Any

from jules.server.protocol import (
    CancelledEvent,
    CommandResultEvent,
    DoneEvent,
    ErrorEvent,
    IpcMessage,
    ModelChangedEvent,
    ModelListEvent,
    ReadyEvent,
    StatusEvent,
    TokenEvent,
)

logger = logging.getLogger(__name__)

_BOOT_TIME: float = time.perf_counter()

# Mutable override state for model_set
_override_provider: str | None = None
_override_model: str | None = None


def handle_init(protocol_version: int) -> ReadyEvent:
    boot_ms = (time.perf_counter() - _BOOT_TIME) * 1000
    return ReadyEvent(protocol_version=protocol_version, boot_ms=boot_ms)


async def handle_message(content: str) -> AsyncGenerator[IpcMessage, None]:
    """Route user message through the cognitive router and stream tokens."""
    token_count = 0
    try:
        from jules.core.router import CognitiveRouter, TaskType
        from jules.memory.models import SessionContext

        context = SessionContext(
            project=None,
            directory=".",
            active_files=[],
            inferred_intent=None,
            time_of_day="unknown",
        )

        router = CognitiveRouter()
        task_type = TaskType.QUICK
        user_override = f"{_override_provider}:{_override_model}" if _override_provider else None

        provider, model = router.route(task_type, user_override=user_override)

        # Try streaming first
        stream = provider.stream(content, context, model)
        async for chunk in stream:
            token_count += 1
            yield TokenEvent(content=chunk)
    except Exception as exc:
        # If streaming fails, try non-streaming ask
        try:
            response, model, provider_name = await router.ask_with_fallback(
                content, context, task_type, user_override=user_override
            )
            token_count = 1
            yield TokenEvent(content=response)
        except Exception as inner_exc:
            logger.error("handle_message failed: %s", inner_exc)
            yield ErrorEvent(message=str(inner_exc), recoverable=True)

    yield DoneEvent(tokens=token_count)


def handle_cancel(active_task: asyncio.Task[Any] | None) -> CancelledEvent:
    if active_task is not None and not active_task.done():
        active_task.cancel()
    return CancelledEvent()


def handle_model_list() -> ModelListEvent:
    """Read available models from config via the router's registry."""
    try:
        from jules.core.router import CognitiveRouter

        router = CognitiveRouter()
        models = router.available_models()
        return ModelListEvent(models=[list(pair) for pair in models])
    except Exception as exc:
        logger.error("handle_model_list failed: %s", exc)
        return ModelListEvent(models=[["ollama", "llama3.2:1b"]])


def handle_model_set(provider: str, model: str) -> ModelChangedEvent:
    global _override_provider, _override_model
    _override_provider = provider
    _override_model = model
    return ModelChangedEvent(provider=provider, model=model)


def _status_get_sync() -> StatusEvent:
    """Blocking I/O — run via run_in_executor, never call from the event loop directly."""
    online = False
    episodes = 0
    scoring_healthy = True

    try:
        import httpx

        resp = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        online = resp.status_code == 200
    except Exception:
        pass

    try:
        import sqlite3

        from jules.memory.persistent import DEFAULT_SQLITE_PATH

        db_path = DEFAULT_SQLITE_PATH
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM episodes")
            episodes = cursor.fetchone()[0]
            conn.close()
    except Exception:
        pass

    return StatusEvent(online=online, episodes=episodes, scoring_healthy=scoring_healthy)


async def handle_status_get() -> StatusEvent:
    """Non-blocking: offloads sync I/O (httpx + SQLite) to a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _status_get_sync)


def handle_command(name: str, args: list[str]) -> CommandResultEvent:
    """Dispatch known commands, return error for unknown."""
    known = {"doctor", "status", "memory", "debug"}
    if name not in known:
        return CommandResultEvent(name=name, ok=False, error=f"Unknown command: {name}")
    # For now, commands return a placeholder — full dispatch can be wired later
    return CommandResultEvent(name=name, ok=True, data={"info": f"Command '{name}' acknowledged"})


def handle_quit() -> None:
    sys.stdout.flush()
    raise SystemExit(0)
