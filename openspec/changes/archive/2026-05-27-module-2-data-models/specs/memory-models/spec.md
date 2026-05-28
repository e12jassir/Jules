# Memory Models Specification

## Purpose

Define the canonical data-model contracts and persisted SQLite schema for Jules memory episodes and session context.

## Requirements

### Requirement: SessionContext Dataclass Contract

The system MUST expose a pure `SessionContext` dataclass with these fields:

- `project: str | None`
- `directory: str`
- `active_files: list[str]`
- `inferred_intent: str | None`
- `time_of_day: str`

#### Scenario: Create a SessionContext value
- **Given** Module 2 models are imported
- **When** a caller constructs `SessionContext(project, directory, active_files, inferred_intent, time_of_day)`
- **Then** the value MUST be usable without importing SQLAlchemy
- **And** `active_files` MUST remain a list payload on the dataclass contract.

### Requirement: Episode Dataclass Contract

The system MUST expose a pure `Episode` dataclass with these fields:

- `id: str`
- `timestamp: datetime`
- `context: SessionContext`
- `problem: str | None`
- `process: str | None`
- `solution: str | None`
- `duration_seconds: int | None`
- `friction_score: float`
- `tags: list[str]`
- `importance: float = 0.0`
- `model_used: str = ""`
- `provider_used: str = ""`
- `memory_schema_version: str = "1.2"`

#### Scenario: Create an Episode value
- **Given** a valid `SessionContext`
- **When** a caller constructs `Episode(...)`
- **Then** default values for `importance`, `model_used`, `provider_used`, and `memory_schema_version` MUST be applied when omitted
- **And** the dataclass MUST remain independent from ORM/session state.

### Requirement: ORM Separation

The system MUST define both `SessionContextORM` and `EpisodeORM`, and business logic MUST NOT depend on ORM models directly.

#### Scenario: Persist through ORM models
- **Given** a valid `Episode` dataclass
- **When** the system converts it to ORM objects for persistence
- **Then** `EpisodeORM` MUST hold a one-to-one reference to `SessionContextORM`
- **And** `active_files` MAY remain JSON inside `session_contexts`
- **And** callers outside persistence MUST still work only with dataclasses.

### Requirement: Explicit ORM Round-Trip Conversion

The system MUST provide explicit conversion helpers between dataclasses and ORM models.

#### Scenario: Convert dataclass to ORM and back
- **Given** an `Episode` dataclass with nested `SessionContext`
- **When** `EpisodeORM.from_dataclass()` and `EpisodeORM.to_dataclass()` are used
- **Then** the restored `Episode` MUST be equivalent to the original value
- **And** timestamp handling MUST preserve UTC semantics.

### Requirement: SQLite-Compatible Migrations

The system MUST support SQLite Alembic migrations for the Module 2 schema.

#### Scenario: Upgrade an empty SQLite database
- **Given** a SQLite database at revision `db91a0ae1c2b`
- **When** Alembic upgrades to head
- **Then** the database MUST contain both `session_contexts` and `episodes`
- **And** `episodes.session_context_id` MUST be unique, non-null, and refer to `session_contexts.id`.

#### Scenario: Upgrade a populated SQLite database
- **Given** a SQLite database at revision `db91a0ae1c2b` with existing `episodes.context_json` data
- **When** Alembic upgrades to revision `123f8dc39e81`
- **Then** the migration MUST backfill `session_contexts` rows from `context_json`
- **And** existing episode rows MUST keep equivalent context values through the new foreign-key relation.

#### Scenario: Downgrade after roadmap-literal migration
- **Given** a SQLite database at revision `123f8dc39e81`
- **When** Alembic downgrades to `db91a0ae1c2b`
- **Then** the migration MUST reconstruct `episodes.context_json`
- **And** no existing episode context data may be lost in the downgrade.

### Requirement: Verification Baseline

The system MUST maintain unit coverage for Module 2 contracts and persistence behavior.

#### Scenario: Run Module 2 verification
- **Given** the project virtualenv is active
- **When** `./.venv/bin/python -m pytest tests/unit/test_models.py` runs
- **Then** defaults, conversions, and SQLite ORM round-trip behavior MUST pass
- **And** Alembic upgrade/downgrade rehearsal MUST succeed for SQLite.