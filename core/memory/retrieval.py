"""Hybrid memory retrieval: structured rows + semantic top-k, formatted for the system prompt."""
from __future__ import annotations

import asyncio
from typing import Any

from .semantic import SemanticMemory
from .structured import StructuredMemory


class MemoryRetrieval:
    def __init__(self, structured: StructuredMemory, semantic: SemanticMemory) -> None:
        self.structured = structured
        self.semantic = semantic

    async def assemble(self, query: str, k: int = 5) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        facts = await loop.run_in_executor(None, self.structured.list_facts)
        prefs = await loop.run_in_executor(None, self.structured.list_prefs)
        shortcuts = await loop.run_in_executor(None, self.structured.list_shortcuts)
        try:
            hits = await loop.run_in_executor(None, lambda: self.semantic.query(query, k))
        except Exception:
            hits = []

        text = self._format(facts, prefs, shortcuts, hits)
        items = [
            *({"src": "fact", **f} for f in facts),
            *({"src": "pref", **p} for p in prefs),
            *({"src": "semantic", **h} for h in hits),
        ]
        return {"text": text, "items": items}

    @staticmethod
    def _format(
        facts: list[dict[str, Any]],
        prefs: list[dict[str, Any]],
        shortcuts: list[dict[str, Any]],
        hits: list[dict[str, Any]],
    ) -> str:
        if not (facts or prefs or shortcuts or hits):
            return ""
        parts: list[str] = []
        if facts:
            parts.append("## What you know about the user")
            for f in facts[:25]:
                parts.append(f"- ({f['category']}) {f['content']}")
        if prefs:
            parts.append("\n## Preferences")
            for p in prefs:
                parts.append(f"- {p['key']}: {p['value']}")
        if shortcuts:
            parts.append("\n## App shortcuts")
            for s in shortcuts:
                parts.append(f"- '{s['alias']}' -> {', '.join(s['apps'])}")
        if hits:
            parts.append("\n## Relevant past conversation")
            for h in hits:
                ts = (h.get("metadata") or {}).get("ts", "")
                parts.append(f"- [{ts}] {h['text']}")
        return "\n".join(parts)
