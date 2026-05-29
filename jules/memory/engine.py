import asyncio
import logging

from jules.memory.episodic import EpisodicMemory
from jules.memory.models import Episode
from jules.memory.persistent import PersistentMemory
from jules.memory.scoring import TextGenerationProvider, evaluate_importance

class MemoryEngine:
    def __init__(
        self,
        persistent: PersistentMemory,
        episodic: EpisodicMemory,
        provider: TextGenerationProvider,
    ) -> None:
        self.persistent = persistent
        self.episodic = episodic
        self.provider = provider
        self._background_tasks: set[asyncio.Task] = set()

    def _dummy_vector(self) -> list[float]:
        return [0.0] * self.episodic.vector_dimension

    async def _run_persistence_pipeline(self, episode: Episode) -> None:
        try:
            episode.importance = await evaluate_importance(episode, self.provider)
            await self.episodic.store_async(episode, self._dummy_vector())
            await self.persistent.save_async(episode)
        except Exception as error:
            logging.error("Memory persistence pipeline failed: %s", error)

    async def persist_async(self, episode: Episode) -> None:
        task = asyncio.create_task(self._run_persistence_pipeline(episode))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def retrieve_async(self, query: str, limit: int = 5) -> list[Episode]:
        _ = query
        ids = await self.episodic.retrieve_async(self._dummy_vector(), limit)
        return await self.persistent.get_many_async(ids)
