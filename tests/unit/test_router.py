from __future__ import annotations

import asyncio
from dataclasses import replace
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


def write_config(tmp_path: Path, fallback_chain: str = '["primary", "ollama"]') -> Path:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_TEXT.replace('["primary", "ollama"]', fallback_chain))
    return path


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


def test_cloud_user_override_is_blocked_for_local_only_task(config_path: Path) -> None:
    with pytest.raises(ValueError, match="requires local provider"):
        make_router(config_path).route(
            TaskType.IDENTITY,
            user_override="opencode:oc-high",
        )


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
    assert [call[2] for call in opencode.calls] == ["oc-low", "oc-low-secondary"]
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


async def test_local_only_fallback_never_leaks_to_cloud_provider(
    tmp_path: Path,
    context: SessionContext,
) -> None:
    config_path = write_config(tmp_path, fallback_chain='["primary", "opencode", "ollama"]')
    opencode = FakeProvider("opencode", response="cloud answer")
    router = make_router(
        config_path,
        ollama=FakeProvider("ollama", error=ProviderUnavailableError("local down")),
        opencode=opencode,
    )

    with pytest.raises(ProviderError, match="Local-only task identity failed"):
        await router.ask_with_fallback("identity", context, TaskType.IDENTITY)

    assert opencode.calls == []


async def test_route_value_error_can_fallback_to_ollama(
    tmp_path: Path,
    context: SessionContext,
) -> None:
    config_path = write_config(tmp_path, fallback_chain='["primary", "ollama"]')
    router = make_router(config_path)
    low_cost_tier = router.config.routing.tiers["low_cost"]
    router.config.routing.tiers["low_cost"] = replace(low_cost_tier, opencode=())

    response, model, provider = await router.ask_with_fallback("hello", context, TaskType.CODING)

    assert (response, model, provider) == ("local answer", "local-test-model", "ollama")


async def test_ask_with_fallback_reports_when_ollama_also_fails(
    config_path: Path,
    context: SessionContext,
) -> None:
    router = make_router(
        config_path,
        opencode=FakeProvider("opencode", error=ProviderError("primary failed")),
        ollama=FakeProvider("ollama", error=ProviderUnavailableError("local down")),
    )

    with pytest.raises(ProviderError, match="All providers in fallback chain failed"):
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


async def test_antigravity_ask_passes_prompt_directly_without_separator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """agy --print <prompt> — no '--' separator; prompt goes as a positional arg."""
    source_config = tmp_path / "real_config"
    source_config.mkdir()
    (source_config / "config.toml").write_text('model = "old"\ntimeout = 60\nenabled = true\n', encoding="utf-8")
    (source_config / "auth.json").write_text('{"token":"kept"}\n', encoding="utf-8")
    captured_env: dict[str, str] = {}
    captured_args: tuple[str, ...] = ()

    class FakeProcess:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"ok", b""

    async def fake_create_subprocess_exec(*args: str, **kwargs: object) -> FakeProcess:
        nonlocal captured_args
        captured_args = args
        env = kwargs.get("env")
        assert isinstance(env, dict)
        captured_env.update({str(key): str(value) for key, value in env.items()})
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    provider = AntigravityProvider()
    provider.profile_root = tmp_path / "profiles"
    provider.source_config = source_config
    provider.prepare_profiles(("ag/low",))

    response = await provider.ask("hello world", context=SessionContext(
        project="Jules",
        directory="/tmp/jules",
        active_files=[],
        inferred_intent="testing",
        time_of_day="night",
    ), model="ag/low")

    expected_profile = provider._profile_path("ag/low")
    assert response == "ok"
    # No '--' separator — prompt is passed directly as a positional arg.
    assert captured_args == ("agy", "--print", "hello world")
    assert captured_env["XDG_CONFIG_HOME"] == str(expected_profile)
    assert (expected_profile / "antigravity" / "config.toml").read_text(encoding="utf-8") == (
        'model = "ag/low"\ntimeout = 60\nenabled = true\n'
    )
    assert (expected_profile / "antigravity" / "auth.json").read_text(encoding="utf-8") == '{"token":"kept"}\n'


async def test_antigravity_ask_rejects_prompt_starting_with_dash(
    tmp_path: Path,
) -> None:
    """Prompts starting with '-' are rejected to prevent argument injection."""
    source_config = tmp_path / "real_config"
    source_config.mkdir()
    (source_config / "config.toml").write_text('model = "old"\n', encoding="utf-8")
    provider = AntigravityProvider()
    provider.profile_root = tmp_path / "profiles"
    provider.source_config = source_config
    provider.prepare_profiles(("ag/low",))

    with pytest.raises(ProviderError, match="must not start with '-'"):
        await provider.ask("--not-a-flag", context=SessionContext(
            project="Jules",
            directory="/tmp/jules",
            active_files=[],
            inferred_intent="testing",
            time_of_day="night",
        ), model="ag/low")


async def test_antigravity_run_cli_does_not_create_profiles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    provider = AntigravityProvider()
    provider.profile_root = tmp_path / "profiles"

    response = await provider._run_cli(["agy", "--print", "--", "hello"], timeout=1.0, model="ag-low")

    assert response == "ok"
    assert captured_env["XDG_CONFIG_HOME"] == str(provider._profile_path("ag-low"))
    assert not (tmp_path / "profiles").exists()


def test_antigravity_profile_symlink_safety(tmp_path: Path) -> None:
    # 1. Test _copy_config dereferences symlinks
    source_dir = tmp_path / "source_config"
    source_dir.mkdir()
    real_file = tmp_path / "real_file.toml"
    real_file.write_text("token = 'secret'", encoding="utf-8")

    symlink_file = source_dir / "config.toml"
    symlink_file.symlink_to(real_file)

    provider = AntigravityProvider()
    dest_dir = tmp_path / "profile_config"
    provider._copy_config(source_dir, dest_dir)

    dest_file = dest_dir / "config.toml"
    assert dest_file.exists()
    assert not dest_file.is_symlink()  # Must not be a symlink!
    assert dest_file.read_text(encoding="utf-8") == "token = 'secret'"

    # 2. Test _write_model_config breaks existing symlinks to prevent mutating user config
    profile_dir = tmp_path / "profile_home"
    profile_config_dir = profile_dir / "antigravity"
    profile_config_dir.mkdir(parents=True)

    user_real_config = tmp_path / "user_real_config.toml"
    user_real_config.write_text("model = 'original'\nenabled = true", encoding="utf-8")

    symlink_in_profile = profile_config_dir / "config.toml"
    symlink_in_profile.symlink_to(user_real_config)

    # Write model config
    provider._write_model_config(profile_dir, "new-model")

    # The symlink in the profile must be broken and turned into a regular file
    assert symlink_in_profile.exists()
    assert not symlink_in_profile.is_symlink()
    assert 'model = "new-model"' in symlink_in_profile.read_text(encoding="utf-8")

    # The user's real config must remain completely untouched!
    assert user_real_config.read_text(encoding="utf-8") == "model = 'original'\nenabled = true"

