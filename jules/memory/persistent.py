from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_SQLITE_PATH = Path.home() / ".jules" / "memory.sqlite3"


def build_sqlite_async_url(database_path: str | Path = DEFAULT_SQLITE_PATH) -> str:
    """Build the async SQLite URL used by runtime persistence."""
    path = Path(database_path).expanduser()
    return f"sqlite+aiosqlite:///{path}"


def create_memory_engine(database_url: str | None = None) -> AsyncEngine:
    """Create the non-blocking SQLAlchemy engine for memory persistence."""
    return create_async_engine(
        database_url or build_sqlite_async_url(),
        future=True,
    )


def create_memory_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the AsyncSession factory used by persistence operations."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


class PersistentMemory:
    """Async relational persistence boundary for Jules memory episodes."""

    def __init__(self, database_url: str | None = None) -> None:
        self.engine = create_memory_engine(database_url)
        self.session_factory = create_memory_sessionmaker(self.engine)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session
