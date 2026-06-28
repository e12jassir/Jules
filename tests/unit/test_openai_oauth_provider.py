from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from jules.memory.models import SessionContext
from jules.providers.base import ProviderError
from jules.providers.openai_oauth import OpenAIOAuthProvider

FAKE_JWT = "header.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOiB7ImNoYXRncHRfYWNjb3VudF9pZCI6ICJhY2MtMTIzIn19.signature"


class _FakeWebSocket:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages
        self.sent: list[str] = []

    async def __aenter__(self) -> _FakeWebSocket:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        if not self.messages:
            # Simulate socket close or EOF
            raise asyncio.CancelledError()
        msg = self.messages.pop(0)
        return json.dumps(msg)


def _context() -> SessionContext:
    return SessionContext(
        project="Jules",
        directory="/tmp/jules",
        active_files=[],
        inferred_intent="testing",
        time_of_day="night",
    )


async def test_openai_oauth_ask_uses_websocket(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    ws_responses = [
        {"type": "response.text.delta", "delta": "hello "},
        {"type": "response.text.delta", "delta": "from websocket"},
        {"type": "response.done"},
    ]
    fake_ws = _FakeWebSocket(ws_responses)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        assert provider_name == "openai"
        assert auto_login is False
        return type("Token", (), {"access_token": FAKE_JWT})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)

    connect_calls = []

    def fake_connect(url: str, additional_headers: dict[str, str], open_timeout: float):
        connect_calls.append((url, additional_headers, open_timeout))
        return fake_ws

    import websockets
    monkeypatch.setattr(websockets, "connect", fake_connect)

    result = await provider.ask("hi", _context(), "gpt-5")

    assert result == "hello from websocket"
    assert len(connect_calls) == 1
    assert connect_calls[0][0] == "wss://chatgpt.com/backend-api/codex/responses"
    assert connect_calls[0][1]["Authorization"] == f"Bearer {FAKE_JWT}"
    assert connect_calls[0][1]["chatgpt-account-id"] == "acc-123"

    sent_payload = json.loads(fake_ws.sent[0])
    assert sent_payload["type"] == "response.create"
    assert sent_payload["model"] == "gpt-5"
    assert sent_payload["input"] == "hi"
    assert sent_payload["stream"] is False


async def test_openai_oauth_stream_yields_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    ws_responses = [
        {"type": "response.text.delta", "delta": "stream"},
        {"type": "response.text.delta", "delta": "ing"},
        {"type": "response.done"},
    ]
    fake_ws = _FakeWebSocket(ws_responses)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": FAKE_JWT})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)

    def fake_connect(url: str, additional_headers: dict[str, str], open_timeout: float):
        return fake_ws

    import websockets
    monkeypatch.setattr(websockets, "connect", fake_connect)

    chunks = []
    async for chunk in provider.stream("hi", _context(), "gpt-5"):
        chunks.append(chunk)

    assert chunks == ["stream", "ing"]
    sent_payload = json.loads(fake_ws.sent[0])
    assert sent_payload["stream"] is True


async def test_openai_oauth_stream_yields_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    ws_responses = [
        {"type": "error", "error": {"message": "unauthorized account"}},
    ]
    fake_ws = _FakeWebSocket(ws_responses)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": FAKE_JWT})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)

    def fake_connect(url: str, additional_headers: dict[str, str], open_timeout: float):
        return fake_ws

    import websockets
    monkeypatch.setattr(websockets, "connect", fake_connect)

    chunks = []
    async for chunk in provider.stream("hi", _context(), "gpt-5"):
        chunks.append(chunk)

    assert chunks == ["[Error: unauthorized account]"]


async def test_openai_oauth_ask_raises_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    ws_responses = [
        {"type": "error", "error": {"message": "quota exceeded"}},
    ]
    fake_ws = _FakeWebSocket(ws_responses)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": FAKE_JWT})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)

    def fake_connect(url: str, additional_headers: dict[str, str], open_timeout: float):
        return fake_ws

    import websockets
    monkeypatch.setattr(websockets, "connect", fake_connect)

    with pytest.raises(ProviderError, match="OpenAI WS Error: quota exceeded"):
        await provider.ask("hi", _context(), "gpt-5")


async def test_openai_oauth_list_models_returns_static() -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    assert await provider.list_models() == (
        "gpt-5.5",
        "gpt-5.5-pro",
        "gpt-5.4",
        "gpt-5.4-pro",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
    )


async def test_openai_oauth_health_check(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    # 1. Valid token
    async def fake_get_valid_token_ok(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": FAKE_JWT, "is_expired": lambda *a: False})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token_ok)
    assert await provider.health_check() is True

    # 2. Expired token
    async def fake_get_valid_token_expired(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": FAKE_JWT, "is_expired": lambda *a: True})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token_expired)
    assert await provider.health_check() is False

    # 3. Invalid JWT token format
    async def fake_get_valid_token_bad_jwt(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": "bad-token", "is_expired": lambda *a: False})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token_bad_jwt)
    assert await provider.health_check() is False
