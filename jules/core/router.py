from __future__ import annotations

import asyncio
from enum import Enum
import logging
from pathlib import Path
from typing import Mapping

from jules.core.config import JulesConfig, RoutingTier, load_config
from jules.memory.models import SessionContext
from jules.providers.antigravity import AntigravityProvider
from jules.providers.base import Provider, ProviderError
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

_router_instance: CognitiveRouter | None = None

class CognitiveRouter:
    def __init__(
        self,
        config: JulesConfig | None = None,
        providers: Mapping[str, Provider] | None = None,
        config_path: Path | str | None = None,
    ) -> None:
        self.config = config or load_config(config_path)
        self.providers = dict(providers) if providers is not None else self._build_providers()

    def _get_tier(self, name: str) -> RoutingTier:
        try:
            return self.config.routing.tiers[name]
        except KeyError:
            pass
        try:
            return self.config.routing.tiers[self.config.routing.default_tier]
        except KeyError:
            if not self.config.routing.tiers:
                raise ValueError("No routing tiers configured")
            return next(iter(self.config.routing.tiers.values()))

    def route(self, task: TaskType, user_override: str | None = None) -> tuple[Provider, str]:
        if user_override:
            provider, model = self._resolve_user_override(user_override)
            if task in LOCAL_ONLY_TASKS and provider.name != "ollama":
                raise ValueError(f"Task {task.value} requires local provider, cannot override to {provider.name}")
            return provider, model

        if task in LOCAL_ONLY_TASKS:
            return self._ollama_route()

        if task == TaskType.CODING:
            return self._provider_route("opencode", self._get_tier("low_cost"))

        if task == TaskType.CODING_HEAVY:
            return self._provider_route("opencode", self._get_tier("high_cost"))

        if task == TaskType.ANALYSIS:
            return self._provider_route("antigravity", self._get_tier("high_cost"))

        return self._provider_route("antigravity", self._get_tier(self.config.routing.default_tier))

    async def ask_with_fallback(
        self,
        prompt: str,
        context: SessionContext,
        task: TaskType,
        user_override: str | None = None,
    ) -> tuple[str, str, str]:
        provider_name = "unresolved"
        model = "unresolved"
        tier = None
        try:
            provider, model = self.route(task, user_override=user_override)
            provider_name = provider.name
            tier = None if user_override else self._tier_for_task(task)
            logger.info(
                "Router selected model",
                extra={"provider": provider.name, "model": model, "task_type": task.value},
            )
            response = await provider.ask(prompt, context, model)
            return response, model, provider.name
        except (ProviderError, ValueError) as exc:
            if isinstance(exc, ValueError) and ("override" in str(exc).lower() or "requires local" in str(exc).lower()):
                raise
            last_exc = exc
            if task in LOCAL_ONLY_TASKS:
                raise ProviderError(f"Local-only task {task.value} failed, no fallbacks allowed. Last error: {last_exc}") from last_exc

            if tier is not None:
                models = self._models_for_provider(provider_name, tier)
                if model in models:
                    for secondary_model in models[models.index(model) + 1:]:
                        logger.warning(
                            "Provider model failed, falling back to same-tier secondary model",
                            extra={
                                "provider": provider_name,
                                "model": model,
                                "fallback_model": secondary_model,
                                "task_type": task.value,
                            },
                        )
                        try:
                            fallback_provider = self._provider_by_name(provider_name)
                            response = await fallback_provider.ask(prompt, context, secondary_model)
                            return response, secondary_model, fallback_provider.name
                        except (ProviderError, ValueError) as fallback_exc:
                            last_exc = fallback_exc

            for fallback_name in self.config.routing.fallback_chain:
                if fallback_name == "primary" or fallback_name == provider_name:
                    continue

                logger.warning(
                    "Provider failed, falling back to %s",
                    fallback_name,
                    extra={"provider": provider_name, "fallback": fallback_name, "task_type": task.value},
                )

                try:
                    if fallback_name == "ollama":
                        fallback_provider, fallback_model = self._ollama_route()
                    else:
                        fallback_tier = self._get_tier(self.config.routing.default_tier)
                        fallback_provider, fallback_model = self._provider_route(fallback_name, fallback_tier)

                    response = await fallback_provider.ask(prompt, context, fallback_model)
                    return response, fallback_model, fallback_provider.name
                except (ProviderError, ValueError) as fallback_exc:
                    last_exc = fallback_exc

            raise ProviderError(f"All providers in fallback chain failed. Last error: {last_exc}") from last_exc

    def _build_providers(self) -> dict[str, Provider]:
        provider_config = self.config.providers
        ollama_default = self._ollama_model()

        return {
            "ollama": OllamaProvider(
                base_url=provider_config.ollama.base_url,
                timeout_seconds=provider_config.ollama.timeout_seconds,
                default_model=ollama_default,
            ),
            "antigravity": AntigravityProvider(
                timeout_seconds=provider_config.antigravity.timeout_seconds,
                models=self._configured_models_for_provider("antigravity"),
            ),
            "opencode": OpenCodeProvider(
                timeout_seconds=provider_config.opencode.timeout_seconds,
            ),
        }

    def _resolve_user_override(self, override: str) -> tuple[Provider, str]:
        matches = []
        for provider_name, model in self._configured_models():
            if model == override and provider_name not in [m[0].name for m in matches]:
                matches.append((self.providers[provider_name], model))

        if len(matches) > 1:
            raise ValueError(f"Ambiguous model override '{override}'. Found in multiple providers. Please use 'provider:{override}'.")
        if matches:
            return matches[0]

        if ":" in override:
            provider_name, model = override.split(":", 1)
            try:
                provider = self.providers[provider_name]
            except KeyError as exc:
                raise ValueError(f"Unknown provider override: '{provider_name}'") from exc
            return provider, self._validate_model(model, override)

        raise ValueError(
            "user_override must be 'provider:model' or a model present in config.toml"
        )

    def _provider_route(self, provider_name: str, tier: RoutingTier) -> tuple[Provider, str]:
        models = self._models_for_provider(provider_name, tier)
        if not models:
            raise ValueError(f"No {provider_name} models configured for requested routing tier")
        return self._provider_by_name(provider_name), models[0]

    def _tier_for_task(self, task: TaskType) -> RoutingTier:
        if task == TaskType.CODING:
            return self._get_tier("low_cost")
        if task in {TaskType.CODING_HEAVY, TaskType.ANALYSIS}:
            return self._get_tier("high_cost")
        return self._get_tier(self.config.routing.default_tier)

    def _ollama_route(self) -> tuple[Provider, str]:
        return self._provider_by_name("ollama"), self._ollama_model()

    def _ollama_model(self) -> str:
        tier = self._get_tier("free")
        if not tier.models:
            raise ValueError("No Ollama model configured in tier")
        return tier.models[0]

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

    def _configured_models_for_provider(self, provider_name: str) -> tuple[str, ...]:
        return tuple(
            model
            for configured_provider, model in self._configured_models()
            if configured_provider == provider_name
        )

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


async def _get_router() -> CognitiveRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = await asyncio.to_thread(CognitiveRouter)
    return _router_instance


async def close_router() -> None:
    global _router_instance
    if _router_instance is None:
        return

    for provider in _router_instance.providers.values():
        close = getattr(provider, "close", None)
        if close is None:
            continue
        await close()

    _router_instance = None


async def route(task: TaskType, user_override: str | None = None) -> tuple[Provider, str]:
    router = await _get_router()
    return router.route(task, user_override=user_override)


async def ask_with_fallback(
    prompt: str,
    context: SessionContext,
    task: TaskType,
    user_override: str | None = None,
) -> tuple[str, str, str]:
    router = await _get_router()
    return await router.ask_with_fallback(
        prompt,
        context,
        task,
        user_override=user_override,
    )
