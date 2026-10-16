import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from jules.core.chat_engine import ChatEngine, classify_task_type, compose_prompt
from jules.core.router import TaskType
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


@pytest.mark.asyncio
async def test_voice_session_appends_conversational_directive():
    """ChatEngine appends voice conversational directive when session_id is voice_session or starts with voice."""
    provider = MagicMock()
    provider.name = "ollama"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "llama3.2:1b"))

    captured_prompts: dict[str, str] = {}

    async def fake_stream(prompt, context, task, user_override=None):
        yield ContentEvent(content="Hola Esteban."), "llama3.2:1b", "ollama"

    router.stream_with_fallback = fake_stream

    memory_engine = MagicMock()
    memory_engine.start_active_query = MagicMock()
    memory_engine.end_active_query = MagicMock()
    memory_engine.retrieve_async = AsyncMock(return_value=[])
    memory_engine.persist_async = AsyncMock()

    personality_loader = MagicMock()
    personality_loader.load.return_value = "Soy Jules, tu asistente."

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=True, reason=None)

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    # 1. Test voice_session
    async def capture_stream(prompt, context, task, user_override=None):
        captured_prompts["voice_session"] = prompt
        yield ContentEvent(content="Respuesta corta."), "llama3.2:1b", "ollama"

    router.stream_with_fallback = capture_stream
    session_ctx = CoreSessionContext(cwd="/workspace")

    events = [
        e
        async for e in engine.stream_turn(
            user_input="Hola Jules",
            session_id="voice_session",
            session_ctx=session_ctx,
            chat_history=[],
        )
    ]
    assert len(events) == 1
    prompt_voice = captured_prompts["voice_session"]
    assert "[MODO CONVERSACIÓN POR VOZ EN TIEMPO REAL]" in prompt_voice
    assert "Estás conversando verbalmente por voz con Esteban." in prompt_voice
    assert "máximo 1 a 2 oraciones naturales" in prompt_voice

    # 2. Test session_id.startswith("voice")
    async def capture_stream_prefix(prompt, context, task, user_override=None):
        captured_prompts["voice_prefix"] = prompt
        yield ContentEvent(content="Respuesta."), "llama3.2:1b", "ollama"

    router.stream_with_fallback = capture_stream_prefix

    events = [
        e
        async for e in engine.stream_turn(
            user_input="Cómo va todo",
            session_id="voice_chat_42",
            session_ctx=session_ctx,
            chat_history=[],
        )
    ]
    prompt_prefix = captured_prompts["voice_prefix"]
    assert "[MODO CONVERSACIÓN POR VOZ EN TIEMPO REAL]" in prompt_prefix

    # 3. Test non-voice session
    async def capture_stream_normal(prompt, context, task, user_override=None):
        captured_prompts["normal"] = prompt
        yield ContentEvent(content="Respuesta normal."), "llama3.2:1b", "ollama"

    router.stream_with_fallback = capture_stream_normal

    events = [
        e
        async for e in engine.stream_turn(
            user_input="Hola texto",
            session_id="cli_terminal_session",
            session_ctx=session_ctx,
            chat_history=[],
        )
    ]
    prompt_normal = captured_prompts["normal"]
    assert "[MODO CONVERSACIÓN POR VOZ EN TIEMPO REAL]" not in prompt_normal


@pytest.mark.asyncio
async def test_stream_turn_action_parsing_and_execution() -> None:
    """Action tags [ACTION: ...] are parsed, executed in real-time and stripped from ContentEvents."""
    provider = MagicMock()
    provider.name = "ollama"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "llama3.2:1b"))

    async def fake_stream_with_actions(prompt, context, task, user_override=None):
        yield ContentEvent(content="[ACTION: set_volume(30)] Bajando el volumen."), "llama3.2:1b", "ollama"
        # Split action across chunks
        yield ContentEvent(content=" Cambiando canción [ACT"), "llama3.2:1b", "ollama"
        yield ContentEvent(content="ION: media_control(\"next\")] y pausando [ACT"), "llama3.2:1b", "ollama"
        yield ContentEvent(content="ION: media_control(\"pause\")] Listo."), "llama3.2:1b", "ollama"

    router.stream_with_fallback = fake_stream_with_actions

    memory_engine = MagicMock()
    memory_engine.start_active_query = MagicMock()
    memory_engine.end_active_query = MagicMock()
    memory_engine.retrieve_async = AsyncMock(return_value=[])
    memory_engine.persist_async = AsyncMock()

    personality_loader = MagicMock()
    personality_loader.load.return_value = "Soy Jules."

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=True, reason=None)

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    with patch("jules.platform.os_tools.set_volume", new_callable=AsyncMock) as mock_set_vol, \
         patch("jules.platform.os_tools.media_control", new_callable=AsyncMock) as mock_media_ctrl:

        mock_set_vol.return_value = "Volumen ok"
        mock_media_ctrl.return_value = "Media ok"

        session_ctx = CoreSessionContext(cwd="/workspace")
        chat_history: list[tuple[str, str]] = []

        events = [
            e
            async for e in engine.stream_turn(
                user_input="Baja el volumen y cambia la música",
                session_id="voice_session",
                session_ctx=session_ctx,
                chat_history=chat_history,
            )
        ]

        # Verify action executions
        mock_set_vol.assert_awaited_once_with("30", gate=None)
        assert mock_media_ctrl.await_count == 2
        mock_media_ctrl.assert_any_await("next", gate=None)
        mock_media_ctrl.assert_any_await("pause", gate=None)

        # Verify no [ACTION: ...] leaked to ContentEvents
        content_text = "".join(e.content for e in events if isinstance(e, ContentEvent))
        assert "[ACTION:" not in content_text
        assert "Bajando el volumen." in content_text
        assert "Cambiando canción " in content_text
        assert " y pausando " in content_text
        assert " Listo." in content_text


@pytest.mark.asyncio
async def test_voice_turn_chat_history_preservation_and_system_snapshot() -> None:
    """Voice turn preserves chat_history and includes dynamic system snapshot with action instructions."""
    provider = MagicMock()
    provider.name = "ollama"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "llama3.2:1b"))

    captured_prompt = None

    async def fake_stream(prompt, context, task, user_override=None):
        nonlocal captured_prompt
        captured_prompt = prompt
        yield ContentEvent(content="[ACTION: open_app(\"firefox\")] Abriendo el navegador."), "llama3.2:1b", "ollama"

    router.stream_with_fallback = fake_stream

    memory_engine = MagicMock()
    memory_engine.start_active_query = MagicMock()
    memory_engine.end_active_query = MagicMock()
    memory_engine.retrieve_async = AsyncMock(return_value=[])
    memory_engine.persist_async = AsyncMock()

    personality_loader = MagicMock()
    personality_loader.load.return_value = "Soy Jules."

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=True, reason=None)

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    mock_status = {
        "ram": {"summary": "8.0GB / 16.0GB (50%)"},
        "volume": "60%",
        "media_track": "Queen - Bohemian Rhapsody",
        "active_window": {"title": "Kitty Terminal", "class": "kitty"},
    }

    with patch("jules.platform.os_tools.get_system_status", new_callable=AsyncMock, return_value=mock_status), \
         patch("jules.platform.os_tools.open_app", new_callable=AsyncMock, return_value="App ok") as mock_open:

        session_ctx = CoreSessionContext(cwd="/workspace")
        chat_history: list[tuple[str, str]] = [("user", "Hola Jules"), ("jules", "Hola Esteban!")]

        events = [
            e
            async for e in engine.stream_turn(
                user_input="Abre firefox por favor",
                session_id="voice_session",
                session_ctx=session_ctx,
                chat_history=chat_history,
            )
        ]

        # Check prompt snapshot & action instructions
        assert captured_prompt is not None
        assert "[ESTADO ACTUAL DEL SISTEMA]" in captured_prompt
        assert "8.0GB / 16.0GB (50%)" in captured_prompt
        assert "60%" in captured_prompt
        assert "Queen - Bohemian Rhapsody" in captured_prompt
        assert "Kitty Terminal (kitty)" in captured_prompt
        assert "Tienes brazos y control del sistema" in captured_prompt
        assert '[ACTION: set_volume(30)]' in captured_prompt
        assert '[ACTION: open_app("firefox")]' in captured_prompt

        # Check chat history from prior turn was included in prompt
        assert "User: Hola Jules" in captured_prompt
        assert "Jules: Hola Esteban!" in captured_prompt

        # Check new turn was accumulated in chat_history
        assert len(chat_history) == 4
        assert chat_history[-2] == ("user", "Abre firefox por favor")
        assert chat_history[-1] == ("jules", "Abriendo el navegador.")
        assert "[ACTION:" not in chat_history[-1][1]

        # Check action was executed
        mock_open.assert_awaited_once_with("firefox", gate=None)


@pytest.mark.asyncio
async def test_stream_turn_compatibility_wrapper_respects_passed_session_id() -> None:
    """stream_turn compatibility wrapper respects the passed session_id."""
    from jules.core.chat_engine import ChatEngineState, stream_turn
    import jules.core.chat_engine as ce_module

    state = ChatEngineState()
    custom_session = "custom-session-12345"

    captured_kwargs: dict = {}

    mock_engine = MagicMock()

    async def fake_stream_turn(**kwargs):
        captured_kwargs.update(kwargs)
        yield ContentEvent(content="Hello from mock!")

    mock_engine.stream_turn = fake_stream_turn
    mock_engine.last_provider = "test-provider"
    mock_engine.last_model = "test-model"

    with patch.object(ce_module, "_default_engine_instance", mock_engine):
        events = [
            e
            async for e in stream_turn(
                state=state,
                message="test input",
                session_id=custom_session,
            )
        ]

    assert len(events) == 1
    assert events[0].content == "Hello from mock!"
    assert captured_kwargs.get("session_id") == custom_session
    assert captured_kwargs.get("user_input") == "test input"
    assert state.active_provider == "test-provider"
    assert state.active_model == "test-model"


@pytest.mark.asyncio
async def test_stream_turn_compatibility_wrapper_generates_uuid_when_session_id_none() -> None:
    """stream_turn compatibility wrapper generates uuid when session_id is None."""
    import uuid
    from jules.core.chat_engine import ChatEngineState, stream_turn
    import jules.core.chat_engine as ce_module

    state = ChatEngineState()
    captured_kwargs: dict = {}

    mock_engine = MagicMock()

    async def fake_stream_turn(**kwargs):
        captured_kwargs.update(kwargs)
        yield ContentEvent(content="Hello fallback!")

    mock_engine.stream_turn = fake_stream_turn
    mock_engine.last_provider = None
    mock_engine.last_model = None

    with patch.object(ce_module, "_default_engine_instance", mock_engine):
        events = [
            e
            async for e in stream_turn(
                state=state,
                message="test input",
            )
        ]

    assert len(events) == 1
    sid = captured_kwargs.get("session_id")
    assert sid is not None
    # Validate it is a valid UUID
    uuid_obj = uuid.UUID(sid)
    assert str(uuid_obj) == sid


def test_classify_task_type_comprehensive() -> None:
    # VISION
    assert classify_task_type("¿Qué hay en mi pantalla?") == TaskType.VISION
    assert classify_task_type("Toma un screenshot de esta ventana") == TaskType.VISION
    assert classify_task_type("Haz una captura de pantalla") == TaskType.VISION
    assert classify_task_type("Analiza esta imagen adjunta") == TaskType.VISION

    # CODING_HEAVY
    assert classify_task_type("Necesito un refactor del módulo auth") == TaskType.CODING_HEAVY
    assert classify_task_type("Reescribe este módulo usando asyncio") == TaskType.CODING_HEAVY
    assert classify_task_type("Implementa la arquitectura limpia") == TaskType.CODING_HEAVY
    assert classify_task_type("Vamos a hacer una migración completa de base de datos") == TaskType.CODING_HEAVY

    # CODING
    assert classify_task_type("Revisa este código por favor") == TaskType.CODING
    assert classify_task_type("Escribe una función auxiliar") == TaskType.CODING
    assert classify_task_type("Crea una clase abstracta") == TaskType.CODING
    assert classify_task_type("def calculate_total():") == TaskType.CODING
    assert classify_task_type("class OrderProcessor:") == TaskType.CODING
    assert classify_task_type("Tengo un bug en producción") == TaskType.CODING
    assert classify_task_type("Mira este traceback") == TaskType.CODING
    assert classify_task_type("error: connection refused") == TaskType.CODING
    assert classify_task_type("Lanza una exception no controlada") == TaskType.CODING
    assert classify_task_type("Corre el test unitario") == TaskType.CODING
    assert classify_task_type("Aplica este fix rápido") == TaskType.CODING
    assert classify_task_type("Genera un script en bash") == TaskType.CODING
    assert classify_task_type("Escribe una regex para correos") == TaskType.CODING
    assert classify_task_type("ayuda con esto", intent="debugging") == TaskType.CODING

    # ANALYSIS
    assert classify_task_type("Analiza el rendimiento del sistema") == TaskType.ANALYSIS
    assert classify_task_type("Compara Postgres con SQLite") == TaskType.ANALYSIS
    assert classify_task_type("Discutamos la arquitectura general") == TaskType.ANALYSIS
    assert classify_task_type("Cuál es el tradeoff entre latencia y throughput") == TaskType.ANALYSIS

    # REASONING
    assert classify_task_type("Por qué el kernel usa páginas virtuales") == TaskType.REASONING
    assert classify_task_type("Explica cómo funciona epoll") == TaskType.REASONING
    assert classify_task_type("Cuál es el razonamiento detrás de esta decisión") == TaskType.REASONING
    assert classify_task_type("Cómo funciona el garbage collector") == TaskType.REASONING

    # QUICK (default)
    assert classify_task_type("Hola Jules, ¿cómo estás?") == TaskType.QUICK
    assert classify_task_type("Gracias por la ayuda") == TaskType.QUICK


@pytest.mark.asyncio
async def test_stream_turn_uses_dynamic_task_classification() -> None:
    provider = MagicMock()
    provider.name = "opencode"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "opencode/deepseek-v4-flash-free"))

    routed_tasks: list[TaskType] = []

    async def fake_stream_with_fallback(prompt, context, task, user_override=None):
        routed_tasks.append(task)
        yield ContentEvent(content="Captura procesada"), "model", "provider"

    router.stream_with_fallback = fake_stream_with_fallback

    memory_engine = MagicMock()
    memory_engine.retrieve_async = AsyncMock(return_value=[])
    personality_loader = MagicMock()
    personality_loader.load.return_value = "Jules prompt"

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=True, reason=None)

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
    )

    session_ctx = CoreSessionContext(cwd="/workspace")
    events = [
        e
        async for e in engine.stream_turn(
            user_input="¿Puedes ver mi pantalla?",
            session_id="test_vision_classification",
            session_ctx=session_ctx,
            chat_history=[],
        )
    ]

    assert len(events) == 1
    # Verify router.route received TaskType.VISION
    router.route.assert_awaited_once_with(TaskType.VISION, user_override=None)
    # Verify stream_with_fallback received TaskType.VISION
    assert routed_tasks == [TaskType.VISION]


@pytest.mark.asyncio
async def test_stream_turn_executes_perception_action_tags() -> None:
    provider = MagicMock()
    provider.name = "opencode"

    router = MagicMock()
    router.route = AsyncMock(return_value=(provider, "opencode/deepseek-v4-flash-free"))

    async def fake_stream_with_fallback(prompt, context, task, user_override=None):
        yield ContentEvent(content="Revisando pantalla [ACTION: capture_screen()] y portapapeles [ACTION: read_clipboard()]."), "model", "opencode"

    router.stream_with_fallback = fake_stream_with_fallback

    memory_engine = MagicMock()
    memory_engine.retrieve_async = AsyncMock(return_value=[])
    personality_loader = MagicMock()
    personality_loader.load.return_value = "Jules prompt"

    mock_sanitizer = MagicMock()
    mock_sanitizer.check.return_value = SanitizeResult(is_safe=True, reason=None)

    mock_gate = MagicMock()

    engine = ChatEngine(
        router=router,
        memory_engine=memory_engine,
        personality_loader=personality_loader,
        sanitizer=mock_sanitizer,
        permission_gate=mock_gate,
    )

    with patch("jules.platform.os_tools.capture_screen_tool", new_callable=AsyncMock) as mock_cap, \
         patch("jules.platform.os_tools.read_clipboard_tool", new_callable=AsyncMock) as mock_clip:

        mock_cap.return_value = "Captura ok"
        mock_clip.return_value = "Clip ok"

        session_ctx = CoreSessionContext(cwd="/workspace")
        chat_history: list[tuple[str, str]] = []

        events = [
            e
            async for e in engine.stream_turn(
                user_input="Mira la pantalla y el portapapeles",
                session_id="test_actions",
                session_ctx=session_ctx,
                chat_history=chat_history,
            )
        ]

        # Verify action tags were executed with gate
        mock_cap.assert_awaited_once_with(gate=mock_gate)
        mock_clip.assert_awaited_once_with(gate=mock_gate)

        # Verify stripped from output
        full_text = "".join(e.content for e in events if isinstance(e, ContentEvent))
        assert "[ACTION:" not in full_text
        assert "Revisando pantalla" in full_text
        assert "portapapeles" in full_text


