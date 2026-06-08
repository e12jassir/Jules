from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from jules.core.config import load_config

_provider_registry = importlib.import_module("jules.core.provider_registry")
AuthRequirement = _provider_registry.AuthRequirement
ProviderKind = _provider_registry.ProviderKind
ProviderRegistry = _provider_registry.ProviderRegistry


CONFIG_TEXT = """
[routing]
default_tier = "low_cost"

[routing.tiers.free]
provider = "ollama"
models = ["local-test-model"]

[routing.tiers.low_cost]
antigravity = ["ag-low"]
opencode = ["oc-low"]
codex = ["openai/gpt-5.4-mini"]
google = ["gemini-2.5-flash"]
openrouter = ["openrouter/model-a"]
openai_oauth = ["gpt-5-mini"]

[routing.tiers.high_cost]
antigravity = ["ag-high"]
opencode = ["oc-high"]
openai_oauth = ["gpt-5"]

[providers.ollama]
base_url = "http://localhost:11434"
timeout_seconds = 30

[providers.antigravity]
timeout_seconds = 60

[providers.opencode]
timeout_seconds = 60

[providers.google]
timeout_seconds = 60

[providers.openrouter]
timeout_seconds = 60

[providers.openai_oauth]
timeout_seconds = 60
"""


def _config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(CONFIG_TEXT)
    return path


def test_provider_registry_catalog_exposes_kind_auth_and_models(tmp_path: Path) -> None:
    registry = ProviderRegistry(load_config(_config_path(tmp_path)))
    catalog = {entry.provider_id: entry for entry in registry.catalog()}

    assert catalog["opencode"].kind == ProviderKind.CLI
    assert catalog["google"].kind == ProviderKind.API_KEY
    assert catalog["openai_oauth"].kind == ProviderKind.OAUTH
    assert catalog["codex"].auth_requirement == AuthRequirement.OAUTH
    assert catalog["openrouter"].auth_requirement == AuthRequirement.API_KEY
    assert catalog["openai_oauth"].model_ids == ("gpt-5-mini", "gpt-5")
    assert catalog["openai_oauth"].enabled is True


@pytest.mark.asyncio
async def test_provider_registry_available_models_includes_all_enabled_configured_models(tmp_path: Path) -> None:
    registry = ProviderRegistry(load_config(_config_path(tmp_path)))
    models = await registry.available_models()

    assert ("antigravity", "ag-low") in models
    assert ("opencode", "oc-low") in models
    assert ("codex", "openai/gpt-5.4-mini") in models
    assert ("google", "gemini-2.5-flash") in models
    assert ("openrouter", "openrouter/model-a") in models
    assert ("openai_oauth", "gpt-5") in models
    assert ("ollama", "local-test-model") in models


def test_provider_registry_marks_unconfigured_provider_as_disabled(tmp_path: Path) -> None:
    config_path = _config_path(tmp_path)
    config_path.write_text(CONFIG_TEXT.replace('openrouter = ["openrouter/model-a"]\n', ''))

    registry = ProviderRegistry(load_config(config_path))
    catalog = {entry.provider_id: entry for entry in registry.catalog()}

    assert catalog["openrouter"].enabled is False
    assert catalog["openrouter"].model_ids == ()
