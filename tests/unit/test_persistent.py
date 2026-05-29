from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from jules.memory.persistent import PersistentMemory, build_sqlite_async_url, create_memory_sessionmaker


def test_build_sqlite_async_url_uses_aiosqlite_driver(tmp_path):
    database_path = tmp_path / "memory.sqlite3"

    assert build_sqlite_async_url(database_path) == f"sqlite+aiosqlite:///{database_path}"


def test_persistent_memory_initializes_async_engine_and_sessionmaker():
    persistence = PersistentMemory("sqlite+aiosqlite:///:memory:")

    try:
        assert isinstance(persistence.engine, AsyncEngine)
        assert persistence.engine.url.drivername == "sqlite+aiosqlite"

        session_factory = create_memory_sessionmaker(persistence.engine)
        session = session_factory()
        try:
            assert isinstance(session, AsyncSession)
        finally:
            assert session.sync_session is not None
    finally:
        # Engine disposal is asynchronous; CRUD tests in Phase 2 will own lifecycle cleanup.
        pass
