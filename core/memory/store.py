"""MemoryService: facade composing all three memory tiers."""
from __future__ import annotations

import logging
from typing import Any

from ..config import Settings, settings as default_settings
from .curator import MemoryCurator
from .db import Database
from .retrieval import MemoryRetrieval
from .semantic import SemanticMemory
from .structured import StructuredMemory
from .working import WorkingMemory

log = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self.settings.ensure_data_dir()
        self.db = Database(self.settings.db_path)
        self.working = WorkingMemory(self.db, max_recent=self.settings.memory_max_recent_turns)
        self.structured = StructuredMemory(self.db)
        self.semantic = SemanticMemory(self.settings.chroma_path)
        self.retrieval = MemoryRetrieval(self.structured, self.semantic)
        self.curator = MemoryCurator(self.working, self.semantic)
        log.info(
            "memory ready (db=%s, chroma=%s)",
            self.settings.db_path,
            self.settings.chroma_path,
        )

    async def assemble_context(self, query: str, k: int | None = None) -> dict[str, Any]:
        return await self.retrieval.assemble(query, k or self.settings.memory_top_k)

    async def write_turn(
        self, user_text: str, assistant_text: str, source: str = "unknown"
    ) -> dict[str, int]:
        return await self.curator.write_turn(user_text, assistant_text, source)
