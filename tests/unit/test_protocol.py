"""Unit tests for jules.server.protocol — round-trip serialization for every type."""
from __future__ import annotations

import json

import pytest

from jules.server.protocol import (
    CancelledEvent,
    CancelRequest,
    CommandRequest,
    CommandResultEvent,
    DoneEvent,
    ErrorEvent,
    InitRequest,
    MessageRequest,
    ModelChangedEvent,
    ModelListEvent,
    ModelListRequest,
    ModelSetRequest,
    QuitRequest,
    ReadyEvent,
    StatusEvent,
    StatusGetRequest,
    ThoughtEvent,
    TokenEvent,
    from_json,
    to_json,
)


class TestInboundRoundTrip:
    def test_init_request(self):
        msg = InitRequest(protocol_version=2)
        data = json.loads(to_json(msg))
        assert data == {"type": "init", "protocol_version": 2}
        parsed = from_json(data)
        assert isinstance(parsed, InitRequest)
        assert parsed.protocol_version == 2

    def test_message_request(self):
        msg = MessageRequest(content="hello world")
        data = json.loads(to_json(msg))
        assert data == {"type": "message", "content": "hello world"}
        parsed = from_json(data)
        assert isinstance(parsed, MessageRequest)
        assert parsed.content == "hello world"

    def test_command_request(self):
        msg = CommandRequest(name="doctor", args=["--verbose"])
        data = json.loads(to_json(msg))
        assert data == {"type": "command", "name": "doctor", "args": ["--verbose"]}
        parsed = from_json(data)
        assert isinstance(parsed, CommandRequest)
        assert parsed.name == "doctor"
        assert parsed.args == ["--verbose"]

    def test_model_set_request(self):
        msg = ModelSetRequest(provider="ollama", model="llama3.2:1b")
        data = json.loads(to_json(msg))
        assert data == {"type": "model_set", "provider": "ollama", "model": "llama3.2:1b"}
        parsed = from_json(data)
        assert isinstance(parsed, ModelSetRequest)
        assert parsed.provider == "ollama"
        assert parsed.model == "llama3.2:1b"

    def test_model_list_request(self):
        msg = ModelListRequest()
        data = json.loads(to_json(msg))
        assert data == {"type": "model_list"}
        parsed = from_json(data)
        assert isinstance(parsed, ModelListRequest)

    def test_status_get_request(self):
        msg = StatusGetRequest()
        data = json.loads(to_json(msg))
        assert data == {"type": "status_get"}
        parsed = from_json(data)
        assert isinstance(parsed, StatusGetRequest)

    def test_cancel_request(self):
        msg = CancelRequest()
        data = json.loads(to_json(msg))
        assert data == {"type": "cancel"}
        parsed = from_json(data)
        assert isinstance(parsed, CancelRequest)

    def test_quit_request(self):
        msg = QuitRequest()
        data = json.loads(to_json(msg))
        assert data == {"type": "quit"}
        parsed = from_json(data)
        assert isinstance(parsed, QuitRequest)


class TestOutboundSerialization:
    def test_ready_event(self):
        msg = ReadyEvent(protocol_version=1, boot_ms=42.5)
        data = json.loads(to_json(msg))
        assert data == {"type": "ready", "protocol_version": 1, "boot_ms": 42.5}

    def test_token_event(self):
        msg = TokenEvent(content="Hello")
        data = json.loads(to_json(msg))
        assert data == {"type": "token", "content": "Hello"}

    def test_thought_event(self):
        msg = ThoughtEvent(content="thinking...")
        data = json.loads(to_json(msg))
        assert data == {"type": "thought", "content": "thinking..."}

    def test_done_event(self):
        msg = DoneEvent(tokens=150)
        data = json.loads(to_json(msg))
        assert data == {"type": "done", "tokens": 150}

    def test_cancelled_event(self):
        msg = CancelledEvent()
        data = json.loads(to_json(msg))
        assert data == {"type": "cancelled"}

    def test_command_result_event(self):
        msg = CommandResultEvent(name="doctor", ok=True, data={"status": "ok"}, error=None)
        data = json.loads(to_json(msg))
        assert data == {"type": "command_result", "name": "doctor", "ok": True, "data": {"status": "ok"}, "error": None}

    def test_model_changed_event(self):
        msg = ModelChangedEvent(provider="ollama", model="llama3.2:1b")
        data = json.loads(to_json(msg))
        assert data == {"type": "model_changed", "provider": "ollama", "model": "llama3.2:1b"}

    def test_model_list_event(self):
        msg = ModelListEvent(models=[["ollama", "llama3.2:1b"], ["google", "gemini-2.5-flash"]])
        data = json.loads(to_json(msg))
        assert data == {"type": "model_list", "models": [["ollama", "llama3.2:1b"], ["google", "gemini-2.5-flash"]]}

    def test_status_event(self):
        msg = StatusEvent(online=True, episodes=42, scoring_healthy=True)
        data = json.loads(to_json(msg))
        assert data == {"type": "status", "online": True, "episodes": 42, "scoring_healthy": True}

    def test_error_event(self):
        msg = ErrorEvent(message="something broke", recoverable=False)
        data = json.loads(to_json(msg))
        assert data == {"type": "error", "message": "something broke", "recoverable": False}


class TestFromJsonEdgeCases:
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown or missing"):
            from_json({"type": "bogus"})

    def test_missing_type_raises(self):
        with pytest.raises(ValueError, match="Unknown or missing"):
            from_json({"content": "no type"})

    def test_extra_fields_ignored(self):
        parsed = from_json({"type": "quit", "extra": "ignored"})
        assert isinstance(parsed, QuitRequest)
