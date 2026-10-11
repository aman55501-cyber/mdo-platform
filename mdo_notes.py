"""Research notes — what Claude (the in-app Brain, or a session) found and Aman wants kept. Saved on the VPS, searchable.

Aman, chat 2026-10-11: "the app connected to Claude for research, and progress saving in Claude or the VPS wherever convenient."
Convenient = the VPS: one table, one endpoint, three Brain tools (save_note / list_notes / get_note), so a WhatsApp or app
question like "research X and save it" lands as a note he can reopen from the phone. No LLM in this module.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from fastapi import HTTPException

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
    title TEXT NOT NULL, body TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT ''
);
"""


def register(app, vdb: Callable[[], Awaitable[Any]]) -> dict:
    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def add_note(title: str, body: str, tags: str = "", source: str = "") -> dict:
        title, body = str(title or "").strip()[:200], str(body or "").strip()[:60000]
        if not title or not body:
            raise HTTPException(400, "title and body are required")
        db = await vdb()
        await ensure_schema(db)
        cur = await db.execute("INSERT INTO notes (title, body, tags, source) VALUES (?,?,?,?)", (title, body, str(tags or "")[:200], str(source or "")[:60]))
        await db.commit()
        return {"id": cur.lastrowid, "title": title}

    async def list_notes(q: str = "", limit: int = 20) -> dict:
        db = await vdb()
        await ensure_schema(db)
        limit = max(1, min(int(limit or 20), 100))
        if q:
            like = f"%{q.strip()}%"
            rows = await db.execute_fetchall("SELECT id, created_at, title, tags, source, substr(body,1,200) AS preview FROM notes "
                                             "WHERE title LIKE ? OR body LIKE ? OR tags LIKE ? ORDER BY id DESC LIMIT ?", (like, like, like, limit))
        else:
            rows = await db.execute_fetchall("SELECT id, created_at, title, tags, source, substr(body,1,200) AS preview FROM notes ORDER BY id DESC LIMIT ?", (limit,))
        return {"notes": [dict(r) for r in rows]}

    async def get_note(note_id: int) -> dict:
        db = await vdb()
        await ensure_schema(db)
        rows = await db.execute_fetchall("SELECT * FROM notes WHERE id=?", (int(note_id),))
        if not rows:
            raise HTTPException(404, f"no note #{note_id}")
        return dict(rows[0])

    @app.get("/api/notes")
    async def notes_list(q: str = "", limit: int = 20):
        return await list_notes(q, limit)

    @app.post("/api/notes")
    async def notes_post(body: dict):
        return await add_note(body.get("title", ""), body.get("body", ""), body.get("tags", ""), body.get("source", "app"))

    @app.get("/api/notes/{note_id}")
    async def notes_get(note_id: int):
        return await get_note(note_id)

    return {"ensure_schema": ensure_schema, "add_note": add_note, "list_notes": list_notes, "get_note": get_note}
