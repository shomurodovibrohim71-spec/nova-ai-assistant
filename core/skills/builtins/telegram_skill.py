"""Telegram integration — send messages and files to your Telegram chat."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ...config import settings
from ...security import PathError, safe_resolve
from ..base import Skill

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _root() -> Path:
    return Path(settings.file_root).expanduser().resolve()


def _token() -> str | None:
    return settings.telegram_bot_token


def _chat() -> str | None:
    return settings.telegram_chat_id


class TelegramSendMessageSkill(Skill):
    name = "telegram_send_message"
    description = "Send a text message to your Telegram chat."
    tool_description = (
        "Send a text message to the owner's Telegram account via their personal bot."
    )
    patterns = [
        r"^\s*(?:send|telegram)\s+(?:message\s+)?['\"](?P<msg>.+?)['\"]\s*(?:to\s+telegram)?\s*[!.\?]*\s*$",
        r"^\s*telegram[:\s]+(?P<msg>.+?)\s*[!.\?]*\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Text to send."},
            "chat_id": {
                "type": "string",
                "description": "Optional override chat_id. Defaults to TELEGRAM_CHAT_ID.",
            },
        },
        "required": ["message"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        msg = match.group("msg").strip() if match else text.strip()
        return await self.run_tool({"message": msg})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        token = _token()
        chat_id = args.get("chat_id") or _chat()
        if not token:
            return {"ok": False, "reply": "TELEGRAM_BOT_TOKEN not set in .env"}
        if not chat_id:
            return {"ok": False, "reply": "TELEGRAM_CHAT_ID not set in .env"}
        message = (args.get("message") or "").strip()
        if not message:
            return {"ok": False, "reply": "Nothing to send."}

        import httpx

        url = f"{TELEGRAM_API.format(token=token)}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"})
            data = resp.json()
            if not data.get("ok"):
                return {"ok": False, "reply": f"Telegram error: {data.get('description', resp.text)}"}
        except Exception as e:
            return {"ok": False, "reply": f"Telegram request failed: {e}"}

        return {"ok": True, "reply": f"Sent to Telegram: \"{message[:60]}{'…' if len(message)>60 else ''}\""}


class TelegramSendFileSkill(Skill):
    name = "telegram_send_file"
    description = "Send a file to your Telegram chat."
    tool_description = (
        "Upload and send a file (document, image, PDF, etc.) to the owner's Telegram account."
    )
    patterns = [
        r"^\s*(?:send|yubor)\s+(?P<path>[\w\\/:\.\- ]+?)\s+(?:to\s+)?telegram\s*[!.\?]*\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to send."},
            "caption": {"type": "string", "description": "Optional caption."},
            "chat_id": {"type": "string"},
        },
        "required": ["path"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        path = match.group("path").strip() if match else text.strip()
        return await self.run_tool({"path": path})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        token = _token()
        chat_id = args.get("chat_id") or _chat()
        if not token:
            return {"ok": False, "reply": "TELEGRAM_BOT_TOKEN not set in .env"}
        if not chat_id:
            return {"ok": False, "reply": "TELEGRAM_CHAT_ID not set in .env"}

        try:
            target = safe_resolve(args.get("path") or "", _root())
        except PathError as e:
            return {"ok": False, "reply": str(e)}
        if not target.exists() or not target.is_file():
            return {"ok": False, "reply": f"File not found: {target}"}

        caption = (args.get("caption") or "").strip()
        import httpx

        url = f"{TELEGRAM_API.format(token=token)}/sendDocument"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with target.open("rb") as fh:
                    resp = await client.post(
                        url,
                        data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                        files={"document": (target.name, fh)},
                    )
            data = resp.json()
            if not data.get("ok"):
                return {"ok": False, "reply": f"Telegram error: {data.get('description', resp.text)}"}
        except Exception as e:
            return {"ok": False, "reply": f"File send failed: {e}"}

        size_kb = target.stat().st_size // 1024
        return {"ok": True, "reply": f"Sent {target.name} ({size_kb} KB) to Telegram."}
