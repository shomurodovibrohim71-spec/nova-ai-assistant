"""Quick offline smoke test — exercises the orchestrator without spinning up the server."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Fix Windows console encoding so emoji don't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

from core.config import settings
from core.llm import LLMRouter
from core.memory import MemoryService
from core.orchestrator import EventBus, Orchestrator
from core.skills import SkillRegistry
from core.skills.builtins import load_builtin_skills


async def main() -> None:
    bus = EventBus()
    registry = SkillRegistry()
    memory = MemoryService(settings)
    load_builtin_skills(registry, memory=memory)
    llm = LLMRouter(registry, bus, memory=memory)
    orch = Orchestrator(registry, bus, llm=llm, memory=memory)

    fast_path = ["hello", "system status", "open notepad"]
    for cmd in fast_path:
        result = await orch.handle_text(cmd, source="smoke")
        print(f"> {cmd}\n  {result}\n")

    print("--- Memory fast path ---")
    for cmd in [
        "remember that I drink coffee at 8am",
        "remember that my favorite editor is VS Code",
        "what do you remember about coffee",
    ]:
        result = await orch.handle_text(cmd, source="smoke")
        print(f"> {cmd}\n  {result.get('reply')}\n")

    print("structured facts on disk:", memory.structured.list_facts())
    print()

    # LLM-routed only if API key is present.
    if llm.available:
        print("--- LLM fallback ---")
        for cmd in [
            "what can you do for me?",
            "open chrome and then tell me how my system is doing",
        ]:
            print(f"> {cmd}")

            async def on_event(ev: dict) -> None:
                if ev["type"] == "sentence":
                    print(f"   . {ev['text']}")
                elif ev["type"] == "tool_use":
                    print(f"   [tool] {ev['name']}({ev['input']})")

            result = await orch.handle_text(cmd, source="smoke", on_event=on_event)
            print(f"   final: {result.get('reply')}\n")
    else:
        print("(skipping LLM tests — set ANTHROPIC_API_KEY to enable)")


if __name__ == "__main__":
    asyncio.run(main())
