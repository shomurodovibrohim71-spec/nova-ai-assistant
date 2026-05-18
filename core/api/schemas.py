from typing import Any, Literal
from pydantic import BaseModel


class CommandRequest(BaseModel):
    text: str
    source: str = "rest"


class CommandResponse(BaseModel):
    ok: bool
    reply: str
    data: dict[str, Any] | None = None


class WSMessage(BaseModel):
    """JSON-RPC-ish envelope used over the WebSocket transport."""

    type: Literal["command", "event", "reply", "error", "ping", "pong"]
    id: str | None = None
    payload: dict[str, Any] = {}
