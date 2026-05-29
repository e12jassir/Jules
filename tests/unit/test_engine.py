import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

from jules.memory.engine import MemoryEngine
from jules.memory.models import Episode, SessionContext


def make_episode() -> Episode:
    return Episode(
        id="episode-engine",
        timestamp=datetime.now(timezone.utc),
        context=SessionContext(
            project="Jules",
            directory="/home/e12jassir/proyects/Jules",
            active_files=["jules/memory/engine.py"],
            inferred_intent="implementation",
            time_of_day="night",
        ),
        problem="Persist memory without blocking the terminal",
        process="Move scoring and storage to a background task",
        solution="Schedule the persistence pipeline with asyncio.create_task",
        duration_seconds=30,
        friction_score=0.1,
        tags=["memory", "engine"],
    )


async def test_persist_async_is_zero_latency(monkeypatch):
    persistent = AsyncMock()
    episodic = AsyncMock()
    episodic.vector_dimension = 3
    provider = AsyncMock()
    engine = MemoryEngine(persistent=persistent, episodic=episodic, provider=provider)
    episode = make_episode()
    created_tasks = []
    original_create_task = asyncio.create_task

    async def slow_save(_: Episode) -> None:
        await asyncio.sleep(1)

    def tracking_create_task(coroutine):
        task = original_create_task(coroutine)
        created_tasks.append(task)
        return task

    persistent.save_async.side_effect = slow_save
    monkeypatch.setattr("jules.memory.engine.evaluate_importance", AsyncMock(return_value=0.8))
    monkeypatch.setattr("jules.memory.engine.asyncio.create_task", tracking_create_task)

    start = time.perf_counter()
    await engine.persist_async(episode)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.05
    assert len(created_tasks) == 1

    created_tasks[0].cancel()
    await asyncio.gather(*created_tasks, return_exceptions=True)


async def test_pipeline_handles_exceptions_silently(monkeypatch):
    persistent = AsyncMock()
    episodic = AsyncMock()
    episodic.vector_dimension = 3
    provider = AsyncMock()
    engine = MemoryEngine(persistent=persistent, episodic=episodic, provider=provider)
    episode = make_episode()
    persistent.save_async.side_effect = Exception("db exploded")
    error_logger = Mock()

    monkeypatch.setattr("jules.memory.engine.evaluate_importance", AsyncMock(return_value=0.4))
    monkeypatch.setattr("jules.memory.engine.logging.error", error_logger)

    await engine._run_persistence_pipeline(episode)

    error_logger.assert_called_once()


async def test_retrieve_async_filters_missing_episodes():
    persistent = AsyncMock()
    episodic = AsyncMock()
    episodic.vector_dimension = 3
    provider = AsyncMock()
    engine = MemoryEngine(persistent=persistent, episodic=episodic, provider=provider)
    first = make_episode()
    second = make_episode()
    second.id = "episode-engine-2"

    episodic.retrieve_async.return_value = [first.id, "missing", second.id]

    async def get_async_side_effect(episode_id: str):
        if episode_id == first.id:
            return first
        if episode_id == second.id:
            return second
        return None

    persistent.get_async.side_effect = get_async_side_effect

    episodes = await engine.retrieve_async("debug recent memory", limit=3)

    assert episodes == [first, second]
    episodic.retrieve_async.assert_awaited_once_with([0.0, 0.0, 0.0], 3)


async def test_engine_uses_episodic_vector_dimension(monkeypatch):
    persistent = AsyncMock()
    episodic = AsyncMock()
    episodic.vector_dimension = 5
    provider = AsyncMock()
    engine = MemoryEngine(persistent=persistent, episodic=episodic, provider=provider)
    episode = make_episode()

    monkeypatch.setattr("jules.memory.engine.evaluate_importance", AsyncMock(return_value=0.6))
    episodic.retrieve_async.return_value = []

    await engine._run_persistence_pipeline(episode)
    await engine.retrieve_async("memory query", limit=2)

    episodic.store_async.assert_awaited_once_with(episode, [0.0, 0.0, 0.0, 0.0, 0.0])
    episodic.retrieve_async.assert_awaited_once_with([0.0, 0.0, 0.0, 0.0, 0.0], 2)
