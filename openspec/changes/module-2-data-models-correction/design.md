# Design: Correction for Module 2 Data Models

This correction design realigns the current work with the roadmap while keeping the branch cleanup already completed. The immediate correction is: keep Module 1 sanitizer follow-up isolated, keep Module 2 on its own branch/change, and restore the roadmap's explicit ORM split with both `SessionContextORM` and `EpisodeORM`.

## Quick path

1. Freeze the current mixed branch; do not add more code to it.
2. Promote `fix/module-1-sanitizer-review` as the clean sanitizer base branch.
3. Keep `feat/module-2-data-models` as the stacked Module 2 branch on top of that base.
4. Replace embedded `context_json` persistence with explicit `SessionContextORM` plus a relation from `EpisodeORM`.
5. Verify tests and Alembic again on the Module 2 branch before continuing with more memory work.

## Problem being corrected

The originally pushed sanitizer branch mixes two concerns:

- Module 1 sanitizer follow-up and cleanup
- Module 2 data-model and Alembic work

That mix increases review confusion and previously hid an architectural mismatch with the written plan: the implementation persisted `SessionContext` inside `EpisodeORM.context_json` instead of creating a separate `SessionContextORM` table.

Because that mixed branch was already pushed, this correction prefers a non-destructive cleanup: create clean additive branches for sanitizer and Module 2 instead of force-rewriting the old remote history.

## Correction goals

| Goal | Why it matters |
|---|---|
| Separate Module 1 and Module 2 work | Keeps roadmap steps reviewable and reversible. |
| Preserve valid Module 2 implementation | The current dataclasses, ORM helpers, tests, and migration are useful and should not be discarded. |
| Make the persistence model explicit | Avoids silent drift between ROADMAP and code. |
| Protect future memory work | Later modules should build on a declared contract, not an accidental schema. |

## Decisions

| Topic | Decision | Rationale |
|---|---|---|
| Branch scope | Use a clean stacked branch layout: `fix/module-1-sanitizer-review` → `feat/module-2-data-models` | Keeps review units focused without force-rewriting already-pushed history. |
| Canonical business model | `SessionContext` and `Episode` remain pure dataclasses | Matches AGENT.md and keeps business logic ORM-free. |
| ORM shape for Phase 1 | Implement both `SessionContextORM` and `EpisodeORM` | Matches the roadmap literally and makes persistence boundaries explicit. |
| Context persistence | Store session context in `session_contexts` and reference it from `episodes` | Restores the intended schema while preserving pure dataclasses in business logic. |
| Roadmap divergence handling | Remove the divergence by aligning code to the roadmap | Prevents future confusion between design docs and implementation. |
| IDs | Keep `Episode.id` as string UUID | Stable, portable, and already aligned with the implementation direction. |

## Scope boundaries

### In scope
- branch/change separation
- explicit persistence decision for `SessionContext`
- preserving current dataclass approach while expanding ORM structure
- re-verification of tests and migration on the dedicated Module 2 branch

### Out of scope
- implementing memory engine behavior
- retrieval/scoring logic
- provider/router integration
- redesigning Module 2 into a fully normalized relational model

## Technical approach

### 1. Separate the work units

Create a dedicated Module 2 branch from the sanitizer-review baseline. Because the mixed sanitizer branch was already pushed, the cleanup strategy is additive rather than destructive.

Target shape:

- `fix/module-1-sanitizer-review`
  - sanitizer fixes
  - cleanup ancestry accepted as legacy
- `feat/module-2-data-models`
  - stacked on `fix/module-1-sanitizer-review`
  - `jules/memory/models.py`
  - `tests/unit/test_models.py`
  - `alembic/env.py`
  - `alembic.ini`
  - `alembic/versions/<initial_schema>.py`
- `chore/module-1-sanitizer-cleanup`
  - deprecated mixed branch; keep as legacy reference only

### 2. Keep the canonical domain model pure

Business logic MUST continue to speak only in dataclasses:

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

No core logic should depend on SQLAlchemy models directly.

### 3. Restore explicit context persistence for Phase 1

Phase 1 will use a dedicated `SessionContextORM` table plus a one-to-one relation from `EpisodeORM`.

```python
class SessionContextORM(Base):
    __tablename__ = "session_contexts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project: Mapped[str | None] = mapped_column()
    directory: Mapped[str] = mapped_column()
    active_files: Mapped[list[str]] = mapped_column(JSON)
    inferred_intent: Mapped[str | None] = mapped_column()
    time_of_day: Mapped[str] = mapped_column()

class EpisodeORM(Base):
    __tablename__ = "episodes"
    id: Mapped[str] = mapped_column(primary_key=True)
    session_context_id: Mapped[int] = mapped_column(ForeignKey("session_contexts.id"), nullable=False, unique=True)
    session_context: Mapped[SessionContextORM] = relationship(...)
```

`active_files` remains JSON inside `session_contexts` because the roadmap requires `SessionContextORM`, not full normalization of the list payload.

## Tradeoffs

| Option | Keep | Reject for now | Why |
|---|---|---|---|
| Embedded `context_json` | — | Yes | Rejected because the user chose roadmap-literal alignment. |
| Separate `SessionContextORM` table | Yes | — | Matches the roadmap and keeps ORM structure explicit. |
| Fully normalized `active_files` child table | — | Yes | Still unnecessary for current needs; JSON inside `session_contexts` is enough. |
| Dataclass-only with no ORM helpers | — | Yes | Roadmap requires SQLite/Alembic persistence groundwork. |

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Mixed branch continues to grow | Review confusion and harder rollback | Stop coding on mixed branch; split immediately. |
| Hidden roadmap drift | Future uncertainty about intended schema | Keep this correction design with the Module 2 change. |
| ORM relation and migration become more complex | More moving parts in Module 2 | Keep explicit `from_dataclass` and `to_dataclass` helpers plus tests and Alembic verification. |
| Future queries need deeper normalization of `active_files` | Possible migration later | Accept as Phase 2 concern; keep `active_files` as JSON inside `session_contexts` for now. |

## Verification strategy

| Layer | Check | Expected result |
|---|---|---|
| Git hygiene | Module 2 lives on its own stacked branch | `feat/module-2-data-models` is reviewed against `fix/module-1-sanitizer-review`, and the legacy mixed branch receives no further work. |
| Unit tests | `./.venv/bin/python -m pytest tests/unit/test_models.py` | Model defaults and ORM round-trip pass. |
| Sanitizer regression safety | `./.venv/bin/python -m pytest tests/unit/test_sanitizer.py` on sanitizer branch | Module 1 remains stable after branch split. |
| Migration | `./.venv/bin/python -m alembic upgrade head` | `session_contexts` and `episodes` tables create cleanly with the expected foreign key. |
| Metadata wiring | `./.venv/bin/python -m alembic current` | Head points to the initial schema revision. |

## Checklist

- [x] Freeze the legacy mixed branch and stop using it for new work
- [x] Use `fix/module-1-sanitizer-review` as the sanitizer base branch
- [x] Use `feat/module-2-data-models` as the stacked Module 2 branch
- [x] Replace `context_json` with explicit `SessionContextORM` persistence
- [x] Re-run tests and Alembic on the dedicated Module 2 branch
- [x] Continue Module 2 only after the stacked branch layout is clear

## Next step

Execute the stacked-branch cleanup first. After that, continue Module 2 using this correction design as the declared architecture baseline.