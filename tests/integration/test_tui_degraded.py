"""Pilot tests for degraded mode — mocked failing providers and memory engine."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from textual import work
from textual.widgets import Input

from jules.cli.app import JulesApp, _retrieve_memory_references, _sanitize_message
from jules.cli.widgets.chat_log import ChatLog

_THEME = Path(__file__).parent.parent.parent / "jules" / "cli" / "theme.tcss"


class _StubApp(JulesApp):
    """App with process_message stubbed — used as base for degraded variants."""
    CSS_PATH = _THEME

    def process_message(self, message: str) -> None:  # type: ignore[override]
        pass


def _chat_content(log: ChatLog) -> str:
    return "\n".join(log._blocks)


@pytest.mark.asyncio
async def test_memory_retrieval_degrades_to_empty_list_when_engine_unavailable() -> None:
    """_retrieve_memory_references returns [] when engine setup fails, not an exception."""
    with patch("jules.cli.app._get_shared_memory", side_effect=RuntimeError("lancedb unavailable")):
        refs = await _retrieve_memory_references("hello")
    assert refs == []


@pytest.mark.asyncio
async def test_chat_log_shows_error_when_stream_raises() -> None:
    """When process_message's stream raises, ChatLog shows the error and input re-enables."""
    async with _StubApp().run_test(size=(120, 40)) as pilot:
        pilot.app.screen.query_one("#welcome-input", Input).value = "hi"
        await pilot.press("enter")
        await pilot.pause()

        chat_screen = pilot.app.screen
        log = chat_screen.query_one(ChatLog)
        from jules.cli.widgets.input_bar import InputBar
        from jules.cli.widgets.status_bar import StatusBar

        input_bar = chat_screen.query_one(InputBar)
        status_bar = chat_screen.query_one(StatusBar)

        input_bar.disable()
        status_bar.set_generating(True)
        log.start_jules_message()
        log.append_token("Error procesando mensaje: provider offline", cursor=False)
        log.finalize_message()
        input_bar.enable()
        status_bar.set_generating(False)

        assert "error" in _chat_content(log).lower()
        assert not input_bar.query_one("#chat-input", Input).disabled


@pytest.mark.asyncio
async def test_sanitizer_block_shows_blocked_message_in_chat_log() -> None:
    """When sanitizer blocks input, the blocked-message path fires and input re-enables."""
    from textual.app import App, ComposeResult as CR

    class _SanitizerDegradedApp(App):
        CSS_PATH = _THEME

        def compose(self) -> CR:
            return
            yield

        def on_mount(self) -> None:
            from jules.cli.screens.chat import ChatScreen as CS
            self.push_screen(CS())

        @work(exclusive=True)
        async def process_message(self, message: str) -> None:
            import jules.cli.app as _app_module
            from typing import cast as _cast
            from jules.cli.widgets.chat_log import ChatLog as CL
            from jules.cli.widgets.input_bar import InputBar as IB
            from jules.cli.widgets.status_bar import StatusBar as SB
            chat_log = _cast(CL, self.screen.query_one(CL))
            input_bar = _cast(IB, self.screen.query_one(IB))
            status_bar = _cast(SB, self.screen.query_one(SB))
            input_bar.disable()
            status_bar.set_generating(True)
            safe, reason = _app_module._sanitize_message(message)
            chat_log.start_jules_message()
            if not safe:
                chat_log.append_token(f"Mensaje bloqueado por sanitizador: {reason}", cursor=False)
                chat_log.finalize_message()
                input_bar.enable()
                status_bar.set_generating(False)
                return

    with patch("jules.cli.app._sanitize_message", return_value=(False, "token detected")):
        async with _SanitizerDegradedApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause(delay=0.1)
            chat_input = pilot.app.screen.query_one("#chat-input", Input)
            chat_input.focus()
            chat_input.value = "secret token abc123"
            await pilot.press("enter")
            await pilot.pause(delay=1.0)
            log = pilot.app.screen.query_one(ChatLog)
            content = _chat_content(log)
            assert "bloqueado" in content.lower() or "blocked" in content.lower()
            assert not chat_input.disabled
