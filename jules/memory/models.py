from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


@dataclass(slots=True)
class SessionContext:
    project: str | None
    directory: str
    active_files: list[str]
    inferred_intent: str | None
    time_of_day: str


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


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy 2.0 ORM models."""
    pass


def _serialize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _deserialize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class EpisodeORM(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column()
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON)
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

    @classmethod
    def from_dataclass(cls, ep: Episode) -> "EpisodeORM":
        """Converts an Episode dataclass to an EpisodeORM instance."""
        return cls(
            id=ep.id,
            timestamp=_serialize_timestamp(ep.timestamp),
            context_json={
                "project": ep.context.project,
                "directory": ep.context.directory,
                "active_files": ep.context.active_files,
                "inferred_intent": ep.context.inferred_intent,
                "time_of_day": ep.context.time_of_day,
            },
            problem=ep.problem,
            process=ep.process,
            solution=ep.solution,
            duration_seconds=ep.duration_seconds,
            friction_score=ep.friction_score,
            tags=ep.tags,
            importance=ep.importance,
            model_used=ep.model_used,
            provider_used=ep.provider_used,
            memory_schema_version=ep.memory_schema_version,
        )

    def to_dataclass(self) -> Episode:
        """Converts an EpisodeORM instance to an Episode dataclass."""
        ctx = SessionContext(
            project=self.context_json.get("project"),
            directory=self.context_json.get("directory", ""),
            active_files=self.context_json.get("active_files", []),
            inferred_intent=self.context_json.get("inferred_intent"),
            time_of_day=self.context_json.get("time_of_day", ""),
        )
        return Episode(
            id=self.id,
            timestamp=_deserialize_timestamp(self.timestamp),
            context=ctx,
            problem=self.problem,
            process=self.process,
            solution=self.solution,
            duration_seconds=self.duration_seconds,
            friction_score=self.friction_score,
            tags=self.tags,
            importance=self.importance,
            model_used=self.model_used,
            provider_used=self.provider_used,
            memory_schema_version=self.memory_schema_version,
        )
