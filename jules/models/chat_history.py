"""Chat history persistence model and query helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select  # type: ignore[import-not-found]
from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore[import-not-found]
from sqlalchemy.orm import Mapped, mapped_column  # type: ignore[import-not-found]

from jules.memory.models import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _deserialize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(slots=True)
class ChatHistoryEntry:
    """A persisted chat message from a TUI session."""

    id: int | None
    session_id: str
    role: str
    content: str
    created_at: datetime


class ChatHistoryORM(Base):
    """SQLAlchemy row for the `chat_history` table."""

    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(index=True)
    role: Mapped[str] = mapped_column()
    content: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    @classmethod
    def from_entry(cls, entry: ChatHistoryEntry) -> "ChatHistoryORM":
        return cls(
            session_id=entry.session_id,
            role=entry.role,
            content=entry.content,
            created_at=_serialize_timestamp(entry.created_at),
        )

    def to_entry(self) -> ChatHistoryEntry:
        return ChatHistoryEntry(
            id=self.id,
            session_id=self.session_id,
            role=self.role,
            content=self.content,
            created_at=_deserialize_timestamp(self.created_at),
        )


async def list_recent_sessions(session: AsyncSession, limit: int = 20) -> list[str]:
    """Return recent chat session ids for `/sessions`."""
    latest_message = func.max(ChatHistoryORM.created_at)
    result = await session.execute(
        select(ChatHistoryORM.session_id)
        .group_by(ChatHistoryORM.session_id)
        .order_by(latest_message.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def list_recent_sessions_info(session: AsyncSession, limit: int = 20) -> list[dict]:
    """Return detailed info for recent chat sessions (ID, title, count, timestamp)."""
    subq = (
        select(
            ChatHistoryORM.session_id,
            func.max(ChatHistoryORM.created_at).label("last_activity"),
            func.count(ChatHistoryORM.id).label("msg_count"),
        )
        .group_by(ChatHistoryORM.session_id)
        .subquery()
    )
    result = await session.execute(
        select(subq).order_by(subq.c.last_activity.desc()).limit(limit)
    )
    rows = result.all()

    sessions_info = []
    for row in rows:
        sid = row.session_id
        title_res = await session.execute(
            select(ChatHistoryORM.content)
            .where(ChatHistoryORM.session_id == sid, ChatHistoryORM.role == "user")
            .order_by(ChatHistoryORM.created_at.asc(), ChatHistoryORM.id.asc())
            .limit(1)
        )
        first_user_msg = title_res.scalar_one_or_none()
        title = (first_user_msg[:45] + "...") if first_user_msg and len(first_user_msg) > 45 else (first_user_msg or sid[:18])
        sessions_info.append({
            "id": sid,
            "title": title,
            "count": row.msg_count,
            "updated_at": row.last_activity.strftime("%Y-%m-%d %H:%M") if row.last_activity else "",
        })
    return sessions_info


async def list_session_messages(session: AsyncSession, session_id: str) -> list[ChatHistoryEntry]:
    """Return messages for one persisted chat session in chronological order."""
    result = await session.execute(
        select(ChatHistoryORM)
        .where(ChatHistoryORM.session_id == session_id)
        .order_by(ChatHistoryORM.created_at.asc(), ChatHistoryORM.id.asc())
    )
    return [row.to_entry() for row in result.scalars()]


async def delete_session(session: AsyncSession, session_id: str) -> None:
    """Delete all history entries for a given session_id."""
    await session.execute(
        delete(ChatHistoryORM).where(ChatHistoryORM.session_id == session_id)
    )
    await session.commit()

