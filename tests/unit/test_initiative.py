"""Unit tests for Contextual Initiative Engine ('El Fantasma en la Shell').

Tests CooldownRegistry, shell friction triggers, project resumed recap,
prolonged stall unblocking, and graceful desktop notification.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jules.core.events import EventBus, EventType
from jules.memory.models import Episode, SessionContext as MemSessionContext
from jules.platform.initiative import (
    CooldownRegistry,
    InitiativeEngine,
    InitiativeIntervention,
    InitiativeTriggerType,
)


# ---------------------------------------------------------------------------
# 1. CooldownRegistry Tests (Golden Rule)
# ---------------------------------------------------------------------------


def test_cooldown_registry_enforces_golden_rule() -> None:
    """Golden Rule: Jules is strictly forbidden from interrupting twice for the same reason in the same session."""
    registry = CooldownRegistry()
    session_id = "session_alpha"
    reason = "shell_friction:cargo build"

    # Initially allowed
    assert registry.can_trigger(session_id, reason) is True

    # Record intervention
    registry.record(session_id, reason)

    # Immediately blocked for the exact same reason in the same session
    assert registry.can_trigger(session_id, reason) is False

    # Check atomic check_and_record
    assert registry.check_and_record(session_id, reason) is False

    # Different reason in same session is allowed
    different_reason = "shell_friction:pytest"
    assert registry.can_trigger(session_id, different_reason) is True
    assert registry.check_and_record(session_id, different_reason) is True
    assert registry.can_trigger(session_id, different_reason) is False

    # Same original reason in a DIFFERENT session is allowed
    other_session = "session_beta"
    assert registry.can_trigger(other_session, reason) is True
    assert registry.check_and_record(other_session, reason) is True
    assert registry.can_trigger(other_session, reason) is False

    # Resetting session clears its cooldowns
    registry.reset(session_id)
    assert registry.can_trigger(session_id, reason) is True
    assert registry.can_trigger(session_id, different_reason) is True
    # other_session remains recorded
    assert registry.can_trigger(other_session, reason) is False

    # Global reset clears everything
    registry.reset()
    assert registry.can_trigger(other_session, reason) is True


# ---------------------------------------------------------------------------
# 2. Trigger 1: Shell Friction / Consecutive Command Errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shell_friction_trigger_with_episodic_memory() -> None:
    """Two consecutive exit_code != 0 within 3 minutes triggers initiative check,
    queries episodic memory for past troubleshooting, dispatches suggestion,
    and a third failure is silenced by CooldownRegistry.
    """
    event_bus = EventBus()
    dispatched_events: list[dict] = []
    event_bus.subscribe(EventType.INITIATIVE_TRIGGERED, dispatched_events.append)

    # Mock past troubleshooting episode
    past_episode = Episode(
        id="ep-101",
        timestamp=datetime.now(timezone.utc) - timedelta(days=2),
        context=MemSessionContext(
            project="backend",
            directory="/workspace/backend",
            active_files=["main.py"],
            inferred_intent="debugging",
            time_of_day="morning",
        ),
        problem="pytest fails with ModuleNotFoundError: No module named requests",
        process="Checked poetry environment",
        solution="poetry install or use poetry run pytest",
        duration_seconds=120,
        friction_score=0.8,
    )

    mock_episodic = AsyncMock()
    mock_persistent = AsyncMock()
    mock_persistent.get_many_async.return_value = [past_episode]
    mock_persistent.get_async.return_value = past_episode
    mock_episodic.retrieve_async.return_value = ["ep-101"]

    desktop_notifications: list[tuple[str, str]] = []

    async def fake_notifier(title: str, message: str) -> bool:
        desktop_notifications.append((title, message))
        return True

    engine = InitiativeEngine(
        event_bus=event_bus,
        episodic_memory=mock_episodic,
        persistent_memory=mock_persistent,
        desktop_notifier=fake_notifier,
    )

    session_id = "test_session_1"
    cmd = "pytest tests/"

    # Failure 1: exit_code = 1 -> First failure, does not trigger yet
    intv1 = await engine.on_shell_event(
        cmd=cmd,
        exit_code=1,
        cwd="/workspace/backend",
        session_id=session_id,
        timestamp=1000.0,
    )
    assert intv1 is None
    assert len(desktop_notifications) == 0
    assert len(dispatched_events) == 0

    # Failure 2: exit_code = 1 within 3 minutes (e.g. 30s later at 1030.0) -> TRIGGERS
    intv2 = await engine.on_shell_event(
        cmd=cmd,
        exit_code=1,
        cwd="/workspace/backend",
        session_id=session_id,
        timestamp=1030.0,
    )
    assert intv2 is not None
    assert intv2.trigger_type == InitiativeTriggerType.SHELL_FRICTION
    assert "poetry run pytest" in intv2.message or "poetry" in intv2.message
    assert len(desktop_notifications) == 1
    assert "Jules" in desktop_notifications[0][0]
    assert len(dispatched_events) == 1
    assert dispatched_events[0]["trigger_type"] == InitiativeTriggerType.SHELL_FRICTION.value

    # Failure 3: exit_code = 1 within 3 minutes for same command -> SILENCED by Golden Rule
    intv3 = await engine.on_shell_event(
        cmd=cmd,
        exit_code=1,
        cwd="/workspace/backend",
        session_id=session_id,
        timestamp=1050.0,
    )
    assert intv3 is None
    # Still only 1 notification dispatched, Golden Rule prevented 2nd notification
    assert len(desktop_notifications) == 1
    assert len(dispatched_events) == 1


@pytest.mark.asyncio
async def test_shell_friction_no_trigger_if_spaced_out_over_3_minutes() -> None:
    """Failures spaced more than 3 minutes (180s) apart should NOT trigger initiative."""
    engine = InitiativeEngine()
    session_id = "test_session_spaced"

    # Failure 1 at t=0
    res1 = await engine.on_shell_event(
        cmd="make build",
        exit_code=2,
        cwd="/workspace",
        session_id=session_id,
        timestamp=0.0,
    )
    assert res1 is None

    # Failure 2 at t=185 (more than 180 seconds later)
    res2 = await engine.on_shell_event(
        cmd="make build",
        exit_code=2,
        cwd="/workspace",
        session_id=session_id,
        timestamp=185.0,
    )
    assert res2 is None


@pytest.mark.asyncio
async def test_shell_friction_resets_on_success() -> None:
    """A successful exit_code == 0 resets the consecutive failure streak."""
    engine = InitiativeEngine()
    session_id = "test_session_reset"

    # 1st failure
    await engine.on_shell_event(
        cmd="cargo check",
        exit_code=1,
        cwd="/workspace",
        session_id=session_id,
        timestamp=100.0,
    )
    # Success in between
    await engine.on_shell_event(
        cmd="cargo check",
        exit_code=0,
        cwd="/workspace",
        session_id=session_id,
        timestamp=120.0,
    )
    # 2nd failure (streak is only 1 now)
    res = await engine.on_shell_event(
        cmd="cargo check",
        exit_code=1,
        cwd="/workspace",
        session_id=session_id,
        timestamp=140.0,
    )
    assert res is None


# ---------------------------------------------------------------------------
# 3. Trigger 2: Project Resumed (> 14 days old recap)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_resumed_trigger_over_14_days() -> None:
    """EventType.PROJECT_OPENED with last episode > 14 days old yields an executive 1-line recap."""
    event_bus = EventBus()
    dispatched_events: list[dict] = []
    event_bus.subscribe(EventType.INITIATIVE_TRIGGERED, dispatched_events.append)

    old_timestamp = datetime.now(timezone.utc) - timedelta(days=21)
    old_episode = Episode(
        id="ep-old-proj",
        timestamp=old_timestamp,
        context=MemSessionContext(
            project="antigravity",
            directory="/home/user/antigravity",
            active_files=["cli.py"],
            inferred_intent="feature implementation",
            time_of_day="afternoon",
        ),
        problem="Migrate database schema to v2",
        process="Wrote alembic script",
        solution="Alembic revision created and verified passing tests",
        duration_seconds=900,
        friction_score=0.2,
    )

    mock_persistent = AsyncMock()
    mock_persistent.list_all_episodes_async.return_value = [old_episode]

    notifications: list[str] = []

    async def fake_notifier(title: str, message: str) -> bool:
        notifications.append(message)
        return True

    engine = InitiativeEngine(
        event_bus=event_bus,
        persistent_memory=mock_persistent,
        desktop_notifier=fake_notifier,
    )

    # Trigger project opened via method
    intervention = await engine.on_project_opened(
        directory="/home/user/antigravity",
        session_id="session_resumed",
    )

    assert intervention is not None
    assert intervention.trigger_type == InitiativeTriggerType.PROJECT_RESUMED
    assert "antigravity" in intervention.message
    assert "Alembic revision created" in intervention.message or "schema" in intervention.message
    assert len(notifications) == 1
    assert len(dispatched_events) == 1

    # Second open in the same session is silenced by CooldownRegistry
    intervention_second = await engine.on_project_opened(
        directory="/home/user/antigravity",
        session_id="session_resumed",
    )
    assert intervention_second is None
    assert len(notifications) == 1


@pytest.mark.asyncio
async def test_project_resumed_not_triggered_for_recent_project() -> None:
    """Project opened with last episode <= 14 days old should NOT trigger recap."""
    recent_timestamp = datetime.now(timezone.utc) - timedelta(days=3)
    recent_episode = Episode(
        id="ep-recent",
        timestamp=recent_timestamp,
        context=MemSessionContext(
            project="recent_app",
            directory="/home/user/recent_app",
            active_files=["index.ts"],
            inferred_intent="coding",
            time_of_day="night",
        ),
        problem=None,
        process=None,
        solution=None,
        duration_seconds=60,
        friction_score=0.1,
    )

    mock_persistent = AsyncMock()
    mock_persistent.list_all_episodes_async.return_value = [recent_episode]

    engine = InitiativeEngine(persistent_memory=mock_persistent)
    intervention = await engine.on_project_opened(
        directory="/home/user/recent_app",
        session_id="session_recent",
    )
    assert intervention is None


# ---------------------------------------------------------------------------
# 4. Trigger 3: Prolonged Stall Detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prolonged_stall_trigger_single_inquiry() -> None:
    """Long modification cycle with test failures produces a single unblocking inquiry."""
    event_bus = EventBus()
    notifications: list[str] = []

    async def fake_notifier(title: str, message: str) -> bool:
        notifications.append(message)
        return True

    engine = InitiativeEngine(
        event_bus=event_bus,
        desktop_notifier=fake_notifier,
        stall_threshold_seconds=120.0,  # 2 minutes for test (default 7200s = 2h)
    )

    session_id = "session_stall"
    file_path = "/workspace/src/auth.py"

    # 1. Start editing at t=0
    engine.on_file_modified(file_path=file_path, timestamp=0.0)

    # 2. Test failure at t=30
    await engine.on_shell_event(
        cmd="pytest tests/test_auth.py",
        exit_code=1,
        cwd="/workspace",
        session_id=session_id,
        timestamp=30.0,
    )

    # Still under threshold (30s < 120s)
    check1 = await engine.check_stall(session_id=session_id, current_time=50.0)
    assert check1 is None

    # 3. Another edit at t=210 (exceeds 120s stall threshold since t=0)
    engine.on_file_modified(file_path=file_path, timestamp=210.0)

    # 4. Another test failure at t=220 (> 180s from first failure so shell friction doesn't trigger)
    await engine.on_shell_event(
        cmd="pytest tests/test_auth.py",
        exit_code=1,
        cwd="/workspace",
        session_id=session_id,
        timestamp=220.0,
    )

    # Check stall now
    intv = await engine.check_stall(session_id=session_id, current_time=230.0)
    assert intv is not None
    assert intv.trigger_type == InitiativeTriggerType.STALL_DETECTED
    assert "auth.py" in intv.message
    assert len(notifications) == 1

    # Second check is silenced by CooldownRegistry (single inquiry rule)
    intv_repeat = await engine.check_stall(session_id=session_id, current_time=240.0)
    assert intv_repeat is None
    assert len(notifications) == 1


# ---------------------------------------------------------------------------
# 5. Desktop Notification Graceful Fallback (notify-send)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graceful_desktop_notification_success() -> None:
    """When notify-send is available and returns exit code 0, notification succeeds."""
    engine = InitiativeEngine()

    with patch("shutil.which", return_value="/usr/bin/notify-send"), \
         patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.wait = AsyncMock(return_value=0)
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc

        result = await engine.notify_desktop("Jules Proactive", "Test message")
        assert result is True
        mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_graceful_desktop_notification_not_installed() -> None:
    """When notify-send is missing, notify_desktop fails gracefully without crashing."""
    engine = InitiativeEngine()

    with patch("shutil.which", return_value=None):
        result = await engine.notify_desktop("Jules Proactive", "Test message")
        assert result is False


@pytest.mark.asyncio
async def test_graceful_desktop_notification_error() -> None:
    """When notify-send fails with error or exception, it returns False gracefully."""
    engine = InitiativeEngine()

    with patch("shutil.which", return_value="/usr/bin/notify-send"), \
         patch("asyncio.create_subprocess_exec", side_effect=OSError("D-Bus error")):
        result = await engine.notify_desktop("Jules Proactive", "Test message")
        assert result is False
