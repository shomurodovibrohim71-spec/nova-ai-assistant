"""Memory skills — also exposed to Claude as tools."""
from __future__ import annotations

import asyncio
from typing import Any

from ...memory import MemoryService
from ..base import Skill


class RememberSkill(Skill):
    name = "remember"
    description = "Remember a durable fact about the user."
    tool_description = (
        "Store a durable fact, preference, or shortcut about the user. "
        "Use for things like 'I drink coffee at 8am', 'My name is X', or 'I prefer dark mode'."
    )
    patterns = [r"^\s*remember(?:\s+that)?\s+(?P<content>.+?)\s*[!.\?]*\s*$"]
    args_schema = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["identity", "preference", "fact", "workflow"],
                "description": "Type of fact being stored.",
            },
            "content": {"type": "string", "description": "The fact itself, in one short sentence."},
        },
        "required": ["content"],
    }

    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        content = match.group("content").strip() if match else text.strip()
        return await self.run_tool({"category": "fact", "content": content})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        content = (args.get("content") or "").strip()
        if not content:
            return {"ok": False, "reply": "There's nothing for me to remember."}
        category = args.get("category") or "fact"
        fact_id = await asyncio.to_thread(
            self.memory.structured.remember_fact, category, content
        )
        return {"ok": True, "reply": "Noted.", "id": fact_id, "category": category}


class RecallSkill(Skill):
    name = "recall"
    description = "Recall what's known about a topic."
    tool_description = "Search Nova's memory (facts and past conversations) for a topic."
    patterns = [
        r"^\s*(?:what do you (?:know|remember) about|recall|do you remember)\s+(?P<query>.+?)\s*[!.\?]*\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Topic to search memory for."},
            "k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        query = match.group("query").strip() if match else text.strip()
        return await self.run_tool({"query": query})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        query = (args.get("query") or "").strip()
        if not query:
            return {"ok": False, "reply": "Tell me what to recall."}
        ctx = await self.memory.assemble_context(query, k=args.get("k") or 5)
        if not ctx["items"]:
            return {"ok": True, "reply": "I don't recall anything about that."}
        return {"ok": True, "reply": ctx["text"], "items": ctx["items"]}


class ForgetSkill(Skill):
    name = "forget"
    description = "Delete a remembered fact."
    tool_description = "Delete stored facts matching an id or a search query."
    patterns = [r"^\s*forget\s+(?P<query>.+?)\s*[!.\?]*\s*$"]
    args_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "query": {"type": "string"},
        },
    }

    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        query = match.group("query").strip() if match else text.strip()
        return await self.run_tool({"query": query})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        fact_id = args.get("id")
        if fact_id is not None:
            n = await asyncio.to_thread(self.memory.structured.delete_fact, int(fact_id))
            return {"ok": bool(n), "reply": f"Forgotten fact {fact_id}." if n else "No such fact."}
        query = (args.get("query") or "").strip()
        if not query:
            return {"ok": False, "reply": "Specify an id or a query."}
        matches = await asyncio.to_thread(self.memory.structured.search_facts, query)
        if not matches:
            return {"ok": False, "reply": "Nothing matched."}
        for f in matches:
            await asyncio.to_thread(self.memory.structured.delete_fact, f["id"])
        return {"ok": True, "reply": f"Forgotten {len(matches)} item(s)."}
