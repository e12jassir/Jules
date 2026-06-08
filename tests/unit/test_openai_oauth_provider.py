from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from jules.memory.models import SessionContext
from jules.providers.base import ProviderError
from jules.providers.openai_oauth import OpenAIOAuthProvider


# Generate a valid-looking mock JWT token payload containing chatgpt_account_id
def _get_mock_jwt_token() -> str:
    payload = {
        "https://api.openai.com/auth": {
            "chatgpt_account_id": "test-account-id"
        }
    }
    payload_bytes = json.dumps(payload).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").replace("=", "")
    return f"header.{payload_b64}.signature"


class _FakeWebSocket:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages
        self.sent: list[str] = []

    async def __aenter__(self) -> _FakeWebSocket:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        pass

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> str:
        if not self.messages:
            raise Exception("WebSocket connection closed")
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


async def test_openai_oauth_ask_uses_responses_api(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        assert provider_name == "openai"
        assert auto_login is False
        return type("Token", (), {"access_token": _get_mock_jwt_token()})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)

    mock_events = [
        {"type": "response.output_text.delta", "delta": "hello"},
        {"type": "response.output_text.delta", "delta": " from oauth"},
        {"type": "response.completed"}
    ]
    ws_mock = _FakeWebSocket(mock_events)

    class FakeConnect:
        def __init__(self, url: str, additional_headers: dict[str, str], open_timeout: float) -> None:
            self.ws = ws_mock

        async def __aenter__(self) -> _FakeWebSocket:
            return self.ws

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            pass

    monkeypatch.setattr("websockets.connect", FakeConnect)

    result = await provider.ask("hi", _context(), "gpt-5.4-mini")

    assert result == "hello from oauth"
    assert len(ws_mock.sent) == 1
    sent_payload = json.loads(ws_mock.sent[0])
    assert sent_payload["model"] == "gpt-5.4-mini"
    assert sent_payload["stream"] is True
    assert sent_payload["input"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "hi"
                }
            ]
        }
    ]


async def test_openai_oauth_stream_yields_text_deltas(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        del provider_name, auto_login
        return type("Token", (), {"access_token": _get_mock_jwt_token()})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)

    mock_events = [
        {"type": "response.output_text.delta", "delta": "hel"},
        {"type": "response.output_text.delta", "delta": "lo"},
        {"type": "response.completed"}
    ]
    ws_mock = _FakeWebSocket(mock_events)

    class FakeConnect:
        def __init__(self, url: str, additional_headers: dict[str, str], open_timeout: float) -> None:
            self.ws = ws_mock

        async def __aenter__(self) -> _FakeWebSocket:
            return self.ws

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            pass

    monkeypatch.setattr("websockets.connect", FakeConnect)

    chunks = []
    async for chunk in provider.stream("hi", _context(), "gpt-5.4-mini"):
        chunks.append(chunk)

    assert chunks == ["hel", "lo"]
    assert len(ws_mock.sent) == 1
    sent_payload = json.loads(ws_mock.sent[0])
    assert sent_payload["stream"] is True


async def test_openai_oauth_list_models_returns_ids() -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)
    models = await provider.list_models()
    assert "gpt-5.4-mini" in models
    assert "gpt-5.5" in models


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


async def test_openai_oauth_ask_raises_on_ws_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIOAuthProvider(timeout_seconds=30.0)

    async def fake_get_valid_token(provider_name: str, *, auto_login: bool = False):
        del provider_name, auto_login
        return type("Token", (), {"access_token": _get_mock_jwt_token()})()

    monkeypatch.setattr("jules.providers.openai_oauth.get_valid_token", fake_get_valid_token)

    mock_events = [
        {"type": "error", "error": {"message": "invalid model type"}}
    ]
    ws_mock = _FakeWebSocket(mock_events)

    class FakeConnect:
        def __init__(self, url: str, additional_headers: dict[str, str], open_timeout: float) -> None:
            self.ws = ws_mock

        async def __aenter__(self) -> _FakeWebSocket:
            return self.ws

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            pass

    monkeypatch.setattr("websockets.connect", FakeConnect)

    with pytest.raises(ProviderError, match="invalid model type"):
        await provider.ask("hi", _context(), "gpt-5.4-mini")
