from __future__ import annotations

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jules.core.config import PermissionsConfig
from jules.core.permissions import (
    PermissionGate,
    Action,
    PermissionClassification,
    PermissionDeniedError,
    IS_BACKGROUND_TASK,
)


@pytest.mark.asyncio
async def test_foreground_prompt_transient() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)

    with patch("jules.core.permissions._read_single_key", new_callable=AsyncMock) as mock_read, \
         patch("rich.live.Live") as mock_live_cls:
        mock_read.return_value = "y"

        mock_live_instance = MagicMock()
        mock_live_cls.return_value.__enter__.return_value = mock_live_instance

        approved = await gate._prompt_foreground(Action.PACKAGE_OP, "pacman -Syu")

        assert approved is True
        mock_live_cls.assert_called_once()
        _, kwargs = mock_live_cls.call_args
        assert kwargs.get("transient") is True
        mock_read.assert_called_once()


@pytest.mark.asyncio
async def test_background_prompt_subprocess_wait() -> None:
    config = PermissionsConfig()
    gate = PermissionGate(config)

    # Mock DISPLAY environment
    with patch.dict(os.environ, {"DISPLAY": ":0"}), \
         patch("shutil.which", return_value="/usr/bin/notify-send"):

        # Create a mock process
        mock_proc = AsyncMock()

        async def mock_communicate():
            # yield control to let sibling tasks run
            await asyncio.sleep(0.05)
            return b"approve\n", b""

        mock_proc.communicate = mock_communicate
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_spawn:
            sibling_ran = False

            async def sibling_task():
                nonlocal sibling_ran
                await asyncio.sleep(0.01)
                sibling_ran = True

            loop = asyncio.get_running_loop()

            token = IS_BACKGROUND_TASK.set(True)
            try:
                check_task = loop.create_task(gate.check(Action.PACKAGE_OP, "pacman -Syu"))
                sib_task = loop.create_task(sibling_task())

                await asyncio.gather(check_task, sib_task)

                assert sibling_ran is True

                mock_spawn.assert_called_once()
                args, _ = mock_spawn.call_args
                assert "notify-send" in args
                assert "--action=approve=Approve" in args
                assert "--action=deny=Deny" in args
                assert "--wait" in args
            finally:
                IS_BACKGROUND_TASK.reset(token)


@pytest.mark.asyncio
async def test_event_bus_graceful_degradation() -> None:
    from jules.core.events import EventBus, EventType

    config = PermissionsConfig()
    gate = PermissionGate(config)

    handler1_ran = False
    handler2_ran = False

    async def handler1(payload):
        nonlocal handler1_ran
        handler1_ran = True
        await gate.check(Action.SHELL_COMMAND, "rm -rf /")

    async def handler2(payload):
        nonlocal handler2_ran
        handler2_ran = True

    bus = EventBus()
    bus.subscribe(EventType.SESSION_STARTED, handler1)
    bus.subscribe(EventType.SESSION_STARTED, handler2)

    # Emit event
    bus.emit(EventType.SESSION_STARTED, {})

    # Wait for the EventBus background tasks to complete
    await asyncio.sleep(0.05)

    assert handler1_ran is True
    assert handler2_ran is True
