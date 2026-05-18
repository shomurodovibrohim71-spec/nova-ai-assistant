"""Decides what to write where after each turn."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .semantic import SemanticMemory
from .working import WorkingMemory

log = logging.getLogger(__name__)


class MemoryCurator:
    def __init__(self, working: WorkingMemory, semantic: SemanticMemory) -> None:
        self.working = working
        self.semantic = semantic

    async def write_turn(
        self, user_text: str, assistant_text: str, source: str = "unknown"
    ) -> dict[str, int]:
        """Persist a (user, assistant) exchange. Returns {user_id, assistant_id}."""
        loop = asyncio.get_running_loop()
        user_id = await loop.run_in_executor(None, self.working.add_turn, "user", user_text, source)
        asst_id = 0
        if assistant_text:
            asst_id = await loop.run_in_executor(
                None, self.working.add_turn, "assistant", assistant_text, source
            )

        # Push to semantic memory — skip if the reply looks like a memory retrieval
        # (prevents infinite nesting of recall results inside semantic store).
        _is_recall = assistant_text.startswith("##") or "What you know about" in assistant_text[:60]
        _too_long = len(assistant_text) > 1200
        if not _is_recall:
            try:
                stored_reply = assistant_text[:800] if _too_long else assistant_text
                doc = f"User: {user_text}\nNova: {stored_reply}".strip()
                ts = datetime.now(timezone.utc).isoformat()
                await loop.run_in_executor(
                    None,
                    self.semantic.add_turn,
                    user_id,
                    doc,
                    {"ts": ts, "source": source, "user_turn_id": user_id, "asst_turn_id": asst_id},
                )
            except Exception:
                log.exception("semantic write failed (continuing)")

        return {"user_id": user_id, "assistant_id": asst_id}
