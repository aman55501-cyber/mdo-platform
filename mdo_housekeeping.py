#!/usr/bin/env python3
"""MDO housekeeping — the routine memory purge (CHIEF_OF_STAFF.md §1.12).

Runs weekly on the VPS, inside the backend container, against the SQLite
file directly. It archives, trims, vacuums and measures, then files ONE
heartbeat that says exactly what it freed and how much room is left — every
run, even when it freed nothing.

Never touches: the Objectives sheet, agenda.yaml, COS_LOG.md, open
intel_items, open ops_tasks, open cos_jobs, the checks registry, bot_memory,
the decision log, or the last 20 turns of any chat.

Usage:  python mdo_housekeeping.py            (cron: weekly Sun 03:00 IST)
        python mdo_housekeeping.py --dry-run  (measure, change nothing)
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

from mdo_cos import IST

DB_PATH = os.environ.get("VEGA_DB_PATH", os.environ.get("DB_PATH", "/data/vega_data.db"))
ARCHIVE_DIR = os.environ.get("MDO_ARCHIVE_DIR", os.path.join(os.path.dirname(DB_PATH), "archive"))
BASE = os.environ.get("MDO_SELF_URL", "http://localhost:8501")
KEY = os.environ.get("MDO_AUTH_TOKEN", "").strip()

KEEP_REPORT_DAYS = int(os.environ.get("HK_KEEP_REPORT_DAYS", "60"))
KEEP_WA_DAYS = int(os.environ.get("HK_KEEP_WA_DAYS", "90"))
KEEP_EXTRACT_DAYS = int(os.environ.get("HK_KEEP_EXTRACT_DAYS", "180"))
KEEP_RUN_DAYS = int(os.environ.get("HK_KEEP_RUN_DAYS", "90"))
KEEP_SPEND_DAYS = int(os.environ.get("HK_KEEP_SPEND_DAYS", "400"))
KEEP_CHAT_TURNS = int(os.environ.get("HK_KEEP_CHAT_TURNS", "20"))
KEEP_CHAT_DAYS = int(os.environ.get("HK_KEEP_CHAT_DAYS", "30"))
DISK_ALERT_PCT_FREE = float(os.environ.get("HK_DISK_ALERT_PCT_FREE", "20"))


def log(msg: str) -> None:
    print(f"[{datetime.now(IST):%Y-%m-%d %H:%M:%S} IST] housekeeping: {msg}", flush=True)


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _table_exists(c: sqlite3.Connection, name: str) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _archive_rows(c: sqlite3.Connection, table: str, where: str, params: tuple, label: str, dry: bool) -> int:
    """Append matching rows to archive/<label>-YYYY-MM.jsonl.gz, then delete them."""
    if not _table_exists(c, table):
        return 0
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]
    if not rows or dry:
        return len(rows)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y-%m")
    path = os.path.join(ARCHIVE_DIR, f"{label}-{stamp}.jsonl.gz")
    with gzip.open(path, "at", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    c.execute(f"DELETE FROM {table} WHERE {where}", params)
    return len(rows)


def compact_chats(c: sqlite3.Connection, dry: bool) -> int:
    """Per chat: keep the newest KEEP_CHAT_TURNS turns; archive older turns
    that are also older than KEEP_CHAT_DAYS. The brain keeps a rolling summary
    in cos_chat_summary so nothing important is lost."""
    if not _table_exists(c, "cos_chat"):
        return 0
    removed = 0
    chats = [r[0] for r in c.execute("SELECT DISTINCT chat_id FROM cos_chat").fetchall()]
    for chat in chats:
        ids = [r[0] for r in c.execute(
            "SELECT id FROM cos_chat WHERE chat_id=? ORDER BY id DESC LIMIT -1 OFFSET ?",
            (chat, KEEP_CHAT_TURNS)).fetchall()]
        if not ids:
            continue
        marks = ",".join("?" * len(ids))
        old_turns = c.execute(
            f"SELECT role, content FROM cos_chat WHERE id IN ({marks}) AND created_at < ? ORDER BY id",
            (*ids, _cutoff(KEEP_CHAT_DAYS))).fetchall()
        if old_turns and not dry:
            _roll_summary(c, chat, [(r[0], r[1]) for r in old_turns])
        removed += _archive_rows(
            c, "cos_chat", f"id IN ({marks}) AND created_at < ?", (*ids, _cutoff(KEEP_CHAT_DAYS)), "chat", dry)
    return removed


def _roll_summary(c: sqlite3.Connection, chat_id: str, turns: list[tuple[str, str]]) -> None:
    """Fold the turns about to be archived into cos_chat_summary so the brain
    keeps the gist. Uses Haiku when a key exists; otherwise keeps a plain
    extract of the last lines, so the summary is never silently empty."""
    prev = c.execute("SELECT summary FROM cos_chat_summary WHERE chat_id=?", (chat_id,)).fetchone()
    prev = prev[0] if prev else ""
    transcript = "\n".join(f"{r}: {t[:600]}" for r, t in turns)[:30000]
    summary = ""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        try:
            payload = json.dumps({
                "model": "claude-haiku-4-5", "max_tokens": 1200,
                "messages": [{"role": "user", "content":
                    "Rolling memory for Aman Agrawal's Chief of Staff. Merge the EXISTING SUMMARY and the "
                    "NEW TURNS into one summary under 250 words: decisions Aman made, standing preferences he "
                    "stated, open threads, names and dates. Keep every number with its source turn; drop "
                    "pleasantries. Never invent.\n\nEXISTING SUMMARY:\n" + prev + "\n\nNEW TURNS:\n" + transcript}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=payload,
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
            summary = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()
            usage = resp.get("usage") or {}
            _record_spend("claude-haiku-4-5", int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0))
        except Exception as e:
            log(f"summary model call failed for chat {chat_id}: {e} — falling back to extract")
    if not summary:
        tail = "\n".join(f"{r}: {t[:160]}" for r, t in turns[-12:])
        summary = (prev + "\n" if prev else "") + f"[extract {datetime.now(IST):%Y-%m-%d}]\n" + tail
        summary = summary[-6000:]
    c.execute(
        "INSERT INTO cos_chat_summary (chat_id, summary, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(chat_id) DO UPDATE SET summary=excluded.summary, updated_at=datetime('now')",
        (chat_id, summary))


def _record_spend(model: str, inp: int, out: int) -> None:
    if not KEY:
        return
    try:
        req = urllib.request.Request(
            BASE + "/api/spend/record",
            data=json.dumps({"bot": "housekeeping", "model": model, "input_tokens": inp, "output_tokens": out}).encode(),
            headers={"X-MDO-Key": KEY, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:
        log(f"spend not recorded: {e}")


def run(dry: bool = False) -> int:
    if not os.path.exists(DB_PATH):
        _report("error", f"database not found at {DB_PATH}")
        return 2
    before = os.path.getsize(DB_PATH)
    c = sqlite3.connect(DB_PATH, timeout=60)
    freed: dict[str, int] = {}
    try:
        freed["reports"] = _archive_rows(
            c, "agent_reports", "created_at < ?", (_cutoff(KEEP_REPORT_DAYS),), "reports", dry)
        freed["wa_messages"] = _archive_rows(
            c, "whatsapp_messages", "created_at < ? AND COALESCE(flagged,0)=0",
            (_cutoff(KEEP_WA_DAYS),), "whatsapp", dry)
        freed["extractions"] = _archive_rows(
            c, "whatsapp_extractions", "created_at < ?", (_cutoff(KEEP_EXTRACT_DAYS),), "extractions", dry)
        freed["runs"] = _archive_rows(
            c, "cos_runs", "created_at < ?", (_cutoff(KEEP_RUN_DAYS),), "runs", dry)
        freed["spend"] = _archive_rows(
            c, "spend_ledger", "created_at < ?", (_cutoff(KEEP_SPEND_DAYS),), "spend", dry)
        freed["closed_intel"] = _archive_rows(
            c, "intel_items", "status != 'open' AND updated_at < ?", (_cutoff(KEEP_REPORT_DAYS),), "intel", dry)
        freed["done_jobs"] = _archive_rows(
            c, "cos_jobs", "status IN ('done','rejected','skipped') AND updated_at < ?",
            (_cutoff(KEEP_REPORT_DAYS),), "jobs", dry)
        freed["chat_turns"] = compact_chats(c, dry)
        c.commit()
        if not dry:
            c.execute("VACUUM")
    finally:
        c.close()

    after = os.path.getsize(DB_PATH)
    usage = shutil.disk_usage(os.path.dirname(DB_PATH) or "/")
    pct_free = usage.free / usage.total * 100 if usage.total else 0
    archives = len(os.listdir(ARCHIVE_DIR)) if os.path.isdir(ARCHIVE_DIR) else 0
    mb = lambda b: b / 1_048_576  # noqa: E731

    rows = sum(freed.values())
    summary = (f"{'DRY RUN — ' if dry else ''}archived {rows} rows "
               f"({', '.join(f'{k} {v}' for k, v in freed.items() if v)}) · "
               f"db {mb(before):.1f}→{mb(after):.1f} MB · disk {pct_free:.0f}% free "
               f"({mb(usage.free):,.0f} MB) · {archives} archive files")
    status = "clean"
    if pct_free < DISK_ALERT_PCT_FREE:
        status = "warning"
        summary = f"🔴 DISK LOW: {pct_free:.0f}% free. " + summary
    log(summary)
    _report(status, summary, findings=(
        [{"level": "critical", "title": f"VPS disk {pct_free:.0f}% free",
          "detail": summary, "action": "free space or enlarge the volume", "owner": "Aman",
          "domain": "projects"}] if status == "warning" else []))
    return 0


def _report(status: str, summary: str, findings: list | None = None) -> None:
    if not KEY:
        log("MDO_AUTH_TOKEN not set — heartbeat not filed: " + summary)
        return
    try:
        req = urllib.request.Request(
            BASE + "/api/agent/report",
            data=json.dumps({"bot": "housekeeping", "cadence": "weekly", "heartbeat": not findings,
                             "status": status, "agent": "housekeeping (vps)",
                             "title": f"housekeeping: {status}", "summary": summary,
                             "body": "", "findings": findings or [], "checks_run": []}).encode(),
            headers={"X-MDO-Key": KEY, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        log("heartbeat filed")
    except Exception as e:
        log(f"FATAL: heartbeat could not be filed: {e}")


if __name__ == "__main__":
    sys.exit(run(dry="--dry-run" in sys.argv))
