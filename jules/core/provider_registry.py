from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from jules.core.config import JulesConfig, RoutingTier

if TYPE_CHECKING:
    from jules.providers.base import Provider


class ProviderKind(str, Enum):
    LOCAL = "local"
    CLI = "cli"
    API_KEY = "api_key"
    OAUTH = "oauth"


class AuthRequirement(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"


@dataclass(frozen=True, slots=True)
class ProviderCatalogEntry:
    provider_id: str
    kind: ProviderKind
    auth_requirement: AuthRequirement
    enabled: bool
    model_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    provider_id: str
    kind: ProviderKind
    auth_requirement: AuthRequirement
    tier_field: str


_PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec("ollama", ProviderKind.LOCAL, AuthRequirement.NONE, "models"),
    ProviderSpec("antigravity", ProviderKind.CLI, AuthRequirement.NONE, "antigravity"),
    ProviderSpec("opencode", ProviderKind.CLI, AuthRequirement.NONE, "opencode"),
    ProviderSpec("codex", ProviderKind.CLI, AuthRequirement.OAUTH, "codex"),
    ProviderSpec("google", ProviderKind.API_KEY, AuthRequirement.API_KEY, "google"),
    ProviderSpec("openrouter", ProviderKind.API_KEY, AuthRequirement.API_KEY, "openrouter"),
    ProviderSpec("openai_oauth", ProviderKind.OAUTH, AuthRequirement.OAUTH, "openai_oauth"),
)


class ProviderRegistry:
    def __init__(
        self,
        config: JulesConfig,
        providers: Mapping[str, Provider] | None = None,
    ) -> None:
        self.config = config
        self.providers = dict(providers or {})
        self._specs = {spec.provider_id: spec for spec in _PROVIDER_SPECS}

    def spec(self, provider_id: str) -> ProviderSpec:
        try:
            return self._specs[provider_id]
        except KeyError as exc:
            raise ValueError(f"Unknown provider: {provider_id}") from exc

    def models_for_provider(self, provider_id: str, tier: RoutingTier) -> tuple[str, ...]:
        spec = self.spec(provider_id)
        models = getattr(tier, spec.tier_field)
        if not isinstance(models, tuple):
            raise ValueError(f"Invalid model catalog for provider: {provider_id}")
        return models

    def catalog(self) -> tuple[ProviderCatalogEntry, ...]:
        result: list[ProviderCatalogEntry] = []
        for spec in _PROVIDER_SPECS:
            result.append(
                ProviderCatalogEntry(
                    provider_id=spec.provider_id,
                    kind=spec.kind,
                    auth_requirement=spec.auth_requirement,
                    enabled=self._is_enabled(spec.provider_id),
                    model_ids=self._all_models_for_provider(spec.provider_id),
                )
            )
        return tuple(result)

    def available_models(self) -> tuple[tuple[str, str], ...]:
        seen: set[tuple[str, str]] = set()
        result: list[tuple[str, str]] = []

        for entry in self.catalog():
            if not entry.enabled:
                continue
            for model in entry.model_ids:
                pair = (entry.provider_id, model)
                if pair not in seen:
                    seen.add(pair)
                    result.append(pair)

        for model in self._discover_ollama_models():
            pair = ("ollama", model)
            if pair not in seen:
                seen.add(pair)
                result.append(pair)

        return tuple(result)

    def _is_enabled(self, provider_id: str) -> bool:
        return bool(self._all_models_for_provider(provider_id))

    def _all_models_for_provider(self, provider_id: str) -> tuple[str, ...]:
        seen: set[str] = set()
        models: list[str] = []
        for tier in self.config.routing.tiers.values():
            for model in self.models_for_provider(provider_id, tier):
                if model not in seen:
                    seen.add(model)
                    models.append(model)
        return tuple(models)

    @staticmethod
    def _discover_ollama_models() -> tuple[str, ...]:
        import os

        manifests_roots = [
            Path.home() / ".ollama" / "models" / "manifests",
            Path("/usr/share/ollama/.ollama/models/manifests"),
            Path("/var/lib/ollama/.ollama/models/manifests"),
        ]
        env_models = os.environ.get("OLLAMA_MODELS")
        if env_models:
            manifests_roots.insert(0, Path(env_models) / "manifests")

        seen: set[str] = set()
        result: list[str] = []
        for manifests_root in manifests_roots:
            if not manifests_root.exists():
                continue
            for tag_file in manifests_root.rglob("*"):
                if not tag_file.is_file():
                    continue
                parts = tag_file.parts[len(manifests_root.parts):]
                if len(parts) < 2:
                    continue
                model_str = f"{parts[-2]}:{parts[-1]}"
                if model_str not in seen:
                    seen.add(model_str)
                    result.append(model_str)
        return tuple(result)
