from datetime import datetime, timezone
import uuid

from jules.memory.models import Base, Episode, SessionContext
from jules.memory.persistent import PersistentMemory, build_sqlite_async_url, create_memory_sessionmaker


async def create_temp_db() -> PersistentMemory:
    persistence = PersistentMemory("sqlite+aiosqlite:///:memory:")
    async with persistence.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return persistence


def test_build_sqlite_async_url_uses_aiosqlite_driver(tmp_path):
    database_path = tmp_path / "nested" / "memory.sqlite3"

    assert build_sqlite_async_url(database_path) == f"sqlite+aiosqlite:///{database_path}"
    assert database_path.parent.exists()


async def test_persistent_memory_initializes_async_engine_and_sessionmaker():
    persistence = PersistentMemory("sqlite+aiosqlite:///:memory:")

    assert persistence.engine.url.drivername == "sqlite+aiosqlite"

    session_factory = create_memory_sessionmaker(persistence.engine)
    session = session_factory()
    try:
        assert session.sync_session is not None
    finally:
        await session.close()
        await persistence.engine.dispose()


async def test_save_and_get_episode_async():
    temp_db = await create_temp_db()
    episode = Episode(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        context=SessionContext(
            project="Jules",
            directory="/home/e12jassir/proyects/Jules",
            active_files=["jules/memory/persistent.py", "tests/unit/test_persistent.py"],
            inferred_intent="implementation",
            time_of_day="night",
        ),
        problem="Persist memory episodes asynchronously",
        process="Use AsyncSession with merge and commit",
        solution="Hydrate the Episode dataclass through async select",
        duration_seconds=180,
        friction_score=0.2,
        tags=["memory", "persistence"],
        importance=0.7,
        model_used="llama3.2:1b",
        provider_used="ollama",
    )

    try:
        await temp_db.save_async(episode)

        fetched = await temp_db.get_async(episode.id)

        assert fetched is not None
        assert fetched == episode
    finally:
        await temp_db.engine.dispose()


async def test_get_episode_async_returns_none_for_missing_id():
    temp_db = await create_temp_db()
    try:
        assert await temp_db.get_async("missing-episode-id") is None
    finally:
        await temp_db.engine.dispose()


async def test_get_many_async_returns_existing_episodes_in_requested_order():
    temp_db = await create_temp_db()
    first = Episode(
        id="episode-first",
        timestamp=datetime.now(timezone.utc),
        context=SessionContext(
            project="Jules",
            directory="/home/e12jassir/proyects/Jules",
            active_files=["jules/memory/persistent.py"],
            inferred_intent="implementation",
            time_of_day="night",
        ),
        problem="Persist first episode",
        process="Use a batch select",
        solution="Return dataclasses by requested IDs",
        duration_seconds=60,
        friction_score=0.1,
    )
    second = Episode(
        id="episode-second",
        timestamp=datetime.now(timezone.utc),
        context=SessionContext(
            project="Jules",
            directory="/home/e12jassir/proyects/Jules",
            active_files=["jules/memory/persistent.py"],
            inferred_intent="implementation",
            time_of_day="night",
        ),
        problem="Persist second episode",
        process="Use a batch select",
        solution="Preserve vector ranking order",
        duration_seconds=60,
        friction_score=0.1,
    )
    try:
        await temp_db.save_async(first)
        await temp_db.save_async(second)

        episodes = await temp_db.get_many_async([second.id, "missing", first.id])

        assert episodes == [second, first]
    finally:
        await temp_db.engine.dispose()
