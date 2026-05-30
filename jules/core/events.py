from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import inspect
import logging
import os
from typing import Callable

from jules.core.session import SessionContext


class EventType(str, Enum):
    SESSION_STARTED = "session_started"
    PROJECT_OPENED = "project_opened"
    CODING_DETECTED = "coding_detected"
    IDLE_DETECTED = "idle_detected"
    SESSION_ENDED = "session_ended"


EventHandler = Callable[[dict], None]


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
        for handler in self._handlers.get(event_type, []):
            p = payload.copy()
            
            async def _run_handler(h=handler, p=p, e_type=event_type):
                try:
                    if inspect.iscoroutinefunction(h):
                        await h(p)
                    else:
                        await asyncio.to_thread(h, p)
                except Exception:
                    logging.getLogger(__name__).exception("Error in handler for %s", e_type)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                task = loop.create_task(_run_handler())
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            else:
                # Fallback para tests síncronos
                try:
                    if inspect.iscoroutinefunction(handler):
                        asyncio.run(handler(p))
                    else:
                        handler(p)
                except Exception:
                    logging.getLogger(__name__).exception("Error in handler for %s", event_type)

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
