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

    def _dummy_vector(self) -> list[float]:
        return [0.0] * self.episodic.vector_dimension

    async def _run_persistence_pipeline(self, episode: Episode) -> None:
        try:
            episode.importance = await evaluate_importance(episode, self.provider)
            await self.persistent.save_async(episode)
            await self.episodic.store_async(episode, self._dummy_vector())
        except Exception as error:
            logging.error("Memory persistence pipeline failed: %s", error)

    async def persist_async(self, episode: Episode) -> None:
        asyncio.create_task(self._run_persistence_pipeline(episode))

    async def retrieve_async(self, query: str, limit: int = 5) -> list[Episode]:
        _ = query
        ids = await self.episodic.retrieve_async(self._dummy_vector(), limit)
        episodes: list[Episode] = []
        for episode_id in ids:
            episode = await self.persistent.get_async(episode_id)
            if episode is not None:
                episodes.append(episode)
        return episodes
