#!/usr/bin/env python3
"""MDO housekeeping — the routine memory purge (CHIEF_OF_STAFF.md §1.12)
and the system of record's backups (DEPLOY_HOSTINGER.md §10).

Runs on the VPS, inside the backend container, against the SQLite file
directly. Two modes, one bot, one heartbeat per run — every run, even when
it freed or copied nothing:

  --daily   snapshot every SQLite database the backend uses (VEGA_DB_PATH,
            VEDANTA_DB_PATH when set and present) with the sqlite3 backup API
            into BACKUP_DIR as <name>-YYYYMMDD.db.gz, verify each snapshot
            with PRAGMA integrity_check, then keep the newest 14. A failed
            snapshot or disk under 15% free is a critical finding.
  (weekly)  archive, trim, vacuum, measure; then take a fresh snapshot and
            bundle the latest snapshot of every database plus the vault
            (memory/, finance/) into ONE encrypted file
            BACKUP_DIR/weekly-YYYYMMDD.tar.enc (openssl aes-256-cbc, pbkdf2,
            passphrase VAULT_BACKUP_PASSPHRASE). Keeps the newest 8. Without a
            passphrase the bundle is skipped and the heartbeat says so.

The weekly bundle is the file the off-site door serves
(GET /api/vault/backup/latest) and the backup-offsite Routine copies to Drive.

Never touches: the Objectives sheet, agenda.yaml, COS_LOG.md, open
intel_items, open ops_tasks, open cos_jobs, the checks registry, bot_memory,
the decision log, or the last 20 turns of any chat.

Usage:  python mdo_housekeeping.py            (cron: weekly Sun 03:00 IST)
        python mdo_housekeeping.py --daily    (cron: daily 03:00 IST)
        python mdo_housekeeping.py --dry-run  (measure, change nothing; works with --daily)
"""
from __future__ import annotations

import contextlib
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
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

# Backups (DEPLOY_HOSTINGER.md §10). BACKUP_DIR is /data/backups on the VPS —
# inside the mdo-data volume, next to the database it protects.
BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(os.path.dirname(DB_PATH), "backups"))
KEEP_DAILY_SNAPSHOTS = int(os.environ.get("HK_KEEP_DAILY_SNAPSHOTS", "14"))
KEEP_WEEKLY_BUNDLES = int(os.environ.get("HK_KEEP_WEEKLY_BUNDLES", os.environ.get("HK_KEEP_VAULT_BACKUPS", "8")))
DAILY_DISK_CRIT_PCT_FREE = float(os.environ.get("HK_DAILY_DISK_CRIT_PCT_FREE", "15"))


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


VAULT_DIR = os.environ.get("VAULT_DIR", os.path.join(os.path.dirname(DB_PATH), "vault"))


def _mb(b: float) -> float:
    return b / 1_048_576


def _disk_pct_free(path: str) -> tuple[float, int]:
    """(% free, bytes free) of the filesystem holding `path` (or its parent)."""
    probe = path if os.path.isdir(path) else (os.path.dirname(path) or "/")
    if not os.path.exists(probe):
        probe = "/"
    usage = shutil.disk_usage(probe)
    return (usage.free / usage.total * 100 if usage.total else 0.0), usage.free


@contextlib.contextmanager
def _lock():
    """Serialise runs that share BACKUP_DIR. The daily cron (every day 21:30
    UTC) and the weekly one (Sat 21:30 UTC) fire in the same minute on
    Saturdays; whichever starts second waits here rather than racing the
    other for the same snapshot file."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    fd = os.open(os.path.join(BACKUP_DIR, ".housekeeping.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        except ImportError:   # not POSIX — run unlocked rather than not at all
            pass
        yield
    finally:
        os.close(fd)


# ── database snapshots (--daily) ─────────────────────────────────────────────
def db_paths() -> list[tuple[str, str]]:
    """Every SQLite file the backend uses, as (short name, path). The main
    database is always listed (run() refuses to start without it); the
    Vedanta CRM only when its variable is set and the file exists."""
    out = [("vega", DB_PATH)]
    vedanta = os.environ.get("VEDANTA_DB_PATH", "").strip()
    if vedanta and os.path.isfile(vedanta) and os.path.abspath(vedanta) != os.path.abspath(DB_PATH):
        out.append(("vedanta", vedanta))
    return out


def _integrity_ok(db_file: str) -> bool:
    c = sqlite3.connect(db_file)
    try:
        row = c.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"
    finally:
        c.close()


def verify_snapshot(gz_path: str) -> bool:
    """Decompress a <name>-YYYYMMDD.db.gz next to itself and integrity-check
    it. Used by the restore procedure and the tests; never deletes anything."""
    tmp = gz_path + ".verify"
    try:
        with gzip.open(gz_path, "rb") as src, open(tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return _integrity_ok(tmp)
    except (OSError, sqlite3.Error):
        return False
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def snapshot_db(name: str, src: str, dry: bool = False) -> dict:
    """Copy `src` with the sqlite3 online-backup API (consistent even while
    the backend writes), integrity-check the copy, gzip it to
    BACKUP_DIR/<name>-YYYYMMDD.db.gz, and only then prune older snapshots
    down to KEEP_DAILY_SNAPSHOTS. A snapshot that fails the check is
    discarded and nothing older is touched."""
    res = {"name": name, "src": src, "bytes": os.path.getsize(src) if os.path.exists(src) else 0,
           "ok": False, "file": "", "kept": 0, "note": ""}
    if not os.path.isfile(src):
        res["note"] = "source missing"
        return res
    stamp = datetime.now(IST).strftime("%Y%m%d")
    final = os.path.join(BACKUP_DIR, f"{name}-{stamp}.db.gz")
    existing = sorted(f for f in os.listdir(BACKUP_DIR)
                      if f.startswith(f"{name}-") and f.endswith(".db.gz")) if os.path.isdir(BACKUP_DIR) else []
    if dry:
        res.update(ok=True, file=os.path.basename(final), kept=len(existing), note="dry run")
        return res
    os.makedirs(BACKUP_DIR, exist_ok=True)
    raw = final[:-3] + ".tmp"          # <name>-YYYYMMDD.db.tmp — plain copy, verified, then gzipped
    tmp_gz = final + ".tmp"
    try:
        src_c = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=60)
        try:
            dst_c = sqlite3.connect(raw)
            try:
                src_c.backup(dst_c)
            finally:
                dst_c.close()
        finally:
            src_c.close()
        if not _integrity_ok(raw):
            res["note"] = "integrity_check FAILED — snapshot discarded, older ones kept"
            return res
        with open(raw, "rb") as f_in, gzip.open(tmp_gz, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.chmod(tmp_gz, 0o600)
        os.replace(tmp_gz, final)
    except (OSError, sqlite3.Error) as e:
        res["note"] = f"snapshot FAILED — {e}"
        return res
    finally:
        for f in (raw, tmp_gz):
            if os.path.exists(f):
                os.remove(f)
    # Prune only after a verified snapshot landed.
    files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(f"{name}-") and f.endswith(".db.gz"))
    for f in files[:-KEEP_DAILY_SNAPSHOTS] if KEEP_DAILY_SNAPSHOTS > 0 else []:
        os.remove(os.path.join(BACKUP_DIR, f))
    res.update(ok=True, file=os.path.basename(final), kept=min(len(files), KEEP_DAILY_SNAPSHOTS),
               snapshot_bytes=os.path.getsize(final))
    return res


def latest_snapshots() -> list[str]:
    """Newest <name>-YYYYMMDD.db.gz per database name in BACKUP_DIR (full paths)."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    newest: dict[str, str] = {}
    for f in sorted(os.listdir(BACKUP_DIR)):
        if f.endswith(".db.gz") and "-" in f and not f.endswith(".tmp"):
            newest[f.rsplit("-", 1)[0]] = f
    return [os.path.join(BACKUP_DIR, f) for _, f in sorted(newest.items())]


def run_daily(dry: bool = False) -> int:
    """--daily: snapshot every database, keep 14, say so in one line."""
    if not os.path.exists(DB_PATH):
        _report("error", f"daily: database not found at {DB_PATH}", cadence="daily")
        return 2
    with _lock():
        results = [snapshot_db(name, path, dry) for name, path in db_paths()]
    pct_free, free_b = _disk_pct_free(BACKUP_DIR)
    parts = []
    for r in results:
        if r["ok"]:
            parts.append(f"{r['name']} {_mb(r['bytes']):.1f} MB snapshot {'would be taken (dry run)' if dry else 'ok'} · {r['kept']} kept")
        else:
            parts.append(f"{r['name']} {_mb(r['bytes']):.1f} MB snapshot FAILED ({r['note']})")
    summary = f"{'DRY RUN — ' if dry else ''}daily: " + " · ".join(parts) + f" · disk {pct_free:.0f}% free ({_mb(free_b):,.0f} MB)"
    findings: list[dict] = []
    for r in results:
        if not r["ok"]:
            findings.append({"level": "critical", "title": f"DB snapshot failed: {r['name']}",
                             "detail": f"{r['src']}: {r['note']}", "action": "run `python mdo_housekeeping.py --daily` by hand and read the log",
                             "owner": "CoS", "domain": "projects"})
    if pct_free < DAILY_DISK_CRIT_PCT_FREE:
        summary = f"🔴 DISK LOW: {pct_free:.0f}% free. " + summary
        findings.append({"level": "critical", "title": f"VPS disk {pct_free:.0f}% free",
                         "detail": summary, "action": "free space or enlarge the volume", "owner": "Aman",
                         "domain": "projects"})
    status = "warning" if findings else "clean"
    log(summary)
    _report(status, summary, findings=findings, cadence="daily")
    return 0


# ── weekly bundle: vault + latest DB snapshots, one encrypted file ────────────
def backup_bundle(dry: bool) -> str:
    """Weekly encrypted bundle BACKUP_DIR/weekly-YYYYMMDD.tar.enc holding
    vault/ (memory/ + finance/) and db/<name>-YYYYMMDD.db.gz (the newest
    snapshot per database). AES-256-CBC, pbkdf2, passphrase in
    VAULT_BACKUP_PASSPHRASE. Without a passphrase the bundle is skipped and
    said so — an unencrypted copy of the finance workbook is not a backup, it
    is a leak. Keeps the newest KEEP_WEEKLY_BUNDLES. Returns one note for the
    heartbeat line."""
    vault_files = sum(len(f) for _, _, f in os.walk(VAULT_DIR)) if os.path.isdir(VAULT_DIR) else 0
    snaps = latest_snapshots()
    what = " + ".join(x for x in (f"vault {vault_files} files" if vault_files else "",
                                  f"{len(snaps)} db snapshot{'s' if len(snaps) != 1 else ''}" if snaps else "") if x)
    if not vault_files and not snaps:
        return "bundle: nothing to back up yet (no vault, no snapshots)"
    passphrase = os.environ.get("VAULT_BACKUP_PASSPHRASE", "").strip()
    if not passphrase:
        return f"bundle: {what}, backup SKIPPED — set VAULT_BACKUP_PASSPHRASE in .env"
    if dry:
        return f"bundle: {what} would be bundled (dry run)"
    os.makedirs(BACKUP_DIR, exist_ok=True)
    out = os.path.join(BACKUP_DIR, f"weekly-{datetime.now(IST):%Y%m%d}.tar.enc")
    tar_tmp = out[:-4] + ".tmp"      # weekly-YYYYMMDD.tar.tmp — plain tar, lives seconds, same volume as the raw DB
    enc_tmp = out + ".tmp"
    try:
        with tarfile.open(tar_tmp, "w") as tar:
            if vault_files:
                tar.add(VAULT_DIR, arcname="vault")
            for p in snaps:
                tar.add(p, arcname="db/" + os.path.basename(p))
        os.chmod(tar_tmp, 0o600)
        subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-pass", "env:VAULT_BACKUP_PASSPHRASE",
                        "-in", tar_tmp, "-out", enc_tmp], check=True, capture_output=True,
                       env={**os.environ, "VAULT_BACKUP_PASSPHRASE": passphrase})
        os.chmod(enc_tmp, 0o600)
        os.replace(enc_tmp, out)
    except FileNotFoundError as e:
        return f"bundle: backup FAILED — {e.filename} not installed in the image"
    except subprocess.CalledProcessError as e:
        return f"bundle: backup FAILED — {e.stderr.decode(errors='replace')[-120:]}"
    except OSError as e:
        return f"bundle: backup FAILED — {e}"
    finally:
        for f in (tar_tmp, enc_tmp):
            if os.path.exists(f):
                os.remove(f)
    bundles = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("weekly-") and f.endswith(".tar.enc"))
    for f in bundles[:-KEEP_WEEKLY_BUNDLES] if KEEP_WEEKLY_BUNDLES > 0 else []:
        os.remove(os.path.join(BACKUP_DIR, f))
    return (f"bundle: {what} → {os.path.basename(out)} ({_mb(os.path.getsize(out)):.1f} MB, AES-256) · "
            f"{min(len(bundles), KEEP_WEEKLY_BUNDLES)} kept")


def run(dry: bool = False) -> int:
    if not os.path.exists(DB_PATH):
        _report("error", f"database not found at {DB_PATH}")
        return 2
    with _lock():
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
                c, "media_extractions", "created_at < ?", (_cutoff(KEEP_EXTRACT_DAYS),), "extractions", dry)
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
        # Fresh post-vacuum snapshot of every database, then the bundle holds today's copy.
        snaps = [snapshot_db(name, path, dry) for name, path in db_paths()]
        bundle_note = backup_bundle(dry)
    for r in snaps:
        log(f"snapshot {r['name']}: {'ok' if r['ok'] else 'FAILED'} {r['note']}".rstrip())
    log(bundle_note)
    pct_free, free_b = _disk_pct_free(os.path.dirname(DB_PATH) or "/")
    archives = len(os.listdir(ARCHIVE_DIR)) if os.path.isdir(ARCHIVE_DIR) else 0
    snap_note = " · ".join(
        f"{r['name']} snapshot {'ok' if r['ok'] else 'FAILED'} ({r['kept']} kept)" if r["ok"] else f"{r['name']} snapshot FAILED"
        for r in snaps)

    rows = sum(freed.values())
    summary = (f"{'DRY RUN — ' if dry else ''}archived {rows} rows "
               f"({', '.join(f'{k} {v}' for k, v in freed.items() if v)}) · "
               f"db {_mb(before):.1f}→{_mb(after):.1f} MB · disk {pct_free:.0f}% free "
               f"({_mb(free_b):,.0f} MB) · {archives} archive files · {snap_note} · {bundle_note}")
    status = "clean"
    findings: list[dict] = []
    if "FAILED" in bundle_note or "SKIPPED" in bundle_note or any(not r["ok"] for r in snaps):
        status = "warning"
    if pct_free < DISK_ALERT_PCT_FREE:
        status = "warning"
        summary = f"🔴 DISK LOW: {pct_free:.0f}% free. " + summary
        findings.append({"level": "critical", "title": f"VPS disk {pct_free:.0f}% free",
                         "detail": summary, "action": "free space or enlarge the volume", "owner": "Aman",
                         "domain": "projects"})
    for r in snaps:
        if not r["ok"]:
            findings.append({"level": "critical", "title": f"DB snapshot failed: {r['name']}",
                             "detail": f"{r['src']}: {r['note']}", "action": "run `python mdo_housekeeping.py --daily` by hand and read the log",
                             "owner": "CoS", "domain": "projects"})
    log(summary)
    _report(status, summary, findings=findings)
    return 0


def _report(status: str, summary: str, findings: list | None = None, cadence: str = "weekly") -> None:
    if not KEY:
        log("MDO_AUTH_TOKEN not set — heartbeat not filed: " + summary)
        return
    try:
        req = urllib.request.Request(
            BASE + "/api/agent/report",
            data=json.dumps({"bot": "housekeeping", "cadence": cadence, "heartbeat": not findings,
                             "status": status, "agent": "housekeeping (vps)",
                             "title": f"housekeeping {cadence}: {status}", "summary": summary,
                             "body": "", "findings": findings or [], "checks_run": []}).encode(),
            headers={"X-MDO-Key": KEY, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        log("heartbeat filed")
    except Exception as e:
        log(f"FATAL: heartbeat could not be filed: {e}")


if __name__ == "__main__":
    _dry = "--dry-run" in sys.argv
    sys.exit(run_daily(dry=_dry) if "--daily" in sys.argv else run(dry=_dry))
