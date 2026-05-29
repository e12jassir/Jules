# Delta Spec: memory-models

## ADDED

### Requirement: Async ORM Compatibility

The ORM definitions MUST be fully compatible with `aiosqlite` and Async SQLAlchemy.

#### Scenario: Query ORM models asynchronously
- **Given** `SessionContextORM` and `EpisodeORM`
- **When** queried through an `AsyncSession`
- **Then** all relationships MUST NOT use implicit synchronous lazy loading that would trigger `MissingGreenlet` errors
- **And** any required relationships MUST be explicitly eager loaded or awaited.

## MODIFIED

### Requirement: SQLite-Compatible Migrations

The system MUST support SQLite Alembic migrations for the Module 2 schema, and now MUST support both sync (Alembic) and async (`aiosqlite`) runtime access.

#### Scenario: Upgrade an empty SQLite database
- **Given** a SQLite database
- **When** Alembic upgrades to head
- **Then** the migration MUST execute successfully
- **And** the resulting schema MUST be strictly compatible with `aiosqlite` usage.

## REMOVED
*(None)*
