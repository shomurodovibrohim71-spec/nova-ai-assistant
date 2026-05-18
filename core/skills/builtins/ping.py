from typing import Any

from ..base import Skill


class PingSkill(Skill):
    name = "ping"
    description = "Liveness check. Replies with a friendly greeting."
    tool_description = "Confirm Nova is online and responsive."
    patterns = [r"^\s*(ping|hello|hi|hey)\s*[!.\?]*\s*$"]
    args_schema = {"type": "object", "properties": {}}

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return {"ok": True, "reply": "Online and listening, sir."}
