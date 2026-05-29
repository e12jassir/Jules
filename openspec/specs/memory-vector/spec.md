# Memory Vector Specification

## Purpose

Define the episodic vector storage component using LanceDB, ensuring synchronous operations are safely offloaded to prevent blocking.

## Requirements

### Requirement: Non-blocking Vector Operations

The vector module MUST use LanceDB's synchronous API wrapped safely in thread offloading.

#### Scenario: Store an episode vector
- **Given** an `Episode` dataclass with an importance score
- **When** the system calls `episodic.store_async(episode)`
- **Then** the vector computation and LanceDB `add()` operation MUST be executed within `asyncio.to_thread()`
- **And** the main event loop MUST NOT be blocked during disk or network I/O.

### Requirement: Dimension Consistency

The vector store MUST strictly enforce vector dimensions matching the configured model.

#### Scenario: Schema initialization
- **Given** the system is starting up
- **When** LanceDB creates or opens the table
- **Then** it MUST enforce a schema with the exact vector dimension required by the embedding model.

### Requirement: Time-Decay Retrieval

The vector module MUST apply a time-decay penalty to relevance scores when retrieving episodes, to favor more recent memories.

#### Scenario: Retrieve with time decay
- **Given** a query and a requested `limit` of N
- **When** `episodic.retrieve_async(query, limit=N)` is called
- **Then** it MUST fetch `N * 2` vectors from LanceDB by cosine distance
- **And** it MUST apply a mathematical time-decay penalty to the raw distance scores in Python
- **And** it MUST sort the results by the penalized score
- **And** it MUST return the top `N` episode IDs.
