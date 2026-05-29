from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from jules.memory.episodic import EpisodicMemory
from jules.memory.models import Episode, SessionContext


@pytest.fixture
async def temp_episodic(tmp_path):
    yield EpisodicMemory(db_path=str(tmp_path))


def test_init_defers_lancedb_connection(tmp_path, monkeypatch):
    connect = Mock()
    monkeypatch.setattr("jules.memory.episodic.lancedb.connect", connect)

    memory = EpisodicMemory(db_path=str(tmp_path))

    assert memory._table is None
    connect.assert_not_called()


def make_episode(episode_id: str, timestamp: datetime) -> Episode:
    return Episode(
        id=episode_id,
        timestamp=timestamp,
        context=SessionContext(
            project="Jules",
            directory="/home/e12jassir/proyects/Jules",
            active_files=["jules/memory/episodic.py"],
            inferred_intent="implementation",
            time_of_day="night",
        ),
        problem="Store episodic memory vectors",
        process="Persist vector rows in LanceDB",
        solution="Retrieve relevant episode IDs asynchronously",
        duration_seconds=60,
        friction_score=0.1,
        tags=["memory", "vector"],
    )


async def test_store_and_retrieve_async(temp_episodic):
    episode = make_episode("episode-relevant", datetime.now(timezone.utc))

    await temp_episodic.store_async(episode, [1.0, 0.0, 0.0])

    result = await temp_episodic.retrieve_async([1.0, 0.0, 0.0], limit=1)

    assert result == ["episode-relevant"]


async def test_time_decay_logic(temp_episodic):
    old_episode = make_episode("old", datetime.now(timezone.utc) - timedelta(days=365))
    recent_episode = make_episode("recent", datetime.now(timezone.utc))
    vector = [0.2, 0.4, 0.6]

    await temp_episodic.store_async(old_episode, vector)
    await temp_episodic.store_async(recent_episode, vector)

    result = await temp_episodic.retrieve_async(vector, limit=2)

    assert result[0] == "recent"


async def test_store_and_retrieve_use_thread_offloading(temp_episodic, monkeypatch):
    calls = []

    async def fake_to_thread(func, *args):
        calls.append(func.__name__)
        return func(*args)

    monkeypatch.setattr("jules.memory.episodic.asyncio.to_thread", fake_to_thread)
    episode = make_episode("threaded", datetime.now(timezone.utc))

    await temp_episodic.store_async(episode, [0.0, 1.0, 0.0])
    result = await temp_episodic.retrieve_async([0.0, 1.0, 0.0], limit=1)

    assert result == ["threaded"]
    assert calls == ["_store", "_retrieve"]
