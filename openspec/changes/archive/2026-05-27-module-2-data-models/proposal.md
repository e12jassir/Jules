# Proposal: Module 2 Data Models

## Intent

Define Jules' canonical memory data structures and their first persisted SQLite representation so later memory, router, and provider work can build on a stable contract.

## Scope

### In Scope
- Pure Python `dataclass` contracts for `SessionContext` and `Episode` in `jules/memory/models.py`.
- SQLAlchemy 2.0 ORM models `SessionContextORM` and `EpisodeORM`.
- Explicit conversion helpers between dataclasses and ORM models.
- Initial Alembic schema plus follow-up migration to the roadmap-literal split context model.
- Unit tests for defaults, conversion, and real SQLite ORM round-trip behavior.
- SQLite-safe Alembic configuration and populated-database migration backfill.

### Out of Scope
- Memory engine retrieval or persistence orchestration.
- Embeddings, scoring, decay, or semantic search.
- Provider/router integration.
- Full normalization of `active_files` into a separate child table.

## Capabilities

### New Capabilities
- `memory-models`: canonical in-memory and persisted representations for Jules memory episodes and session context.

### Modified Capabilities
- Alembic environment now supports SQLite batch migrations for safe table rewrites.

## Behavior Contract

- Business logic MUST use pure `SessionContext` and `Episode` dataclasses, never ORM models directly.
- `Episode` MUST include `model_used`, `provider_used`, and `memory_schema_version`.
- `SessionContextORM` and `EpisodeORM` MUST round-trip to equivalent dataclass values.
- SQLite migrations MUST upgrade and downgrade both empty and populated databases without losing context data.

## Approach

Follow the roadmap literally: implement both `SessionContextORM` and `EpisodeORM`, keep `active_files` as JSON inside `session_contexts`, and use explicit conversion helpers plus Alembic batch mode for SQLite constraint changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `jules/memory/models.py` | Modified | Canonical dataclasses, ORM models, conversion helpers, UTC timestamp normalization, naming convention metadata. |
| `tests/unit/test_models.py` | New | Contract/default/conversion/SQLite round-trip coverage for Module 2. |
| `alembic/env.py` | Modified | SQLite batch-mode migration support. |
| `alembic/versions/db91a0ae1c2b_initial_schema.py` | Existing | Initial `episodes` table schema baseline. |
| `alembic/versions/123f8dc39e81_roadmap_session_context_orm.py` | New | Roadmap-literal migration with populated-db backfill. |
| `openspec/specs/memory-models/spec.md` | New | Canonical spec for Module 2 memory models. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| SQLite constraint rewrites fail | Med | Use Alembic `render_as_batch` and named constraints. |
| Existing `context_json` data is lost during migration | Med | Backfill into `session_contexts` on upgrade and reconstruct on downgrade. |
| Timestamp semantics drift across SQLite | Low | Normalize stored timestamps to naive UTC and restore UTC-aware dataclass values. |

## Rollback Plan

Revert Module 2 model/test changes and downgrade Alembic from `123f8dc39e81` to `db91a0ae1c2b`. Canonical spec additions can be removed without touching user data if the feature is abandoned before shipping.

## Dependencies

- Module 1 sanitizer already complete.
- Project-local pytest runner from `openspec/config.yaml`.
- SQLAlchemy and Alembic already declared in `pyproject.toml`.

## Success Criteria

- [x] `SessionContext` and `Episode` exist as pure dataclasses.
- [x] `SessionContextORM` and `EpisodeORM` exist and round-trip correctly.
- [x] Alembic upgrade/downgrade works on empty and populated SQLite databases.
- [x] Model tests pass with real SQLite ORM persistence.
- [x] Branch is cleanly separated so Module 3 can start from Module 2 as a stable base.

## Open Questions

None blocking.