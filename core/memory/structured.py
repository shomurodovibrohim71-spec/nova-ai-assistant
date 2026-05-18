"""Structured memory: typed CRUD over prefs / shortcuts / facts / notes."""
from __future__ import annotations

import json
from typing import Any

from .db import Database


class StructuredMemory:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- facts ----
    def remember_fact(self, category: str, content: str) -> int:
        content = content.strip()
        existing = self.db.fetchone("SELECT id FROM facts WHERE content=?", (content,))
        if existing:
            return int(existing["id"])
        cur = self.db.execute(
            "INSERT INTO facts(category, content) VALUES(?, ?)", (category, content)
        )
        return cur.lastrowid or 0

    def list_facts(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.fetchall(
            "SELECT id, category, content, ts FROM facts ORDER BY id DESC"
        )]

    def search_facts(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        like = f"%{query}%"
        return [dict(r) for r in self.db.fetchall(
            "SELECT id, category, content, ts FROM facts "
            "WHERE content LIKE ? OR category LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            (like, like, limit),
        )]

    def delete_fact(self, fact_id: int) -> int:
        return self.db.execute("DELETE FROM facts WHERE id=?", (fact_id,)).rowcount

    # ---- prefs ----
    def set_pref(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO prefs(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, value),
        )

    def get_pref(self, key: str) -> str | None:
        row = self.db.fetchone("SELECT value FROM prefs WHERE key=?", (key,))
        return row["value"] if row else None

    def list_prefs(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.db.fetchall("SELECT key, value, updated_at FROM prefs")]

    # ---- shortcuts ----
    def set_shortcut(self, alias: str, apps: list[str]) -> None:
        self.db.execute(
            "INSERT INTO app_shortcuts(alias, apps) VALUES(?, ?) "
            "ON CONFLICT(alias) DO UPDATE SET apps=excluded.apps, updated_at=CURRENT_TIMESTAMP",
            (alias, json.dumps(apps)),
        )

    def get_shortcut(self, alias: str) -> list[str] | None:
        row = self.db.fetchone("SELECT apps FROM app_shortcuts WHERE alias=?", (alias,))
        return json.loads(row["apps"]) if row else None

    def list_shortcuts(self) -> list[dict[str, Any]]:
        rows = self.db.fetchall("SELECT alias, apps FROM app_shortcuts")
        return [{"alias": r["alias"], "apps": json.loads(r["apps"])} for r in rows]
