# Tasks: Module 2 Data Models

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 280-360 |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | One focused Module 2 work unit |
| Delivery strategy | single-pr-default |
| Chain strategy | stacked on `fix/module-1-sanitizer-review` |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: stacked on `fix/module-1-sanitizer-review`
400-line budget risk: Medium

## Phase 1: Contract / RED

- [x] 1.1 RED: Add tests for canonical `SessionContext` and `Episode` dataclass initialization and defaults.
- [x] 1.2 RED: Add failing conversion tests for ORM ↔ dataclass round-trip.
- [x] 1.3 RED: Add real SQLite ORM persistence test for `EpisodeORM` + `SessionContextORM`.

## Phase 2: Core Implementation / GREEN

- [x] 2.1 GREEN: Implement pure `SessionContext` and `Episode` dataclasses in `jules/memory/models.py`.
- [x] 2.2 GREEN: Implement SQLAlchemy 2.0 `Base`, `SessionContextORM`, and `EpisodeORM`.
- [x] 2.3 GREEN: Implement explicit `from_dataclass()` / `to_dataclass()` helpers.
- [x] 2.4 REFACTOR: Normalize SQLite timestamp handling to preserve UTC semantics in dataclasses.

## Phase 3: Migration / Roadmap-Literal Alignment

- [x] 3.1 Add SQLite batch-mode migration config in `alembic/env.py`.
- [x] 3.2 Keep `db91a0ae1c2b_initial_schema` as the original baseline.
- [x] 3.3 Create `123f8dc39e81_roadmap_session_context_orm` to add `session_contexts` and relate `episodes`.
- [x] 3.4 Backfill populated databases from `episodes.context_json` during upgrade.
- [x] 3.5 Reconstruct `context_json` during downgrade so downgrade is data-safe.

## Phase 4: Verification / Closure

- [x] 4.1 Run `./.venv/bin/python -m pytest tests/unit/test_models.py` and keep it GREEN.
- [x] 4.2 Run `./.venv/bin/python -m compileall jules`.
- [x] 4.3 Rehearse Alembic upgrade/downgrade/upgrade on an empty SQLite database.
- [x] 4.4 Rehearse Alembic upgrade/downgrade/upgrade on a populated SQLite database with existing `context_json`.
- [x] 4.5 Fresh-review the final Module 2 diff before commit.
