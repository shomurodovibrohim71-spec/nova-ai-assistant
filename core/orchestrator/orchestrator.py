import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from ..skills.registry import SkillRegistry
from .event_bus import Event, EventBus

log = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class Orchestrator:
    """Routes user input.

    1. Try the deterministic regex fast path against registered skills.
    2. Fall back to the LLM router (Phase 3) — Claude can also call skills as tools.

    `on_event` lets callers (voice pipeline, WS endpoint) react to streamed
    events (sentence-chunked TTS, tool calls, memory recall/write).
    """

    def __init__(
        self,
        registry: SkillRegistry,
        bus: EventBus,
        llm: Any | None = None,
        memory: Any | None = None,
    ) -> None:
        self.registry = registry
        self.bus = bus
        self.llm = llm
        self.memory = memory

    async def handle_text(
        self,
        text: str,
        source: str = "user",
        on_event: EventCallback | None = None,
    ) -> dict[str, Any]:
        text_norm = text.strip()
        log.info("[%s] -> %s", source, text_norm)
        await self.bus.publish(Event("user.input", {"text": text_norm, "source": source}))

        skill, match = self._match_skill(text_norm)
        if skill is not None:
            try:
                reply = await skill.run(text_norm, match=match)
            except Exception as e:
                log.exception("skill %s failed", skill.name)
                reply = {"ok": False, "reply": f"Skill '{skill.name}' errored: {e}"}
            asyncio.ensure_future(self._record_turn(text_norm, reply.get("reply", ""), source))
            await self.bus.publish(Event("assistant.reply", {"reply": reply}))
            return reply

        # Fall back to LLM
        if self.llm is None or not getattr(self.llm, "available", False):
            reply = {
                "ok": False,
                "reply": "I can't reach my brain right now — set ANTHROPIC_API_KEY to enable conversation.",
            }
            await self.bus.publish(Event("assistant.reply", {"reply": reply}))
            return reply

        final_text = ""
        tool_calls: list[dict[str, Any]] = []
        async for event in self.llm.respond(text_norm):
            if on_event is not None:
                res = on_event(event)
                if hasattr(res, "__await__"):
                    await res  # type: ignore[func-returns-value]
            if event["type"] == "final":
                final_text = event["text"]
            elif event["type"] == "tool_use":
                tool_calls.append(event)
            elif event["type"] == "error":
                final_text = event["message"]

        reply = {"ok": bool(final_text), "reply": final_text, "tool_calls": tool_calls}
        await self.bus.publish(Event("assistant.reply", {"reply": reply}))
        return reply

    async def _record_turn(self, user_text: str, reply: str, source: str) -> None:
        """Persist fast-path turns to memory. LLM-routed turns are persisted by the router itself."""
        if self.memory is None or not reply:
            return
        try:
            await self.memory.write_turn(user_text, reply, source=source)
        except Exception:
            log.exception("fast-path memory write failed")

    def _match_skill(self, text: str):
        for skill in self.registry.all():
            for pat in skill.patterns:
                m = re.search(pat, text, flags=re.IGNORECASE)
                if m:
                    return skill, m
        return None, None
