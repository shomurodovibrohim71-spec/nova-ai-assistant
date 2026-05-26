import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from ..config import settings
from ..llm import LLMRouter
from ..logging_setup import setup_logging
from ..memory import MemoryService
from ..orchestrator import EventBus, Orchestrator
from ..skills import SkillRegistry
from ..skills.builtins import load_builtin_skills
from ..telegram_bot import TelegramBot
from .schemas import CommandRequest, CommandResponse, WSMessage

log = logging.getLogger("nova")


def build_app() -> FastAPI:
    setup_logging()

    bus = EventBus()
    registry = SkillRegistry()
    memory = MemoryService(settings)
    load_builtin_skills(registry, memory=memory)
    llm = LLMRouter(registry, bus, memory=memory)
    orchestrator = Orchestrator(registry, bus, llm=llm, memory=memory)

    tg_bot = TelegramBot(orchestrator)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        brain = "Claude (online)" if llm.available else "fast-path only (no API key)"
        log.info("Nova online — %d skills, brain: %s", len(list(registry.all())), brain)
        await tg_bot.start()
        if tg_bot.available:
            log.info("Telegram bot listening on chat_id=%s", settings.telegram_chat_id)
        yield
        await tg_bot.stop()
        log.info("Nova shutting down")

    app = FastAPI(title="Nova Core", version="0.1.0", lifespan=lifespan)
    app.state.bus = bus
    app.state.registry = registry
    app.state.orchestrator = orchestrator

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "online", "version": "0.1.0"}

    @app.get("/skills")
    async def list_skills() -> list[dict[str, str]]:
        return [{"name": s.name, "description": s.description} for s in registry.all()]

    @app.get("/memory/facts")
    async def memory_facts() -> list[dict]:
        return memory.structured.list_facts()

    @app.delete("/memory/facts/{fact_id}")
    async def memory_delete(fact_id: int) -> dict[str, Any]:
        n = memory.structured.delete_fact(fact_id)
        return {"deleted": n}

    @app.get("/memory/recent")
    async def memory_recent(limit: int = 20) -> list[dict]:
        return memory.working.recent_turns(limit)

    @app.post("/command", response_model=CommandResponse)
    async def command(req: CommandRequest) -> CommandResponse:
        result = await orchestrator.handle_text(req.text, source=req.source)
        return CommandResponse(
            ok=result.get("ok", False),
            reply=result.get("reply", ""),
            data={k: v for k, v in result.items() if k not in {"ok", "reply"}} or None,
        )

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        log.info("ws client connected")
        try:
            while True:
                raw = await ws.receive_json()
                try:
                    msg = WSMessage(**raw)
                except Exception as e:
                    await ws.send_json(
                        WSMessage(type="error", payload={"error": str(e)}).model_dump()
                    )
                    continue

                if msg.type == "ping":
                    await ws.send_json(WSMessage(type="pong", id=msg.id).model_dump())
                    continue

                if msg.type == "command":
                    text = msg.payload.get("text", "")

                    async def stream_event(ev: dict) -> None:
                        await ws.send_json(
                            WSMessage(type="event", id=msg.id, payload=ev).model_dump()
                        )

                    result = await orchestrator.handle_text(
                        text, source="ws", on_event=stream_event
                    )
                    await ws.send_json(
                        WSMessage(type="reply", id=msg.id, payload=result).model_dump()
                    )
                    continue

                await ws.send_json(
                    WSMessage(
                        type="error",
                        id=msg.id,
                        payload={"error": f"unsupported type {msg.type!r}"},
                    ).model_dump()
                )
        except WebSocketDisconnect:
            log.info("ws client disconnected")

    return app


app = build_app()


def run() -> None:
    # Pass the app object directly (not string) to avoid re-importing the
    # module and running build_app() a second time (double skill init).
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
