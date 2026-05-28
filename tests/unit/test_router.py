from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jules.core.config import load_config
from jules.core.router import CognitiveRouter, TaskType
from jules.memory.models import SessionContext
from jules.providers.antigravity import AntigravityProvider
from jules.providers.base import ProviderError, ProviderTimeoutError, ProviderUnavailableError


CONFIG_TEXT = """
[routing]
default_tier = "low_cost"

[routing.tiers.free]
provider = "ollama"
models = ["local-test-model", "llama3.2:1b"]

[routing.tiers.low_cost]
antigravity = ["ag-low", "ag-low-secondary"]
opencode = ["oc-low", "oc-low-secondary"]

[routing.tiers.high_cost]
antigravity = ["ag-high"]
opencode = ["oc-high"]

[routing.fallback]
chain = ["primary", "ollama"]

[providers.ollama]
base_url = "http://localhost:11434"
timeout_seconds = 30

[providers.antigravity]
timeout_seconds = 60

[providers.opencode]
timeout_seconds = 60
"""


class FakeProvider:
    def __init__(self, name: str, response: str | None = None, error: Exception | None = None) -> None:
        self.name = name
        self.response = response or f"{name}-response"
        self.error = error
        self.calls: list[tuple[str, SessionContext, str]] = []

    async def ask(self, prompt: str, context: SessionContext, model: str) -> str:
        self.calls.append((prompt, context, model))
        if self.error is not None:
            raise self.error
        return self.response

    def stream(self, prompt: str, context: SessionContext, model: str):
        del prompt, context, model
        raise NotImplementedError

    async def embed(self, text: str) -> list[float]:
        del text
        raise NotImplementedError

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        return None


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_TEXT)
    return path


@pytest.fixture()
def context() -> SessionContext:
    return SessionContext(
        project="Jules",
        directory="/tmp/jules",
        active_files=[],
        inferred_intent="testing",
        time_of_day="night",
    )


def make_router(config_path: Path, **provider_overrides: FakeProvider) -> CognitiveRouter:
    providers = {
        "ollama": FakeProvider("ollama", response="local answer"),
        "antigravity": FakeProvider("antigravity", response="agy answer"),
        "opencode": FakeProvider("opencode", response="code answer"),
    }
    providers.update(provider_overrides)
    return CognitiveRouter(config=load_config(config_path), providers=providers)


@pytest.mark.parametrize("task", [TaskType.IDENTITY, TaskType.MEMORY_SCORING, TaskType.OFFLINE])
def test_local_only_tasks_always_route_to_ollama(config_path: Path, task: TaskType) -> None:
    provider, model = make_router(config_path).route(task)

    assert provider.name == "ollama"
    assert model == "local-test-model"


def test_coding_routes_to_opencode_low_cost(config_path: Path) -> None:
    provider, model = make_router(config_path).route(TaskType.CODING)

    assert provider.name == "opencode"
    assert model == "oc-low"


def test_coding_heavy_routes_to_opencode_high_cost(config_path: Path) -> None:
    provider, model = make_router(config_path).route(TaskType.CODING_HEAVY)

    assert provider.name == "opencode"
    assert model == "oc-high"


@pytest.mark.parametrize("task", [TaskType.QUICK, TaskType.REASONING])
def test_quick_and_reasoning_route_to_antigravity_default_tier(config_path: Path, task: TaskType) -> None:
    provider, model = make_router(config_path).route(task)

    assert provider.name == "antigravity"
    assert model == "ag-low"


def test_analysis_routes_to_antigravity_high_cost(config_path: Path) -> None:
    provider, model = make_router(config_path).route(TaskType.ANALYSIS)

    assert provider.name == "antigravity"
    assert model == "ag-high"


def test_user_override_provider_model_is_strictly_respected(config_path: Path) -> None:
    provider, model = make_router(config_path).route(
        TaskType.IDENTITY,
        user_override="opencode:oc-high",
    )

    assert provider.name == "opencode"
    assert model == "oc-high"


def test_user_override_configured_model_resolves_provider(config_path: Path) -> None:
    provider, model = make_router(config_path).route(TaskType.QUICK, user_override="ag-high")

    assert provider.name == "antigravity"
    assert model == "ag-high"


def test_user_override_configured_ollama_model_with_colon_resolves_provider(config_path: Path) -> None:
    provider, model = make_router(config_path).route(TaskType.QUICK, user_override="llama3.2:1b")

    assert provider.name == "ollama"
    assert model == "llama3.2:1b"


async def test_ask_with_fallback_returns_primary_metadata(config_path: Path, context: SessionContext) -> None:
    router = make_router(config_path)

    response, model, provider = await router.ask_with_fallback("hello", context, TaskType.CODING)

    assert (response, model, provider) == ("code answer", "oc-low", "opencode")


@pytest.mark.parametrize("error", [ProviderUnavailableError("down"), ProviderTimeoutError("slow")])
async def test_ask_with_fallback_degrades_directly_to_ollama(
    config_path: Path,
    context: SessionContext,
    error: Exception,
) -> None:
    opencode = FakeProvider("opencode", error=error)
    ollama = FakeProvider("ollama", response="fallback answer")
    router = make_router(config_path, opencode=opencode, ollama=ollama)

    response, model, provider = await router.ask_with_fallback("hello", context, TaskType.CODING)

    assert (response, model, provider) == ("fallback answer", "local-test-model", "ollama")
    assert [call[2] for call in opencode.calls] == ["oc-low"]
    assert [call[2] for call in ollama.calls] == ["local-test-model"]


async def test_ask_with_fallback_degrades_on_generic_external_provider_error(
    config_path: Path,
    context: SessionContext,
) -> None:
    router = make_router(
        config_path,
        antigravity=FakeProvider("antigravity", error=ProviderError("bad request")),
        ollama=FakeProvider("ollama", response="fallback answer"),
    )

    response, model, provider = await router.ask_with_fallback("hello", context, TaskType.QUICK)

    assert (response, model, provider) == ("fallback answer", "local-test-model", "ollama")


async def test_ask_with_fallback_reports_when_ollama_also_fails(
    config_path: Path,
    context: SessionContext,
) -> None:
    router = make_router(
        config_path,
        opencode=FakeProvider("opencode", error=ProviderError("primary failed")),
        ollama=FakeProvider("ollama", error=ProviderUnavailableError("local down")),
    )

    with pytest.raises(ProviderError, match="Primary provider and Ollama fallback both failed"):
        await router.ask_with_fallback("hello", context, TaskType.CODING)


def test_unknown_override_provider_fails(config_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        make_router(config_path).route(TaskType.QUICK, user_override="unknown:model")


def test_model_names_are_read_from_config_not_router_literals(config_path: Path) -> None:
    router = make_router(config_path)

    assert router.route(TaskType.QUICK)[1] == "ag-low"
    assert router.route(TaskType.CODING)[1] == "oc-low"
    assert router.route(TaskType.CODING_HEAVY)[1] == "oc-high"


def test_empty_provider_override_model_fails(config_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid user_override"):
        make_router(config_path).route(TaskType.QUICK, user_override="opencode:")


async def test_antigravity_run_cli_isolates_xdg_config_home_and_writes_model_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured_env: dict[str, str] = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"ok", b""

    async def fake_create_subprocess_exec(*args: str, **kwargs: object) -> FakeProcess:
        del args
        env = kwargs.get("env")
        assert isinstance(env, dict)
        captured_env.update({str(key): str(value) for key, value in env.items()})
        return FakeProcess()

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    response = await AntigravityProvider()._run_cli(
        ["agy", "--print", "hello"],
        timeout=1.0,
        model="ag-low",
    )

    expected_config_home = tmp_path / ".jules" / "antigravity_config"
    model_config = expected_config_home / "antigravity" / "config.toml"
    assert response == "ok"
    assert captured_env["XDG_CONFIG_HOME"] == str(expected_config_home)
    assert model_config.read_text() == 'model = "ag-low"\n'
