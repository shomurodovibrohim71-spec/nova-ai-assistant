import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import uuid4

log = logging.getLogger(__name__)

Handler = Callable[["Event"], Awaitable[None]]


@dataclass
class Event:
    topic: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: uuid4().hex)


class EventBus:
    """In-process async pub/sub. Replace with Redis pub/sub when scaling out."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subs[topic].append(handler)
        log.debug("subscribed handler to %s", topic)

    async def publish(self, event: Event) -> None:
        handlers = self._subs.get(event.topic, []) + self._subs.get("*", [])
        if not handlers:
            return
        await asyncio.gather(
            *(self._safe_call(h, event) for h in handlers), return_exceptions=False
        )

    @staticmethod
    async def _safe_call(handler: Handler, event: Event) -> None:
        try:
            await handler(event)
        except Exception:
            log.exception("handler error on topic %s", event.topic)
