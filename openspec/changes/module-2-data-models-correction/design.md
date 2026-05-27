# Design: Correction for Module 2 Data Models

This correction design realigns the current work with the roadmap without throwing away valid implementation. The immediate correction is: keep Module 1 sanitizer follow-up isolated, move Module 2 work to its own branch/change, and formalize the Phase 1 persistence decision that `SessionContext` is embedded as JSON inside `EpisodeORM` rather than modeled as a separate ORM table.

## Quick path

1. Freeze the current mixed branch; do not add more code to it.
2. Move the Module 2 commit(s) to a dedicated branch/change such as `feat/module-2-data-models`.
3. Treat embedded `context_json` as the official Phase 1 design unless explicitly rejected.
4. Verify tests and Alembic again on the new branch before continuing with more memory work.

## Problem being corrected

The current branch mixes two concerns:

- Module 1 sanitizer follow-up and cleanup
- Module 2 data-model and Alembic work

That mix increases review confusion and hides an architectural decision that is not yet explicit in the written plan: the implementation persists `SessionContext` inside `EpisodeORM.context_json` instead of creating a separate `SessionContextORM` table.

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
| Branch scope | Split Module 2 off the sanitizer branch | Current branch name and PR context are sanitizer-focused; memory work deserves its own review unit. |
| Canonical business model | `SessionContext` and `Episode` remain pure dataclasses | Matches AGENT.md and keeps business logic ORM-free. |
| ORM shape for Phase 1 | Keep `EpisodeORM` as the only ORM entity for now | `SessionContext` behaves like nested contextual payload, not an independent aggregate. |
| Context persistence | Store session context in `EpisodeORM.context_json` | Simpler Phase 1 schema, fewer joins, and better fit for `active_files` list payload. |
| Roadmap divergence handling | Record this as an explicit design correction | Prevents hidden mismatch with the original expectation of `SessionContextORM`. |
| IDs | Keep `Episode.id` as string UUID | Stable, portable, and already aligned with the implementation direction. |

## Scope boundaries

### In scope
- branch/change separation
- explicit persistence decision for `SessionContext`
- preserving current dataclass and `EpisodeORM` approach
- re-verification of tests and migration on the dedicated Module 2 branch

### Out of scope
- implementing memory engine behavior
- retrieval/scoring logic
- provider/router integration
- redesigning Module 2 into a fully normalized relational model

## Technical approach

### 1. Separate the work units

Create a dedicated Module 2 branch from the current memory commit chain. The sanitizer branch should stop carrying memory-model changes.

Target shape:

- `chore/module-1-sanitizer-cleanup`
  - sanitizer fixes
  - cleanup only
- `feat/module-2-data-models`
  - `jules/memory/models.py`
  - `tests/unit/test_models.py`
  - `alembic/env.py`
  - `alembic.ini`
  - `alembic/versions/<initial_schema>.py`

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

### 3. Formalize embedded-context persistence for Phase 1

Instead of creating `SessionContextORM`, Phase 1 persists the nested context inside `EpisodeORM.context_json`.

```python
class EpisodeORM(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column()
    context_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    ...
```

This is a deliberate simplification, not an omission.

## Tradeoffs

| Option | Keep | Reject for now | Why |
|---|---|---|---|
| Embedded `context_json` | Yes | — | Best fit for Phase 1 simplicity and current context payload shape. |
| Separate `SessionContextORM` table | — | Yes, for now | Adds schema and conversion complexity without clear Phase 1 payoff. |
| Fully normalized `active_files` child table | — | Yes | Too much complexity for current needs. |
| Dataclass-only with no ORM helpers | — | Yes | Roadmap requires SQLite/Alembic persistence groundwork. |

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Mixed branch continues to grow | Review confusion and harder rollback | Stop coding on mixed branch; split immediately. |
| Hidden roadmap drift | Future uncertainty about intended schema | Keep this correction design with the Module 2 change. |
| JSON payload evolves informally | Serialization drift | Keep explicit `from_dataclass` and `to_dataclass` helpers plus tests. |
| Future queries need normalized context | Possible migration later | Accept as Phase 2 concern; preserve `memory_schema_version` for migration path. |

## Verification strategy

| Layer | Check | Expected result |
|---|---|---|
| Git hygiene | Module 2 lives on its own branch | Sanitizer branch no longer contains memory-model changes. |
| Unit tests | `./.venv/bin/python -m pytest tests/unit/test_models.py` | Model defaults and ORM round-trip pass. |
| Sanitizer regression safety | `./.venv/bin/python -m pytest tests/unit/test_sanitizer.py` on sanitizer branch | Module 1 remains stable after branch split. |
| Migration | `./.venv/bin/python -m alembic upgrade head` | `episodes` table creates cleanly. |
| Metadata wiring | `./.venv/bin/python -m alembic current` | Head points to the initial schema revision. |

## Checklist

- [ ] Split Module 2 commit(s) to `feat/module-2-data-models`
- [ ] Restore sanitizer branch to sanitizer/cleanup-only scope
- [ ] Accept `context_json` as Phase 1 persistence shape
- [ ] Re-run tests and Alembic on the dedicated Module 2 branch
- [ ] Continue Module 2 only after the branch split is clean

## Next step

Execute the branch split first. After that, continue Module 2 using this correction design as the declared architecture baseline.