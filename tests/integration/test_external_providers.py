from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jules.core.config import load_config
from jules.memory.models import SessionContext
from jules.providers.antigravity import AntigravityProvider
from jules.providers.base import ProviderTimeoutError, ProviderUnavailableError
from jules.providers.opencode import OpenCodeProvider


OPENCODE_TEST_MODEL = "opencode/deepseek-v4-flash-free"


def _context() -> SessionContext:
    return SessionContext(
        project="jules",
        directory=str(Path(__file__).parents[2]),
        active_files=["jules/providers/antigravity.py", "jules/providers/opencode.py"],
        inferred_intent="testing",
        time_of_day="afternoon",
    )


def _require_cli(executable: str) -> None:
    if shutil.which(executable) is None:
        pytest.skip(f"{executable} CLI is required for this integration test")


def _antigravity_test_model() -> str:
    config = load_config()
    tier = config.routing.tiers[config.routing.default_tier]
    if not tier.antigravity:
        pytest.skip("config.toml default tier must define an Antigravity model")
    return tier.antigravity[0]


async def test_antigravity_health_check_returns_true_when_cli_is_available() -> None:
    _require_cli("agy")
    provider = AntigravityProvider(timeout_seconds=30.0)
    try:
        result = await provider.health_check()
    finally:
        await provider.close()
    assert result is True


async def test_antigravity_ask_returns_non_empty_response() -> None:
    _require_cli("agy")
    model = _antigravity_test_model()
    provider = AntigravityProvider(timeout_seconds=60.0, models=(model,))
    try:
        response = await provider.ask("Responde Hola", _context(), model)
    finally:
        await provider.close()

    assert isinstance(response, str)
    assert response.strip()


async def test_antigravity_timeout_raises_provider_timeout_error() -> None:
    _require_cli("agy")
    model = _antigravity_test_model()
    provider = AntigravityProvider(timeout_seconds=0.001, models=(model,))
    try:
        with pytest.raises(ProviderTimeoutError):
            await provider.ask("Responde Hola", _context(), model)
    finally:
        await provider.close()


async def test_opencode_health_check_returns_true_when_cli_is_available() -> None:
    _require_cli("opencode")
    provider = OpenCodeProvider(timeout_seconds=30.0)
    try:
        result = await provider.health_check()
    finally:
        await provider.close()
    assert result is True


async def test_opencode_ask_returns_non_empty_response() -> None:
    _require_cli("opencode")
    provider = OpenCodeProvider(timeout_seconds=60.0)
    try:
        response = await provider.ask("Responde Jules", _context(), OPENCODE_TEST_MODEL)
    finally:
        await provider.close()

    assert isinstance(response, str)
    assert response.strip()


async def test_opencode_timeout_raises_provider_timeout_error() -> None:
    _require_cli("opencode")
    provider = OpenCodeProvider(timeout_seconds=0.001)
    try:
        with pytest.raises(ProviderTimeoutError):
            await provider.ask("Responde Jules", _context(), OPENCODE_TEST_MODEL)
    finally:
        await provider.close()


async def test_antigravity_raises_unavailable_when_binary_missing() -> None:
    model = _antigravity_test_model()
    provider = AntigravityProvider(models=(model,))
    provider.executable = "__nonexistent_cli_xyz__"
    with pytest.raises(ProviderUnavailableError):
        await provider.ask("hello", context=_context(), model=model)


async def test_opencode_raises_unavailable_when_binary_missing() -> None:
    provider = OpenCodeProvider()
    provider.executable = "__nonexistent_cli_xyz__"
    with pytest.raises(ProviderUnavailableError):
        await provider.ask("hello", context=_context(), model="openai/gpt-4o")


async def test_antigravity_stream_raises_not_implemented() -> None:
    provider = AntigravityProvider()
    with pytest.raises(NotImplementedError):
        provider.stream("hello", context=_context(), model="ignored")


async def test_antigravity_embed_raises_not_implemented() -> None:
    provider = AntigravityProvider()
    with pytest.raises(NotImplementedError):
        await provider.embed("hello")


async def test_opencode_stream_raises_not_implemented() -> None:
    provider = OpenCodeProvider()
    with pytest.raises(NotImplementedError):
        provider.stream("hello", context=_context(), model="openai/gpt-4o")


async def test_opencode_embed_raises_not_implemented() -> None:
    provider = OpenCodeProvider()
    with pytest.raises(NotImplementedError):
        await provider.embed("hello")
