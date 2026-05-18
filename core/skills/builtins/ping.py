from typing import Any
from ..base import Skill


class PingSkill(Skill):
    name = "ping"
    description = "Liveness check and simple acknowledgment handler."
    tool_description = "Confirm Nova is online and responsive."
    patterns = [
        # English greetings / liveness
        r"^\s*(ping|hello|hi|hey|yo)\s*[!.\?]*\s*$",
        # Uzbek/Russian greetings
        r"^\s*(salom|assalomu?\s*alaykum|salom)\s*[!.\?]*\s*$",
        # Simple acknowledgments — catch before LLM
        r"^\s*(ha|ok|okay|yaxshi|zo[''`]?r|rahmat|tashakkur|tushund[ium]+|tushunarli|bajarildi|qabul|understood|thanks?|great|perfect|nice|good)\s*[!.\?]*\s*$",
        # /start command
        r"^\s*/start\s*$",
    ]
    args_schema = {"type": "object", "properties": {}}

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        t = text.strip().lower().rstrip("!?.").strip()
        if t in ("/start", "ping"):
            return {"ok": True, "reply": "✅ Nova online — ayt nima kerak."}
        if t in ("salom", "assalomu alaykum", "assalomu aleykum", "salome"):
            return {"ok": True, "reply": "Salom! Nima kerak?"}
        if t in ("hello", "hi", "hey", "yo"):
            return {"ok": True, "reply": "Hey! What do you need?"}
        # acknowledgment
        return {"ok": True, "reply": "👍"}
