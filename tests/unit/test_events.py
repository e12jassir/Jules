from __future__ import annotations

import logging

import pytest

from jules.core.events import EventBus, EventType
from jules.core.session import SessionContext


def test_event_bus_can_be_created_without_session_context() -> None:
    bus = EventBus()
    observed: list[dict] = []

    bus.subscribe(EventType.CODING_DETECTED, observed.append)
    bus.emit(EventType.CODING_DETECTED, {"file_path": "main.py"})

    assert observed == [{"file_path": "main.py"}]


def test_event_bus_uses_simple_dict_for_handlers() -> None:
    bus = EventBus()

    assert type(bus._handlers) is dict


def test_event_bus_routes_events_to_subscribers(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    session = SessionContext(cwd="/tmp")
    bus = EventBus(session=session)
    observed: list[dict] = []

    bus.subscribe(EventType.CODING_DETECTED, observed.append)
    bus.emit(EventType.CODING_DETECTED, {"file_path": "main.py"})

    assert observed == [{"file_path": "main.py"}]
    assert bus.runtime.last_activity_at is not None


def test_project_opened_updates_active_directory(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    session = SessionContext(cwd="/old")
    bus = EventBus(session=session)

    bus.emit(EventType.PROJECT_OPENED, {"directory": "/new"})

    assert session.cwd == "/new"


def test_session_started_requires_shell_environment(monkeypatch) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    bus = EventBus(session=SessionContext(cwd="/tmp"))

    bus.emit(EventType.SESSION_STARTED, {})
    assert bus.runtime.shell == "unknown"


def test_session_started_records_detected_shell(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    bus = EventBus(session=SessionContext(cwd="/tmp"))

    bus.emit(EventType.SESSION_STARTED, {})

    assert bus.runtime.shell == "/usr/bin/zsh"


def test_idle_detected_marks_runtime_idle(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    bus = EventBus(session=SessionContext(cwd="/tmp"))

    bus.emit(EventType.IDLE_DETECTED, {})

    assert bus.runtime.is_idle is True


def test_session_ended_records_end_state(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    bus = EventBus(session=SessionContext(cwd="/tmp"))

    bus.emit(EventType.SESSION_ENDED, {"summary": "done"})

    assert bus.runtime.ended_at is not None
    assert bus.runtime.summary == "done"


async def test_emit_updates_default_handlers_before_returning(monkeypatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    bus = EventBus(session=SessionContext(cwd="/tmp"))

    bus.emit(EventType.CODING_DETECTED, {"file_path": "main.py"})

    import asyncio
    for _ in range(10):
        if bus.runtime.last_activity_at is not None:
            break
        await asyncio.sleep(0.05)

    assert bus.runtime.last_activity_at is not None


@pytest.mark.asyncio
async def test_async_handlers_are_executed_properly() -> None:
    bus = EventBus()
    observed: list[dict] = []

    async def handler(payload: dict) -> None:
        observed.append(payload)

    bus.subscribe(EventType.CODING_DETECTED, handler)
    bus.emit(EventType.CODING_DETECTED, {"file_path": "async.py"})
    
    import asyncio
    await asyncio.sleep(0) # allow background task to run

    assert observed == [{"file_path": "async.py"}]


def test_handler_errors_keep_traceback_and_isolate_other_handlers(caplog) -> None:
    bus = EventBus()
    observed: list[dict] = []

    def failing_handler(payload: dict) -> None:
        del payload
        raise RuntimeError("boom")

    bus.subscribe(EventType.CODING_DETECTED, failing_handler)
    bus.subscribe(EventType.CODING_DETECTED, observed.append)

    with caplog.at_level(logging.ERROR):
        bus.emit(EventType.CODING_DETECTED, {"file_path": "main.py"})

    assert observed == [{"file_path": "main.py"}]
    assert "Traceback" in caplog.text
    assert "RuntimeError: boom" in caplog.text
