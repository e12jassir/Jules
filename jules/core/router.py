from __future__ import annotations

import asyncio
from enum import Enum
import logging
from pathlib import Path
from typing import Any, Mapping

from jules.core.config import JulesConfig, RoutingTier, load_config

from jules.providers.base import Provider, ProviderError

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

TASK_PROVIDER_CANDIDATES: dict[TaskType, tuple[str, ...]] = {
    TaskType.QUICK: ("antigravity", "openai_oauth", "openrouter", "google", "codex"),
    TaskType.REASONING: ("antigravity", "openai_oauth", "openrouter", "google", "codex"),
    TaskType.ANALYSIS: ("antigravity", "openai_oauth", "openrouter", "google", "codex"),
    TaskType.CODING: ("opencode", "openai_oauth", "codex"),
    TaskType.CODING_HEAVY: ("opencode", "openai_oauth", "codex"),
}

_router_instance: CognitiveRouter | None = None

class CognitiveRouter:
    def __init__(
        self,
        config: JulesConfig | None = None,
        providers: Mapping[str, Provider] | None = None,
        config_path: Path | str | None = None,
    ) -> None:
        import importlib

        self.config = config or load_config(config_path)
        if providers is None:
            raise ValueError("providers mapping must be injected")
        self.providers = dict(providers)
        provider_registry = importlib.import_module("jules.core.provider_registry")
        registry_cls = getattr(provider_registry, "ProviderRegistry")
        self.registry: Any = registry_cls(self.config, self.providers)

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

    async def route(self, task: TaskType, user_override: str | None = None) -> tuple[Provider, str]:
        if user_override:
            provider, model = await self._resolve_user_override(user_override)
            if task in LOCAL_ONLY_TASKS and provider.name != "ollama":
                raise ValueError(f"Task {task.value} requires local provider, cannot override to {provider.name}")
            return provider, model

        if task in LOCAL_ONLY_TASKS:
            return self._ollama_route()

        tier = self._tier_for_task(task)
        # If tier is the local/free tier (only ollama), route directly — no cloud candidates
        if tier.provider == "ollama" or (
            not tier.antigravity and not tier.opencode and not tier.codex
            and not tier.google and not tier.openrouter and not tier.openai_oauth
            and tier.models
        ):
            return self._ollama_route()

        return self._route_via_candidates(task, tier)

    async def ask_with_fallback(
        self,
        prompt: str,
        context: list[dict],
        task: TaskType,
        user_override: str | None = None,
    ) -> tuple[str, str, str]:
        provider_name = "unresolved"
        model = "unresolved"
        tier = None
        try:
            provider, model = await self.route(task, user_override=user_override)
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

    async def stream_with_fallback(
        self,
        prompt: str,
        context: list[dict],
        task: TaskType,
        user_override: str | None = None,
    ):
        provider_name = "unresolved"
        model = "unresolved"
        tier = None
        try:
            provider, model = await self.route(task, user_override=user_override)
            provider_name = provider.name
            tier = None if user_override else self._tier_for_task(task)
            logger.info(
                "Router selected model for streaming",
                extra={"provider": provider.name, "model": model, "task_type": task.value},
            )
            if hasattr(provider, "stream_events"):
                async for event in provider.stream_events(prompt, context, model):
                    yield event, model, provider.name
            else:
                async for token in provider.stream(prompt, context, model):
                    yield token, model, provider.name
            return
        except (ProviderError, ValueError, NotImplementedError) as exc:
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
                            if hasattr(fallback_provider, "stream_events"):
                                async for event in fallback_provider.stream_events(prompt, context, secondary_model):
                                    yield event, secondary_model, fallback_provider.name
                            else:
                                async for token in fallback_provider.stream(prompt, context, secondary_model):
                                    yield token, secondary_model, fallback_provider.name
                            return
                        except (ProviderError, ValueError, NotImplementedError) as fallback_exc:
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

                    if hasattr(fallback_provider, "stream_events"):
                        async for event in fallback_provider.stream_events(prompt, context, fallback_model):
                            yield event, fallback_model, fallback_provider.name
                    else:
                        async for token in fallback_provider.stream(prompt, context, fallback_model):
                            yield token, fallback_model, fallback_provider.name
                    return
                except (ProviderError, ValueError, NotImplementedError) as fallback_exc:
                    last_exc = fallback_exc

            raise ProviderError(f"All providers in fallback chain failed. Last error: {last_exc}") from last_exc

    async def _resolve_user_override(self, override: str) -> tuple[Provider, str]:
        matches: list[tuple[Provider, str]] = []
        for provider_name, model in await self._configured_models():
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

    def _route_via_candidates(self, task: TaskType, tier: RoutingTier) -> tuple[Provider, str]:
        candidates = TASK_PROVIDER_CANDIDATES.get(task)
        if not candidates:
            raise ValueError(f"No provider candidates configured for task: {task.value}")
        for provider_name in candidates:
            models = self._models_for_provider(provider_name, tier)
            if models:
                return self._provider_by_name(provider_name), models[0]
        raise ValueError(
            f"No providers with configured models available for task {task.value} in tier"
        )

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

    async def _configured_models(self) -> tuple[tuple[str, str], ...]:
        return await self.registry.available_models()

    async def _configured_models_for_provider(self, provider_name: str) -> tuple[str, ...]:
        return tuple(
            model
            for configured_provider, model in await self._configured_models()
            if configured_provider == provider_name
        )

    def _models_for_provider(self, provider_name: str, tier: RoutingTier) -> tuple[str, ...]:
        return self.registry.models_for_provider(provider_name, tier)

    async def available_models(self) -> tuple[tuple[str, str], ...]:
        """Return de-duped (provider, model) tuples from the provider registry."""
        return await self.registry.available_models()

    async def current_model(self, task: TaskType = TaskType.QUICK) -> tuple[str, str]:
        """Return (provider_name, model) for the default route of the given task."""
        try:
            provider, model = await self.route(task)
            return provider.name, model
        except Exception:
            return ("ollama", "local")

    @staticmethod
    def _validate_model(model: str, override: str) -> str:
        if not model:
            raise ValueError(f"Invalid user_override: {override}")
        return model


async def _get_router() -> CognitiveRouter:
    global _router_instance
    if _router_instance is None:
        from jules.providers.antigravity import AntigravityProvider
        from jules.providers.codex import CodexProvider
        from jules.providers.google import GoogleAIProvider
        from jules.providers.ollama import OllamaProvider
        from jules.providers.openai_oauth import OpenAIOAuthProvider
        from jules.providers.opencode import OpenCodeProvider
        from jules.providers.openrouter import OpenRouterProvider

        providers = {
            "antigravity": AntigravityProvider(),
            "codex": CodexProvider(),
            "google": GoogleAIProvider(),
            "ollama": OllamaProvider(),
            "openai_oauth": OpenAIOAuthProvider(),
            "opencode": OpenCodeProvider(),
            "openrouter": OpenRouterProvider(),
        }
        _router_instance = await asyncio.to_thread(CognitiveRouter, providers=providers)
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
    return await router.route(task, user_override=user_override)


async def ask_with_fallback(
    prompt: str,
    context: list[dict],
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


async def stream_with_fallback(
    prompt: str,
    context: list[dict],
    task: TaskType,
    user_override: str | None = None,
):
    router = await _get_router()
    async for event, model, provider_name in router.stream_with_fallback(
        prompt,
        context,
        task,
        user_override=user_override,
    ):
        yield event, model, provider_name
