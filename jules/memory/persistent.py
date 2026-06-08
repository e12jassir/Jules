from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from jules.memory.models import Episode, EpisodeORM

DEFAULT_SQLITE_PATH = Path.home() / ".jules" / "memory.sqlite3"


def build_sqlite_async_url(database_path: str | Path = DEFAULT_SQLITE_PATH) -> str:
    """Build the async SQLite URL used by runtime persistence."""
    path = Path(database_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
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

    async def save_async(self, episode: Episode) -> None:
        async with self.session() as session:
            result = await session.execute(select(EpisodeORM).where(EpisodeORM.id == episode.id))
            existing_orm = result.scalar_one_or_none()
            
            orm_episode = EpisodeORM.from_dataclass(episode)
            if existing_orm and getattr(existing_orm, "session_context", None) and getattr(orm_episode, "session_context", None):
                orm_episode.session_context.id = existing_orm.session_context.id
                
            await session.merge(orm_episode)
            await session.commit()

    async def save_chat_history(self, session_id: str, message: str, response: str) -> None:
        from datetime import datetime, timezone
        from jules.models.chat_history import ChatHistoryEntry, ChatHistoryORM
        async with self.session() as session:
            async with session.begin():
                session.add(ChatHistoryORM.from_entry(ChatHistoryEntry(
                    id=None, session_id=session_id,
                    role="user", content=message,
                    created_at=datetime.now(timezone.utc)
                )))
                session.add(ChatHistoryORM.from_entry(ChatHistoryEntry(
                    id=None, session_id=session_id,
                    role="assistant", content=response,
                    created_at=datetime.now(timezone.utc)
                )))

    async def get_async(self, episode_id: str) -> Episode | None:
        async with self.session() as session:
            result = await session.execute(select(EpisodeORM).where(EpisodeORM.id == episode_id))
            orm_episode = result.scalar_one_or_none()
            return orm_episode.to_dataclass() if orm_episode else None

    async def get_many_async(self, ids: list[str]) -> list[Episode]:
        if not ids:
            return []

        async with self.session() as session:
            result = await session.execute(select(EpisodeORM).where(EpisodeORM.id.in_(ids)))
            episodes_by_id = {episode.id: episode.to_dataclass() for episode in result.scalars()}
            return [episodes_by_id[episode_id] for episode_id in ids if episode_id in episodes_by_id]
