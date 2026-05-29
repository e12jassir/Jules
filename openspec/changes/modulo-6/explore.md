## Exploration: modulo-6

### Current State
Currently, `jules/memory/` contains `models.py` with `Episode`, `SessionContext`, and their respective SQLAlchemy ORMs. The modules `engine.py`, `episodic.py`, `persistent.py`, and `scoring.py` are empty stubs. `OllamaProvider` is implemented and can provide both text generation (`ask`) and vector embeddings (`embed`). 

### Affected Areas
- `jules/memory/scoring.py` — Needs to evaluate episodes.
- `jules/memory/episodic.py` — Needs to manage vectors using `lancedb`.
- `jules/memory/persistent.py` — Needs to manage relational data using SQLAlchemy.
- `jules/memory/engine.py` — Needs to orchestrate the retrieval and background persistence.
- `pyproject.toml` (potentially) — May need `aiosqlite` if we use async SQLAlchemy.

### Approaches

#### 1. Scoring (jules/memory/scoring.py)
**Approach A: JSON Output from Llama**
Prompt `llama3.2:1b` to return a strictly formatted JSON `{"score": 0.85}`.
- Pros: Easy to parse.
- Cons: Small models (1B) can sometimes fail at strictly adhering to JSON.
- Effort: Medium

**Approach B: Regex extraction from Text**
Prompt the model to end its evaluation with `SCORE: X.X`, then use regex to extract it.
- Pros: Highly robust for small models.
- Cons: Requires slightly more parsing logic.
- Effort: Low

#### 2. Vector Store (jules/memory/episodic.py)
**Approach A: Synchronous LanceDB with `to_thread`**
Use the standard sync `lancedb` API but wrap calls in `asyncio.to_thread()` to satisfy the zero-latency skill.
- Pros: Does not require finding async equivalents in LanceDB.
- Cons: Overhead of threads.
- Effort: Low

**Approach B: Async LanceDB API**
Use `lancedb.connect_async()` if available in the installed version.
- Pros: True async I/O.
- Cons: LanceDB async API is sometimes less stable or feature-complete.
- Effort: Medium

*Decay Implementation*: Retrieve top `limit * 2` from LanceDB by cosine distance, then re-rank in Python applying the time-decay penalty to the distance, then slice to `limit`.

#### 3. Persistent Store (jules/memory/persistent.py)
**Approach A: `asyncio.to_thread` with sync SQLAlchemy**
Use the existing sync SQLAlchemy engine and wrap `session.commit()` in `to_thread`.
- Pros: No new dependencies.
- Cons: Thread overhead.
- Effort: Low

**Approach B: Async SQLAlchemy with `aiosqlite`**
Update `pyproject.toml` to include `aiosqlite` and use `create_async_engine`.
- Pros: Native async, better scaling, idiomatic.
- Cons: Requires changing dependencies.
- Effort: Medium

### Recommendation
- **Scoring**: Use **Approach B** (Regex extraction). Small models are unreliable with JSON unless using format enforcers (which Ollama API might support, but `OllamaProvider` doesn't currently expose formatting flags). We will prompt the model for `SCORE: X.X`.
- **Episodic**: Use **Approach A** (`to_thread` for LanceDB). LanceDB is very fast for local storage, and thread delegation is safe enough for zero-latency requirement. Re-rank in Python to apply the decay factor.
- **Persistent**: Use **Approach B** (Async SQLAlchemy with `aiosqlite`). It is the standard way to do async SQLite in Python. We will add `aiosqlite` to `pyproject.toml`.
- **Engine**: The `persist_async` will wrap all these in an `async def`. The CLI or router will call `asyncio.create_task(engine.persist_async(episode))`.

### Risks
- **Zero-Latency Violation**: Any forgotten `await` on a synchronous function (like `session.commit()`) without `to_thread` or an async driver will block the main loop.
- **Model Hallucination**: The 1B Llama model might give a score outside 0.0-1.0 or fail to follow the prompt. We need a fallback score (e.g., 0.5) if parsing fails.
- **Vector Dimension Mismatch**: We must ensure LanceDB schema dimension matches what `OllamaProvider.embed()` returns.

### Ready for Proposal
Yes. The orchestrator should now proceed to the proposal/design phase with these recommendations.
