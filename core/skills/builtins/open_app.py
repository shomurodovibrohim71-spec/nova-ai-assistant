import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..base import Skill

# Well-known system apps — checked first (fast path)
APP_ALIASES: dict[str, list[str]] = {
    "chrome": ["chrome.exe", "chrome"],
    "edge": ["msedge.exe", "msedge"],
    "firefox": ["firefox.exe", "firefox"],
    "vscode": ["code.cmd", "code"],
    "code": ["code.cmd", "code"],
    "notepad": ["notepad.exe", "notepad"],
    "explorer": ["explorer.exe", "explorer"],
    "calculator": ["calc.exe", "calc"],
    "calc": ["calc.exe", "calc"],
    "terminal": ["wt.exe", "wt", "powershell.exe"],
    "powershell": ["powershell.exe"],
    "word": ["WINWORD.EXE", "winword"],
    "excel": ["EXCEL.EXE", "excel"],
    "steam": ["steam.exe", "steam"],
    "spotify": ["Spotify.exe", "spotify"],
    "discord": ["Discord.exe", "discord"],
    "vlc": ["vlc.exe", "vlc"],
    "telegram": ["Telegram.exe", "telegram"],
}

# Fast search roots — shallow first, slow roots last and depth-limited
SEARCH_ROOTS = [
    (Path.home() / "Desktop", 3),           # Desktop + 3 levels deep
    (Path.home() / "Downloads", 2),
    (Path("C:/Games"), 4),
    (Path("C:/Program Files"), 2),           # Only 2 levels — top-level app folders
    (Path("C:/Program Files (x86)"), 2),
]


_HELPER_KEYWORDS = {
    "uninstall", "setup", "installer", "update", "updater", "crash",
    "report", "helper", "service", "redist", "vcredist", "directx",
    "dotnet", "vc_redist", "dxsetup", "uplay_bootstrapper",
}


def _walk_depth(root: Path, max_depth: int):
    """Yield all items under root up to max_depth levels."""
    for item in root.iterdir():
        yield item
        if item.is_dir() and max_depth > 1:
            yield from _walk_depth(item, max_depth - 1)


def _is_helper_exe(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _HELPER_KEYWORDS)


class OpenAppSkill(Skill):
    name = "open_app"
    description = "Launch a desktop application or game by name."
    tool_description = (
        "Launch any application, game, or executable on the user's PC by name. "
        "Searches system PATH, common app aliases, and Desktop/Program Files folders."
    )
    patterns = [
        r"^\s*(?:open|launch|start|run)\s+(?P<app>[\w\-\+\.\s]+?)\s*[!.\?]*\s*$",
        r"^\s*(?P<app>[\w\-\+\.\s]+?)\s+(?:och|ishga\s*tushir|yoq|start\s*qil|ochib\s*ber)\s*[!.\?]*\s*$",
        r"^\s*(?:och|oching|yoq|yoqing)\s+(?P<app>[\w\-\+\.\s]+?)\s*[!.\?]*\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": "App or game name, e.g. 'chrome', 'Batman Arkham Origins', 'steam'.",
            },
            "path": {
                "type": "string",
                "description": "Optional explicit path to the exe (skip search).",
            },
        },
        "required": ["app"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        if match is None:
            return {"ok": False, "reply": "I couldn't parse the app name."}
        return await self._launch(match.group("app").strip())

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        explicit_path = (args.get("path") or "").strip()
        if explicit_path:
            try:
                await asyncio.to_thread(self._spawn, explicit_path)
                return {"ok": True, "reply": f"Launched {Path(explicit_path).name}.", "path": explicit_path}
            except Exception as e:
                return {"ok": False, "reply": f"Failed to launch: {e}"}
        app = (args.get("app") or "").strip()
        if not app:
            return {"ok": False, "reply": "No app name provided."}
        return await self._launch(app)

    async def _launch(self, app: str) -> dict[str, Any]:
        key = app.lower()

        # 1. Known alias
        for candidate in APP_ALIASES.get(key, []):
            resolved = shutil.which(candidate) or candidate
            try:
                await asyncio.to_thread(self._spawn, resolved)
                return {"ok": True, "reply": f"Opening {app}.", "app": app}
            except (FileNotFoundError, OSError):
                continue

        # 2. Plain name on PATH
        if shutil.which(key):
            try:
                await asyncio.to_thread(self._spawn, key)
                return {"ok": True, "reply": f"Opening {app}.", "app": app}
            except Exception:
                pass

        # 3. Search Desktop, Program Files, etc. for a matching .exe or .lnk
        found = await asyncio.to_thread(self._find_app, app)
        if found:
            try:
                await asyncio.to_thread(self._spawn, str(found))
                return {"ok": True, "reply": f"Opening {found.name}.", "app": app, "path": str(found)}
            except Exception as e:
                return {"ok": False, "reply": f"Found {found.name} but couldn't launch it: {e}"}

        return {
            "ok": False,
            "reply": (
                f"Couldn't find '{app}'. "
                "Try providing the full path, or tell me which folder it's in."
            ),
        }

    @staticmethod
    def _find_app(app: str) -> Path | None:
        """Search common roots for a .lnk shortcut or .exe matching `app`.

        Priority: .lnk shortcut (exact name match) > .exe in matching folder > .exe name match
        """
        keywords = [w.lower() for w in app.split() if len(w) > 2]
        if not keywords:
            return None

        lnk_hits: list[tuple[int, Path]] = []
        exe_folder_hits: list[tuple[int, Path]] = []
        exe_name_hits: list[tuple[int, Path]] = []

        for root, max_depth in SEARCH_ROOTS:
            if not root.exists():
                continue
            try:
                for item in _walk_depth(root, max_depth):
                    item_lower = item.name.lower()
                    matched_kw = sum(1 for kw in keywords if kw in item_lower)

                    if item.suffix.lower() == ".lnk":
                        if matched_kw == len(keywords):
                            lnk_hits.append((len(item.parts), item))

                    elif item.is_dir():
                        if matched_kw == len(keywords):
                            for exe in item.glob("*.exe"):  # only 1 level inside matching folder
                                if not _is_helper_exe(exe.name):
                                    exe_folder_hits.append((len(exe.parts), exe))

                    elif item.suffix.lower() == ".exe" and not _is_helper_exe(item.name):
                        if matched_kw >= max(1, len(keywords) - 1):
                            exe_name_hits.append((len(item.parts) * 10 - matched_kw, item))

            except (PermissionError, OSError):
                continue

        for hits in (lnk_hits, exe_folder_hits, exe_name_hits):
            if hits:
                hits.sort(key=lambda x: x[0])
                return hits[0][1]
        return None

    @staticmethod
    def _resolve_lnk(lnk_path: str) -> str:
        """Resolve a .lnk shortcut → actual target path (or steam:// URL)."""
        try:
            import win32com.client  # type: ignore
            shell = win32com.client.Dispatch("WScript.Shell")
            sc = shell.CreateShortcut(lnk_path)
            target = sc.TargetPath or ""
            args = sc.Arguments or ""
            # Steam shortcut: target is steam.exe, args contain -applaunch <id>
            if "steam.exe" in target.lower() and "-applaunch" in args.lower():
                parts = args.split()
                for i, p in enumerate(parts):
                    if p.lower() == "-applaunch" and i + 1 < len(parts):
                        return f"steam://rungameid/{parts[i + 1]}"
            if target and Path(target).exists():
                return target
        except Exception:
            pass
        return lnk_path

    @staticmethod
    def _steam_appid_from_exe(exe_path: str) -> str | None:
        """If the exe lives inside a Steam game folder, return steam://rungameid/<id>."""
        p = Path(exe_path)
        for candidate in (p.parent, p.parent.parent, p.parent.parent.parent):
            appid_file = candidate / "steam_appid.txt"
            if appid_file.exists():
                try:
                    appid = appid_file.read_text().strip()
                    if appid.isdigit():
                        return f"steam://rungameid/{appid}"
                except Exception:
                    pass
        return None

    @staticmethod
    def _spawn(executable: str) -> None:
        if os.name == "nt":
            # 1. Resolve .lnk → real target or steam:// URL
            if executable.lower().endswith(".lnk"):
                executable = OpenAppSkill._resolve_lnk(executable)

            # 2. If still a plain exe inside a Steam game folder, use steam:// protocol
            #    so Steam can apply DRM checks and inject overlays correctly.
            if executable.lower().endswith(".exe"):
                steam_url = OpenAppSkill._steam_appid_from_exe(executable)
                if steam_url:
                    executable = steam_url

            data_dir = Path(__file__).resolve().parents[3] / "data"
            data_dir.mkdir(exist_ok=True)
            (data_dir / "launch_target.txt").write_text(executable, encoding="utf-8")
            result = subprocess.run(
                ["schtasks", "/run", "/tn", "NovaLauncher"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                # NovaLauncher task not registered — fall back to direct ShellExecuteW
                import ctypes
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "open", executable, None,
                    str(Path(executable).parent) if Path(executable).exists() else None,
                    1,
                )
                if ret <= 32:
                    raise OSError(f"ShellExecuteW failed with code {ret}: {executable}")
        else:
            subprocess.Popen([executable])


# ── Process name aliases for taskkill ────────────────────────────────────────
CLOSE_ALIASES: dict[str, str] = {
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "notepad": "notepad.exe",
    "calculator": "win32calc.exe",
    "calc": "win32calc.exe",
    "excel": "EXCEL.EXE",
    "word": "WINWORD.EXE",
    "vscode": "Code.exe",
    "code": "Code.exe",
    "steam": "steam.exe",
    "spotify": "Spotify.exe",
    "discord": "Discord.exe",
    "vlc": "vlc.exe",
    "telegram": "Telegram.exe",
    "explorer": "explorer.exe",
    "powershell": "powershell.exe",
}


class CloseAppSkill(Skill):
    name = "close_app"
    description = "Close / kill a running application by name."
    tool_description = "Kill a running process by app name (e.g. 'chrome', 'notepad', 'excel')."
    patterns = [
        r"^\s*(?:close|kill|quit|exit|stop|yop)\s+(?P<app>[\w\-\+\.\s]+?)\s*[!.\?]*\s*$",
        r"^\s*(?P<app>[\w\-\+\.\s]+?)\s+(?:yop|o[''`]?chir|close\s*qil|yopib\s*ber)\s*[!.\?]*\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "App name, e.g. 'chrome', 'notepad'."},
        },
        "required": ["app"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        if match is None:
            return {"ok": False, "reply": "App nomini ayta olmadim."}
        return await self.run_tool({"app": match.group("app").strip()})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        app = (args.get("app") or "").strip().lower()
        if not app:
            return {"ok": False, "reply": "App nomi kerak."}
        exe = CLOSE_ALIASES.get(app, app if app.endswith(".exe") else app + ".exe")
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/F", "/IM", exe, "/T"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return {"ok": True, "reply": f"✅ {app} yopildi."}
            # Try without .exe suffix variant
            result2 = await asyncio.to_thread(
                subprocess.run,
                ["taskkill", "/F", "/IM", exe.replace(".exe", "").replace(".EXE", "") + ".exe", "/T"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result2.returncode == 0:
                return {"ok": True, "reply": f"✅ {app} yopildi."}
            return {"ok": False, "reply": f"'{app}' jarayoni topilmadi yoki allaqachon yopiq."}
        except Exception as e:
            return {"ok": False, "reply": f"Yopishda xato: {e}"}


class InstallAppSkill(Skill):
    name = "install_app"
    description = "Download and install an application from the internet using winget or direct URL."
    tool_description = (
        "Install an application on the user's PC. Uses winget (Windows Package Manager) by default. "
        "Can also download an .exe/.msi from a direct URL and run the installer silently. "
        "Examples: 'install vlc', 'install 7zip', 'download and install from https://...'"
    )
    patterns = [
        r"^\s*(?:install|yuklab\s*o[''`]?rnat|o[''`]?rnat)\s+(?P<app>[\w\-\+\.\s]+?)\s*[!.\?]*\s*$",
        r"^\s*(?:download\s+and\s+install|yukla\s+va\s+o[''`]?rnat)\s+(?P<app>[\w\-\+\.\s]+?)\s*[!.\?]*\s*$",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "App name for winget, e.g. 'vlc', '7zip', 'notepad++'."},
            "url": {"type": "string", "description": "Direct download URL for .exe/.msi installer (optional)."},
            "silent": {"type": "boolean", "default": True, "description": "Install silently without UI prompts."},
        },
        "required": ["app"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        if match is None:
            return {"ok": False, "reply": "App nomini ayta olmadim."}
        return await self.run_tool({"app": match.group("app").strip()})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        app = (args.get("app") or "").strip()
        url = (args.get("url") or "").strip()
        silent = bool(args.get("silent", True))

        if url:
            return await self._install_from_url(url, app)
        return await self._install_winget(app, silent)

    async def _install_winget(self, app: str, silent: bool) -> dict[str, Any]:
        # Check winget available
        if not shutil.which("winget"):
            return {"ok": False, "reply": "winget topilmadi. Windows 10 1709+ kerak."}
        flags = ["winget", "install", "--accept-package-agreements",
                 "--accept-source-agreements", app]
        if silent:
            flags += ["--silent"]
        try:
            result = await asyncio.to_thread(
                subprocess.run, flags,
                capture_output=True, text=True, timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                return {"ok": True, "reply": f"✅ '{app}' muvaffaqiyatli o'rnatildi."}
            out = (result.stdout + result.stderr)[:300]
            return {"ok": False, "reply": f"winget xato (code {result.returncode}): {out}"}
        except asyncio.TimeoutError:
            return {"ok": False, "reply": "O'rnatish juda uzoq davom etdi (>5 daqiqa)."}
        except Exception as e:
            return {"ok": False, "reply": f"O'rnatishda xato: {e}"}

    async def _install_from_url(self, url: str, name: str) -> dict[str, Any]:
        import tempfile, httpx
        from urllib.parse import urlparse
        parsed = urlparse(url)
        suffix = Path(parsed.path).suffix or ".exe"
        tmp = Path(tempfile.mktemp(suffix=suffix))
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                tmp.write_bytes(resp.content)
        except Exception as e:
            return {"ok": False, "reply": f"Yuklab olishda xato: {e}"}
        try:
            flags = [str(tmp)]
            if suffix == ".msi":
                flags = ["msiexec", "/i", str(tmp), "/quiet", "/norestart"]
            else:
                flags += ["/S", "/silent", "/quiet", "--silent"]
            await asyncio.to_thread(
                subprocess.run, flags,
                capture_output=True, timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return {"ok": True, "reply": f"✅ '{name or tmp.name}' yuklab o'rnatildi."}
        except Exception as e:
            return {"ok": False, "reply": f"O'rnatishda xato: {e}"}
        finally:
            tmp.unlink(missing_ok=True)
