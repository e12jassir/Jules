# Design: Modulo 6 (Motor de Memoria)

## Technical Approach
1. **Scoring Subsystem (`jules/memory/scoring.py`)**: Implement an asynchronous function `evaluate_importance(episode: Episode) -> float`. It will send a prompt via the local `OllamaProvider` (using Llama 3.2 1B). The prompt will instruct the model to analyze the episode's problem, process, and solution, ending exactly with `SCORE: X.X`. A regular expression (e.g., `r"SCORE:\s*(0\.\d+|1\.0)"`) will extract the score. A fallback value (e.g., `0.5`) will be returned if extraction fails.
2. **Vector Subsystem (`jules/memory/episodic.py`)**: Wrap LanceDB's synchronous API inside `asyncio.to_thread()` to prevent blocking the event loop. Implement `store_async(episode: Episode)` to add embeddings. For context retrieval, implement `retrieve_async(query: str, limit: int) -> list[str]` which retrieves `limit * 2` results based on cosine distance, computes a time-decay penalty locally in Python based on `timestamp`, re-sorts the vectors, and returns the top `limit` IDs.
3. **Relational Subsystem (`jules/memory/persistent.py`)**: Utilize `aiosqlite` and `AsyncSession` for SQLite interactions. Implement `save_async(episode: Episode)` and `get_async(episode_id: str) -> Episode`. The ORM setup enables non-blocking CRUD for long-term storage of episodes.
4. **Engine Orchestration (`jules/memory/engine.py`)**: Implement a `MemoryEngine` class. The `persist_async(episode: Episode)` method will immediately call `asyncio.create_task()` to spawn a background operation, returning instantly. The background operation will await the importance score, update the dataclass, and then concurrently (or sequentially) dispatch `episodic.store_async` and `persistent.save_async`. Errors will be logged without crashing the background task loop. `retrieve_async(query: str, limit: int)` will orchestrate vector retrieval and relational hydration asynchronously.

## Architecture Decisions
1. **Fire-and-forget Background Persistence**: Using `asyncio.create_task()` directly supports the zero-latency requirement for the terminal experience. The caller isn't blocked by scoring or database I/O.
2. **Regex over JSON parsing**: Small 1B models struggle with strict JSON schemas. Leveraging text parsing and a rigid `SCORE: X.X` suffix pattern via Regex is a resilient approach for extracting structured data.
3. **Thread Offloading for LanceDB**: LanceDB's synchronous C++ engine must not block the asynchronous event loop. By wrapping LanceDB operations in `asyncio.to_thread()`, we ensure smooth scaling and non-blocking semantics for Jules.
4. **Python-side Time Decay**: Rather than enforcing complex vector similarity re-ranking inside the DB, fetching extra rows (`limit * 2`) and re-ranking them inside Python allows high flexibility for tuning the memory time-decay algorithm.
5. **Async SQLAlchemy**: Moving from standard SQLite drivers to `aiosqlite` with `AsyncSession` modernizes the relational I/O. `lazy="joined"` is already present in `EpisodeORM` ensuring that related entities (`session_context`) are eager-loaded, avoiding async lazy-load exceptions.

## Data Flow
1. **Capture**: A new `Episode` dataclass is generated post-interaction.
2. **Dispatch**: Main execution calls `engine.persist_async(episode)`, which returns immediately.
3. **Background Pipeline**:
   - `scoring.evaluate_importance(episode)` runs asynchronously, returning a float.
   - `episode.importance` is updated.
   - `episodic.store_async(episode)` is awaited (runs in a thread pool).
   - `persistent.save_async(episode)` is awaited (runs non-blocking via `aiosqlite`).
4. **Retrieval**:
   - Main execution awaits `engine.retrieve_async(query, limit)`.
   - Engine calls `episodic.retrieve_async(query, limit)`.
   - LanceDB fetches `limit * 2` vectors, Python applies time-decay based on `timestamp` age, and returns the top `limit` IDs.
   - For each ID, the Engine calls `persistent.get_async(id)` to retrieve the hydrated `Episode` dataclass.

## File Changes
- **`pyproject.toml`**: Add `aiosqlite` dependency.
- **`jules/memory/scoring.py`**: Add Llama 3.2 1B prompting and regex parsing.
- **`jules/memory/episodic.py`**: Add thread-offloaded LanceDB operations and time-decay logic.
- **`jules/memory/persistent.py`**: Add async CRUD using `AsyncSession`.
- **`jules/memory/engine.py`**: Implement `MemoryEngine` orchestrator, background task management, and exception handling.

## Interfaces / Contracts
- `engine.persist_async(episode: Episode) -> None` (returns immediately, dispatches task)
- `engine.retrieve_async(query: str, limit: int) -> list[Episode]`
- `scoring.evaluate_importance(episode: Episode) -> float`
- `episodic.store_async(episode: Episode) -> None`
- `episodic.retrieve_async(query: str, limit: int) -> list[str]`
- `persistent.save_async(episode: Episode) -> None`
- `persistent.get_async(episode_id: str) -> Episode | None`

## Testing Strategy
1. **Scoring**: Mock `OllamaProvider` with responses containing well-formed `SCORE: X.X` and malformed data to ensure the regex acts robustly and fallbacks are used.
2. **Episodic**: Use an in-memory or temporary LanceDB directory. Test thread-offloading doesn't block the loop. Insert vectors with various timestamps and test `retrieve_async` to ensure older vectors are correctly penalized during re-ranking.
3. **Persistent**: Spin up a transient `sqlite+aiosqlite:///:memory:` or temporary file database. Validate that `save_async` writes perfectly and `get_async` returns a fully hydrated `Episode` (including eager-loaded context).
4. **Engine**: Mock scoring, episodic, and persistent modules. Fire `persist_async` and assert the task executed correctly. Force an exception in the mock scoring or storage and ensure the background task handles it securely without bubbling to the global loop.

## Migration / Rollout
- Update `pyproject.toml` to install `aiosqlite`.
- Ensure Alembic is executed against the database normally (synchronous), but runtime processes consume the database asynchronously. No major changes to `alembic.ini` needed if sync is still used for migrations.
- Verify that LanceDB embeddings table is correctly initialized if it does not exist, with the exact required vector dimensions matching the embedding model configuration.

## Open Questions
- **Time-Decay Formula**: What specific function to use? (e.g., exponential decay base $e^{-\lambda t}$).
- **Embedder**: The Vector Spec mentions the embedding model. Does Jules have a shared instance of the embedder, or should `episodic.py` manage its own embedding generation inside `to_thread()`?
- **Task Management**: Should `asyncio.create_task` tasks be tracked to prevent them from being garbage-collected or forcefully terminated during app shutdown?
