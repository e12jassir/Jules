from datetime import datetime, timezone
from unittest.mock import AsyncMock

from jules.memory.models import Episode, SessionContext
from jules.memory.scoring import evaluate_importance


def make_episode() -> Episode:
    return Episode(
        id="episode-scoring",
        timestamp=datetime.now(timezone.utc),
        context=SessionContext(
            project="Jules",
            directory="/home/e12jassir/proyects/Jules",
            active_files=["jules/memory/scoring.py"],
            inferred_intent="implementation",
            time_of_day="night",
        ),
        problem="The user fixed an async persistence bug",
        process="Investigated the failing async flow",
        solution="Added awaited non-blocking persistence operations",
        duration_seconds=120,
        friction_score=0.3,
        tags=["memory", "scoring"],
    )


async def test_evaluate_importance_valid():
    provider = AsyncMock()
    provider.generate_text = AsyncMock(return_value="Useful fix for future incidents. SCORE: 0.9")

    score = await evaluate_importance(make_episode(), provider)

    assert score == 0.9


async def test_evaluate_importance_malformed():
    provider = AsyncMock()
    provider.generate_text = AsyncMock(return_value="El puntaje es ocho")

    score = await evaluate_importance(make_episode(), provider)

    assert score == 0.5


async def test_evaluate_importance_rejects_unescaped_decimal_separator():
    provider = AsyncMock()
    provider.generate_text = AsyncMock(return_value="Invalid decimal separator. SCORE: 0A9")

    score = await evaluate_importance(make_episode(), provider)

    assert score == 0.5


async def test_evaluate_importance_rejects_partial_one_decimal_match():
    provider = AsyncMock()
    provider.generate_text = AsyncMock(return_value="Out of range score. SCORE: 1.5")

    score = await evaluate_importance(make_episode(), provider)

    assert score == 0.5


async def test_evaluate_importance_provider_error():
    provider = AsyncMock()
    provider.generate_text = AsyncMock(side_effect=ConnectionError("provider offline"))

    score = await evaluate_importance(make_episode(), provider)

    assert score == 0.5
