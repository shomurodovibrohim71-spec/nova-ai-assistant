"""File-system skills.

All ops are confined to `settings.file_root` (defaults to user's home directory).
Destructive ops require an explicit `confirm: true` arg unless
`settings.allow_destructive` is set.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from ...config import settings
from ...security import PathError, safe_resolve
from ..base import Skill


def _root() -> Path:
    return Path(settings.file_root).expanduser().resolve()


def _resolve(path: str) -> Path:
    return safe_resolve(path, _root())


def _ok(reply: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "reply": reply, **extra}


def _err(reply: str) -> dict[str, Any]:
    return {"ok": False, "reply": reply}


class ListDirSkill(Skill):
    name = "list_dir"
    description = "List the contents of a directory."
    tool_description = "List files and folders in a directory (relative to user's home, or absolute if inside the allowed root)."
    patterns = [r"^\s*(?:list|ls|show)\s+(?:files\s+in\s+|the\s+)?(?P<path>[\w\-\.\/\\\\\:\s~]+?)\s*$"]
    args_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path. '.' or '~' for home."},
            "limit": {"type": "integer", "default": 50},
        },
        "required": ["path"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        path = match.group("path").strip() if match else "."
        return await self.run_tool({"path": path})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        path = args.get("path", ".")
        limit = int(args.get("limit", 50))
        try:
            target = _resolve(path)
        except PathError as e:
            return _err(str(e))
        if not target.exists():
            return _err(f"{target} doesn't exist.")
        if not target.is_dir():
            return _err(f"{target} is not a directory.")
        try:
            entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError as e:
            return _err(f"Permission denied: {e}")
        items = []
        for p in entries[:limit]:
            kind = "dir" if p.is_dir() else "file"
            size = p.stat().st_size if p.is_file() else None
            items.append({"name": p.name, "kind": kind, "size": size})
        more = max(0, len(entries) - limit)
        listing = ", ".join(f"{i['name']}{'/' if i['kind']=='dir' else ''}" for i in items[:20])
        suffix = f" (+{more} more)" if more else ""
        return _ok(f"{len(entries)} items in {target}: {listing}{suffix}", items=items, path=str(target))


class FindFilesSkill(Skill):
    name = "find_files"
    description = "Find files by glob pattern under a starting directory."
    tool_description = "Search files by glob pattern (e.g. '**/*.pdf') under a starting directory."
    patterns = [
        r"^\s*find\s+(?P<pattern>\S+)(?:\s+in\s+(?P<path>.+?))?\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '*.pdf' or '**/*.xlsx'."},
            "path": {"type": "string", "default": "."},
            "limit": {"type": "integer", "default": 100},
        },
        "required": ["pattern"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        if match is None:
            return _err("No pattern.")
        return await self.run_tool({"pattern": match.group("pattern"), "path": match.group("path") or "."})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        limit = int(args.get("limit", 100))
        try:
            base = _resolve(path)
        except PathError as e:
            return _err(str(e))
        if not base.is_dir():
            return _err(f"{base} is not a directory.")
        glob = "**/" + pattern if "*" not in pattern.split("/")[0] else pattern
        try:
            matches = list(await asyncio.to_thread(lambda: list(base.glob(glob))[:limit]))
        except OSError as e:
            return _err(f"Search error: {e}")
        names = [str(p.relative_to(base)) for p in matches]
        if not names:
            return _ok(f"No matches for '{pattern}' under {base}.", matches=[], path=str(base))
        preview = ", ".join(names[:10])
        more = max(0, len(names) - 10)
        return _ok(
            f"Found {len(names)} match{'es' if len(names)!=1 else ''}: {preview}{f' (+{more} more)' if more else ''}",
            matches=names,
            path=str(base),
        )


class MoveSkill(Skill):
    name = "move_file"
    description = "Move or rename a file or folder."
    tool_description = "Move/rename a file or folder. Both src and dst must be inside the allowed root."
    patterns: list[str] = []   # always via LLM tool — no fast-path; too easy to misparse
    args_schema = {
        "type": "object",
        "properties": {"src": {"type": "string"}, "dst": {"type": "string"}},
        "required": ["src", "dst"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return _err("Use the move_file tool with src and dst arguments.")

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            src = _resolve(args["src"])
            dst = _resolve(args["dst"])
        except (PathError, KeyError) as e:
            return _err(str(e))
        if not src.exists():
            return _err(f"{src} doesn't exist.")
        try:
            await asyncio.to_thread(shutil.move, str(src), str(dst))
        except OSError as e:
            return _err(f"Move failed: {e}")
        return _ok(f"Moved {src.name} to {dst}.", src=str(src), dst=str(dst))


class CopySkill(Skill):
    name = "copy_file"
    description = "Copy a file or folder."
    tool_description = "Copy a file or folder. Both src and dst must be inside the allowed root."
    patterns: list[str] = []
    args_schema = {
        "type": "object",
        "properties": {"src": {"type": "string"}, "dst": {"type": "string"}},
        "required": ["src", "dst"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return _err("Use the copy_file tool with src and dst arguments.")

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            src = _resolve(args["src"])
            dst = _resolve(args["dst"])
        except (PathError, KeyError) as e:
            return _err(str(e))
        if not src.exists():
            return _err(f"{src} doesn't exist.")
        try:
            if src.is_dir():
                await asyncio.to_thread(shutil.copytree, str(src), str(dst))
            else:
                await asyncio.to_thread(shutil.copy2, str(src), str(dst))
        except OSError as e:
            return _err(f"Copy failed: {e}")
        return _ok(f"Copied {src.name} to {dst}.", src=str(src), dst=str(dst))


class DeleteSkill(Skill):
    name = "delete_file"
    description = "Delete a file or folder. Requires explicit confirmation."
    tool_description = (
        "Permanently delete a file or folder. ALWAYS confirm with the user before invoking; "
        "must be called with confirm=true. Folders are deleted recursively."
    )
    patterns: list[str] = []   # never via fast path — too dangerous
    args_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "confirm": {"type": "boolean", "description": "Must be true to actually delete."},
        },
        "required": ["path", "confirm"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return _err("Deleting via voice is disabled — ask Nova and confirm explicitly.")

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        if not (args.get("confirm") or settings.allow_destructive):
            return _err("Deletion refused: confirm=true required.")
        try:
            target = _resolve(args["path"])
        except (PathError, KeyError) as e:
            return _err(str(e))
        if not target.exists():
            return _err(f"{target} doesn't exist.")
        try:
            if target.is_dir():
                await asyncio.to_thread(shutil.rmtree, str(target))
            else:
                await asyncio.to_thread(target.unlink)
        except OSError as e:
            return _err(f"Delete failed: {e}")
        return _ok(f"Deleted {target}.", path=str(target))


class ZipSkill(Skill):
    name = "zip_files"
    description = "Create a ZIP archive from a file or folder."
    tool_description = "Create a ZIP archive of a file or directory. Returns the zip path."
    patterns = [
        r"^\s*zip\s+(?P<path>[\w\-\.\/\\\\\s~]+?)\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or folder to zip."},
            "output": {"type": "string", "description": "Output .zip path (optional, defaults to same location)."},
        },
        "required": ["path"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        path = match.group("path").strip() if match else text.strip()
        return await self.run_tool({"path": path})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            src = _resolve(args.get("path") or "")
        except PathError as e:
            return _err(str(e))
        if not src.exists():
            return _err(f"Not found: {src}")

        out_raw = (args.get("output") or "").strip()
        if out_raw:
            try:
                out = _resolve(out_raw)
            except PathError as e:
                return _err(str(e))
        else:
            out = src.with_suffix(".zip")

        try:
            await asyncio.to_thread(_do_zip, src, out)
        except Exception as e:
            return _err(f"Zip failed: {e}")

        size_kb = out.stat().st_size // 1024
        return _ok(f"Created {out.name} ({size_kb} KB).", path=str(out), zip_path=str(out))


def _do_zip(src: Path, out: Path) -> None:
    import zipfile
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        if src.is_dir():
            for f in src.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(src.parent))
        else:
            zf.write(src, src.name)


class MakeDirSkill(Skill):
    name = "make_dir"
    description = "Create a folder."
    tool_description = "Create a folder (and any missing parents) inside the allowed root."
    patterns = [r"^\s*(?:create|make|mkdir)\s+(?:a\s+)?(?:folder|directory|dir)\s+(?:called\s+|named\s+)?(?P<path>[\w\-\.\/\\\\\s~]+?)\s*$"]
    args_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        if match is None:
            return _err("No path.")
        return await self.run_tool({"path": match.group("path").strip()})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            target = _resolve(args["path"])
        except (PathError, KeyError) as e:
            return _err(str(e))
        try:
            await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)
        except OSError as e:
            return _err(f"Couldn't create folder: {e}")
        return _ok(f"Created folder {target}.", path=str(target))


class ReadFileSkill(Skill):
    name = "read_file"
    description = "Read a text file."
    tool_description = "Read the text content of a file. For binary files this will fail; use it on .txt, .md, .py, .json, etc."
    patterns: list[str] = []
    args_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_chars": {"type": "integer", "default": 8000},
        },
        "required": ["path"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        return _err("Use the read_file tool with a path argument.")

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        try:
            target = _resolve(args["path"])
        except (PathError, KeyError) as e:
            return _err(str(e))
        if not target.is_file():
            return _err(f"{target} is not a file.")
        max_chars = int(args.get("max_chars", 8000))
        try:
            data = await asyncio.to_thread(target.read_text, "utf-8", errors="replace")
        except OSError as e:
            return _err(f"Read failed: {e}")
        truncated = len(data) > max_chars
        if truncated:
            data = data[:max_chars]
        return _ok(
            f"Read {target.name} ({len(data)} chars{', truncated' if truncated else ''}).",
            content=data,
            truncated=truncated,
            path=str(target),
        )
