"""OpenAI OAuth provider config."""

from __future__ import annotations

import os

from jules.auth.base import OAuthProviderConfig

OPENAI_DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


def build_openai_provider_config() -> OAuthProviderConfig:
    return OAuthProviderConfig(
        name="openai",
        authorization_url=os.getenv("JULES_OPENAI_AUTH_URL", "https://auth.openai.com/oauth/authorize"),
        client_id=os.getenv("JULES_OPENAI_CLIENT_ID", OPENAI_DEFAULT_CLIENT_ID),
        token_url=os.getenv("JULES_OPENAI_TOKEN_URL", "https://auth.openai.com/oauth/token"),
        redirect_path="/auth/callback",
        scope=os.getenv("JULES_OPENAI_SCOPE", "openid profile email offline_access"),
        localhost_port=int(os.getenv("JULES_OPENAI_CALLBACK_PORT", "1455")),
        extra_authorization_params={
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": os.getenv("JULES_OPENAI_ORIGINATOR", "jules"),
        },
        token_request_encoding="form",
        refresh_request_encoding="form",
        device_code_url=os.getenv(
            "JULES_OPENAI_DEVICE_CODE_URL",
            "https://auth.openai.com/api/accounts/deviceauth/usercode",
        ),
        device_token_url=os.getenv(
            "JULES_OPENAI_DEVICE_TOKEN_URL",
            "https://auth.openai.com/api/accounts/deviceauth/token",
        ),
        device_verification_url=os.getenv(
            "JULES_OPENAI_DEVICE_VERIFICATION_URL",
            "https://auth.openai.com/codex/device",
        ),
        device_callback_uri=os.getenv(
            "JULES_OPENAI_DEVICE_CALLBACK_URI",
            "https://auth.openai.com/deviceauth/callback",
        ),
        cli_env_var="CODEX_ACCESS_TOKEN",
    )
