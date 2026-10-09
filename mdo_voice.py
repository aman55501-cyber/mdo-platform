"""voice — WhatsApp voice notes transcribed on the VPS, no API, zero LLM spend.

The Baileys bridges (whatsapp_bridge/index.js ≥ 2.2) forward audio / voice messages (audioMessage, ptt) of the
chats they already forward as text: the clip is downloaded with downloadMediaMessage and POSTed as multipart to
POST /api/wa/media (same X-MDO-Key as text) with the fields account, chat_jid, chat_name, sender, message_id,
mimetype, duration_seconds, file (+ timestamp, from_me, chat_kind). The backend keeps the file under the data
dir (voice/<date>/<message_id>.ogg) and one row in wa_media (message_id UNIQUE; status pending → done | failed).
The personal-chat gate of mdo_wa_intel applies: a chat classified personal stores nothing, not even the file.

Transcription: faster-whisper (CTranslate2, CPU, int8), model VOICE_MODEL (default "small"; "base" if the VPS is
slow), language auto (Hindi/English mix), model files cached in VOICE_MODEL_DIR (default <data dir>/whisper-models,
i.e. the mdo-data volume, so a rebuild does not re-download them). ffmpeg/PyAV decode ogg/opus. The bot
`python mdo_agent.py voice` runs every 10 min 07:00–22:00 IST (POST /api/wa/media/transcribe): the pending rows,
oldest first, at most VOICE_MAX_PER_RUN (20) and time-boxed to VOICE_BUDGET_S (480 s). Each transcript is written
back into the message store (whatsapp_messages, through mdo_wa_intel's ingest — the same path the bridge text
takes) as a text message "[voice transcript] …" with voice=1 and wa_msg_id "<message_id>:voice", so wa-sweep and
wa-intel treat it like any text.

Heartbeat every run, even when nothing is pending: "voice: N transcribed, P pending, F failed, model small,
avg Xs/clip". faster-whisper missing → "voice: faster-whisper not installed — nothing transcribed" (a warning,
exit 0), never a crash (Directive 5). The pure helpers above register() take plain values and touch nothing;
tests/test_voice.py runs them with a fake faster_whisper module — no model is ever downloaded in tests.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request

from mdo_cos import IST

BOT_ID = "voice"
MODEL_DEFAULT = "small"
MAX_PER_RUN_DEFAULT = 20
BUDGET_S_DEFAULT = 480
MAX_MB_DEFAULT = 20
TRANSCRIPT_TAG = "[voice transcript]"
NOT_INSTALLED_LINE = f"{BOT_ID}: faster-whisper not installed — nothing transcribed"
STATUSES = ("pending", "done", "failed")
EXT_BY_MIME = {"audio/ogg": ".ogg", "application/ogg": ".ogg", "audio/opus": ".ogg", "audio/mpeg": ".mp3", "audio/mp3": ".mp3",
               "audio/mp4": ".m4a", "audio/m4a": ".m4a", "audio/x-m4a": ".m4a", "audio/aac": ".aac", "audio/wav": ".wav",
               "audio/x-wav": ".wav", "audio/webm": ".webm", "audio/amr": ".amr"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,                  -- the WhatsApp message id (dedupe key)
    account TEXT NOT NULL DEFAULT '1',
    chat_jid TEXT NOT NULL DEFAULT '',
    chat_name TEXT NOT NULL DEFAULT '',
    chat_kind TEXT NOT NULL DEFAULT 'group',          -- group | dm
    sender TEXT NOT NULL DEFAULT '',
    from_me INTEGER NOT NULL DEFAULT 0,
    received_at TEXT,                                 -- ISO UTC (the message timestamp)
    mimetype TEXT NOT NULL DEFAULT '',
    path TEXT NOT NULL DEFAULT '',                    -- relative to the voice dir: <date>/<message_id>.ogg
    bytes INTEGER NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0,                 -- seconds, as the bridge reported
    transcript TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',           -- pending | done | failed
    error TEXT NOT NULL DEFAULT '',
    seconds REAL NOT NULL DEFAULT 0,                  -- processing time
    attempts INTEGER NOT NULL DEFAULT 0,
    store_msg_id INTEGER,                             -- whatsapp_messages.id of the transcript row
    created_at TEXT DEFAULT (datetime('now')),
    done_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_wa_media_status ON wa_media(status, id);
CREATE TABLE IF NOT EXISTS wa_media_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at TEXT DEFAULT (datetime('now')),
    transcribed INTEGER DEFAULT 0, pending INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
    model TEXT DEFAULT '', avg_s REAL DEFAULT 0, line TEXT DEFAULT ''
);
"""


# ═════════════════════════════════════════════════════════════════════════════
# Pure helpers — no database, no network
# ═════════════════════════════════════════════════════════════════════════════
def model_name() -> str:
    return (os.environ.get("VOICE_MODEL") or MODEL_DEFAULT).strip() or MODEL_DEFAULT


def _int_env(key: str, default: int, lo: int = 1, hi: int = 100000) -> int:
    try:
        return max(lo, min(int(os.environ.get(key, "") or default), hi))
    except ValueError:
        return default


def max_per_run() -> int:
    return _int_env("VOICE_MAX_PER_RUN", MAX_PER_RUN_DEFAULT, 1, 500)


def budget_s() -> int:
    return _int_env("VOICE_BUDGET_S", BUDGET_S_DEFAULT, 10, 3600)


def max_bytes() -> int:
    return _int_env("VOICE_MAX_MB", MAX_MB_DEFAULT, 1, 200) * 1024 * 1024


def data_dir() -> str:
    return os.path.dirname(os.path.abspath(os.environ.get("VEGA_DB_PATH", "/data/vega_data.db")))


def voice_dir() -> str:
    return os.environ.get("VOICE_DIR", "").strip() or os.path.join(data_dir(), "voice")


def model_dir() -> str:
    return os.environ.get("VOICE_MODEL_DIR", "").strip() or os.path.join(data_dir(), "whisper-models")


def _mono() -> float:
    return time.monotonic()


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def ext_for(mimetype: str) -> str:
    base = str(mimetype or "").split(";")[0].strip().lower()
    return EXT_BY_MIME.get(base, ".ogg" if "ogg" in base or "opus" in base else ".bin")


def safe_id(message_id: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(message_id or "")).strip("._-")
    return s[:120] or "msg"


def media_rel_path(received_at: str | None, message_id: str, mimetype: str) -> str:
    """voice/<date>/<message_id>.ogg — the date is the message's IST day."""
    try:
        d = datetime.fromisoformat(str(received_at or "").replace("Z", "+00:00")) if received_at else datetime.now(timezone.utc)
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        d = datetime.now(timezone.utc)
    return f"{d.astimezone(IST):%Y-%m-%d}/{safe_id(message_id)}{ext_for(mimetype)}"


def load_model(name: str | None = None, cache_dir: str | None = None):
    """A faster_whisper.WhisperModel on CPU, int8. Raises when faster-whisper is missing or the model cannot load."""
    from faster_whisper import WhisperModel
    name = name or model_name()
    cache_dir = cache_dir or model_dir()
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError:
        cache_dir = None
    kwargs = {"device": "cpu", "compute_type": "int8"}
    if cache_dir:
        kwargs["download_root"] = cache_dir
    return WhisperModel(name, **kwargs)


def transcribe_file(model, path: str) -> dict:
    """{text, language, duration} — language auto-detected (Hindi/English mix), VAD on, greedy decoding."""
    segments, info = model.transcribe(path, language=None, beam_size=1, vad_filter=True)
    text = " ".join(str(getattr(s, "text", "") or "").strip() for s in segments).strip()
    text = re.sub(r"\s+", " ", text)
    return {"text": text, "language": str(getattr(info, "language", "") or ""),
            "duration": float(getattr(info, "duration", 0) or 0)}


def transcript_body(row: dict, text: str) -> dict:
    """The message-store body for a transcript — the same shape the bridge posts for text."""
    jid = str(row.get("chat_jid") or "")
    kind = str(row.get("chat_kind") or ("group" if jid.endswith("@g.us") else "dm"))
    return {"account": str(row.get("account") or "1"), "group": str(row.get("chat_name") or ""),
            "sender": str(row.get("sender") or ""), "text": f"{TRANSCRIPT_TAG} {text}"[:2000],
            "timestamp": str(row.get("received_at") or ""), "jid": jid, "chat_jid": jid, "chat_kind": kind,
            "from_me": int(row.get("from_me") or 0), "wa_msg_id": f"{row.get('message_id')}:voice"}


def heartbeat_line(transcribed: int, pending: int, failed: int, model: str, avg_s: float | None) -> str:
    """"voice: N transcribed, P pending, F failed, model small, avg Xs/clip"."""
    avg = f"{avg_s:.0f}" if avg_s else "0"
    return f"{BOT_ID}: {transcribed} transcribed, {pending} pending, {failed} failed, model {model}, avg {avg}s/clip"


def _parse_now(v: Any) -> datetime:
    if isinstance(v, datetime):
        d = v
    elif v:
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            d = datetime.now(IST)
    else:
        d = datetime.now(IST)
    return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(IST)


# ═════════════════════════════════════════════════════════════════════════════
# Registration — tables, endpoints, the run the bot triggers
# ═════════════════════════════════════════════════════════════════════════════
def register(app, vdb: Callable[[], Awaitable[Any]], ingest: Callable[..., Awaitable[dict]] | None = None) -> dict:
    """Mount /api/wa/media*. `ingest` is mdo_wa_intel.register()['ingest'] — the one path into whatsapp_messages
    (chat upsert, personal gate, dedupe on wa_msg_id); without it the transcript row is inserted directly."""
    import asyncio

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        rows = await db.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name='whatsapp_messages'")
        if rows:
            cols = {r[1] for r in await db.execute_fetchall("PRAGMA table_info(whatsapp_messages)")}
            if "voice" not in cols:
                await db.execute("ALTER TABLE whatsapp_messages ADD COLUMN voice INTEGER DEFAULT 0")
        await db.commit()

    def _row(r) -> dict:
        d = dict(r)
        d["from_me"] = bool(d.get("from_me"))
        return d

    async def chat_is_personal(db, jid: str) -> bool:
        if not jid:
            return False
        try:
            rows = await db.execute_fetchall("SELECT classification FROM wa_chats WHERE jid=?", (jid,))
        except Exception:
            return False
        return bool(rows) and dict(rows[0]).get("classification") == "personal"

    async def store(fields: dict, data: bytes) -> dict:
        """Write the clip and the pending row. {stored, id, path, status} or {stored: False, reason}."""
        message_id = str(fields.get("message_id") or "").strip()[:120]
        if not message_id:
            raise HTTPException(400, "message_id required")
        if not data:
            raise HTTPException(400, "file is empty")
        if len(data) > max_bytes():
            raise HTTPException(413, f"file over {max_bytes() // (1024 * 1024)} MB")
        db = await vdb()
        await ensure_schema(db)
        dup = await db.execute_fetchall("SELECT id, status FROM wa_media WHERE message_id=?", (message_id,))
        if dup:
            d = dict(dup[0])
            return {"received": True, "stored": False, "reason": "duplicate", "id": d["id"], "status": d["status"]}
        jid = str(fields.get("chat_jid") or fields.get("jid") or "")[:100]
        if await chat_is_personal(db, jid):
            return {"received": True, "stored": False, "reason": "personal"}
        mimetype = str(fields.get("mimetype") or "audio/ogg")[:80]
        received_at = str(fields.get("timestamp") or fields.get("received_at") or "")[:50] or datetime.now(timezone.utc).isoformat()
        rel = media_rel_path(received_at, message_id, mimetype)
        full = os.path.join(voice_dir(), *rel.split("/"))

        def _write():
            os.makedirs(os.path.dirname(full), exist_ok=True)
            tmp = full + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, full)
        await asyncio.to_thread(_write)
        try:
            duration = float(fields.get("duration_seconds") or fields.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        kind = str(fields.get("chat_kind") or ("group" if jid.endswith("@g.us") else "dm"))
        kind = "dm" if kind.lower() == "dm" else "group"
        from_me = 1 if str(fields.get("from_me") or "0") in ("1", "true", "True") else 0
        cur = await db.execute(
            "INSERT OR IGNORE INTO wa_media (message_id, account, chat_jid, chat_name, chat_kind, sender, from_me, received_at, "
            "mimetype, path, bytes, duration, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending')",
            (message_id, str(fields.get("account") or "1")[:8], jid, str(fields.get("chat_name") or fields.get("group") or "")[:200],
             kind, str(fields.get("sender") or "")[:100], from_me, received_at, mimetype, rel, len(data), duration))
        await db.commit()
        return {"received": True, "stored": True, "id": cur.lastrowid, "path": rel, "status": "pending"}

    async def write_transcript(db, row: dict, text: str) -> int | None:
        """The transcript into whatsapp_messages as a text message tagged [voice transcript], voice=1."""
        body = transcript_body(row, text)
        if ingest is not None:
            r = await ingest(db, body)
            mid = r.get("id") if r.get("stored") else None
        else:
            cur = await db.execute(
                "INSERT INTO whatsapp_messages (group_name, sender, text, timestamp, jid, account, chat_kind, from_me, wa_msg_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (body["group"], body["sender"], body["text"], body["timestamp"], body["jid"], body["account"], body["chat_kind"],
                 body["from_me"], body["wa_msg_id"]))
            mid = cur.lastrowid
        if mid:
            await db.execute("UPDATE whatsapp_messages SET voice=1 WHERE id=?", (mid,))
        await db.commit()
        return mid

    async def run(now_v: Any = None, limit: int | None = None, budget: int | None = None) -> dict:
        """One transcription pass: the pending rows oldest first, ≤limit, inside the time budget. Heartbeat line
        always; faster-whisper missing → the warning line, nothing transcribed, no exception (Directive 5)."""
        now = _parse_now(now_v)
        limit = max(1, int(limit or max_per_run()))
        budget = max(10, int(budget or budget_s()))
        name = model_name()
        out: dict[str, Any] = {"as_of": now.isoformat(), "installed": whisper_available(), "model": name, "transcribed": 0,
                               "pending": 0, "failed": 0, "avg_s": 0.0, "items": [], "status": "clean", "line": "", "note": ""}
        db = await vdb()
        await ensure_schema(db)
        pend = await db.execute_fetchall("SELECT * FROM wa_media WHERE status='pending' ORDER BY id LIMIT ?", (limit,))
        rows = [_row(r) for r in pend]
        total_pending = int(dict((await db.execute_fetchall("SELECT COUNT(*) AS n FROM wa_media WHERE status='pending'"))[0])["n"] or 0)
        if not out["installed"]:
            out["pending"] = total_pending
            out["status"] = "warning"
            out["line"] = NOT_INSTALLED_LINE + (f" · {total_pending} pending" if total_pending else "")
            await _record(db, out)
            return out
        if not rows:
            out["line"] = heartbeat_line(0, 0, 0, name, 0.0)
            await _record(db, out)
            return out
        t0 = _mono()
        try:
            model = await asyncio.to_thread(load_model, name, model_dir())
        except Exception as e:
            out["status"] = "error"
            out["pending"] = total_pending
            out["note"] = f"model {name} failed to load: {type(e).__name__}: {str(e)[:120]}"
            out["line"] = heartbeat_line(0, total_pending, 0, name, 0.0) + " · " + out["note"]
            await _record(db, out)
            return out
        durations: list[float] = []
        for row in rows:
            if _mono() - t0 > budget:
                out["note"] = f"time budget {budget}s reached"
                break
            full = os.path.join(voice_dir(), *str(row["path"]).split("/"))
            t1 = _mono()
            try:
                if not os.path.exists(full):
                    raise FileNotFoundError(f"clip missing: {row['path']}")
                res = await asyncio.to_thread(transcribe_file, model, full)
            except Exception as e:
                took = _mono() - t1
                out["failed"] += 1
                await db.execute("UPDATE wa_media SET status='failed', error=?, seconds=?, attempts=attempts+1, done_at=? WHERE id=?",
                                 (f"{type(e).__name__}: {str(e)[:200]}", took, datetime.now(timezone.utc).isoformat(), row["id"]))
                await db.commit()
                out["items"].append({"id": row["id"], "message_id": row["message_id"], "status": "failed", "error": str(e)[:120]})
                continue
            took = _mono() - t1
            durations.append(took)
            text = res["text"]
            mid = None
            if text:
                try:
                    mid = await write_transcript(db, row, text)
                except Exception as e:
                    out["note"] = (out["note"] + " · " if out["note"] else "") + f"store failed for {row['message_id']}: {str(e)[:80]}"
            await db.execute(
                "UPDATE wa_media SET status='done', transcript=?, language=?, seconds=?, attempts=attempts+1, store_msg_id=?, "
                "error=?, done_at=? WHERE id=?",
                (text[:8000], res["language"], took, mid, "" if text else "no speech detected",
                 datetime.now(timezone.utc).isoformat(), row["id"]))
            await db.commit()
            out["transcribed"] += 1
            out["items"].append({"id": row["id"], "message_id": row["message_id"], "status": "done", "chat_name": row["chat_name"],
                                 "sender": row["sender"], "language": res["language"], "seconds": round(took, 1),
                                 "transcript": text[:300], "store_msg_id": mid})
        out["avg_s"] = round(sum(durations) / len(durations), 1) if durations else 0.0
        out["pending"] = int(dict((await db.execute_fetchall("SELECT COUNT(*) AS n FROM wa_media WHERE status='pending'"))[0])["n"] or 0)
        if out["failed"]:
            out["status"] = "warning"
        out["line"] = heartbeat_line(out["transcribed"], out["pending"], out["failed"], name, out["avg_s"])
        if out["note"]:
            out["line"] += " · " + out["note"]
        await _record(db, out)
        return out

    async def _record(db, out: dict) -> None:
        await db.execute("INSERT INTO wa_media_runs (ran_at, transcribed, pending, failed, model, avg_s, line) VALUES (?,?,?,?,?,?,?)",
                         (datetime.now(timezone.utc).isoformat(), out["transcribed"], out["pending"], out["failed"], out["model"],
                          float(out.get("avg_s") or 0), str(out["line"])[:1000]))
        await db.commit()

    async def recent(limit: int = 20, status: str = "", now_v: Any = None) -> dict:
        limit = max(1, min(int(limit or 20), 500))
        if status and status not in STATUSES:
            raise HTTPException(400, f"status must be one of {', '.join(STATUSES)}")
        q, params = "SELECT * FROM wa_media", []
        if status:
            q += " WHERE status=?"; params.append(status)
        q += " ORDER BY COALESCE(done_at, created_at) DESC, id DESC LIMIT ?"; params.append(limit)
        db = await vdb()
        await ensure_schema(db)
        items = [_row(r) for r in await db.execute_fetchall(q, params)]
        return {"items": items, "count": len(items), "status": status, "as_of": _parse_now(now_v).isoformat()}

    async def stats(now_v: Any = None) -> dict:
        now = _parse_now(now_v)
        db = await vdb()
        await ensure_schema(db)
        counts = {s: 0 for s in STATUSES}
        for r in await db.execute_fetchall("SELECT status, COUNT(*) AS n FROM wa_media GROUP BY status"):
            d = dict(r)
            counts[d["status"]] = int(d["n"] or 0)
        today = (now - timedelta(days=1)).astimezone(timezone.utc).isoformat()
        last24 = int(dict((await db.execute_fetchall("SELECT COUNT(*) AS n FROM wa_media WHERE created_at>=? OR received_at>=?",
                                                     (today, today)))[0])["n"] or 0)
        runs = await db.execute_fetchall("SELECT * FROM wa_media_runs ORDER BY id DESC LIMIT 1")
        transcripts = [_row(r) for r in await db.execute_fetchall(
            "SELECT * FROM wa_media WHERE status='done' ORDER BY done_at DESC, id DESC LIMIT 20")]
        return {"as_of": now.isoformat(), "installed": whisper_available(), "model": model_name(), "counts": counts,
                "last_24h": last24, "transcripts": transcripts, "state": dict(runs[0]) if runs else None,
                "voice_dir": voice_dir(), "model_dir": model_dir()}

    # ── endpoints ─────────────────────────────────────────────────────────────
    @app.post("/api/wa/media")
    async def wa_media(request: Request):
        """The bridge's multipart upload: fields account, chat_jid, chat_name, sender, message_id, mimetype,
        duration_seconds, timestamp, from_me, chat_kind + the clip as `file`."""
        try:
            form = await request.form()
        except Exception as e:
            raise HTTPException(400, f"multipart form expected: {type(e).__name__}")
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(400, "file required")
        data = await upload.read()
        fields = {k: v for k, v in form.multi_items() if k != "file" and isinstance(v, str)}
        if not fields.get("mimetype"):
            fields["mimetype"] = getattr(upload, "content_type", "") or "audio/ogg"
        return await store(fields, data)

    @app.post("/api/wa/media/transcribe")
    async def wa_media_transcribe(body: dict | None = None):
        body = body or {}
        return await run(body.get("now"), body.get("limit"), body.get("budget_s"))

    @app.get("/api/wa/media/recent")
    async def wa_media_recent(limit: int = 20, status: str = ""):
        return await recent(limit, status)

    @app.get("/api/wa/media/stats")
    async def wa_media_stats():
        return await stats()

    return {"ensure_schema": ensure_schema, "store": store, "run": run, "recent": recent, "stats": stats}
