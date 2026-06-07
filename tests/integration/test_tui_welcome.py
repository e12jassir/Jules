"""Pilot tests for WelcomeScreen."""
from __future__ import annotations

from pathlib import Path

import pytest

from jules.cli.app import JulesApp
from jules.cli.screens.welcome import BRAILLE_ROSE, WelcomeScreen
from jules.cli.widgets.status_bar import StatusBar

# Textual resolves CSS_PATH relative to the subclass file, so we must
# point it at the real theme from this test file's location.
_THEME = Path(__file__).parent.parent.parent / "jules" / "cli" / "theme.tcss"


class _TestApp(JulesApp):
    CSS_PATH = _THEME

    def process_message(self, message: str) -> None:  # type: ignore[override]
        pass


@pytest.mark.asyncio
async def test_welcome_screen_mounts() -> None:
    async with _TestApp().run_test(size=(120, 40)) as pilot:
        assert isinstance(pilot.app.screen, WelcomeScreen)


@pytest.mark.asyncio
async def test_welcome_screen_contains_logo() -> None:
    async with _TestApp().run_test(size=(120, 40)) as pilot:
        from textual.widgets import Static
        contents = [str(w.render()) for w in pilot.app.screen.query(Static)]
        assert any("j u l e s" in c or "JULES" in c or "██" in c for c in contents)


@pytest.mark.asyncio
async def test_welcome_screen_contains_braille_art() -> None:
    async with _TestApp().run_test(size=(120, 40)) as pilot:
        from textual.widgets import Static
        contents = [str(w.render()) for w in pilot.app.screen.query(Static)]
        first_line = BRAILLE_ROSE.splitlines()[0]
        assert any(first_line in c for c in contents)


@pytest.mark.asyncio
async def test_welcome_screen_has_input() -> None:
    async with _TestApp().run_test(size=(120, 40)) as pilot:
        from textual.widgets import Input
        assert len(list(pilot.app.screen.query(Input))) == 1
