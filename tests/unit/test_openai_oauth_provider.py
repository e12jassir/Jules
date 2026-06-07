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
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.post_calls: list[tuple[str, dict[str, str], dict[str, Any]]] = []
        self.get_calls: list[tuple[str, dict[str, str]]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FakeResponse:
        self.post_calls.append((url, headers, json))
        return self.response

    def stream(self, method: str, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FakeStreamContext:
        assert method == "POST"
        self.post_calls.append((url, headers, json))
        return _FakeStreamContext(self.response)

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
    client = _FakeAsyncClient(
        _FakeResponse(payload={"output_text": "hello from oauth"})
    )

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        assert provider_name == "openai"
        assert auto_login is False
        return type("Token", (), {"access_token": "oauth-token"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(
        "httpx.AsyncClient",
        lambda timeout: client,
    )

    result = await provider.ask("hi", _context(), "gpt-5")

    assert result == "hello from oauth"
    assert client.post_calls[0][0].endswith("/responses")
    assert client.post_calls[0][1]["Authorization"] == "Bearer oauth-token"
    assert client.post_calls[0][2] == {"model": "gpt-5", "input": "hi"}


async def test_openai_oauth_stream_yields_text_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    stream_text = "\n".join(
        [
            'data: {"type":"response.output_text.delta","delta":"hel"}',
            "",
            'data: {"type":"response.output_text.delta","delta":"lo"}',
            "",
            "data: [DONE]",
            "",
        ]
    )
    client = _FakeAsyncClient(_FakeResponse(text=stream_text))

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        del provider_name, auto_login
        return type("Token", (), {"access_token": "oauth-token"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: client)

    chunks = []
    async for chunk in provider.stream("hi", _context(), "gpt-5"):
        chunks.append(chunk)

    assert chunks == ["hel", "lo"]
    assert client.post_calls[0][2]["stream"] is True


async def test_openai_oauth_stream_uses_completed_event_when_no_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    stream_text = "\n".join(
        [
            'data: {"type":"response.completed","response":{"output_text":"hello from completed"}}',
            "",
            "data: [DONE]",
            "",
        ]
    )
    client = _FakeAsyncClient(_FakeResponse(text=stream_text))

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        del provider_name, auto_login
        return type("Token", (), {"access_token": "oauth-token"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: client)

    chunks = []
    async for chunk in provider.stream("hi", _context(), "gpt-5"):
        chunks.append(chunk)

    assert chunks == ["hello from completed"]


async def test_openai_oauth_stream_does_not_duplicate_completed_text_after_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    stream_text = "\n".join(
        [
            'data: {"type":"response.output_text.delta","delta":"hel"}',
            "",
            'data: {"type":"response.output_text.delta","delta":"lo"}',
            "",
            'data: {"type":"response.completed","response":{"output_text":"hello"}}',
            "",
            "data: [DONE]",
            "",
        ]
    )
    client = _FakeAsyncClient(_FakeResponse(text=stream_text))

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        del provider_name, auto_login
        return type("Token", (), {"access_token": "oauth-token"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: client)

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
        return type("Token", (), {"access_token": "oauth-token"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: client)

    assert await provider.list_models() == ("gpt-5", "gpt-5-mini")


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
    client = _FakeAsyncClient(_FakeResponse(status_code=401, text="unauthorized"))

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        del provider_name, auto_login
        return type("Token", (), {"access_token": "oauth-token"})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)
    monkeypatch.setattr("httpx.AsyncClient", lambda timeout: client)

    with pytest.raises(ProviderError, match="401"):
        await provider.ask("hi", _context(), "gpt-5")
