"""Semantic memory backed by ChromaDB with the default ONNX MiniLM embedder."""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class SemanticMemory:
    def __init__(self, persist_path: str, collection_name: str = "nova_turns") -> None:
        self.persist_path = persist_path
        self.collection_name = collection_name
        self._collection: Any = None

    def _ensure(self) -> Any:
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
            from chromadb.utils import embedding_functions
        except ImportError as e:
            raise RuntimeError("chromadb not installed; run pip install -r requirements.txt") from e

        log.info("loading ChromaDB at %s (downloads embedder on first use)", self.persist_path)
        client = chromadb.PersistentClient(path=self.persist_path)
        embedder = embedding_functions.DefaultEmbeddingFunction()
        self._collection = client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=embedder,
        )
        log.info("semantic collection ready (%d docs)", self._collection.count())
        return self._collection

    def add_turn(self, turn_id: int, text: str, metadata: dict[str, Any]) -> None:
        col = self._ensure()
        col.add(ids=[str(turn_id)], documents=[text], metadatas=[metadata])

    def query(self, q: str, k: int = 5) -> list[dict[str, Any]]:
        # Disabled — ONNX embedding adds ~1-2s latency per request on CPU.
        return []

    def count(self) -> int:
        return self._ensure().count()
