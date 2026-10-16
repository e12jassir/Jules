import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from jules.cli.protocol import _handle_line, handle_line
from jules.core.chat_engine import ChatEngineState
from jules.providers.base import ContentEvent, ThoughtEvent


@pytest.mark.asyncio
async def test_handle_line_passes_session_id_and_does_not_call_persistent_save():
    """handle_line passes session_id to stream_turn and avoids duplicate save_chat_history."""
    state = ChatEngineState(active_provider="test-prov", active_model="test-mod")
    session_id = "test-session-uuid-123"
    persistent_mock = MagicMock()
    persistent_mock.save_chat_history = AsyncMock()

    captured_kwargs: dict = {}

    async def fake_stream_turn(state_arg, message_arg, session_id=None):
        captured_kwargs["state"] = state_arg
        captured_kwargs["message"] = message_arg
        captured_kwargs["session_id"] = session_id
        yield ThoughtEvent(content="Thinking deeply...")
        yield ContentEvent(content="Hello ")
        yield ContentEvent(content="world!")

    written_lines: list[dict] = []

    def mock_write(obj):
        written_lines.append(obj)

    user_msg_line = json.dumps({"type": "user_message", "content": "Hello Jules"})

    with patch("jules.cli.protocol.stream_turn", fake_stream_turn), \
         patch("jules.cli.protocol._write", mock_write):
        await handle_line(
            line=user_msg_line,
            state=state,
            session_id=session_id,
            persistent=persistent_mock,
        )

    # 1. Verify stream_turn was called with the exact session_id
    assert captured_kwargs.get("session_id") == session_id
    assert captured_kwargs.get("message") == "Hello Jules"

    # 2. Verify persistent.save_chat_history was NOT called (deduplication requirement!)
    persistent_mock.save_chat_history.assert_not_called()

    # 3. Verify protocol wire messages
    types = [line.get("type") for line in written_lines]
    assert types == ["thinking", "content_chunk", "content_chunk", "status", "done"]
    assert written_lines[0] == {"type": "thinking", "content": "Thinking deeply..."}
    assert written_lines[1] == {"type": "content_chunk", "content": "Hello "}
    assert written_lines[2] == {"type": "content_chunk", "content": "world!"}
    assert written_lines[3] == {"type": "status", "provider": "test-prov", "model": "test-mod"}
    assert written_lines[4] == {"type": "done"}


@pytest.mark.asyncio
async def test_handle_line_supports_reversed_argument_order():
    """handle_line gracefully accepts (state, line, ...) calling convention."""
    state = ChatEngineState(active_provider="p", active_model="m")
    session_id = "sid-456"

    async def fake_stream_turn(state_arg, message_arg, session_id=None):
        yield ContentEvent(content="ok")

    written_lines: list[dict] = []

    user_msg_line = json.dumps({"type": "user_message", "content": "test"})

    with patch("jules.cli.protocol.stream_turn", fake_stream_turn), \
         patch("jules.cli.protocol._write", written_lines.append):
        # Call with state as first argument, line as second
        await handle_line(
            state,  # type: ignore[arg-type]
            user_msg_line,  # type: ignore[arg-type]
            session_id,
        )

    types = [line.get("type") for line in written_lines]
    assert "content_chunk" in types
    assert "done" in types


@pytest.mark.asyncio
async def test_handle_line_handles_invalid_json():
    """handle_line emits an error message when passed invalid json."""
    state = ChatEngineState()
    written_lines: list[dict] = []

    with patch("jules.cli.protocol._write", written_lines.append):
        await handle_line("this is not json", state, "sid-789")

    assert len(written_lines) == 1
    assert written_lines[0].get("type") == "error"
    assert "invalid json" in written_lines[0].get("message", "")


@pytest.mark.asyncio
async def test_handle_line_unknown_message_type():
    """handle_line emits an error message for unknown message types."""
    state = ChatEngineState()
    written_lines: list[dict] = []

    with patch("jules.cli.protocol._write", written_lines.append):
        await handle_line(json.dumps({"type": "bogus"}), state, "sid-789")

    assert len(written_lines) == 1
    assert written_lines[0].get("type") == "error"
    assert "unknown message type" in written_lines[0].get("message", "")
