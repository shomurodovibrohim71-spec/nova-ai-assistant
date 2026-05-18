"""Google Drive skill — list, upload, download, search files."""
from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

from ...config import settings
from ..base import Skill

_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_path = Path(settings.data_dir) / "google_token.json"
    if not token_path.exists():
        raise RuntimeError(
            "Google Drive ulanmagan. "
            "Avval: python scripts/setup_google_drive.py"
        )
    creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        else:
            raise RuntimeError(
                "Token eskirgan. Qayta: python scripts/setup_google_drive.py"
            )
    return creds


def _svc():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_creds(), cache_discovery=False)


def _list_files(query: str = "", folder_id: str = "root") -> list[dict]:
    q = f"'{folder_id}' in parents and trashed=false"
    if query:
        q += f" and name contains '{query}'"
    res = _svc().files().list(
        q=q, pageSize=25,
        fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
    ).execute()
    return res.get("files", [])


def _search_files(query: str) -> list[dict]:
    q = f"name contains '{query}' and trashed=false"
    res = _svc().files().list(
        q=q, pageSize=15,
        fields="files(id,name,mimeType,size,modifiedTime,webViewLink)",
    ).execute()
    return res.get("files", [])


def _upload_file(local_path: Path, folder_id: str = "") -> dict:
    from googleapiclient.http import MediaFileUpload

    svc = _svc()
    meta: dict = {"name": local_path.name}
    if folder_id:
        meta["parents"] = [folder_id]
    media = MediaFileUpload(str(local_path), resumable=True)
    f = svc.files().create(body=meta, media_body=media,
                           fields="id,name,webViewLink").execute()
    svc.permissions().create(
        fileId=f["id"], body={"type": "anyone", "role": "reader"}
    ).execute()
    return f


def _download_file(file_id: str, dest: Path) -> Path:
    from googleapiclient.http import MediaIoBaseDownload

    request = _svc().files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = dl.next_chunk()
    dest.write_bytes(buf.getvalue())
    return dest


def _file_meta(file_id: str) -> dict:
    return _svc().files().get(
        fileId=file_id,
        fields="id,name,mimeType,size,modifiedTime,webViewLink",
    ).execute()


def _make_folder(name: str, parent_id: str = "") -> dict:
    meta: dict = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        meta["parents"] = [parent_id]
    return _svc().files().create(body=meta, fields="id,name,webViewLink").execute()


class GoogleDriveSkill(Skill):
    name = "google_drive"
    description = "List, upload, download, search files in Google Drive."
    tool_description = (
        "Manage Google Drive. Actions:\n"
        "• list — files in Drive root (optional: query to filter by name)\n"
        "• search — find files anywhere by name keyword\n"
        "• upload — upload a local file; returns shareable link\n"
        "• download — download Drive file to local PC (needs file_id)\n"
        "• mkdir — create a folder\n"
        "\n"
        "Examples:\n"
        "  'Drive dagi fayllarni ko\\'rsat' → action=list\n"
        "  'Excel faylni Drive ga yuklа' → action=upload, path=<full path>\n"
        "  'Drive da report qidir' → action=search, query=report\n"
    )
    args_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "search", "upload", "download", "mkdir"],
            },
            "path": {"type": "string", "description": "Local file path (upload) or save path (download)."},
            "query": {"type": "string", "description": "Name filter for list/search."},
            "file_id": {"type": "string", "description": "Google Drive file ID."},
            "folder_name": {"type": "string", "description": "Folder name for mkdir."},
        },
        "required": ["action"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return {"ok": False, "reply": "Drive uchun tool form ishlatilsin."}

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        action = (args.get("action") or "").strip()

        try:
            if action == "list":
                files = await asyncio.to_thread(_list_files, args.get("query", ""))
                if not files:
                    return {"ok": True, "reply": "📁 Drive bo'sh yoki fayl topilmadi."}
                lines = [
                    ("📁 " if "folder" in f.get("mimeType", "") else "📄 ") + f["name"]
                    for f in files
                ]
                return {"ok": True, "reply": "📁 <b>Google Drive:</b>\n" + "\n".join(lines), "files": files}

            elif action == "search":
                q = (args.get("query") or "").strip()
                if not q:
                    return {"ok": False, "reply": "query kiriting."}
                files = await asyncio.to_thread(_search_files, q)
                if not files:
                    return {"ok": True, "reply": f"🔍 '{q}' — topilmadi."}
                lines = []
                for f in files:
                    icon = "📁" if "folder" in f.get("mimeType", "") else "📄"
                    link = f.get("webViewLink", "#")
                    lines.append(f"{icon} <a href='{link}'>{f['name']}</a>")
                return {"ok": True, "reply": "🔍 <b>Natijalar:</b>\n" + "\n".join(lines), "files": files}

            elif action == "upload":
                p = (args.get("path") or "").strip()
                if not p:
                    return {"ok": False, "reply": "path kiriting."}
                local = Path(p)
                if not local.exists():
                    return {"ok": False, "reply": f"Fayl topilmadi: {p}"}
                info = await asyncio.to_thread(_upload_file, local)
                link = info.get("webViewLink", "")
                return {
                    "ok": True,
                    "reply": (
                        f"✅ <b>{local.name}</b> Drive ga yuklandi.\n"
                        f"🔗 <a href='{link}'>Ochish</a>"
                    ),
                    "link": link,
                    "file_id": info.get("id"),
                }

            elif action == "download":
                fid = (args.get("file_id") or "").strip()
                if not fid:
                    return {"ok": False, "reply": "file_id kiriting."}
                dest_str = (args.get("path") or "").strip()
                if dest_str:
                    dest = Path(dest_str)
                else:
                    meta = await asyncio.to_thread(_file_meta, fid)
                    dest = Path(settings.downloads_dir) / meta.get("name", fid)
                saved = await asyncio.to_thread(_download_file, fid, dest)
                return {"ok": True, "reply": f"✅ Yuklandi: {saved}"}

            elif action == "mkdir":
                name = (args.get("folder_name") or args.get("query") or "").strip()
                if not name:
                    return {"ok": False, "reply": "folder_name kiriting."}
                info = await asyncio.to_thread(_make_folder, name)
                link = info.get("webViewLink", "")
                return {
                    "ok": True,
                    "reply": f"📁 '{name}' papkasi yaratildi. <a href='{link}'>Ochish</a>",
                    "file_id": info.get("id"),
                }

            return {"ok": False, "reply": f"Noma'lum action: {action}"}

        except RuntimeError as e:
            return {"ok": False, "reply": str(e)}
        except Exception as e:
            return {"ok": False, "reply": f"Drive xatosi: {e}"}
