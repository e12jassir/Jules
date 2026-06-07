import asyncio
import logging
from typing import Protocol

from jules.memory.episodic import EpisodicMemory
from jules.memory.models import Episode
from jules.memory.persistent import PersistentMemory
from jules.memory.scoring import ScoringHealthMonitor, TextGenerationProvider, evaluate_importance

IMPORTANCE_PERSISTENCE_THRESHOLD = 0.3
CONSERVATIVE_FRICTION_THRESHOLD = 0.5
ACTIVE_PROJECT_TAGS = frozenset({"active_project", "project_active", "current_project"})
logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class MemoryEngine:
    def __init__(
        self,
        persistent: PersistentMemory,
        episodic: EpisodicMemory,
        provider: TextGenerationProvider,
        scoring_health_monitor: ScoringHealthMonitor | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.persistent = persistent
        self.episodic = episodic
        self.provider = provider
        self.embedding_provider = embedding_provider
        self.scoring_health_monitor = scoring_health_monitor or ScoringHealthMonitor()
        self._background_tasks: set[asyncio.Task] = set()
        self.persistence_delay_seconds: float = 5.0
        self.is_query_active: bool = False

    def _dummy_vector(self) -> list[float]:
        # Fallback cuando embedding_provider no está disponible.
        # Dimensión: 2048 (llama3.2:1b). Retrieval será temporal, no semántico.
        return [0.0] * self.episodic.vector_dimension

    async def _get_vector(self, text: str) -> list[float]:
        if self.embedding_provider is not None:
            try:
                return await self.embedding_provider.embed(text)
            except Exception as exc:
                logger.warning("Embedding falló, usando vector dummy: %s", exc)
        return self._dummy_vector()

    async def _persist_episode(self, episode: Episode) -> None:
        # SQLite es la fuente de verdad. LanceDB es el índice reconstruible.
        # Guardamos SQLite primero; si LanceDB falla, el episodio no se pierde.
        await self.persistent.save_async(episode)
        text = f"{episode.problem or ''} {episode.solution or ''}".strip()
        vector = await self._get_vector(text)
        await self.episodic.store_async(episode, vector)

    def _has_active_project_tag(self, episode: Episode) -> bool:
        return any(tag in ACTIVE_PROJECT_TAGS or tag.startswith("project:") for tag in episode.tags)

    def _should_persist_conservatively(self, episode: Episode) -> bool:
        return episode.friction_score > CONSERVATIVE_FRICTION_THRESHOLD or self._has_active_project_tag(episode)

    async def _persist_if_allowed(self, episode: Episode, record_health: bool = True) -> bool:
        score = episode.importance
        if record_health:
            self.scoring_health_monitor.record(score)
        if self.scoring_health_monitor.is_healthy():
            if score >= IMPORTANCE_PERSISTENCE_THRESHOLD:
                await self._persist_episode(episode)
                return True
            return False

        logger.warning("Scoring degenerado, modo conservador activado", extra={"mode": "conservative"})
        if self._should_persist_conservatively(episode):
            await self._persist_episode(episode)
            return True
        return False

    async def _run_persistence_pipeline(self, episode: Episode) -> None:
        try:
            # Scoring corre primero, antes del delay, para que si se cancela
            # el episodio ya tenga su score real (no el default 0.5).
            episode.importance = await evaluate_importance(episode, self.provider)
            self.scoring_health_monitor.record(episode.importance)

            # Esperamos mientras haya una consulta activa del usuario
            while self.is_query_active:
                await asyncio.sleep(0.2)

            if self.persistence_delay_seconds > 0:
                await asyncio.sleep(self.persistence_delay_seconds)

            while self.is_query_active:
                await asyncio.sleep(0.2)

            await self._persist_if_allowed(episode, record_health=False)
        except asyncio.CancelledError:
            # Score ya calculado arriba. Persistimos con el score real.
            async def quick_save():
                try:
                    await self._persist_if_allowed(episode, record_health=False)
                except Exception as e:
                    logging.error("Failed to save cancelled episode: %s", e)
            task = asyncio.create_task(quick_save())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            raise
        except Exception as error:
            logging.error("Memory persistence pipeline failed: %s", error)

    def start_active_query(self) -> None:
        self.is_query_active = True
        # Cancelamos cualquier pipeline en background activo para liberar al LLM local inmediatamente
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()

    async def persist_async(self, episode: Episode) -> None:
        task = asyncio.create_task(self._run_persistence_pipeline(episode))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def persist_and_wait_async(self, episode: Episode) -> bool:
        """Run the scored persistence pipeline and return whether storage happened."""
        episode.importance = await evaluate_importance(episode, self.provider)
        self.scoring_health_monitor.record(episode.importance)
        while self.is_query_active:
            await asyncio.sleep(0.2)
        if self.persistence_delay_seconds > 0:
            await asyncio.sleep(self.persistence_delay_seconds)
        while self.is_query_active:
            await asyncio.sleep(0.2)
        return await self._persist_if_allowed(episode, record_health=False)

    async def retrieve_async(self, query: str, limit: int = 5) -> list[Episode]:
        vector = await self._get_vector(query)
        ids = await self.episodic.retrieve_async(vector, limit)
        return await self.persistent.get_many_async(ids)
