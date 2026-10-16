import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from jules.core.chat_engine import ChatEngine, compose_prompt
from jules.core.session import SessionContext as CoreSessionContext
from jules.memory.models import Episode, SessionContext as MemorySessionContext
from jules.personality.loader import MasterPersonalityMissingError
from jules.providers.base import ContentEvent, ThoughtEvent
from jules.sanitizer.sanitizer import SanitizeResult


@pytest.mark.asyncio
async def test_sanitizer_blocks_dangerous_input_without_calling_router_or_memory():
    """Sanitizer blocks dangerous input with ContentEvent and aborts before memory/router."""
    router = MagicMock()
    router.route = AsyncMock()
    router.stream_with_fallback = MagicMock()

    memory_engine = MagicMock()
    memory_engine.start_active_query = MagicMock()
    memory_engine.end_active_query = MagicMock()
    memory_engine.retrieve_async = AsyncMock()
    memory_engine.persist_async = AsyncMock()

    personality_loader = MagicMock()
    personality_loader.load = MagicMock()

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=False, reason="export_secret")

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    dangerous_input = "export AWS_SECRET_ACCESS_KEY=supersecret"
    session_ctx = CoreSessionContext(cwd="/workspace")
    chat_history: list[tuple[str, str]] = []

    events = [
        event
        async for event in engine.stream_turn(
            user_input=dangerous_input,
            session_id="test-session-123",
            session_ctx=session_ctx,
            chat_history=chat_history,
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0], ContentEvent)
    assert "bloqueado por sanitizador" in events[0].content
    assert "export_secret" in events[0].content

    mock_sanitizer.check.assert_called_once_with(dangerous_input)
    memory_engine.start_active_query.assert_not_called()
    memory_engine.end_active_query.assert_not_called()
    memory_engine.retrieve_async.assert_not_called()
    memory_engine.persist_async.assert_not_called()
    router.route.assert_not_called()
    router.stream_with_fallback.assert_not_called()
    personality_loader.load.assert_not_called()
    assert len(chat_history) == 0


@pytest.mark.asyncio
async def test_successful_streaming_turn_with_prompt_assembly_and_background_persistence():
    """Successful streaming turn with prompt assembly and background persistence task dispatched."""
    provider = MagicMock()
    provider.name = "ollama"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "llama3.2:1b"))

    captured_prompt = None

    async def fake_stream_with_fallback(prompt, context, task, user_override=None):
        nonlocal captured_prompt
        captured_prompt = prompt
        yield ThoughtEvent(content="Let me think..."), "llama3.2:1b", "ollama"
        yield ContentEvent(content="Hello "), "llama3.2:1b", "ollama"
        yield ContentEvent(content="world!"), "llama3.2:1b", "ollama"

    router.stream_with_fallback = fake_stream_with_fallback

    retrieved_ep = Episode(
        id="ep-001",
        timestamp=datetime.now(timezone.utc),
        context=MemorySessionContext(
            project="Jules",
            directory="/workspace",
            active_files=[],
            inferred_intent="chat",
            time_of_day="12",
        ),
        problem="how do I test in python",
        process="ran pytest",
        solution="use pytest tests/",
        duration_seconds=5,
        friction_score=0.1,
    )

    persistent_memory = MagicMock()
    persistent_memory.save_chat_history = AsyncMock()

    memory_engine = MagicMock()
    memory_engine.persistent = persistent_memory
    memory_engine.start_active_query = MagicMock()
    memory_engine.end_active_query = MagicMock()
    memory_engine.retrieve_async = AsyncMock(return_value=[retrieved_ep])
    memory_engine.persist_async = AsyncMock()

    personality_loader = MagicMock()
    personality_loader.load.return_value = "You are Jules, a helpful OS assistant."

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=True, reason=None)

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    session_ctx = CoreSessionContext(cwd="/workspace")
    chat_history: list[tuple[str, str]] = [("user", "hi"), ("jules", "hello")]

    events = [
        event
        async for event in engine.stream_turn(
            user_input="How do I run tests?",
            session_id="test-session-456",
            session_ctx=session_ctx,
            chat_history=chat_history,
        )
    ]

    assert len(events) == 3
    assert isinstance(events[0], ThoughtEvent)
    assert events[0].content == "Let me think..."
    assert isinstance(events[1], ContentEvent)
    assert events[1].content == "Hello "
    assert isinstance(events[2], ContentEvent)
    assert events[2].content == "world!"

    assert engine.last_provider == "ollama"
    assert engine.last_model == "llama3.2:1b"

    # Prompt assembly checks
    assert captured_prompt is not None
    assert "You are Jules, a helpful OS assistant." in captured_prompt
    assert "how do I test in python" in captured_prompt
    assert "Conversation so far:" in captured_prompt
    assert "User: How do I run tests?" in captured_prompt

    memory_engine.start_active_query.assert_called_once()
    memory_engine.end_active_query.assert_called_once()

    assert len(chat_history) == 4
    assert chat_history[-2] == ("user", "How do I run tests?")
    assert chat_history[-1] == ("jules", "Hello world!")

    # Wait briefly for background persistence task to execute
    await asyncio.sleep(0.05)

    memory_engine.persist_async.assert_called_once()
    persisted_ep = memory_engine.persist_async.call_args[0][0]
    assert isinstance(persisted_ep, Episode)
    assert persisted_ep.problem == "How do I run tests?"
    assert persisted_ep.solution == "Hello world!"
    assert persisted_ep.provider_used == "ollama"
    assert persisted_ep.model_used == "llama3.2:1b"

    persistent_memory.save_chat_history.assert_called_once_with(
        "test-session-456",
        "How do I run tests?",
        "Hello world!",
    )


@pytest.mark.asyncio
async def test_graceful_degradation_when_memory_retrieval_times_out():
    """Graceful degradation when memory retrieval times out (>150ms)."""
    provider = MagicMock()
    provider.name = "ollama"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "llama3.2:1b"))

    captured_prompt = None

    async def fake_stream_with_fallback(prompt, context, task, user_override=None):
        nonlocal captured_prompt
        captured_prompt = prompt
        yield ContentEvent(content="I am still answering promptly!"), "llama3.2:1b", "ollama"

    router.stream_with_fallback = fake_stream_with_fallback

    async def slow_retrieve(query, limit=3):
        await asyncio.sleep(0.5)
        return []

    memory_engine = MagicMock()
    memory_engine.start_active_query = MagicMock()
    memory_engine.end_active_query = MagicMock()
    memory_engine.retrieve_async = slow_retrieve
    memory_engine.persist_async = AsyncMock()

    personality_loader = MagicMock()
    personality_loader.load.return_value = "Master prompt."

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=True, reason=None)

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    session_ctx = CoreSessionContext(cwd="/workspace")
    chat_history: list[tuple[str, str]] = []

    start_time = asyncio.get_event_loop().time()
    events = [
        event
        async for event in engine.stream_turn(
            user_input="Quick question",
            session_id="test-session-789",
            session_ctx=session_ctx,
            chat_history=chat_history,
        )
    ]
    elapsed = asyncio.get_event_loop().time() - start_time

    assert elapsed < 0.35, f"Elapsed time was {elapsed}s, expected < 0.35s"
    assert len(events) == 1
    assert events[0].content == "I am still answering promptly!"

    assert captured_prompt is not None
    assert "Relevant past context:" not in captured_prompt

    memory_engine.end_active_query.assert_called_once()


@pytest.mark.asyncio
async def test_master_personality_missing_yields_warning_event():
    """Missing master.md yields descriptive ContentEvent and halts."""
    provider = MagicMock()
    provider.name = "ollama"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "llama3.2:1b"))
    router.stream_with_fallback = MagicMock()

    memory_engine = MagicMock()
    memory_engine.start_active_query = MagicMock()
    memory_engine.end_active_query = MagicMock()
    memory_engine.retrieve_async = AsyncMock(return_value=[])

    personality_loader = MagicMock()
    personality_loader.load.side_effect = MasterPersonalityMissingError("Missing master.md")

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=True, reason=None)

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    events = [
        event
        async for event in engine.stream_turn(
            user_input="Hello",
            session_id="test-session",
            session_ctx=CoreSessionContext(cwd="/workspace"),
            chat_history=[],
        )
    ]

    assert len(events) == 1
    assert isinstance(events[0], ContentEvent)
    assert "master.md" in events[0].content
    router.stream_with_fallback.assert_not_called()
    memory_engine.end_active_query.assert_called_once()


@pytest.mark.asyncio
async def test_response_sanitizer_blocks_leaked_secret_from_persistence():
    """Leaked secret in response is blocked from memory persistence."""
    provider = MagicMock()
    provider.name = "ollama"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "llama3.2:1b"))

    async def fake_stream_with_fallback(prompt, context, task, user_override=None):
        yield ContentEvent(content="Here is a key: sk-abcdef1234567890123456"), "llama3.2:1b", "ollama"

    router.stream_with_fallback = fake_stream_with_fallback

    persistent_memory = MagicMock()
    persistent_memory.save_chat_history = AsyncMock()

    memory_engine = MagicMock()
    memory_engine.persistent = persistent_memory
    memory_engine.start_active_query = MagicMock()
    memory_engine.end_active_query = MagicMock()
    memory_engine.retrieve_async = AsyncMock(return_value=[])
    memory_engine.persist_async = AsyncMock()

    personality_loader = MagicMock()
    personality_loader.load.return_value = "System prompt"

    # User input is safe, but response contains a secret
    def check_fn(text: str) -> SanitizeResult:
        if "sk-" in text:
            return SanitizeResult(is_safe=False, reason="openai_key")
        return SanitizeResult(is_safe=True, reason=None)

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.side_effect = check_fn

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    events = [
        event
        async for event in engine.stream_turn(
            user_input="Tell me secret",
            session_id="test-session",
            session_ctx=CoreSessionContext(cwd="/workspace"),
            chat_history=[],
        )
    ]

    assert len(events) == 1
    assert "sk-" in events[0].content

    await asyncio.sleep(0.05)

    # Persistence must NOT be called for unsafe response
    memory_engine.persist_async.assert_not_called()
    persistent_memory.save_chat_history.assert_not_called()


def test_compose_prompt_formatting():
    """Verify compose_prompt structure with personality, memory, history and facts."""
    prompt = compose_prompt(
        personality="You are an assistant.",
        message="What is the time?",
        memory_refs=["past question about time"],
        chat_history=[("user", "hi"), ("assistant", "hello")],
        facts=["Project is Jules", "OS is Linux"],
    )

    assert "You are an assistant." in prompt
    assert "Project facts:\n- Project is Jules\n- OS is Linux" in prompt
    assert "Relevant past context:\n- past question about time" in prompt
    assert "Conversation so far:\nUser: hi\nAssistant: hello" in prompt
    assert "User: What is the time?" in prompt
