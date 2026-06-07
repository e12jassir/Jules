"""Pilot tests for slash command routing in ChatScreen."""
from __future__ import annotations

from pathlib import Path
import unittest

from textual.widgets import Input

from jules.cli.app import JulesApp
from jules.cli.screens.chat import ChatScreen
from jules.cli.widgets.chat_log import ChatLog

_THEME = Path(__file__).parent.parent.parent / "jules" / "cli" / "theme.tcss"


class _TestApp(JulesApp):
    CSS_PATH = str(_THEME)

    def process_message(self, message: str) -> None:  # type: ignore[override]
        pass


async def _open_chat(pilot) -> None:
    """Transition from WelcomeScreen to ChatScreen."""
    pilot.app.screen.query_one("#welcome-input", Input).value = "hi"
    await pilot.press("enter")
    await pilot.pause()


async def _submit_chat(pilot, text: str) -> None:
    """Submit text via the ChatScreen input."""
    chat_input = pilot.app.screen.query_one("#chat-input", Input)
    chat_input.focus()
    chat_input.value = text
    await pilot.press("enter")
    await pilot.pause()


def _chat_content(log: ChatLog) -> str:
    return "\n".join(log._blocks)


class TestChatCommands(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_slash_command_shows_error(self) -> None:
        async with _TestApp().run_test(size=(120, 40)) as pilot:
            await _open_chat(pilot)
            await _submit_chat(pilot, "/unknowncmd")
            log = pilot.app.screen.query_one(ChatLog)
            assert "unknowncmd" in _chat_content(log)

    async def test_clear_command_empties_chat_log(self) -> None:
        async with _TestApp().run_test(size=(120, 40)) as pilot:
            await _open_chat(pilot)
            log = pilot.app.screen.query_one(ChatLog)
            log.add_user_message("sentinel message")
            await pilot.pause()
            assert "sentinel message" in _chat_content(log)

            await _submit_chat(pilot, "/clear")
            assert "sentinel message" not in _chat_content(log)

    async def test_known_stub_command_replies(self) -> None:
        """Known commands wired to real handlers return provider output."""
        async with _TestApp().run_test(size=(120, 40)) as pilot:
            await _open_chat(pilot)
            await _submit_chat(pilot, "/status")
            log = pilot.app.screen.query_one(ChatLog)
            content = _chat_content(log)
            assert "providers" in content.lower() or "disponible" in content

    async def test_auth_command_shows_saved_auth_state(self) -> None:
        async with _TestApp().run_test(size=(120, 40)) as pilot:
            await _open_chat(pilot)
            await _submit_chat(pilot, "/auth")
            log = pilot.app.screen.query_one(ChatLog)
            content = _chat_content(log)
            assert "openai" in content.lower()
            assert "claude" in content.lower()

    async def test_exit_command_calls_app_exit(self) -> None:
        """Submitting /exit triggers app.exit() without raising exceptions."""
        exited = False

        class _ExitTracker(_TestApp):
            def exit(self, *args, **kwargs) -> None:  # type: ignore[override]
                nonlocal exited
                exited = True

        async with _ExitTracker().run_test(size=(120, 40)) as pilot:
            await _open_chat(pilot)
            await _submit_chat(pilot, "/exit")

        assert exited
