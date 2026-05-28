from __future__ import annotations

from enum import Enum
import logging
from pathlib import Path
from typing import Mapping

from jules.core.config import JulesConfig, RoutingTier, load_config
from jules.memory.models import SessionContext
from jules.providers.antigravity import AntigravityProvider
from jules.providers.base import Provider, ProviderError, ProviderTimeoutError, ProviderUnavailableError
from jules.providers.ollama import OllamaProvider
from jules.providers.opencode import OpenCodeProvider

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    IDENTITY = "identity"
    MEMORY_SCORING = "memory_scoring"
    QUICK = "quick"
    REASONING = "reasoning"
    CODING = "coding"
    CODING_HEAVY = "coding_heavy"
    ANALYSIS = "analysis"
    OFFLINE = "offline"


LOCAL_ONLY_TASKS = {TaskType.IDENTITY, TaskType.MEMORY_SCORING, TaskType.OFFLINE}


class CognitiveRouter:
    def __init__(
        self,
        config: JulesConfig | None = None,
        providers: Mapping[str, Provider] | None = None,
        config_path: Path | str | None = None,
    ) -> None:
        self.config = config or load_config(config_path)
        self.providers = dict(providers) if providers is not None else self._build_providers()

    def route(self, task: TaskType, user_override: str | None = None) -> tuple[Provider, str]:
        if user_override:
            return self._resolve_user_override(user_override)

        if task in LOCAL_ONLY_TASKS:
            return self._ollama_route()

        if task == TaskType.CODING:
            return self._provider_route("opencode", self.config.routing.tiers["low_cost"])

        if task == TaskType.CODING_HEAVY:
            return self._provider_route("opencode", self.config.routing.tiers["high_cost"])

        if task == TaskType.ANALYSIS:
            return self._provider_route("antigravity", self.config.routing.tiers["high_cost"])

        if task in {TaskType.QUICK, TaskType.REASONING}:
            tier = self.config.routing.tiers[self.config.routing.default_tier]
            return self._provider_route("antigravity", tier)

        tier = self.config.routing.tiers[self.config.routing.default_tier]
        return self._provider_route("antigravity", tier)

    async def ask_with_fallback(
        self,
        prompt: str,
        context: SessionContext,
        task: TaskType,
        user_override: str | None = None,
    ) -> tuple[str, str, str]:
        provider, model = self.route(task, user_override=user_override)
        logger.info(
            "Router selected model",
            extra={"provider": provider.name, "model": model, "task_type": task.value},
        )

        try:
            response = await provider.ask(prompt, context, model)
            return response, model, provider.name
        except ProviderError as exc:
            if provider.name == "ollama" or "ollama" not in self.config.routing.fallback_chain:
                raise ProviderError(f"Provider failed with no fallback available: {exc}") from exc
            logger.warning(
                "Provider failed, falling back to Ollama",
                extra={"provider": provider.name, "model": model, "task_type": task.value},
            )
            ollama, ollama_model = self._ollama_route()
            try:
                response = await ollama.ask(prompt, context, ollama_model)
            except ProviderError as fallback_exc:
                raise ProviderError(f"Primary provider and Ollama fallback both failed: {fallback_exc}") from fallback_exc
            return response, ollama_model, ollama.name

    def _build_providers(self) -> dict[str, Provider]:
        provider_config = self.config.providers
        return {
            "ollama": OllamaProvider(
                base_url=provider_config.ollama.base_url,
                timeout_seconds=provider_config.ollama.timeout_seconds,
                default_model=self._ollama_model(),
            ),
            "antigravity": AntigravityProvider(
                timeout_seconds=provider_config.antigravity.timeout_seconds,
            ),
            "opencode": OpenCodeProvider(
                timeout_seconds=provider_config.opencode.timeout_seconds,
            ),
        }

    def _resolve_user_override(self, override: str) -> tuple[Provider, str]:
        for provider_name, model in self._configured_models():
            if model == override:
                return self._provider_by_name(provider_name), model

        if ":" in override:
            provider_name, model = override.split(":", 1)
            return self._provider_by_name(provider_name), self._validate_model(model, override)

        raise ValueError(
            "user_override must be 'provider:model' or a model present in config.toml"
        )

    def _provider_route(self, provider_name: str, tier: RoutingTier) -> tuple[Provider, str]:
        models = self._models_for_provider(provider_name, tier)
        if not models:
            raise ValueError(f"No {provider_name} models configured for requested routing tier")
        return self._provider_by_name(provider_name), models[0]

    def _ollama_route(self) -> tuple[Provider, str]:
        return self._provider_by_name("ollama"), self._ollama_model()

    def _ollama_model(self) -> str:
        free_tier = self.config.routing.tiers["free"]
        if not free_tier.models:
            raise ValueError("No Ollama model configured in [routing.tiers.free].models")
        return free_tier.models[0]

    def _provider_by_name(self, provider_name: str) -> Provider:
        try:
            return self.providers[provider_name]
        except KeyError as exc:
            raise ValueError(f"Unknown provider: {provider_name}") from exc

    def _configured_models(self) -> tuple[tuple[str, str], ...]:
        entries: list[tuple[str, str]] = []
        for tier in self.config.routing.tiers.values():
            entries.extend(("ollama", model) for model in tier.models)
            entries.extend(("antigravity", model) for model in tier.antigravity)
            entries.extend(("opencode", model) for model in tier.opencode)
        return tuple(entries)

    @staticmethod
    def _models_for_provider(provider_name: str, tier: RoutingTier) -> tuple[str, ...]:
        if provider_name == "antigravity":
            return tier.antigravity
        if provider_name == "opencode":
            return tier.opencode
        if provider_name == "ollama":
            return tier.models
        raise ValueError(f"Unknown provider: {provider_name}")

    @staticmethod
    def _validate_model(model: str, override: str) -> str:
        if not model:
            raise ValueError(f"Invalid user_override: {override}")
        return model


def route(task: TaskType, user_override: str | None = None) -> tuple[Provider, str]:
    return CognitiveRouter().route(task, user_override=user_override)


async def ask_with_fallback(
    prompt: str,
    context: SessionContext,
    task: TaskType,
    user_override: str | None = None,
) -> tuple[str, str, str]:
    return await CognitiveRouter().ask_with_fallback(
        prompt,
        context,
        task,
        user_override=user_override,
    )
