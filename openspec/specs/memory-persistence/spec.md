# Memory Persistence Specification

## Purpose

Define the asynchronous relational storage for Jules memory, utilizing `aiosqlite` and Async SQLAlchemy for non-blocking CRUD operations.

## Requirements

### Requirement: Async Engine Initialization

The persistence module MUST use an asynchronous SQLAlchemy engine.

#### Scenario: Initialize database engine
- **Given** a SQLite database file path
- **When** the persistence module is initialized
- **Then** it MUST create an engine using the `sqlite+aiosqlite://` driver
- **And** it MUST configure the session maker for async operations (`AsyncSession`).

### Requirement: Non-blocking CRUD

All database operations MUST be fully asynchronous.

#### Scenario: Save episode relationally
- **Given** an `Episode` dataclass
- **When** `persistent.save_async(episode)` is called
- **Then** it MUST `await` the session `add` and `commit` operations
- **And** the event loop MUST NOT be blocked.

#### Scenario: Fetch episode by ID
- **Given** an episode ID
- **When** `persistent.get_async(episode_id)` is called
- **Then** it MUST execute an async `select` statement
- **And** it MUST return the mapped `Episode` dataclass (re-hydrated from ORM models).
