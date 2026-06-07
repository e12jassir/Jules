"""Pilot tests for ChatScreen — welcome→chat transition and token streaming."""
from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input

from jules.cli.app import JulesApp
from jules.cli.screens.chat import ChatScreen
from jules.cli.widgets.chat_log import ChatLog

_THEME = Path(__file__).parent.parent.parent / "jules" / "cli" / "theme.tcss"


class _TestApp(JulesApp):
    CSS_PATH = _THEME

    def process_message(self, message: str) -> None:  # type: ignore[override]
        pass


async def _submit_welcome(pilot, text: str) -> None:
    """Helper: fill and submit the welcome input."""
    pilot.app.screen.query_one("#welcome-input", Input).value = text
    await pilot.press("enter")
    await pilot.pause()


def _chat_content(log: ChatLog) -> str:
    """Return all text in the chat log blocks for assertion."""
    return "\n".join(log._blocks)


@pytest.mark.asyncio
async def test_welcome_to_chat_transition() -> None:
    """Submitting a message from WelcomeScreen pushes ChatScreen."""
    async with _TestApp().run_test(size=(120, 40)) as pilot:
        await _submit_welcome(pilot, "hello jules")
        assert isinstance(pilot.app.screen, ChatScreen)


@pytest.mark.asyncio
async def test_chat_screen_shows_user_message_after_transition() -> None:
    """The initial message sent from WelcomeScreen appears in ChatLog."""
    async with _TestApp().run_test(size=(120, 40)) as pilot:
        await _submit_welcome(pilot, "hello jules")
        log = pilot.app.screen.query_one(ChatLog)
        assert "hello jules" in _chat_content(log)


@pytest.mark.asyncio
async def test_chat_log_append_token_updates_content() -> None:
    """append_token() accumulates text in the active response bubble."""
    async with _TestApp().run_test(size=(120, 40)) as pilot:
        await _submit_welcome(pilot, "ping")
        log = pilot.app.screen.query_one(ChatLog)
        log.start_jules_message()
        log.append_token("tok1")
        log.append_token("tok2")
        content = _chat_content(log)
        assert "tok1" in content
        assert "tok2" in content


@pytest.mark.asyncio
async def test_chat_log_finalize_removes_cursor() -> None:
    """finalize_message() removes the streaming cursor ▌."""
    async with _TestApp().run_test(size=(120, 40)) as pilot:
        await _submit_welcome(pilot, "ping")
        log = pilot.app.screen.query_one(ChatLog)
        log.start_jules_message()
        log.append_token("response")
        log.finalize_message()
        # After finalize the active widget body should not contain the cursor
        assert log._active_msg is None
