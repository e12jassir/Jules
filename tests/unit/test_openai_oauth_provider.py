from __future__ import annotations

import json
from typing import Any

import pytest

from jules.memory.models import SessionContext
from jules.providers.base import ProviderError
from jules.providers.openai_oauth import OpenAIOAuthProvider


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload

    async def aread(self) -> bytes:
        return self.text.encode()

    async def aiter_lines(self):
        for line in self.text.splitlines():
            yield line


class _FakeStreamContext:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> _FakeResponse:
        return self.response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.post_calls = []
        self.get_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, *, headers, json):
        self.post_calls.append((url, headers, json))
        return self.response

    def stream(self, method, url, *, headers, json):
        assert method == "POST"
        self.post_calls.append((url, headers, json))
        return _FakeStreamContext(self.response)

class _FakeWebSocket:
    def __init__(self, messages=None, error=False):
        self.messages = messages or []
        self.error = error
        self.sent_messages = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def send(self, data):
        self.sent_messages.append(data)

    async def recv(self):
        if self.error:
            raise Exception("Mocked connection error")
        if not self.messages:
            return '{"type": "response.done"}'
        return self.messages.pop(0)

class _FakeWebsocketsConnect:
    def __init__(self, ws):
        self.ws = ws
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.ws

    async def get(self, url: str, *, headers: dict[str, str]) -> _FakeResponse:
        self.get_calls.append((url, headers))
        return self.response


def _context() -> SessionContext:
    return SessionContext(
        project="Jules",
        directory="/tmp/jules",
        active_files=[],
        inferred_intent="testing",
        time_of_day="night",
    )


async def test_openai_oauth_ask_uses_responses_api(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    ws = _FakeWebSocket(messages=[
        '{"type": "response.text.delta", "delta": "hello "}',
        '{"type": "response.text.delta", "delta": "from "}',
        '{"type": "response.text.delta", "delta": "oauth"}',
        '{"type": "response.done"}'
    ])
    connector = _FakeWebsocketsConnect(ws)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": "header.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOiB7ImNoYXRncHRfYWNjb3VudF9pZCI6ICIxMjM0NSJ9fQ==.signature"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("websockets.connect", connector)

    result = await provider.ask("hi", _context(), "gpt-5")

    assert result == "hello from oauth"
    assert connector.calls[0][0] == "wss://chatgpt.com/backend-api/codex/responses"


async def test_openai_oauth_stream_yields_text_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    ws = _FakeWebSocket(messages=[
        '{"type": "response.text.delta", "delta": "hel"}',
        '{"type": "response.text.delta", "delta": "lo"}',
        '{"type": "response.done"}'
    ])
    connector = _FakeWebsocketsConnect(ws)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": "header.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOiB7ImNoYXRncHRfYWNjb3VudF9pZCI6ICIxMjM0NSJ9fQ==.signature"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("websockets.connect", connector)

    chunks = []
    async for chunk in provider.stream("hi", _context(), "gpt-5"):
        chunks.append(chunk)

    assert chunks == ["hel", "lo"]


async def test_openai_oauth_stream_uses_completed_event_when_no_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    ws = _FakeWebSocket(messages=[
        '{"type": "response.completed", "response": {"output_text": "hello from completed"}}',
        '{"type": "response.done"}'
    ])
    connector = _FakeWebsocketsConnect(ws)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": "header.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOiB7ImNoYXRncHRfYWNjb3VudF9pZCI6ICIxMjM0NSJ9fQ==.signature"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("websockets.connect", connector)

    chunks = []
    async for chunk in provider.stream("hi", _context(), "gpt-5"):
        chunks.append(chunk)

    # The new websocket implementation only looks for 'response.text.delta',
    # so 'response.completed' events are ignored to avoid duplicate text.
    assert chunks == []


async def test_openai_oauth_stream_does_not_duplicate_completed_text_after_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    ws = _FakeWebSocket(messages=[
        '{"type": "response.text.delta", "delta": "hel"}',
        '{"type": "response.text.delta", "delta": "lo"}',
        '{"type": "response.completed", "response": {"output_text": "hello"}}',
        '{"type": "response.done"}'
    ])
    connector = _FakeWebsocketsConnect(ws)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": "header.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOiB7ImNoYXRncHRfYWNjb3VudF9pZCI6ICIxMjM0NSJ9fQ==.signature"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("websockets.connect", connector)

    chunks = []
    async for chunk in provider.stream("hi", _context(), "gpt-5"):
        chunks.append(chunk)

    assert chunks == ["hel", "lo"]


async def test_openai_oauth_list_models_returns_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    client = _FakeAsyncClient(
        _FakeResponse(payload={"data": [{"id": "gpt-5"}, {"id": "gpt-5-mini"}]})
    )

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        del provider_name, auto_login
        return type("Token", (), {"access_token": "header.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOiB7ImNoYXRncHRfYWNjb3VudF9pZCI6ICIxMjM0NSJ9fQ==.signature"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: client)

    assert await provider.list_models() == ("gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.4-pro", "gpt-5.4-mini", "gpt-5.4-nano")


def test_openai_oauth_extracts_output_text_from_nested_response() -> None:
    payload = {
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "hello"},
                    {"type": "output_text", "text": " world"},
                ]
            }
        ]
    }

    assert OpenAIOAuthProvider._extract_output_text(payload) == "hello world"


async def test_openai_oauth_ask_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    ws = _FakeWebSocket(error=True)
    connector = _FakeWebsocketsConnect(ws)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        return type("Token", (), {"access_token": "header.eyJodHRwczovL2FwaS5vcGVuYWkuY29tL2F1dGgiOiB7ImNoYXRncHRfYWNjb3VudF9pZCI6ICIxMjM0NSJ9fQ==.signature"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("websockets.connect", connector)

    with pytest.raises(ProviderError, match="OpenAI OAuth request failed"):
        await provider.ask("hi", _context(), "gpt-5")
