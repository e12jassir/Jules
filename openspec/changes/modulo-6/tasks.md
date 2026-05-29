# Implementation Tasks: Modulo 6 (Motor de Memoria)

## Review Workload Forecast

| Metric | Assessment |
|--------|------------|
| Estimated changed lines | ~650 lines |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Decision needed before apply | Yes |

## Delivery Strategy
- Strategy used: `ask-on-risk`
- Chain strategy: `pending`

---

## Phase 1: Infrastructure & Data Setup

- [x] 1. Update `pyproject.toml` and lockfile to include `aiosqlite`.
- [x] 2. Update `jules/memory/persistent.py` to initialize an asynchronous SQLAlchemy engine using the `sqlite+aiosqlite://` driver, using `AsyncSession`.

## Phase 2: Relational Persistence (`jules/memory/persistent.py`)

- [x] 3. Implement `save_async(episode: Episode) -> None` using `AsyncSession` `add` and `commit` operations, ensuring they are awaited and do not block the event loop.
- [x] 4. Implement `get_async(episode_id: str) -> Episode | None` using an async `select` statement that perfectly re-hydrates the `Episode` dataclass (eager-loading `SessionContext`).
- [x] 5. Write unit tests for `persistent.py` using an in-memory (`sqlite+aiosqlite:///:memory:`) database to validate async CRUD functionality.

## Phase 3: Vector Storage (`jules/memory/episodic.py`)

- [x] 6. Implement LanceDB schema initialization, strictly enforcing vector dimensions to match the embedding model configuration.
- [x] 7. Implement `store_async(episode: Episode) -> None` by wrapping LanceDB's synchronous `.add()` call inside `asyncio.to_thread()` to prevent event loop blocking.
- [x] 8. Implement `retrieve_async(query: str, limit: int) -> list[str]` using `asyncio.to_thread()`. Fetch `limit * 2` vectors by cosine distance, apply time-decay penalty locally in Python using `timestamp`, re-sort, and slice to the top `limit` IDs.
- [x] 9. Write unit tests for `episodic.py` with an in-memory/temp LanceDB instance to assert non-blocking thread offloading and correct mathematical time-decay penalty.

## Phase 4: Importance Scoring (`jules/memory/scoring.py`)

- [x] 10. Implement `evaluate_importance(episode: Episode) -> float` to construct a Llama 3.2 1B prompt that requires the output to end exactly with `SCORE: X.X`.
- [x] 11. Implement robust regular expression parsing (e.g., `r"SCORE:\s*(0\.\d+|1\.0)"`) inside `evaluate_importance` to extract the score reliably, bypassing full JSON schemas.
- [x] 12. Implement fallback behavior to log a warning and return a default score of `0.5` if the LLM output is malformed and fails regex extraction.
- [x] 13. Write unit tests for `scoring.py` mocking `OllamaProvider` with well-formed and malformed responses to validate the regex parsing and fallback safety.

## Phase 5: Engine Orchestration (`jules/memory/engine.py`)

- [ ] 14. Implement the `MemoryEngine` class and `persist_async(episode: Episode) -> None` method. The method MUST use `asyncio.create_task()` to immediately return while pushing the persistence pipeline to the background.
- [ ] 15. Implement the internal background pipeline in `MemoryEngine`: await `evaluate_importance`, update `episode.importance`, and await both `episodic.store_async` and `persistent.save_async`. Add try/except blocks to log exceptions without crashing the background task loop.
- [ ] 16. Implement `retrieve_async(query: str, limit: int) -> list[Episode]` by mapping LanceDB IDs retrieved from `episodic.retrieve_async` to hydrated episodes via `persistent.get_async`.
- [ ] 17. Write unit tests for `engine.py` mocking `scoring`, `episodic`, and `persistent` modules. Assert that `persist_async` immediately returns (zero-latency) and correctly handles intentional exceptions raised by mocked dependencies.
