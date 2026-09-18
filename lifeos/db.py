"""LIFEOS run history — the proof that the run ran (brief rule 3).

Every attempt writes a row to ``runs`` the moment it *starts*, with no finish time.
``finish_run`` fills in the finish time and the per-source tallies. So a run that
dies mid-way leaves a started row with a NULL ``finished_at`` — silent death is
visible in the data, not hidden by a blank page. (Aman's last system died silently
for four months; this table exists so that can't recur.)

Tables
  runs         one row per attempt: started_at, finished_at (NULL until done),
               sources_ok, sources_unreachable, trigger, note
  run_sources  one row per source per run: name, status, detail, ms
  snapshots    the rendered HTML for a completed run (served as the static page)

Plain sqlite3 (sync) — the 06:30 job is sequential and this keeps the write path
simple and robust. Each call opens its own connection so it is thread-safe under
the scheduler + web server sharing one file.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .config import IST, db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at          TEXT NOT NULL,          -- ISO8601 IST
    finished_at         TEXT,                   -- NULL until the run completes
    sources_ok          INTEGER,
    sources_unreachable INTEGER,
    trigger             TEXT NOT NULL,          -- 'scheduled' | 'manual' | 'boot'
    note                TEXT
);
CREATE TABLE IF NOT EXISTS run_sources (
    run_id  INTEGER NOT NULL REFERENCES runs(id),
    name    TEXT NOT NULL,
    status  TEXT NOT NULL,                      -- 'ok' | 'unreachable' | 'blocked' | 'nil'
    detail  TEXT,
    ms      INTEGER,
    PRIMARY KEY (run_id, name)
);
CREATE TABLE IF NOT EXISTS snapshots (
    run_id   INTEGER PRIMARY KEY REFERENCES runs(id),
    html     TEXT NOT NULL,
    built_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nudges (
    fingerprint TEXT PRIMARY KEY,     -- stable key for the underlying issue
    created_at  TEXT NOT NULL         -- when we last filed this nudge to the Inbox
);
"""


def now_ist() -> datetime:
    return datetime.now(IST)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)


# ── run lifecycle ─────────────────────────────────────────────────────────────
def start_run(trigger: str) -> int:
    """Write the started row (no finish yet) and return its id.

    If the process dies before finish_run, this row remains with finished_at NULL —
    that is the whole point: it makes an incomplete run visible."""
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO runs (started_at, trigger) VALUES (?, ?)",
            (_iso(now_ist()), trigger),
        )
        return int(cur.lastrowid)


def record_source(
    run_id: int, name: str, status: str, detail: str = "", ms: int = 0
) -> None:
    """Record one source's outcome. Upsert so a re-run of the same source within a
    run overwrites cleanly."""
    with _conn() as c:
        c.execute(
            "INSERT INTO run_sources (run_id, name, status, detail, ms) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(run_id, name) DO UPDATE SET "
            "status=excluded.status, detail=excluded.detail, ms=excluded.ms",
            (run_id, name, status, detail, ms),
        )


def finish_run(run_id: int, sources_ok: int, sources_unreachable: int, note: str = "") -> None:
    with _conn() as c:
        c.execute(
            "UPDATE runs SET finished_at=?, sources_ok=?, sources_unreachable=?, note=? "
            "WHERE id=?",
            (_iso(now_ist()), sources_ok, sources_unreachable, note, run_id),
        )


def save_snapshot(run_id: int, html: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO snapshots (run_id, html, built_at) VALUES (?, ?, ?) "
            "ON CONFLICT(run_id) DO UPDATE SET html=excluded.html, built_at=excluded.built_at",
            (run_id, html, _iso(now_ist())),
        )


# ── reads for the page ────────────────────────────────────────────────────────
def latest_snapshot() -> Optional[str]:
    """The most recent rendered page, or None if no run has completed one yet."""
    with _conn() as c:
        row = c.execute(
            "SELECT html FROM snapshots ORDER BY run_id DESC LIMIT 1"
        ).fetchone()
        return row["html"] if row else None


def latest_run() -> Optional[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()


def sources_for_run(run_id: int) -> list[sqlite3.Row]:
    with _conn() as c:
        return list(
            c.execute(
                "SELECT * FROM run_sources WHERE run_id=? ORDER BY name", (run_id,)
            ).fetchall()
        )


def previous_incomplete_run(exclude_run_id: Optional[int] = None) -> Optional[sqlite3.Row]:
    """Return the most recent run that started but never finished, so the morning
    page can say 'the previous run did not complete'. Returns None if all runs
    finished.

    ``exclude_run_id`` skips the run currently in flight — at render time the active
    run's own row is still unfinished, so it must be excluded or every run would
    flag itself. Pass the current run_id when rendering mid-run."""
    with _conn() as c:
        if exclude_run_id is not None:
            return c.execute(
                "SELECT * FROM runs WHERE finished_at IS NULL AND id != ? "
                "ORDER BY id DESC LIMIT 1",
                (exclude_run_id,),
            ).fetchone()
        return c.execute(
            "SELECT * FROM runs WHERE finished_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()


def recent_runs(limit: int = 20) -> list[sqlite3.Row]:
    with _conn() as c:
        return list(
            c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        )


# ── nudges (evolving loop de-dup) ─────────────────────────────────────────────
def nudge_filed_recently(fingerprint: str, within_days: int) -> bool:
    """True if this exact nudge was already filed within the window — so the
    proactive loop doesn't recreate the same Inbox row every morning."""
    with _conn() as c:
        row = c.execute(
            "SELECT created_at FROM nudges WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
    if not row:
        return False
    try:
        last = datetime.fromisoformat(row["created_at"])
    except ValueError:
        return False
    return (now_ist() - last).days < within_days


def record_nudge(fingerprint: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO nudges (fingerprint, created_at) VALUES (?, ?) "
            "ON CONFLICT(fingerprint) DO UPDATE SET created_at=excluded.created_at",
            (fingerprint, _iso(now_ist())),
        )
