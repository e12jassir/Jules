# Memory Engine Specification

## Purpose

Define the coordination engine for Jules memory, responsible for orchestrating scoring, vector storage, and relational persistence asynchronously to ensure zero-latency terminal response.

## Requirements

### Requirement: Zero-Latency Coordination

The memory engine MUST expose an asynchronous persistence API that does not block the main event loop when called.

#### Scenario: Background persistence task dispatch
- **Given** a new `Episode` dataclass
- **When** the system calls `engine.persist_async(episode)`
- **Then** the function MUST return immediately
- **And** the actual persistence (scoring, vector, relational) MUST occur as a background task via `asyncio.create_task()` or similar non-blocking mechanism.

### Requirement: Orchestration Flow

The engine MUST orchestrate the three subsystems (scoring, episodic/vector, persistent/relational) in a coordinated pipeline.

#### Scenario: End-to-end memory persistence
- **Given** a newly formed `Episode` dataclass without an importance score
- **When** the background persistence task executes
- **Then** it MUST first invoke the `memory-scoring` module to calculate importance
- **And** it MUST update the `Episode` with the resulting score
- **And** it MUST invoke the `memory-vector` module to store the vector representation
- **And** it MUST invoke the `memory-persistence` module to store the relational record
- **And** failures in one subsystem MUST be logged and SHOULD NOT crash the background loop.

### Requirement: Asynchronous Retrieval

The memory engine MUST provide an asynchronous API for retrieving past episodes.

#### Scenario: Retrieve relevant context
- **Given** a query string and a target `limit`
- **When** `engine.retrieve_async(query, limit)` is called
- **Then** it MUST query the `memory-vector` module for relevant IDs
- **And** it MUST fetch the full `Episode` records from the `memory-persistence` module using those IDs
- **And** it MUST return the hydrated `Episode` dataclasses asynchronously.
