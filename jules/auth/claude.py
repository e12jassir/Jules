"""Claude OAuth provider config."""

from __future__ import annotations

import os

from jules.auth.base import OAuthProviderConfig

CLAUDE_DEFAULT_AUTH_URL = "https://claude.ai/oauth/authorize"
CLAUDE_DEFAULT_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"


def build_claude_provider_config() -> OAuthProviderConfig:
    return OAuthProviderConfig(
        name="claude",
        authorization_url=os.getenv("JULES_CLAUDE_AUTH_URL", CLAUDE_DEFAULT_AUTH_URL),
        client_id=os.getenv("JULES_CLAUDE_CLIENT_ID", ""),
        token_url=os.getenv("JULES_CLAUDE_TOKEN_URL", CLAUDE_DEFAULT_TOKEN_URL),
        redirect_path=os.getenv("JULES_CLAUDE_REDIRECT_PATH", "/callback"),
        scope=os.getenv(
            "JULES_CLAUDE_SCOPE",
            "user:profile user:inference user:sessions:claude_code user:mcp_servers",
        ),
        localhost_port=int(os.getenv("JULES_CLAUDE_CALLBACK_PORT", "53692")),
        token_request_encoding=os.getenv("JULES_CLAUDE_TOKEN_ENCODING", "json"),
        refresh_request_encoding=os.getenv("JULES_CLAUDE_REFRESH_ENCODING", "json"),
        cli_env_var="CLAUDE_CODE_OAUTH_TOKEN",
    )
