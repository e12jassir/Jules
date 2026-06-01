"""
Test de integración DD4 — flujo completo de memoria.

Valida que un episodio persiste en SQLite + LanceDB y se recupera
correctamente después de reiniciar el MemoryEngine (simulando un reinicio real).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from jules.memory.engine import MemoryEngine
from jules.memory.episodic import EpisodicMemory
from jules.memory.models import Base, Episode, SessionContext
from jules.memory.persistent import PersistentMemory
from jules.memory.scoring import ScoringHealthMonitor


def make_episode(episode_id: str) -> Episode:
    return Episode(
        id=episode_id,
        timestamp=datetime.now(timezone.utc),
        context=SessionContext(
            project="Jules",
            directory="/home/e12jassir/proyects/Jules",
            active_files=["jules/memory/engine.py"],
            inferred_intent="debugging",
            time_of_day="night",
        ),
        problem="asyncio.CancelledError no propagaba el score real al persistir",
        process="Mover evaluate_importance antes del delay de espera",
        solution="Scoring corre primero; CancelledError usa score ya calculado",
        duration_seconds=45,
        friction_score=0.6,
        tags=["memory", "async", "scoring"],
    )


def build_engine(
    db_url: str,
    lancedb_path: str,
    scoring_provider: AsyncMock,
    vector_dimension: int = 3,
) -> MemoryEngine:
    persistent = PersistentMemory(db_url)
    episodic = EpisodicMemory(db_path=lancedb_path, vector_dimension=vector_dimension)

    embedding_mock = AsyncMock()
    embedding_mock.embed = AsyncMock(return_value=[0.1, 0.5, 0.9])

    return MemoryEngine(
        persistent=persistent,
        episodic=episodic,
        provider=scoring_provider,
        scoring_health_monitor=ScoringHealthMonitor(),
        embedding_provider=embedding_mock,
    )


async def _init_db(engine: MemoryEngine) -> None:
    async with engine.persistent.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_episode_persists_and_survives_engine_restart(tmp_path):
    """
    Flujo completo:
    1. Crear engine, persistir episodio
    2. Destruir engine (simula reinicio)
    3. Crear nuevo engine con los mismos stores
    4. Recuperar episodio — debe existir con score correcto
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path}/memory.sqlite3"
    lancedb_path = str(tmp_path / "vectors")
    episode_id = f"test-{uuid.uuid4().hex[:8]}"
    episode = make_episode(episode_id)

    scoring_provider = AsyncMock()
    scoring_provider.generate_text = AsyncMock(return_value="Importante fix de async. SCORE: 0.8")

    # ── Fase 1: persistir ────────────────────────────────────────────────────
    engine = build_engine(db_url, lancedb_path, scoring_provider)
    await _init_db(engine)
    engine.persistence_delay_seconds = 0.0

    await engine.persist_async(episode)

    # Esperar a que el pipeline background termine
    import asyncio
    for _ in range(20):
        if not engine._background_tasks:
            break
        await asyncio.sleep(0.1)

    # ── Fase 2: reiniciar engine ─────────────────────────────────────────────
    await engine.persistent.engine.dispose()
    del engine

    # ── Fase 3: recuperar desde stores frescos ───────────────────────────────
    new_engine = build_engine(db_url, lancedb_path, scoring_provider)

    fetched = await new_engine.persistent.get_async(episode_id)

    assert fetched is not None, "El episodio no se encontró en SQLite tras reinicio"
    assert fetched.id == episode_id
    assert fetched.importance == pytest.approx(0.8)
    assert fetched.problem == episode.problem
    assert fetched.solution == episode.solution

    await new_engine.persistent.engine.dispose()


async def test_retrieve_returns_persisted_episode(tmp_path):
    """
    Valida que retrieve_async devuelve el episodio correcto
    usando el embedding mock para la búsqueda.
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path}/memory.sqlite3"
    lancedb_path = str(tmp_path / "vectors")
    episode_id = f"test-{uuid.uuid4().hex[:8]}"
    episode = make_episode(episode_id)

    scoring_provider = AsyncMock()
    scoring_provider.generate_text = AsyncMock(return_value="SCORE: 0.7")

    engine = build_engine(db_url, lancedb_path, scoring_provider)
    await _init_db(engine)
    engine.persistence_delay_seconds = 0.0

    await engine.persist_async(episode)

    import asyncio
    for _ in range(20):
        if not engine._background_tasks:
            break
        await asyncio.sleep(0.1)

    results = await engine.retrieve_async("async scoring bug", limit=5)

    assert any(ep.id == episode_id for ep in results), (
        f"Episodio {episode_id} no apareció en retrieve_async"
    )

    await engine.persistent.engine.dispose()
