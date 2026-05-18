"""Telegram long-polling bot — receives messages and routes them through Nova."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
FILE_API = "https://api.telegram.org/file/bot{token}/{path}"


class TelegramBot:
    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator
        self.token = settings.telegram_bot_token
        self.allowed_chat_id = str(settings.telegram_chat_id or "")
        self._offset = 0
        self._running = False

    @property
    def available(self) -> bool:
        return bool(self.token and self.allowed_chat_id)

    def _url(self, method: str) -> str:
        return f"{TELEGRAM_API.format(token=self.token)}/{method}"

    async def start(self) -> None:
        if not self.available:
            log.warning("Telegram bot disabled — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
            return
        self._running = True
        log.info("Telegram bot started (chat_id=%s)", self.allowed_chat_id)
        asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False

    async def _poll_loop(self) -> None:
        async with httpx.AsyncClient(timeout=40) as client:
            while self._running:
                try:
                    updates = await self._get_updates(client)
                    for update in updates:
                        self._offset = update["update_id"] + 1
                        await self._handle_update(client, update)
                except asyncio.CancelledError:
                    break
                except Exception:
                    log.exception("Telegram poll error — retrying in 3s")
                    await asyncio.sleep(3)

    async def _get_updates(self, client: httpx.AsyncClient) -> list[dict]:
        resp = await client.get(
            self._url("getUpdates"),
            params={"offset": self._offset, "timeout": 30, "allowed_updates": '["message"]'},
        )
        data = resp.json()
        if not data.get("ok"):
            log.warning("getUpdates error: %s", data)
            return []
        return data.get("result", [])

    async def _handle_update(self, client: httpx.AsyncClient, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id = str(message.get("chat", {}).get("id", ""))

        # only respond to the configured owner chat
        if chat_id != self.allowed_chat_id:
            log.debug("ignored message from unknown chat %s", chat_id)
            return

        # voice / audio message → transcribe first
        voice = message.get("voice") or message.get("audio")
        if voice:
            text = await self._transcribe_voice(client, chat_id, voice)
            if not text:
                return
            # Strip the language tag for display, keep it in the text sent to Claude
            display = text.split("] ", 1)[-1] if text.startswith("[RESPOND") else text
            await self._send_message(client, chat_id, f"🎤 <i>{display}</i>")
        else:
            text = (message.get("text") or "").strip()

        if not text:
            return

        log.info("[telegram] -> %s", text)

        # Keep "typing..." visible while Nova processes
        typing_task = asyncio.create_task(self._keep_typing(client, chat_id))

        sentences: list[str] = []

        async def on_event(ev: dict) -> None:
            if ev["type"] == "sentence":
                sentences.append(ev["text"])

        result = await self.orchestrator.handle_text(text, source="telegram", on_event=on_event)
        typing_task.cancel()

        # Only Claude's natural language reply — no raw tool output
        reply = " ".join(sentences).strip() or result.get("reply", "") or "✅"

        await self._send_message(client, chat_id, reply)

    async def _transcribe_voice(
        self, client: httpx.AsyncClient, chat_id: str, voice: dict
    ) -> str:
        """Download a Telegram voice/audio message and transcribe it with Whisper."""
        file_id = voice.get("file_id", "")
        if not file_id:
            return ""

        # 1. Get file path from Telegram
        try:
            r = await client.get(self._url("getFile"), params={"file_id": file_id})
            file_path = r.json()["result"]["file_path"]
        except Exception as e:
            log.error("getFile failed: %s", e)
            await self._send_message(client, chat_id, "❌ Audio faylni yuklab bo'lmadi.")
            return ""

        # 2. Download the audio bytes
        download_url = FILE_API.format(token=self.token, path=file_path)
        try:
            audio_resp = await client.get(download_url, timeout=30)
            audio_bytes = audio_resp.content
        except Exception as e:
            log.error("audio download failed: %s", e)
            await self._send_message(client, chat_id, "❌ Audio yuklanmadi.")
            return ""

        # 3. Save to a temp file and transcribe
        suffix = "." + (file_path.split(".")[-1] if "." in file_path else "oga")
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name

            from ..voice.stt import WhisperSTT
            stt = WhisperSTT(model_size="base")
            text, detected_lang = await asyncio.to_thread(stt.transcribe_file, tmp_path)
            log.info("[telegram voice] transcribed: %r  lang=%s", text, detected_lang)
            # Return text with language tag so the orchestrator tells Claude which language to use
            lang_name = {"uz": "Uzbek", "en": "English", "ru": "Russian"}.get(detected_lang, "English")
            return f"[RESPOND IN {lang_name.upper()} ONLY] {text}"
        except Exception as e:
            log.error("transcription failed: %s", e)
            await self._send_message(client, chat_id, "❌ Audio tanib bo'lmadi. Qayta urinib ko'ring.")
            return ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def _keep_typing(self, client: httpx.AsyncClient, chat_id: str) -> None:
        """Send 'typing' action every 4s so the user sees activity while Nova processes."""
        try:
            while True:
                await client.post(
                    self._url("sendChatAction"),
                    json={"chat_id": chat_id, "action": "typing"},
                )
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    async def _send_message(self, client: httpx.AsyncClient, chat_id: str, text: str) -> None:
        # split long messages (Telegram limit: 4096 chars)
        for chunk in _split(text, 4000):
            try:
                await client.post(
                    self._url("sendMessage"),
                    json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"},
                )
            except Exception:
                log.exception("sendMessage failed")


def _fmt_input(inp: dict) -> str:
    parts = [f"{k}={str(v)[:30]}" for k, v in (inp or {}).items()]
    return ", ".join(parts[:3])


def _split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] if text else [""]
