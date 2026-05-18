from abc import ABC, abstractmethod
from typing import Any, ClassVar


class Skill(ABC):
    """Base class for all Nova capabilities.

    A skill declares regex patterns for the deterministic fast path AND an
    optional JSON Schema (`args_schema`) so the LLM can invoke it as a tool.
    """

    name: ClassVar[str] = "unnamed"
    description: ClassVar[str] = ""
    patterns: ClassVar[list[str]] = []
    requires_confirmation: ClassVar[bool] = False

    # LLM tool-use surface — defaults to a single free-text arg.
    args_schema: ClassVar[dict[str, Any] | None] = None
    tool_description: ClassVar[str | None] = None

    @abstractmethod
    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]: ...

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        """Entrypoint when the LLM calls this skill as a tool.

        Default behavior: build a synthetic text from args and reuse `run`.
        Skills with structured arguments should override this.
        """
        text = args.get("text") or " ".join(str(v) for v in args.values())
        return await self.run(text, match=None)
