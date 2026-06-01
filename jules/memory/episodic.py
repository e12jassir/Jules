import asyncio
import threading
import time
from pathlib import Path
from typing import cast

import lancedb
import pyarrow as pa

from jules.memory.models import Episode

DEFAULT_TABLE_NAME = "episodes_vector"
DEFAULT_VECTOR_DIMENSION = 2048  # llama3.2:1b via Ollama /api/embed
TIME_DECAY_FACTOR = 1e-9


class EpisodicMemory:
    def __init__(
        self,
        db_path: str | Path,
        table_name: str = DEFAULT_TABLE_NAME,
        vector_dimension: int = DEFAULT_VECTOR_DIMENSION,
    ) -> None:
        self.db_path = str(db_path)
        self.table_name = table_name
        self.vector_dimension = vector_dimension
        self._table = None
        self._table_lock = threading.Lock()

    def _open_or_create_table(self):
        db = lancedb.connect(self.db_path)
        tables = db.list_tables()
        table_names = tables.tables if hasattr(tables, "tables") else list(tables)
        if self.table_name in table_names:
            return db.open_table(self.table_name)

        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), list_size=self.vector_dimension)),
                pa.field("timestamp_ts", pa.float64()),
            ]
        )
        return db.create_table(self.table_name, schema=schema)

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self.vector_dimension:
            raise ValueError(f"Vector dimension must be {self.vector_dimension}, got {len(vector)}")

    def _store(self, episode_id: str, vector: list[float], timestamp: float) -> None:
        self._validate_vector(vector)
        with self._table_lock:
            if self._table is None:
                self._table = self._open_or_create_table()
        self._table.add([{"id": episode_id, "vector": vector, "timestamp_ts": timestamp}])

    async def store_async(self, episode: Episode, vector: list[float]) -> None:
        await asyncio.to_thread(self._store, episode.id, vector, episode.timestamp.timestamp())

    def _retrieve(self, query_vector: list[float], limit: int) -> list[str]:
        self._validate_vector(query_vector)
        if limit <= 0:
            return []

        with self._table_lock:
            if self._table is None:
                self._table = self._open_or_create_table()

        now = time.time()
        results = self._table.search(query_vector).limit(limit * 2).to_list()
        ranked = sorted(
            results,
            key=lambda result: result["_distance"] + (now - result["timestamp_ts"]) * TIME_DECAY_FACTOR,
        )
        return [result["id"] for result in ranked[:limit]]

    async def retrieve_async(self, query_vector: list[float], limit: int = 5) -> list[str]:
        return await asyncio.to_thread(self._retrieve, query_vector, limit)
