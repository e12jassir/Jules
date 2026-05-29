from datetime import datetime, timezone
import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from jules.memory.models import Base, Episode, SessionContext
from jules.memory.persistent import PersistentMemory, build_sqlite_async_url, create_memory_sessionmaker


@pytest_asyncio.fixture
async def temp_db():
    persistence = PersistentMemory("sqlite+aiosqlite:///:memory:")
    async with persistence.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield persistence
    finally:
        await persistence.engine.dispose()


def test_build_sqlite_async_url_uses_aiosqlite_driver(tmp_path):
    database_path = tmp_path / "memory.sqlite3"

    assert build_sqlite_async_url(database_path) == f"sqlite+aiosqlite:///{database_path}"


def test_persistent_memory_initializes_async_engine_and_sessionmaker():
    persistence = PersistentMemory("sqlite+aiosqlite:///:memory:")

    assert isinstance(persistence.engine, AsyncEngine)
    assert persistence.engine.url.drivername == "sqlite+aiosqlite"

    session_factory = create_memory_sessionmaker(persistence.engine)
    session = session_factory()
    try:
        assert isinstance(session, AsyncSession)
    finally:
        assert session.sync_session is not None


async def test_save_and_get_episode_async(temp_db):
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

    await temp_db.save_async(episode)

    fetched = await temp_db.get_async(episode.id)

    assert fetched is not None
    assert fetched == episode


async def test_get_episode_async_returns_none_for_missing_id(temp_db):
    assert await temp_db.get_async("missing-episode-id") is None
