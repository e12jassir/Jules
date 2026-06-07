from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import importlib.util
import json
import socket
import stat
import unittest
import urllib.error
import urllib.request

_auth_pkce = importlib.import_module("jules.core.auth_pkce")
OAuthProviderConfig = _auth_pkce.OAuthProviderConfig
TokenRecord = _auth_pkce.TokenRecord
TokenStore = _auth_pkce.TokenStore
build_authorization_url = _auth_pkce.build_authorization_url
generate_code_challenge = _auth_pkce.generate_code_challenge
generate_code_verifier = _auth_pkce.generate_code_verifier
capture_authorization_code = _auth_pkce.capture_authorization_code
OAuthCallbackError = _auth_pkce.OAuthCallbackError
cli_environment_for_runtime = _auth_pkce.cli_environment_for_runtime
default_provider_configs = _auth_pkce.default_provider_configs
get_auth_status = _auth_pkce.get_auth_status
normalize_provider_name = _auth_pkce.normalize_provider_name
logout_provider = _auth_pkce.logout_provider
resolve_runtime_oauth_provider = _auth_pkce.resolve_runtime_oauth_provider


def test_generate_code_verifier_returns_high_entropy_urlsafe_value() -> None:
    verifier = generate_code_verifier()

    assert len(verifier) >= 86
    assert "=" not in verifier
    assert verifier != generate_code_verifier()


def test_generate_code_challenge_uses_s256_base64url_without_padding() -> None:
    verifier = "test-verifier"
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")

    assert generate_code_challenge(verifier) == expected
    assert "=" not in generate_code_challenge(verifier)


def test_build_authorization_url_includes_pkce_parameters() -> None:
    config = OAuthProviderConfig(
        name="example",
        authorization_url="https://example.test/oauth/authorize",
        client_id="client-123",
        token_url="https://example.test/oauth/token",
        scope="openid profile",
        localhost_port=1455,
        redirect_path="/auth/callback",
    )

    url = build_authorization_url(config, "verifier", state="state-123")

    assert url.startswith("https://example.test/oauth/authorize?")
    assert "response_type=code" in url
    assert "client_id=client-123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback" in url
    assert "code_challenge_method=S256" in url
    assert "scope=openid+profile" in url
    assert "state=state-123" in url


def test_token_record_computes_expiration_from_token_response() -> None:
    record = TokenRecord.from_token_response(
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "profile",
        },
        now=1000,
    )

    assert record.expires_at == 4600
    assert not record.is_expired(now=2000)
    assert record.is_expired(now=4550)


def _unused_localhost_port() -> int:
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return int(sock.getsockname()[1])


def _read_url(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def _skip_without_aiohttp() -> None:
    if importlib.util.find_spec("aiohttp") is None:
        raise unittest.SkipTest("aiohttp is not installed")


async def _wait_for_server(url: str) -> None:
    for _ in range(50):
        try:
            await asyncio.to_thread(_read_url, url)
            return
        except OSError:
            await asyncio.sleep(0.01)
    raise AssertionError("callback server did not start")


async def test_callback_ignores_wrong_state_then_accepts_valid_code() -> None:
    _skip_without_aiohttp()
    port = _unused_localhost_port()
    config = OAuthProviderConfig(
        name="example",
        authorization_url="https://example.test/oauth/authorize",
        client_id="client-123",
        token_url="https://example.test/oauth/token",
        localhost_port=port,
    )
    task = asyncio.create_task(
        capture_authorization_code(
            config,
            "https://example.test/auth",
            expected_state="expected-state",
            timeout_seconds=2,
            open_browser=False,
        )
    )

    try:
        await _wait_for_server(f"http://localhost:{port}/callback?state=wrong-state&error=bad")
        wrong_status, _ = await asyncio.to_thread(
            _read_url,
            f"http://localhost:{port}/callback?state=wrong-state&error=bad",
        )
        assert wrong_status == 400
        assert not task.done()

        ok_status, ok_body = await asyncio.to_thread(
            _read_url,
            f"http://localhost:{port}/callback?state=expected-state&code=real-code",
        )
        assert ok_status == 200
        assert "Login successful" in ok_body
        assert await task == "real-code"
    finally:
        if not task.done():
            task.cancel()


async def test_callback_escapes_oauth_error_html() -> None:
    _skip_without_aiohttp()
    port = _unused_localhost_port()
    config = OAuthProviderConfig(
        name="example",
        authorization_url="https://example.test/oauth/authorize",
        client_id="client-123",
        token_url="https://example.test/oauth/token",
        localhost_port=port,
    )
    task = asyncio.create_task(
        capture_authorization_code(
            config,
            "https://example.test/auth",
            expected_state="expected-state",
            timeout_seconds=2,
            open_browser=False,
        )
    )

    try:
        await _wait_for_server(f"http://localhost:{port}/callback?state=wrong-state")
        status, body = await asyncio.to_thread(
            _read_url,
            f"http://localhost:{port}/callback?state=expected-state&error=%3Cscript%3Ealert(1)%3C/script%3E",
        )
        assert status == 400
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
        assert "<script>alert(1)</script>" not in body
        try:
            await task
        except OAuthCallbackError as exc:
            assert "<script>alert" in str(exc)
        else:
            raise AssertionError("expected OAuthCallbackError")
    finally:
        if not task.done():
            task.cancel()


async def test_callback_missing_code_returns_error() -> None:
    _skip_without_aiohttp()
    port = _unused_localhost_port()
    config = OAuthProviderConfig(
        name="example",
        authorization_url="https://example.test/oauth/authorize",
        client_id="client-123",
        token_url="https://example.test/oauth/token",
        localhost_port=port,
    )
    task = asyncio.create_task(
        capture_authorization_code(
            config,
            "https://example.test/auth",
            expected_state="expected-state",
            timeout_seconds=2,
            open_browser=False,
        )
    )

    try:
        await _wait_for_server(f"http://localhost:{port}/callback?state=wrong-state")
        status, body = await asyncio.to_thread(
            _read_url,
            f"http://localhost:{port}/callback?state=expected-state",
        )
        assert status == 400
        assert "did not include a code" in body
        try:
            await task
        except OAuthCallbackError as exc:
            assert "did not include a code" in str(exc)
        else:
            raise AssertionError("expected OAuthCallbackError")
    finally:
        if not task.done():
            task.cancel()


async def test_callback_timeout_cleans_up_server() -> None:
    _skip_without_aiohttp()
    port = _unused_localhost_port()
    config = OAuthProviderConfig(
        name="example",
        authorization_url="https://example.test/oauth/authorize",
        client_id="client-123",
        token_url="https://example.test/oauth/token",
        localhost_port=port,
    )

    try:
        await capture_authorization_code(
            config,
            "https://example.test/auth",
            timeout_seconds=0.01,
            open_browser=False,
        )
    except OAuthCallbackError as exc:
        assert "Timed out" in str(exc)
    else:
        raise AssertionError("expected OAuthCallbackError")

    with socket.socket() as sock:
        sock.bind(("localhost", port))


def test_normalize_provider_name_maps_aliases() -> None:
    assert normalize_provider_name("codex") == "openai"
    assert normalize_provider_name("anthropic") == "claude"
    assert normalize_provider_name("openai") == "openai"


def test_resolve_runtime_oauth_provider_maps_codex_and_model_families() -> None:
    assert resolve_runtime_oauth_provider("codex", None) == "openai"
    assert resolve_runtime_oauth_provider("openai_oauth", None) == "openai"
    assert resolve_runtime_oauth_provider("other", "openai/gpt-5") == "openai"
    assert resolve_runtime_oauth_provider("other", "anthropic/claude-sonnet") == "claude"
    assert resolve_runtime_oauth_provider("opencode", "opencode/deepseek-v4") is None


def test_default_openai_provider_config_has_codex_defaults() -> None:
    config = default_provider_configs()["openai"]

    assert config.client_id
    assert config.redirect_uri == "http://localhost:1455/auth/callback"
    assert config.cli_env_var == "CODEX_ACCESS_TOKEN"
    assert config.device_code_url is not None


async def test_cli_environment_for_runtime_uses_stored_codex_token(tmp_path) -> None:
    store = TokenStore(tmp_path / "auth_tokens.json")
    store.save("openai", TokenRecord(access_token="token-123", refresh_token="refresh", expires_at=9_999_999_999.0))

    env = await cli_environment_for_runtime("codex", "openai/gpt-5", store=store, auto_login=False)

    assert env == {"CODEX_ACCESS_TOKEN": "token-123"}


def test_logout_provider_removes_saved_token_and_status_updates(tmp_path) -> None:
    store = TokenStore(tmp_path / "auth_tokens.json")
    store.save("claude", TokenRecord(access_token="token-abc", expires_at=123.0))

    assert get_auth_status("claude", store=store).logged_in is True
    assert logout_provider("claude", store=store) is True
    assert get_auth_status("claude", store=store).logged_in is False


def test_token_store_writes_user_only_json_file(tmp_path) -> None:
    token_path = tmp_path / "auth_tokens.json"
    store = TokenStore(token_path)

    store.save("example", TokenRecord(access_token="access", refresh_token="refresh", expires_at=123.0))

    mode = stat.S_IMODE(token_path.stat().st_mode)
    assert mode == 0o600
    assert json.loads(token_path.read_text())["example"]["access_token"] == "access"
    assert store.load("example") == TokenRecord(access_token="access", refresh_token="refresh", expires_at=123.0)
