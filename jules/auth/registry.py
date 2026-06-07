"""OAuth provider registry and auth backend resolution."""

from __future__ import annotations

from typing import Mapping

from jules.auth.base import OAuthConfigError, OAuthProviderConfig
from jules.auth.claude import build_claude_provider_config
from jules.auth.openai import build_openai_provider_config

_PROVIDER_ALIASES = {
    "chatgpt": "openai",
    "codex": "openai",
    "openai-codex": "openai",
    "openai_oauth": "openai",
    "openai-oauth": "openai",
    "claude-code": "claude",
    "anthropic": "claude",
}


def default_provider_configs() -> dict[str, OAuthProviderConfig]:
    return {
        "openai": build_openai_provider_config(),
        "claude": build_claude_provider_config(),
    }


def normalize_provider_name(provider: str) -> str:
    normalized = provider.strip().lower()
    return _PROVIDER_ALIASES.get(normalized, normalized)


def resolve_runtime_oauth_provider(provider_name: str, model: str | None = None) -> str | None:
    normalized = provider_name.strip().lower()
    if normalized in {"codex", "openai_oauth", "openai-oauth"}:
        return "openai"
    if normalized == "claude":
        return "claude"
    if model:
        lowered = model.lower()
        if lowered.startswith("openai/"):
            return "openai"
        if lowered.startswith("anthropic/") or lowered.startswith("claude/"):
            return "claude"
    return None


def resolve_provider_config(
    provider: str,
    configs: Mapping[str, OAuthProviderConfig] | None = None,
) -> OAuthProviderConfig:
    normalized = normalize_provider_name(provider)
    available = dict(default_provider_configs()) if configs is None else dict(configs)
    try:
        config = available[normalized]
    except KeyError as exc:
        raise OAuthConfigError(f"OAuth provider '{provider}' is not configured.") from exc
    if not config.client_id:
        env_name = f"JULES_{normalized.upper()}_CLIENT_ID"
        raise OAuthConfigError(
            f"OAuth provider '{normalized}' is missing a client_id. Set {env_name}."
        )
    return config
