"""Canva skill — list designs, export as image/PDF, create designs."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from ...config import settings
from ..base import Skill

_AUTH_URL = "https://www.canva.com/api/oauth/authorize"
_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
_API_BASE  = "https://api.canva.com/rest/v1"
_SCOPES    = "design:meta:read design:content:read design:content:write asset:read asset:write"


def _token_path() -> Path:
    return Path(settings.data_dir) / "canva_token.json"


def _load_token() -> dict:
    p = _token_path()
    if not p.exists():
        raise RuntimeError(
            "Canva ulanmagan. Avval: python scripts/setup_canva.py"
        )
    return json.loads(p.read_text())


def _save_token(data: dict) -> None:
    _token_path().write_text(json.dumps(data, indent=2))


def _refresh_token(token_data: dict) -> dict:
    import httpx

    cfg = settings
    resp = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
            "client_id": cfg.canva_client_id,
            "client_secret": cfg.canva_client_secret,
        },
        timeout=15,
    )
    resp.raise_for_status()
    new_data = resp.json()
    new_data.setdefault("refresh_token", token_data["refresh_token"])
    new_data["expires_at"] = time.time() + new_data.get("expires_in", 3600) - 60
    _save_token(new_data)
    return new_data


def _access_token() -> str:
    data = _load_token()
    if time.time() >= data.get("expires_at", 0):
        data = _refresh_token(data)
    return data["access_token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
    }


def _list_designs(query: str = "", limit: int = 10) -> list[dict]:
    import httpx

    params: dict = {"limit": limit}
    if query:
        params["query"] = query
    resp = httpx.get(f"{_API_BASE}/designs", headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("items", [])


def _get_design(design_id: str) -> dict:
    import httpx

    resp = httpx.get(f"{_API_BASE}/designs/{design_id}", headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json().get("design", {})


_PRESET_MAP = {
    "presentation": "presentation",
    "prezentatsiya": "presentation",
    "taqdimot": "presentation",
    "doc": "doc",
    "a4": "doc",
    "hujjat": "doc",
    "document": "doc",
    "email": "email",
    "whiteboard": "whiteboard",
    "doska": "whiteboard",
}


def _create_design(design_type: str = "presentation", title: str = "") -> dict:
    import httpx

    preset_name = _PRESET_MAP.get(design_type.lower(), "presentation")
    body: dict = {"design_type": {"type": "preset", "name": preset_name}}
    if title:
        body["title"] = title
    resp = httpx.post(f"{_API_BASE}/designs", headers=_headers(), json=body, timeout=15)
    resp.raise_for_status()
    return resp.json().get("design", {})


def _start_export(design_id: str, fmt: str = "png") -> str:
    import httpx

    fmt = fmt.lower()
    body: dict[str, Any] = {
        "design_id": design_id,
        "format": {"type": fmt},
    }
    resp = httpx.post(f"{_API_BASE}/exports", headers=_headers(), json=body, timeout=15)
    resp.raise_for_status()
    return resp.json()["job"]["id"]


def _poll_export(export_id: str, timeout: int = 60) -> list[str]:
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = httpx.get(f"{_API_BASE}/exports/{export_id}", headers=_headers(), timeout=15)
        resp.raise_for_status()
        job = resp.json().get("job", {})
        status = job.get("status")
        if status == "success":
            return [u["url"] for u in job.get("urls", [])]
        if status == "failed":
            raise RuntimeError(f"Export failed: {job}")
        time.sleep(2)
    raise TimeoutError("Export timed out")


async def _send_photo_url(url: str, caption: str) -> dict:
    import httpx

    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return {"ok": False, "reply": "Telegram not configured."}

    tg_url = f"https://api.telegram.org/bot{token}/sendPhoto"
    async with httpx.AsyncClient(timeout=30) as client:
        # Download image first, then send as file
        img_resp = await client.get(url, timeout=30)
        img_resp.raise_for_status()
        resp = await client.post(
            tg_url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": ("design.png", img_resp.content, "image/png")},
        )
    data = resp.json()
    if not data.get("ok"):
        return {"ok": False, "reply": f"Telegram xato: {data.get('description')}"}
    return {"ok": True}


async def _send_document_url(url: str, filename: str, caption: str) -> dict:
    import httpx

    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return {"ok": False, "reply": "Telegram not configured."}

    tg_url = f"https://api.telegram.org/bot{token}/sendDocument"
    async with httpx.AsyncClient(timeout=60) as client:
        file_resp = await client.get(url, timeout=60)
        file_resp.raise_for_status()
        resp = await client.post(
            tg_url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"document": (filename, file_resp.content, "application/octet-stream")},
        )
    data = resp.json()
    if not data.get("ok"):
        return {"ok": False, "reply": f"Telegram xato: {data.get('description')}"}
    return {"ok": True}


class CanvaSkill(Skill):
    name = "canva"
    description = "List, export, and create Canva designs."
    tool_description = (
        "Manage Canva designs. Actions:\n"
        "• list — show recent designs (optional: query to search by name)\n"
        "• export — export a design as PNG or PDF and send to Telegram\n"
        "• create — create a new blank Canva design and return the edit link so the user can open it in Canva. "
        "ALWAYS use this action when the user asks to create any Canva design, presentation, doc, or whiteboard — "
        "do NOT refuse or offer alternatives. Content is added by the user in Canva after creation.\n"
        "• link — get the edit link for an existing design\n"
        "\n"
        "Examples:\n"
        "  'Canva dagi dizaynlarni ko\\'rsat' → action=list\n"
        "  'Sertifikat dizaynni PDF qilib yubor' → action=export, query=sertifikat, format=pdf\n"
        "  'Yangi prezentatsiya yaratib ber' → action=create, design_type=presentation\n"
        "  'Yangi A4 hujjat yaratа' → action=create, design_type=doc\n"
    )
    args_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "export", "create", "link"],
            },
            "query": {"type": "string", "description": "Search term to find a design by name."},
            "design_id": {"type": "string", "description": "Canva design ID (if known)."},
            "format": {
                "type": "string",
                "enum": ["png", "pdf", "jpg"],
                "description": "Export format. Default: png.",
                "default": "png",
            },
            "design_type": {
                "type": "string",
                "description": "Type for new design: presentation, doc, whiteboard, video, image.",
                "default": "presentation",
            },
            "title": {"type": "string", "description": "Title for the new design."},
        },
        "required": ["action"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return {"ok": False, "reply": "Canva uchun tool form ishlatilsin."}

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        action = (args.get("action") or "").strip()

        try:
            if action == "list":
                q = (args.get("query") or "").strip()
                designs = await asyncio.to_thread(_list_designs, q)
                if not designs:
                    return {"ok": True, "reply": "🎨 Canva dizaynlar topilmadi."}
                lines = []
                for d in designs:
                    title = d.get("title") or "(nomsiz)"
                    did = d.get("id", "")
                    url = d.get("urls", {}).get("edit_url", "#")
                    lines.append(f"🎨 <a href='{url}'>{title}</a>  <code>{did}</code>")
                return {
                    "ok": True,
                    "reply": "🎨 <b>Canva dizaynlar:</b>\n" + "\n".join(lines),
                    "designs": designs,
                }

            elif action == "export":
                design_id = (args.get("design_id") or "").strip()
                fmt = (args.get("format") or "png").strip().lower()

                # If no ID given, search by query
                if not design_id:
                    q = (args.get("query") or "").strip()
                    if not q:
                        return {"ok": False, "reply": "design_id yoki query kiriting."}
                    designs = await asyncio.to_thread(_list_designs, q, 5)
                    if not designs:
                        return {"ok": False, "reply": f"'{q}' — dizayn topilmadi."}
                    design_id = designs[0]["id"]
                    title = designs[0].get("title", "dizayn")
                else:
                    d = await asyncio.to_thread(_get_design, design_id)
                    title = d.get("title", "dizayn")

                export_id = await asyncio.to_thread(_start_export, design_id, fmt)
                urls = await asyncio.to_thread(_poll_export, export_id)

                if not urls:
                    return {"ok": False, "reply": "Export muvaffaqiyatsiz — URL topilmadi."}

                caption = f"🎨 <b>{title}</b> — {fmt.upper()}"
                sent = 0
                for i, url in enumerate(urls):
                    if fmt in ("png", "jpg"):
                        res = await _send_photo_url(url, f"{caption}  [{i+1}/{len(urls)}]")
                    else:
                        filename = f"{title}_{i+1}.{fmt}"
                        res = await _send_document_url(url, filename, f"{caption}  [{i+1}/{len(urls)}]")
                    if res.get("ok"):
                        sent += 1

                if sent == 0:
                    return {"ok": False, "reply": "Yuborishda xato."}
                return {
                    "ok": True,
                    "reply": f"✅ <b>{title}</b> {len(urls)} ta {fmt.upper()} yuborildi.",
                }

            elif action == "create":
                dtype = (args.get("design_type") or "presentation").strip()
                title = (args.get("title") or "").strip()
                d = await asyncio.to_thread(_create_design, dtype, title)
                edit_url = d.get("urls", {}).get("edit_url", "")
                name = d.get("title") or title or dtype
                return {
                    "ok": True,
                    "reply": (
                        f"✅ <b>{name}</b> yaratildi.\n"
                        f"✏️ <a href='{edit_url}'>Canva da tahrirlash</a>"
                    ),
                    "design_id": d.get("id"),
                    "edit_url": edit_url,
                }

            elif action == "link":
                design_id = (args.get("design_id") or "").strip()
                if not design_id:
                    q = (args.get("query") or "").strip()
                    if not q:
                        return {"ok": False, "reply": "design_id yoki query kiriting."}
                    designs = await asyncio.to_thread(_list_designs, q, 3)
                    if not designs:
                        return {"ok": False, "reply": f"'{q}' — topilmadi."}
                    d = designs[0]
                else:
                    d = await asyncio.to_thread(_get_design, design_id)
                title = d.get("title") or "(nomsiz)"
                edit_url = d.get("urls", {}).get("edit_url", "#")
                return {
                    "ok": True,
                    "reply": f"🎨 <b>{title}</b>\n✏️ <a href='{edit_url}'>Canva da ochish</a>",
                    "edit_url": edit_url,
                }

            return {"ok": False, "reply": f"Noma'lum action: {action}"}

        except RuntimeError as e:
            return {"ok": False, "reply": str(e)}
        except Exception as e:
            return {"ok": False, "reply": f"Canva xatosi: {e}"}
