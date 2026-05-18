"""Working memory: hot in-process buffer + SQLite write-through for crash recovery."""
from __future__ import annotations

from collections import deque
from typing import Any

from .db import Database


class WorkingMemory:
    def __init__(self, db: Database, max_recent: int = 20) -> None:
        self.db = db
        self.max_recent = max_recent
        self._recent: deque[dict[str, Any]] = deque(maxlen=max_recent)
        # warm cache from DB on startup
        for row in self.db.fetchall(
            "SELECT id, role, text, source, ts FROM turns ORDER BY id DESC LIMIT ?",
            (max_recent,),
        ):
            self._recent.appendleft(
                {"id": row["id"], "role": row["role"], "text": row["text"], "ts": row["ts"]}
            )

    def add_turn(self, role: str, text: str, source: str = "unknown") -> int:
        cur = self.db.execute(
            "INSERT INTO turns(role, text, source) VALUES(?, ?, ?)",
            (role, text, source),
        )
        turn_id = cur.lastrowid or 0
        self._recent.append({"id": turn_id, "role": role, "text": text})
        return turn_id

    def recent_turns(self, n: int | None = None) -> list[dict[str, Any]]:
        n = n or self.max_recent
        return list(self._recent)[-n:]
