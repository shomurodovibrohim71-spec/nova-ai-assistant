"""Skill <-> Anthropic tool schema bridge."""
from __future__ import annotations

import logging
from typing import Any

from ..skills.registry import SkillRegistry

log = logging.getLogger(__name__)

_DEFAULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"text": {"type": "string", "description": "Free-form input."}},
    "required": ["text"],
}


def build_tools(registry: SkillRegistry) -> list[dict[str, Any]]:
    """Render every registered skill as an Anthropic tool definition."""
    tools: list[dict[str, Any]] = []
    for skill in registry.all():
        tools.append(
            {
                "name": skill.name,
                "description": skill.tool_description or skill.description or skill.name,
                "input_schema": skill.args_schema or _DEFAULT_SCHEMA,
            }
        )
    return tools


async def execute_tool(
    registry: SkillRegistry, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    skill = registry.get(name)
    if skill is None:
        return {"ok": False, "reply": f"Unknown tool: {name}"}
    try:
        return await skill.run_tool(args)
    except Exception as e:
        log.exception("tool %s raised", name)
        return {"ok": False, "reply": f"Tool {name!r} errored: {e}"}
