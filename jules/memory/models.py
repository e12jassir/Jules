from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


@dataclass(slots=True)
class SessionContext:
    project: str | None
    directory: str
    active_files: list[str]
    inferred_intent: str | None
    time_of_day: str
    shell: str = "unknown"


@dataclass(slots=True)
class Episode:
    id: str
    timestamp: datetime
    context: SessionContext
    problem: str | None
    process: str | None
    solution: str | None
    duration_seconds: int | None
    friction_score: float
    tags: list[str] = field(default_factory=list)
    importance: float = 0.0
    model_used: str = ""
    provider_used: str = ""
    memory_schema_version: str = "1.2"


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _serialize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware (tzinfo is None)")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _deserialize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SessionContextORM(Base):
    __tablename__ = "session_contexts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project: Mapped[str | None] = mapped_column()
    directory: Mapped[str] = mapped_column()
    active_files: Mapped[list[str]] = mapped_column(JSON)
    inferred_intent: Mapped[str | None] = mapped_column()
    time_of_day: Mapped[str] = mapped_column()
    shell: Mapped[str] = mapped_column(default="unknown", server_default="unknown")

    episode: Mapped["EpisodeORM"] = relationship(back_populates="session_context")

    @classmethod
    def from_dataclass(cls, ctx: SessionContext) -> "SessionContextORM":
        return cls(
            project=ctx.project,
            directory=ctx.directory,
            active_files=list(ctx.active_files),
            inferred_intent=ctx.inferred_intent,
            time_of_day=ctx.time_of_day,
            shell=ctx.shell,
        )

    def to_dataclass(self) -> SessionContext:
        return SessionContext(
            project=self.project,
            directory=self.directory,
            active_files=list(self.active_files),
            inferred_intent=self.inferred_intent,
            time_of_day=self.time_of_day,
            shell=self.shell,
        )


class EpisodeORM(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column()
    session_context_id: Mapped[int] = mapped_column(ForeignKey("session_contexts.id"), nullable=False, unique=True)
    problem: Mapped[str | None] = mapped_column()
    process: Mapped[str | None] = mapped_column()
    solution: Mapped[str | None] = mapped_column()
    duration_seconds: Mapped[int | None] = mapped_column()
    friction_score: Mapped[float] = mapped_column()
    tags: Mapped[list[str]] = mapped_column(JSON)
    importance: Mapped[float] = mapped_column(default=0.0)
    model_used: Mapped[str] = mapped_column(default="")
    provider_used: Mapped[str] = mapped_column(default="")
    memory_schema_version: Mapped[str] = mapped_column(default="1.2")

    session_context: Mapped[SessionContextORM] = relationship(back_populates="episode", cascade="all, delete-orphan", single_parent=True, lazy="joined")

    @classmethod
    def from_dataclass(cls, ep: Episode) -> "EpisodeORM":
        """Converts an Episode dataclass to an EpisodeORM instance."""
        return cls(
            id=ep.id,
            timestamp=_serialize_timestamp(ep.timestamp),
            session_context=SessionContextORM.from_dataclass(ep.context),
            problem=ep.problem,
            process=ep.process,
            solution=ep.solution,
            duration_seconds=ep.duration_seconds,
            friction_score=ep.friction_score,
            tags=list(ep.tags),
            importance=ep.importance,
            model_used=ep.model_used,
            provider_used=ep.provider_used,
            memory_schema_version=ep.memory_schema_version,
        )

    def to_dataclass(self) -> Episode:
        """Converts an EpisodeORM instance to an Episode dataclass."""
        return Episode(
            id=self.id,
            timestamp=_deserialize_timestamp(self.timestamp),
            context=self.session_context.to_dataclass(),
            problem=self.problem,
            process=self.process,
            solution=self.solution,
            duration_seconds=self.duration_seconds,
            friction_score=self.friction_score,
            tags=list(self.tags),
            importance=self.importance,
            model_used=self.model_used,
            provider_used=self.provider_used,
            memory_schema_version=self.memory_schema_version,
        )
