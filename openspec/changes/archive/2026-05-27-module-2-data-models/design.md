# Design: Module 2 Data Models

## Technical Approach

Implement the canonical memory contracts in `jules/memory/models.py` as pure dataclasses plus SQLAlchemy 2.0 ORM models. Follow the roadmap literally with both `SessionContextORM` and `EpisodeORM`, using a one-to-one relationship and explicit conversion helpers. Keep `active_files` as JSON inside `session_contexts` to avoid unnecessary child-table complexity while still honoring the separate-context ORM model.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Canonical business contract | Pure `SessionContext` / `Episode` dataclasses | ORM models in business logic | Keeps later memory engine, router, and providers ORM-free. |
| ORM structure | `SessionContextORM` + `EpisodeORM` one-to-one | Embedded `context_json` only in `episodes` | User explicitly chose roadmap-literal alignment. |
| `active_files` persistence | JSON column in `session_contexts` | Separate `active_files` table | Lower schema complexity without violating roadmap intent. |
| IDs | `Episode.id` remains string UUID | Integer PK for episodes | Portable and stable across future storage layers. |
| Timestamp storage | Store naive UTC in SQLite; restore UTC-aware dataclasses | Rely on SQLite preserving tzinfo | SQLite strips tzinfo; explicit normalization avoids drift. |
| SQLite schema evolution | Alembic batch mode + named constraints | Raw alter-table constraints | Required for safe SQLite table rewrites. |

## Data Flow

    business logic
         ↓
    Episode / SessionContext dataclasses
         ↓  from_dataclass()
    EpisodeORM + SessionContextORM
         ↓
    SQLite via SQLAlchemy / Alembic
         ↓  to_dataclass()
    Episode / SessionContext dataclasses

## File Changes

| File | Action | Description |
|---|---|---|
| `jules/memory/models.py` | Modify | Implement dataclasses, SQLAlchemy metadata naming convention, `SessionContextORM`, `EpisodeORM`, conversion helpers, and UTC timestamp normalization. |
| `tests/unit/test_models.py` | New | Add defaults, conversion, and real SQLite round-trip coverage. |
| `alembic/env.py` | Modify | Enable SQLite batch-mode migration rendering. |
| `alembic/versions/db91a0ae1c2b_initial_schema.py` | Existing | Keep original initial `episodes` table baseline. |
| `alembic/versions/123f8dc39e81_roadmap_session_context_orm.py` | New | Backfill/populated-db-safe migration from `context_json` to `SessionContextORM`. |

## Interfaces / Contracts

```python
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
```

```python
class SessionContextORM(Base):
    __tablename__ = "session_contexts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ...

class EpisodeORM(Base):
    __tablename__ = "episodes"
    id: Mapped[str] = mapped_column(primary_key=True)
    session_context_id: Mapped[int] = mapped_column(ForeignKey("session_contexts.id"), nullable=False, unique=True)
    session_context: Mapped[SessionContextORM] = relationship(...)
```

## Migration Strategy

1. Keep `db91a0ae1c2b` as the initial Module 2 baseline (`episodes` with `context_json`).
2. Add `123f8dc39e81_roadmap_session_context_orm` to:
   - create `session_contexts`
   - add nullable `episodes.session_context_id`
   - backfill rows from `context_json`
   - enforce `NOT NULL`, `UNIQUE`, and FK constraints
   - drop `context_json`
3. On downgrade, temporarily restore nullable `context_json`, reconstruct values from `session_contexts`, remove relation columns/constraints, and drop `session_contexts`.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Dataclass defaults and field contract | Direct pytest construction checks. |
| Unit | `SessionContextORM` ↔ dataclass conversion | Explicit helper tests. |
| Unit | `EpisodeORM` ↔ dataclass conversion | Explicit helper tests including timestamp normalization. |
| Unit | Real SQLAlchemy persistence | In-memory SQLite round-trip through a real ORM session. |
| Migration | Empty DB upgrade/downgrade | Alembic `upgrade head`, `downgrade base`, `upgrade head`. |
| Migration | Populated DB safety | Seed `db91a0ae1c2b` episode row, upgrade, verify backfill, downgrade, verify reconstructed `context_json`. |

## Migration / Rollout

No user-facing rollout is needed yet. Module 2 establishes schema and model contracts only. Later memory-engine work can now build on a verified roadmap-literal persistence base.

## Open Questions

None blocking.