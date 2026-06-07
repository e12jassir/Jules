"""Shared OAuth primitives, PKCE helpers, token storage, and login flows."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import os
import secrets
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlencode, urlparse

DEFAULT_TOKEN_PATH = Path.home() / ".jules" / "auth_tokens.json"
CALLBACK_SUCCESS_HTML = """<!doctype html>
<html lang=\"en\">
  <head><meta charset=\"utf-8\"><title>Jules Login</title></head>
  <body style=\"font-family: system-ui, sans-serif; margin: 3rem;\">
    <h1>✅ Login successful</h1>
    <p>You can close this tab and return to the terminal.</p>
  </body>
</html>
"""
CALLBACK_ERROR_HTML = """<!doctype html>
<html lang=\"en\">
  <head><meta charset=\"utf-8\"><title>Jules Login</title></head>
  <body style=\"font-family: system-ui, sans-serif; margin: 3rem;\">
    <h1>Login failed</h1>
    <p>{message}</p>
  </body>
</html>
"""


class OAuthError(RuntimeError):
    """Base OAuth failure."""


class OAuthConfigError(OAuthError):
    """Raised when OAuth provider configuration is incomplete."""


class OAuthCallbackError(OAuthError):
    """Raised when the local OAuth callback returns an error or times out."""


class OAuthTokenError(OAuthError):
    """Raised when token exchange or refresh fails."""


class OAuthDeviceCodeError(OAuthError):
    """Raised when device code login fails."""


@dataclass(frozen=True)
class OAuthProviderConfig:
    """Provider-specific OAuth authorization metadata."""

    name: str
    authorization_url: str
    client_id: str
    token_url: str
    redirect_path: str = "/callback"
    scope: str | None = None
    localhost_port: int = 53692
    extra_authorization_params: Mapping[str, str] = field(default_factory=dict)
    token_request_encoding: str = "form"
    refresh_request_encoding: str = "form"
    device_code_url: str | None = None
    device_token_url: str | None = None
    device_verification_url: str | None = None
    device_callback_uri: str | None = None
    cli_env_var: str | None = None

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.localhost_port}{self.redirect_path}"


@dataclass(frozen=True)
class DeviceCodeInfo:
    """Server-side device-code challenge details shown to the user."""

    user_code: str
    verification_url: str
    device_auth_id: str
    interval: float = 5.0


@dataclass(frozen=True)
class TokenRecord:
    """Stored OAuth token payload for one provider."""

    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None
    token_type: str = "Bearer"
    scope: str | None = None
    id_token: str | None = None

    @classmethod
    def from_token_response(cls, payload: Mapping[str, Any], now: float | None = None) -> "TokenRecord":
        issued_at = time.time() if now is None else now
        expires_in = payload.get("expires_in")
        expires_at = issued_at + float(expires_in) if expires_in is not None else payload.get("expires_at")
        return cls(
            access_token=str(payload["access_token"]),
            refresh_token=_optional_str(payload.get("refresh_token")),
            expires_at=float(expires_at) if expires_at is not None else None,
            token_type=str(payload.get("token_type", "Bearer")),
            scope=_optional_str(payload.get("scope")),
            id_token=_optional_str(payload.get("id_token")),
        )

    def is_expired(self, skew_seconds: int = 60, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        current_time = time.time() if now is None else now
        return current_time >= self.expires_at - skew_seconds

    def to_json(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
            "scope": self.scope,
            "id_token": self.id_token,
        }


@dataclass(frozen=True)
class AuthStatus:
    provider: str
    logged_in: bool
    expired: bool
    expires_at: float | None = None


class TokenStore:
    """JSON token store with user-only file permissions."""

    def __init__(self, path: Path = DEFAULT_TOKEN_PATH) -> None:
        self.path = path

    def load_all(self) -> dict[str, TokenRecord]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return {}
        if not isinstance(raw, dict):
            return {}
        return {
            provider: TokenRecord(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expires_at=data.get("expires_at"),
                token_type=data.get("token_type", "Bearer"),
                scope=data.get("scope"),
                id_token=data.get("id_token"),
            )
            for provider, data in raw.items()
            if isinstance(data, dict) and "access_token" in data
        }

    def load(self, provider: str) -> TokenRecord | None:
        from jules.auth.registry import normalize_provider_name

        return self.load_all().get(normalize_provider_name(provider))

    def save(self, provider: str, token: TokenRecord) -> None:
        from jules.auth.registry import normalize_provider_name

        tokens = {name: record.to_json() for name, record in self.load_all().items()}
        tokens[normalize_provider_name(provider)] = token.to_json()
        self._write(tokens)

    def delete(self, provider: str) -> bool:
        from jules.auth.registry import normalize_provider_name

        normalized = normalize_provider_name(provider)
        tokens = {name: record.to_json() for name, record in self.load_all().items()}
        removed = tokens.pop(normalized, None) is not None
        self._write(tokens)
        return removed

    def _write(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(payload, file, indent=2, sort_keys=True)
                file.write("\n")
        finally:
            os.chmod(self.path, 0o600)


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorization_url(config: OAuthProviderConfig, verifier: str, state: str | None = None) -> str:
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "code_challenge": generate_code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    if config.scope:
        params["scope"] = config.scope
    if state:
        params["state"] = state
    for key, value in config.extra_authorization_params.items():
        params[str(key)] = str(value)
    return f"{config.authorization_url}?{urlencode(params)}"


def parse_authorization_input(value: str) -> tuple[str | None, str | None]:
    stripped = value.strip()
    if not stripped:
        return None, None
    if "://" not in stripped:
        return stripped, None
    parsed = urlparse(stripped)
    query = parse_qs(parsed.query)
    code = query.get("code", [None])[0]
    state = query.get("state", [None])[0]
    return code, state


async def exchange_code_for_token(
    config: OAuthProviderConfig,
    code: str,
    verifier: str,
    *,
    redirect_uri: str | None = None,
) -> TokenRecord:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": config.client_id,
        "redirect_uri": redirect_uri or config.redirect_uri,
        "code_verifier": verifier,
    }
    data = await _post_json(config.token_url, payload, encoding=config.token_request_encoding)
    return TokenRecord.from_token_response(data)


async def refresh_token_record(config: OAuthProviderConfig, token: TokenRecord) -> TokenRecord:
    if not token.refresh_token:
        raise OAuthTokenError(f"Stored {config.name} token does not include a refresh token.")
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": token.refresh_token,
        "client_id": config.client_id,
    }
    data = await _post_json(config.token_url, payload, encoding=config.refresh_request_encoding)
    return TokenRecord.from_token_response({**data, "refresh_token": data.get("refresh_token") or token.refresh_token})


async def request_device_code(config: OAuthProviderConfig) -> DeviceCodeInfo:
    if not config.device_code_url or not config.device_token_url or not config.device_verification_url:
        raise OAuthDeviceCodeError(f"Provider '{config.name}' does not support device code login.")
    data = await _post_json(config.device_code_url, {"client_id": config.client_id}, encoding="json")
    return DeviceCodeInfo(
        user_code=str(data["user_code"]),
        verification_url=str(config.device_verification_url),
        device_auth_id=str(data["device_auth_id"]),
        interval=float(data.get("interval", 5)),
    )


async def poll_device_code_authorization(
    config: OAuthProviderConfig,
    info: DeviceCodeInfo,
    *,
    timeout_seconds: int = 900,
) -> tuple[str, str]:
    if not config.device_token_url:
        raise OAuthDeviceCodeError(f"Provider '{config.name}' does not support device code login.")
    started = time.monotonic()
    while True:
        if time.monotonic() - started >= timeout_seconds:
            raise OAuthDeviceCodeError("Device code login timed out.")
        response = await _post_json(
            config.device_token_url,
            {"device_auth_id": info.device_auth_id, "user_code": info.user_code},
            encoding="json",
            allow_pending=True,
        )
        status = str(response.get("_status", "")).lower()
        if status == "pending":
            await asyncio.sleep(max(info.interval, 1))
            continue
        if "authorization_code" in response and "code_verifier" in response:
            return str(response["authorization_code"]), str(response["code_verifier"])
        raise OAuthDeviceCodeError("Device code login failed before authorization completed.")


async def login_with_device_code(
    config: OAuthProviderConfig,
    *,
    notify: Callable[[str], None] | None = None,
    timeout_seconds: int = 900,
) -> TokenRecord:
    info = await request_device_code(config)
    if notify is not None:
        notify(f"Open {info.verification_url} and enter code {info.user_code}. Waiting for approval...")
    code, verifier = await poll_device_code_authorization(config, info, timeout_seconds=timeout_seconds)
    redirect_uri = config.device_callback_uri or config.redirect_uri
    return await exchange_code_for_token(config, code, verifier, redirect_uri=redirect_uri)


async def login_with_pkce(
    config: OAuthProviderConfig,
    *,
    timeout_seconds: int = 300,
    open_browser: bool = True,
) -> TokenRecord:
    code, verifier = await start_pkce_login(
        config,
        timeout_seconds=timeout_seconds,
        open_browser=open_browser,
    )
    return await exchange_code_for_token(config, code, verifier)


async def login_provider(
    provider: str,
    *,
    store: TokenStore | None = None,
    configs: Mapping[str, OAuthProviderConfig] | None = None,
    prefer_device_code: bool = False,
    open_browser: bool = True,
    timeout_seconds: int = 300,
    notify: Callable[[str], None] | None = None,
) -> TokenRecord:
    from jules.auth.registry import resolve_provider_config

    config = resolve_provider_config(provider, configs)
    if prefer_device_code:
        token = await login_with_device_code(config, notify=notify, timeout_seconds=max(timeout_seconds, 900))
    else:
        token = await login_with_pkce(config, timeout_seconds=timeout_seconds, open_browser=open_browser)
    (store or TokenStore()).save(config.name, token)
    return token


async def refresh_token_if_needed(
    provider: str,
    *,
    store: TokenStore | None = None,
    configs: Mapping[str, OAuthProviderConfig] | None = None,
    skew_seconds: int = 60,
) -> TokenRecord | None:
    from jules.auth.registry import resolve_provider_config

    token_store = store or TokenStore()
    config = resolve_provider_config(provider, configs)
    token = token_store.load(config.name)
    if token is None:
        return None
    if not token.is_expired(skew_seconds=skew_seconds):
        return token
    refreshed = await refresh_token_record(config, token)
    token_store.save(config.name, refreshed)
    return refreshed


async def get_valid_token(
    provider: str,
    *,
    store: TokenStore | None = None,
    configs: Mapping[str, OAuthProviderConfig] | None = None,
    auto_login: bool = False,
    prefer_device_code: bool = False,
    notify: Callable[[str], None] | None = None,
) -> TokenRecord:
    from jules.auth.registry import resolve_provider_config

    token_store = store or TokenStore()
    config = resolve_provider_config(provider, configs)
    token = token_store.load(config.name)
    if token is not None and not token.is_expired():
        return token
    if token is not None and token.refresh_token:
        try:
            refreshed = await refresh_token_record(config, token)
        except OAuthTokenError:
            if not auto_login:
                raise
        else:
            token_store.save(config.name, refreshed)
            return refreshed
    if not auto_login:
        raise OAuthTokenError(f"No valid {config.name} token is available.")
    return await login_provider(
        config.name,
        store=token_store,
        configs=configs,
        prefer_device_code=prefer_device_code,
        notify=notify,
    )


def logout_provider(provider: str, *, store: TokenStore | None = None) -> bool:
    return (store or TokenStore()).delete(provider)


def get_auth_status(provider: str, *, store: TokenStore | None = None) -> AuthStatus:
    from jules.auth.registry import normalize_provider_name

    normalized = normalize_provider_name(provider)
    token = (store or TokenStore()).load(normalized)
    if token is None:
        return AuthStatus(provider=normalized, logged_in=False, expired=False, expires_at=None)
    return AuthStatus(provider=normalized, logged_in=True, expired=token.is_expired(), expires_at=token.expires_at)


async def cli_environment_for_runtime(
    provider_name: str,
    model: str | None = None,
    *,
    store: TokenStore | None = None,
    configs: Mapping[str, OAuthProviderConfig] | None = None,
    auto_login: bool = True,
    prefer_device_code: bool = False,
    notify: Callable[[str], None] | None = None,
) -> dict[str, str]:
    from jules.auth.registry import resolve_provider_config, resolve_runtime_oauth_provider

    oauth_provider = resolve_runtime_oauth_provider(provider_name, model)
    if oauth_provider is None:
        return {}
    config = resolve_provider_config(oauth_provider, configs)
    if not config.cli_env_var:
        return {}
    token = await get_valid_token(
        oauth_provider,
        store=store,
        configs=configs,
        auto_login=auto_login,
        prefer_device_code=prefer_device_code,
        notify=notify,
    )
    return {config.cli_env_var: token.access_token}


async def start_pkce_login(
    config: OAuthProviderConfig,
    *,
    timeout_seconds: int = 300,
    open_browser: bool = True,
) -> tuple[str, str]:
    verifier = generate_code_verifier()
    state = secrets.token_urlsafe(32)
    auth_url = build_authorization_url(config, verifier, state)
    code = await capture_authorization_code(
        config,
        auth_url,
        expected_state=state,
        timeout_seconds=timeout_seconds,
        open_browser=open_browser,
    )
    return code, verifier


def _require_aiohttp_web() -> Any:
    try:
        from aiohttp import web as aiohttp_web
    except ModuleNotFoundError as exc:
        raise RuntimeError("aiohttp is required for OAuth PKCE callback capture") from exc
    return aiohttp_web


def _require_aiohttp_client() -> Any:
    try:
        import aiohttp
    except ModuleNotFoundError as exc:
        raise RuntimeError("aiohttp is required for OAuth token exchange") from exc
    return aiohttp


async def capture_authorization_code(
    config: OAuthProviderConfig,
    auth_url: str,
    *,
    expected_state: str | None = None,
    timeout_seconds: int = 300,
    open_browser: bool = True,
) -> str:
    web = _require_aiohttp_web()
    completed = asyncio.Event()
    result: dict[str, str] = {}

    async def handle_callback(request: Any) -> Any:
        error = request.query.get("error")
        code = request.query.get("code")
        state = request.query.get("state")
        if expected_state is not None and state != expected_state:
            return web.Response(
                text=CALLBACK_ERROR_HTML.format(message="OAuth callback state did not match."),
                content_type="text/html",
                status=400,
            )
        if error:
            result["error"] = error
            completed.set()
            return web.Response(
                text=CALLBACK_ERROR_HTML.format(message=html.escape(error)),
                content_type="text/html",
                status=400,
            )
        if not code:
            result["error"] = "OAuth callback did not include a code parameter."
            completed.set()
            return web.Response(
                text=CALLBACK_ERROR_HTML.format(message=result["error"]),
                content_type="text/html",
                status=400,
            )
        result["code"] = code
        completed.set()
        return web.Response(text=CALLBACK_SUCCESS_HTML, content_type="text/html")

    app = web.Application()
    app.router.add_get(config.redirect_path, handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", config.localhost_port)
    try:
        await site.start()
        if open_browser:
            webbrowser.open(auth_url)
        await asyncio.wait_for(completed.wait(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise OAuthCallbackError("Timed out waiting for OAuth callback.") from exc
    finally:
        await runner.cleanup()

    if "error" in result:
        raise OAuthCallbackError(result["error"])
    return result["code"]


async def _post_json(
    url: str,
    payload: Mapping[str, Any],
    *,
    encoding: str,
    allow_pending: bool = False,
) -> dict[str, Any]:
    aiohttp = _require_aiohttp_client()
    timeout = aiohttp.ClientTimeout(total=30)
    if encoding == "json":
        request_kwargs = {"json": dict(payload)}
    elif encoding == "form":
        request_kwargs = {"data": {key: str(value) for key, value in payload.items() if value is not None}}
    else:
        raise OAuthConfigError(f"Unsupported OAuth request encoding: {encoding}")

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, **request_kwargs) as response:
            text = await response.text()
            if allow_pending and response.status in {202, 403, 404}:
                return {"_status": "pending", "_body": text}
            if response.status >= 400:
                raise OAuthTokenError(f"OAuth request failed: {response.status} {text.strip()}")
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise OAuthTokenError(f"OAuth response was not valid JSON: {text[:200]!r}") from exc
            if not isinstance(data, dict):
                raise OAuthTokenError("OAuth response body must be a JSON object.")
            return data


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    as_text = str(value).strip()
    return as_text or None
