from __future__ import annotations

import platform
from typing import Any

import psutil

from ..base import Skill


def _gb(b: int) -> str:
    return f"{b / 1024**3:.1f} GB"


def _disk_lines() -> list[str]:
    lines = []
    for p in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(p.mountpoint)
        except PermissionError:
            continue
        pct = u.percent
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        lines.append(
            f"  {p.device}  [{bar}] {pct:.0f}%  "
            f"used {_gb(u.used)} / {_gb(u.total)}  free {_gb(u.free)}"
        )
    return lines


class SystemInfoSkill(Skill):
    name = "system_info"
    description = "Reports CPU, memory, disk, network and running processes."
    tool_description = (
        "Get a full system snapshot: CPU, RAM, every disk/drive (C:, D:, …), "
        "network stats, uptime, and top processes by CPU."
    )
    patterns = [
        r"\b(system|pc|computer)\s+(status|info|health)\b",
        r"\b(cpu|memory|ram)\s+(usage|status)\b",
        r"\bhow('?s| is)\s+(my\s+)?(system|pc|computer)\b",
        # disk-specific
        r"\b(disk|drive|c:|d:|storage)\s*(space|info|status|bosh|joy)?\b",
        r"\b(qancha|necha)\s+(bosh|bo[''s]+)\s+(joy|disk|xotira)\b",
        r"\bhow\s+much\s+(free\s+)?(space|disk)\b",
    ]
    args_schema = {
        "type": "object",
        "properties": {
            "detail": {
                "type": "string",
                "enum": ["full", "disk", "cpu", "ram", "network", "processes"],
                "description": "Which section to show. Default: full.",
            }
        },
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        tl = text.lower()
        if any(w in tl for w in ("disk", "drive", "space", "c:", "d:", "bosh joy", "xotira")):
            return await self.run_tool({"detail": "disk"})
        if any(w in tl for w in ("process", "jarayon", "running")):
            return await self.run_tool({"detail": "processes"})
        if any(w in tl for w in ("network", "tarmoq", "internet speed")):
            return await self.run_tool({"detail": "network"})
        return await self.run_tool({"detail": "full"})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        detail = (args.get("detail") or "full").lower()

        if detail == "disk":
            lines = _disk_lines()
            reply = "💾 <b>Disk holati:</b>\n" + "\n".join(lines)
            return {"ok": True, "reply": reply}

        if detail == "cpu":
            cpu = psutil.cpu_percent(interval=0.5)
            freq = psutil.cpu_freq()
            reply = (
                f"⚙️ CPU: {cpu:.0f}%"
                + (f"  ({freq.current:.0f} MHz)" if freq else "")
            )
            return {"ok": True, "reply": reply}

        if detail == "ram":
            m = psutil.virtual_memory()
            reply = (
                f"🧠 RAM: {m.percent:.0f}% used — "
                f"{_gb(m.used)} / {_gb(m.total)}  free {_gb(m.available)}"
            )
            return {"ok": True, "reply": reply}

        if detail == "network":
            net = psutil.net_io_counters()
            reply = (
                f"🌐 Network:\n"
                f"  Sent:     {_gb(net.bytes_sent)}\n"
                f"  Received: {_gb(net.bytes_recv)}"
            )
            return {"ok": True, "reply": reply}

        if detail == "processes":
            procs = sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                key=lambda p: p.info["cpu_percent"] or 0,
                reverse=True,
            )[:10]
            lines = [
                f"  {p.info['pid']:>6}  {(p.info['cpu_percent'] or 0):>5.1f}% CPU  "
                f"{(p.info['memory_percent'] or 0):>4.1f}% RAM  {p.info['name']}"
                for p in procs
            ]
            reply = "📋 <b>Top jarayonlar (CPU bo'yicha):</b>\n" + "\n".join(lines)
            return {"ok": True, "reply": reply}

        # full snapshot
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        boot = psutil.boot_time()
        import datetime, time
        uptime_sec = int(time.time() - boot)
        h, rem = divmod(uptime_sec, 3600)
        m_up, s_up = divmod(rem, 60)
        disk_lines = _disk_lines()

        reply = (
            f"🖥️ <b>Tizim holati</b>\n\n"
            f"⚙️ CPU:     {cpu:.0f}%\n"
            f"🧠 RAM:     {mem.percent:.0f}%  ({_gb(mem.used)} / {_gb(mem.total)})\n"
            f"⏱️ Uptime:  {h}h {m_up}m\n\n"
            f"💾 <b>Disklar:</b>\n" + "\n".join(disk_lines)
        )
        metrics = {
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "disks": [
                {
                    "device": p.device,
                    "percent": psutil.disk_usage(p.mountpoint).percent,
                    "free_gb": round(psutil.disk_usage(p.mountpoint).free / 1024**3, 1),
                    "total_gb": round(psutil.disk_usage(p.mountpoint).total / 1024**3, 1),
                }
                for p in psutil.disk_partitions(all=False)
                if _safe_disk(p.mountpoint)
            ],
        }
        return {"ok": True, "reply": reply, "metrics": metrics}


def _safe_disk(mount: str) -> bool:
    try:
        psutil.disk_usage(mount)
        return True
    except Exception:
        return False
