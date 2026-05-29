# Proposal: Modulo 6 (Motor de Memoria)

## Intent
Implement the memory engine for Jules to provide a zero-latency terminal experience while orchestrating background persistence. The engine will integrate the relational store (SQLAlchemy + SQLite), the vector store (LanceDB), and importance scoring (local Llama 3.2 1B).

## Scope
- Implement `jules/memory/scoring.py` for evaluating the importance of episodes using local Llama 3.2 1B with robust regex extraction.
- Implement `jules/memory/episodic.py` for managing vectors with LanceDB, using the synchronous API wrapped in `asyncio.to_thread()` and time-decay re-ranking in Python.
- Implement `jules/memory/persistent.py` using Async SQLAlchemy (`aiosqlite`) for relational data.
- Implement `jules/memory/engine.py` to coordinate vector/relational storage and scoring asynchronously without blocking the user response.
- Update `pyproject.toml` to include `aiosqlite`.

## Capabilities
- `memory-engine`: **Needs new spec**. Will orchestrate retrieval and `persist_async` background tasks.
- `memory-vector`: **Needs new spec**. LanceDB integration via `to_thread`, handling cosine distance retrieval and time-decay penalty.
- `memory-scoring`: **Needs new spec**. Prompting the Llama model to return `SCORE: X.X` and using regex extraction.
- `memory-persistence`: **Needs new spec**. Async SQLAlchemy with `aiosqlite` for relational CRUD operations.
- `memory-models`: **Modify existing spec** (if required) to ensure compatibility with `aiosqlite` and async query patterns.

## Approach
1. **Scoring**: Prompt Llama 3.2 1B to evaluate episode importance and terminate its output with `SCORE: X.X`. Use regex to extract the score reliably, mitigating the poor JSON formatting capabilities of 1B models. Provide a fallback score (e.g., 0.5) if parsing fails.
2. **Episodic (Vector Store)**: Utilize LanceDB's synchronous API wrapped inside `asyncio.to_thread()` to ensure the event loop is never blocked, satisfying the zero-latency requirement. For decay implementation, fetch the top `limit * 2` vectors by cosine distance, apply the time-decay penalty locally in Python, and slice to `limit`.
3. **Persistent Store (Relational)**: Switch to Async SQLAlchemy via `aiosqlite`. This enables native async/await for relational data, ensuring better scaling and an idiomatic non-blocking approach.
4. **Memory Engine**: Create an `async def persist_async(episode)` function that coordinates scoring, episodic vector saving, and relational persistence. The system will dispatch this via `asyncio.create_task()`, strictly keeping the synchronous path fast.

## Affected Areas
- `jules/memory/scoring.py`
- `jules/memory/episodic.py`
- `jules/memory/persistent.py`
- `jules/memory/engine.py`
- `pyproject.toml`

## Risks
- **Zero-Latency Violation**: Accidental synchronous I/O or missed `await`/`to_thread` usage could block the event loop.
- **Model Hallucination**: The 1B Llama model could produce malformed score output or values outside the `0.0 - 1.0` range.
- **Vector Dimension Mismatch**: Embedded vector dimensions must strictly match the expected dimensions in the LanceDB schema.

## Rollback Plan
- Revert changes to `jules/memory/` modules back to empty stubs.
- Remove `aiosqlite` from `pyproject.toml` and lockfile.
- Revert any routing logic that relies on `engine.py`.

## Dependencies
- `aiosqlite` for Async SQLAlchemy.
- `lancedb` for the vector store.
- Local `OllamaProvider` configured with `llama3.2:1b`.
- Base schemas (`Episode`, `SessionContext`) defined in `jules/memory/models.py`.

## Success Criteria
- The memory engine persists new episodes in both LanceDB and SQLite asynchronously without blocking terminal output.
- `aiosqlite` successfully reads and writes relational data using Async SQLAlchemy.
- `lancedb` synchronous methods are successfully offloaded to threads via `asyncio.to_thread()`.
- Scoring robustly extracts `SCORE: X.X` via regex from Llama 3.2 1B text output, falling back to 0.5 upon parsing failures.
- Zero-latency terminal response requirement is maintained throughout all operations.
