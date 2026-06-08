from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable, Callable

from jules.core.session import SessionContext
from jules.core.permissions import IS_BACKGROUND_TASK, PermissionDeniedError


class EventType(str, Enum):
    SESSION_STARTED = "session_started"
    PROJECT_OPENED = "project_opened"
    CODING_DETECTED = "coding_detected"
    IDLE_DETECTED = "idle_detected"
    SESSION_ENDED = "session_ended"


EventHandler = Callable[[dict], None | Awaitable[None]]


@dataclass(slots=True)
class EventRuntimeState:
    shell: str = "unknown"
    last_activity_at: datetime | None = None
    is_idle: bool = False
    ended_at: datetime | None = None
    summary: str | None = None


@dataclass(slots=True)
class EventBus:
    session: SessionContext | None = None
    runtime: EventRuntimeState = field(default_factory=EventRuntimeState)
    _handlers: dict[EventType, list[EventHandler]] = field(
        default_factory=dict, init=False, compare=False
    )
    _background_tasks: set[asyncio.Task] = field(
        default_factory=set, init=False, compare=False
    )

    def __post_init__(self) -> None:
        self.subscribe(EventType.SESSION_STARTED, self._on_session_started)
        self.subscribe(EventType.PROJECT_OPENED, self._on_project_opened)
        self.subscribe(EventType.CODING_DETECTED, self._on_coding_detected)
        self.subscribe(EventType.IDLE_DETECTED, self._on_idle_detected)
        self.subscribe(EventType.SESSION_ENDED, self._on_session_ended)

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event_type: EventType, payload: dict) -> None:
        import asyncio
        import threading
        
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        def _get_handler_coro(h, p, e_type):
            async def _run_handler():
                IS_BACKGROUND_TASK.set(True)
                try:
                    if inspect.iscoroutinefunction(h):
                        await h(p)
                    else:
                        await asyncio.to_thread(h, p)
                except PermissionDeniedError as denial:
                    logging.getLogger(__name__).warning(
                        "permission_denied",
                        extra={
                            "event": str(e_type),
                            "denial": {
                                "action": denial.action.value,
                                "target": denial.target,
                                "classification": denial.classification.value,
                                "reason": denial.reason,
                            }
                        }
                    )
                except Exception:
                    logging.getLogger(__name__).exception("Error in handler for %s", e_type)
            return _run_handler()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            for handler in handlers:
                task = loop.create_task(_get_handler_coro(handler, payload.copy(), event_type))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
        else:
            # Synchronous fallback keeps the same background context and
            # structured PermissionDeniedError handling as the task path.
            # Runs in a background thread to prevent blocking.
            def _run_all_sync(handlers_list, e_type, p_dict):
                async def _run_all_async():
                    tasks = [asyncio.create_task(_get_handler_coro(h, p_dict.copy(), e_type)) for h in handlers_list]
                    if tasks:
                        await asyncio.gather(*tasks)
                asyncio.run(_run_all_async())

            threading.Thread(target=_run_all_sync, args=(handlers, event_type, payload), daemon=True).start()

    def _on_session_started(self, payload: dict) -> None:
        del payload
        self.runtime.shell = os.environ.get("SHELL", "unknown")

    def _on_project_opened(self, payload: dict) -> None:
        directory = payload.get("directory")
        if self.session is not None and isinstance(directory, str) and directory:
            self.session.cwd = directory

    def _on_coding_detected(self, payload: dict) -> None:
        del payload
        self.runtime.last_activity_at = datetime.now(timezone.utc)
        self.runtime.is_idle = False

    def _on_idle_detected(self, payload: dict) -> None:
        del payload
        self.runtime.is_idle = True

    def _on_session_ended(self, payload: dict) -> None:
        self.runtime.ended_at = datetime.now(timezone.utc)
        summary = payload.get("summary")
        if isinstance(summary, str) and summary:
            self.runtime.summary = summary
