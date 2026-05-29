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
        self.persistence_delay_seconds: float = 5.0
        self.is_query_active: bool = False

    def _dummy_vector(self) -> list[float]:
        return [0.0] * self.episodic.vector_dimension

    async def _run_persistence_pipeline(self, episode: Episode) -> None:
        try:
            # Esperamos pacientemente mientras haya alguna consulta activa de usuario
            while self.is_query_active:
                await asyncio.sleep(0.2)

            # Damos un respiro para no colisionar con el chat interactivo
            if self.persistence_delay_seconds > 0:
                await asyncio.sleep(self.persistence_delay_seconds)

            # Doble check por si el usuario empezó a escribir en la ventana del respiro
            while self.is_query_active:
                await asyncio.sleep(0.2)

            episode.importance = await evaluate_importance(episode, self.provider)
            await self.episodic.store_async(episode, self._dummy_vector())
            await self.persistent.save_async(episode)
        except asyncio.CancelledError:
            # Si el pipeline es cancelado (por una nueva consulta del usuario),
            # persistimos de inmediato en background para asegurar soberanía de datos sin colisionar
            if episode.importance is None:
                episode.importance = 0.5
            async def quick_save():
                try:
                    await self.episodic.store_async(episode, self._dummy_vector())
                    await self.persistent.save_async(episode)
                except Exception as e:
                    logging.error("Failed to save cancelled episode: %s", e)
            asyncio.create_task(quick_save())
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

    async def retrieve_async(self, query: str, limit: int = 5) -> list[Episode]:
        _ = query
        ids = await self.episodic.retrieve_async(self._dummy_vector(), limit)
        return await self.persistent.get_many_async(ids)
