"""Claude-backed fallback brain with streaming, tool use, memory & prompt caching.

Public entry point: `LLMRouter.respond(text)` is an async generator yielding:
    {"type": "memory_recalled", "items": [...]}     # if memory present
    {"type": "text",     "delta": str}              # partial text token
    {"type": "sentence", "text": str}               # one completed sentence
    {"type": "tool_use", "name": str, "input": dict}
    {"type": "tool_result", "name": str, "ok": bool, "data": dict}
    {"type": "memory_written", "kind": "turn", "ids": {...}}
    {"type": "final",    "text": str, "model": str, "usage": dict}
    {"type": "error",    "message": str}
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ..config import settings
from ..memory import MemoryService
from ..orchestrator.event_bus import Event, EventBus
from ..skills.registry import SkillRegistry
from .client import AnthropicClient
from .sentence_stream import SentenceBuffer
from .tools import build_tools, execute_tool

log = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5
HISTORY_TURNS = 6


class LLMRouter:
    def __init__(
        self,
        registry: SkillRegistry,
        bus: EventBus,
        client: AnthropicClient | None = None,
        memory: MemoryService | None = None,
    ) -> None:
        self.registry = registry
        self.bus = bus
        self.client = client or AnthropicClient()
        self.memory = memory
        self._history: list[dict[str, Any]] = []
        self._persona = self._load_system_prompt()

    @property
    def available(self) -> bool:
        return self.client.available

    def _load_system_prompt(self) -> str:
        path = Path(settings.system_prompt_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            log.warning("system prompt not found at %s; using default", path)
            return "You are Nova, a calm, intelligent voice-first AI assistant."

    async def respond(self, user_text: str) -> AsyncIterator[dict[str, Any]]:
        if not self.client.available:
            yield {"type": "error", "message": "ANTHROPIC_API_KEY not set"}
            return

        try:
            client = self.client.get()
        except Exception as e:
            yield {"type": "error", "message": str(e)}
            return

        # --- Opus trigger detection ---
        chosen_model, user_text = self._route_model(user_text)

        # --- Memory recall ---
        memory_text = ""
        if self.memory is not None:
            try:
                ctx = await self.memory.assemble_context(user_text)
                memory_text = ctx["text"]
                if ctx["items"]:
                    yield {"type": "memory_recalled", "items": ctx["items"]}
                    await self.bus.publish(Event("memory.recalled", {"count": len(ctx["items"])}))
            except Exception:
                log.exception("memory recall failed (continuing)")

        system_blocks = self._build_system(memory_text)
        tools = build_tools(self.registry)
        self._sanitize_history()
        self._history.append({"role": "user", "content": user_text})

        full_text_parts: list[str] = []
        sentence_buf = SentenceBuffer()
        usage: dict[str, Any] = {}

        for _iteration in range(MAX_TOOL_ITERATIONS):
            assistant_blocks: list[dict[str, Any]] = []
            tool_uses: list[dict[str, Any]] = []
            stop_reason: str | None = None

            try:
                async with client.messages.stream(
                    model=chosen_model,
                    max_tokens=settings.max_tokens,
                    system=system_blocks,
                    tools=tools,
                    messages=self._history,
                ) as stream:
                    async for event in stream:
                        async for out in self._handle_stream_event(
                            event, sentence_buf, full_text_parts
                        ):
                            yield out
                    final = await stream.get_final_message()
            except Exception as e:
                log.warning("LLM stream failed: %s", e)
                # history buzilgan bo'lishi mumkin — tozalab qayta urinib ko'r
                self._history = []
                try:
                    async with client.messages.stream(
                        model=chosen_model,
                        max_tokens=settings.max_tokens,
                        system=system_blocks,
                        tools=tools,
                        messages=[{"role": "user", "content": user_text}],
                    ) as stream:
                        async for event in stream:
                            async for out in self._handle_stream_event(
                                event, sentence_buf, full_text_parts
                            ):
                                yield out
                        final = await stream.get_final_message()
                except Exception as e2:
                    log.warning("LLM retry also failed: %s", e2)
                    yield {"type": "error", "message": self._friendly_error(e2)}
                    return

            stop_reason = final.stop_reason
            try:
                u = final.usage
                usage = {
                    "input_tokens": getattr(u, "input_tokens", 0),
                    "output_tokens": getattr(u, "output_tokens", 0),
                    "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                    "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
                }
                if usage["cache_read_input_tokens"]:
                    log.info("cache hit: %d tokens", usage["cache_read_input_tokens"])
            except Exception:
                pass

            for block in final.content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif btype == "tool_use":
                    tu = {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input or {},
                    }
                    assistant_blocks.append(tu)
                    tool_uses.append(tu)

            self._history.append({"role": "assistant", "content": assistant_blocks})

            if stop_reason != "tool_use" or not tool_uses:
                break

            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                yield {"type": "tool_use", "name": tu["name"], "input": tu["input"]}
                await self.bus.publish(
                    Event("llm.tool_use", {"name": tu["name"], "input": tu["input"]})
                )
                result = await execute_tool(self.registry, tu["name"], tu["input"])
                yield {
                    "type": "tool_result",
                    "name": tu["name"],
                    "ok": result.get("ok", False),
                    "data": result,
                }
                await self.bus.publish(
                    Event("llm.tool_result", {"name": tu["name"], "result": result})
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": _format_tool_result(result),
                    }
                )

            self._history.append({"role": "user", "content": tool_results})
        else:
            log.warning("hit MAX_TOOL_ITERATIONS")

        for s in sentence_buf.finalize():
            yield {"type": "sentence", "text": s}

        full_reply = "".join(full_text_parts).strip()

        # --- Memory write-back (fire-and-forget — don't block the response) ---
        if self.memory is not None and full_reply:
            asyncio.ensure_future(self._write_turn_bg(user_text, full_reply))

        yield {"type": "final", "text": full_reply, "model": chosen_model, "usage": usage}
        self._strip_tool_messages()
        self._trim_history()

    # ---------- helpers ----------

    def _route_model(self, text: str) -> tuple[str, str]:
        """Return (chosen_model, possibly-stripped-text). Opus is chosen if a trigger phrase is present."""
        lowered = text.lower()
        for trig in settings.opus_triggers:
            if trig.lower() in lowered:
                stripped = re.sub(re.escape(trig), "", text, count=1, flags=re.IGNORECASE).strip()
                stripped = re.sub(r"\s{2,}", " ", stripped) or text
                log.info("Opus escalation triggered by %r", trig)
                return settings.hard_model, stripped
        return settings.model, text

    def _build_system(self, memory_text: str) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = [{"type": "text", "text": self._persona}]
        if memory_text:
            # Cache the (potentially long) memory block. Cache hits require ≥1024 tokens
            # in that block; small contexts won't actually cache, which is fine — once
            # memory grows organically, hits start landing.
            blocks.append(
                {
                    "type": "text",
                    "text": "## Persistent memory\n\n" + memory_text,
                    "cache_control": {"type": "ephemeral"},
                }
            )
        return blocks

    async def _handle_stream_event(
        self,
        event: Any,
        sentence_buf: SentenceBuffer,
        full_text_parts: list[str],
    ) -> AsyncIterator[dict[str, Any]]:
        etype = getattr(event, "type", None)
        if etype == "content_block_delta":
            delta = getattr(event, "delta", None)
            dtype = getattr(delta, "type", None)
            if dtype == "text_delta":
                txt = getattr(delta, "text", "") or ""
                if txt:
                    full_text_parts.append(txt)
                    yield {"type": "text", "delta": txt}
                    for s in sentence_buf.feed(txt):
                        yield {"type": "sentence", "text": s}

    @staticmethod
    def _friendly_error(e: Exception) -> str:
        try:
            from anthropic import APIConnectionError, AuthenticationError, RateLimitError
        except ImportError:
            return "I can't reach my brain right now."
        if isinstance(e, AuthenticationError):
            return "My API key looks wrong, sir — please check ANTHROPIC_API_KEY in .env."
        if isinstance(e, RateLimitError):
            return "I'm being rate-limited. Try again in a moment."
        if isinstance(e, APIConnectionError):
            return "I can't reach Anthropic — check your internet connection."
        return "I can't reach my brain right now."

    def _strip_tool_messages(self) -> None:
        """After each turn remove tool_use/tool_result messages from history.
        Keeps only plain user text and assistant text blocks.
        This prevents history format errors on the next call."""
        cleaned = []
        for msg in self._history:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user" and isinstance(content, str):
                cleaned.append(msg)
            elif role == "assistant" and isinstance(content, list):
                text_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
                if text_blocks:
                    cleaned.append({"role": "assistant", "content": text_blocks})
        self._history = cleaned

    def _sanitize_history(self) -> None:
        """Remove orphaned tool_use blocks that would cause a 400 from Anthropic."""
        if not _has_orphaned_tool_use(self._history):
            return
        log.warning("orphaned tool_use in history — clearing conversation")
        self._history = []

    def _trim_history(self) -> None:
        msgs = self._history
        keep = HISTORY_TURNS * 2
        if len(msgs) <= keep:
            return
        cut = len(msgs) - keep
        while cut < len(msgs) and msgs[cut]["role"] != "user":
            cut += 1
        self._history = msgs[cut:]

    async def _write_turn_bg(self, user_text: str, reply: str) -> None:
        try:
            ids = await self.memory.write_turn(user_text, reply, source="llm")
            await self.bus.publish(Event("memory.written", {"kind": "turn", "ids": ids}))
        except Exception:
            log.exception("memory write failed")


def _has_orphaned_tool_use(messages: list[dict]) -> bool:
    """Return True if the history has any tool_use/tool_result mismatch."""
    for i, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue

        if role == "assistant":
            # assistant tool_use must be followed by user tool_result
            has_tool_use = any(
                isinstance(b, dict) and b.get("type") == "tool_use" for b in content
            )
            if not has_tool_use:
                continue
            next_msg = messages[i + 1] if i + 1 < len(messages) else None
            if next_msg is None or next_msg.get("role") != "user":
                return True
            next_content = next_msg.get("content", [])
            if not isinstance(next_content, list):
                return True
            if not any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in next_content
            ):
                return True

        if role == "user":
            # user tool_result must be preceded by assistant tool_use with matching id
            tool_results = [
                b for b in content
                if isinstance(b, dict) and b.get("type") == "tool_result"
            ]
            if not tool_results:
                continue
            prev_msg = messages[i - 1] if i > 0 else None
            if prev_msg is None or prev_msg.get("role") != "assistant":
                return True
            prev_content = prev_msg.get("content", [])
            if not isinstance(prev_content, list):
                return True
            prev_ids = {
                b.get("id") for b in prev_content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            }
            for tr in tool_results:
                if tr.get("tool_use_id") not in prev_ids:
                    return True

    return False


def _format_tool_result(result: dict[str, Any]) -> str:
    """Build the tool_result content string sent back to Claude.

    For skills that return rich data (file content, search results, entries…)
    we pass the full payload so Claude can reference it.  For simple
    ok/reply-only results the reply text is enough.
    """
    parts: list[str] = []
    if result.get("reply"):
        parts.append(result["reply"])
    # file content
    if result.get("content"):
        parts.append(f"\n--- file content ---\n{result['content']}")
    # web_fetch page text
    if result.get("text"):
        parts.append(f"\n--- page content ---\n{result['text'][:4000]}")
    # search results
    if result.get("results"):
        for r in result["results"][:5]:
            parts.append(f"• {r.get('title','')} — {r.get('url','')}\n  {r.get('snippet','')[:200]}")
    # directory entries
    if result.get("entries"):
        names = [e["name"] + ("/" if e["kind"] == "dir" else "") for e in result["entries"][:30]]
        parts.append("Contents: " + ", ".join(names))
    # file search matches
    if result.get("matches"):
        parts.append("Matches:\n" + "\n".join(result["matches"][:20]))
    return "\n".join(parts) or str(result)
