"""Chief of Staff endpoints — fleet, spend, memory, agenda, jobs, two-way WhatsApp.

Registered onto the FastAPI app by mdo_server.py via register(). Keeps the
CoS surface in one file; the server keeps the database and the existing
endpoint functions.

Channels (COS_CHANNEL in .env):
  alert    — today's path: self-message through the ops WhatsApp bridge
  baileys  — a dedicated number on its own Baileys bridge (COS_WA_BRIDGE_URL)
  meta     — Meta WhatsApp Cloud API (META_PHONE_NUMBER_ID, META_ACCESS_TOKEN)
Inbound arrives at POST /api/cos/inbound (bridge) or /api/cos/meta-webhook (Meta).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request
from starlette.responses import FileResponse, PlainTextResponse

import mdo_cos
from mdo_cos import (IST, VAULT_MAX_BYTES, budget_mode, cost_inr, is_missed, job_line, next_due, parse_reply,
                     safe_vault_path, spend_cap_inr)

ROOT = Path(__file__).resolve().parent
FLEET_PATH = Path(os.environ.get("FLEET_PATH", ROOT / "fleet.yaml"))
AGENDA_PATH = Path(os.environ.get("AGENDA_PATH", ROOT / "agenda.yaml"))
CONSTITUTION_PATH = ROOT / "CHIEF_OF_STAFF.md"

COS_PREFIX = "CoS ·"   # every outbound line starts with this; the bridge ignores inbound text that does, so a self-chat never loops

SCHEMA = """
CREATE TABLE IF NOT EXISTS cos_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot TEXT NOT NULL, cadence TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'clean',
    summary TEXT DEFAULT '', report_id INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cos_runs_bot ON cos_runs(bot, id);
CREATE TABLE IF NOT EXISTS spend_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot TEXT NOT NULL, model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cache_read_tokens INTEGER DEFAULT 0,
    cost_inr REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cos_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'info',   -- info|needs_click|needs_choice|proposal|stuck|done
    objective TEXT DEFAULT '', bot TEXT DEFAULT 'cos',
    options_json TEXT DEFAULT '[]', eta TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',                      -- open|approved|rejected|chosen|done|skipped
    answer TEXT DEFAULT '', answer_source TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cos_agenda (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    agenda_json TEXT NOT NULL DEFAULT '{}', source TEXT DEFAULT '',
    synced_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cos_chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cos_chat ON cos_chat(chat_id, id);
CREATE TABLE IF NOT EXISTS cos_chat_summary (
    chat_id TEXT PRIMARY KEY, summary TEXT DEFAULT '', updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS vault_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL, path TEXT NOT NULL, bytes INTEGER DEFAULT 0,
    actor TEXT DEFAULT '', ok INTEGER DEFAULT 1, note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS bot_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, source TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',                    -- active|proposed|retired
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(bot, key)
);
"""


def load_yaml(path: Path) -> dict:
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _utc(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ── outbound channel ─────────────────────────────────────────────────────────
def send_cos(text: str, to: str | None = None, legacy_send: Callable[[str], dict] | None = None) -> dict:
    """Deliver one message to Aman on the configured channel. Never raises."""
    text = text if text.startswith(COS_PREFIX) else f"{COS_PREFIX} {text}"
    channel = os.environ.get("COS_CHANNEL", "alert").strip().lower()
    try:
        if channel == "meta":
            pnid = os.environ.get("META_PHONE_NUMBER_ID", "").strip()
            token = os.environ.get("META_ACCESS_TOKEN", "").strip()
            dest = (to or os.environ.get("COS_WHATSAPP_TO", "") or os.environ.get("ALERT_WHATSAPP_TO", "")).strip()
            if not (pnid and token and dest):
                return {"sent": False, "reason": "META_PHONE_NUMBER_ID / META_ACCESS_TOKEN / COS_WHATSAPP_TO not set"}
            req = urllib.request.Request(
                f"https://graph.facebook.com/v21.0/{pnid}/messages",
                data=json.dumps({"messaging_product": "whatsapp", "to": dest,
                                 "type": "text", "text": {"body": text[:4000]}}).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                return {"sent": True, "channel": "meta", **json.loads(r.read() or b"{}")}
        if channel == "baileys":
            url = os.environ.get("COS_WA_BRIDGE_URL", "").strip()
            dest = (to or os.environ.get("COS_WHATSAPP_TO", "") or os.environ.get("ALERT_WHATSAPP_TO", "")).strip()
            if not (url and dest):
                return {"sent": False, "reason": "COS_WA_BRIDGE_URL / COS_WHATSAPP_TO not set"}
            req = urllib.request.Request(
                url.rstrip("/") + "/api/whatsapp/send",
                data=json.dumps({"to": dest, "text": text}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:
                return {"sent": True, "channel": "baileys", **json.loads(r.read() or b"{}")}
        if legacy_send is not None:
            return {"channel": "alert", **legacy_send(text)}
        return {"sent": False, "reason": "no channel configured"}
    except Exception as e:
        return {"sent": False, "channel": channel, "reason": str(e)[:200]}


# ── registration ─────────────────────────────────────────────────────────────
def register(app, vdb: Callable[[], Awaitable[Any]], legacy_send: Callable[[str], dict], brain) -> dict:
    """Mount the CoS endpoints. Returns the toolbox entries the brain needs."""

    async def ensure_schema(db=None):
        """Called by the server with the freshly opened connection (passing it
        avoids re-entering vdb() while it is still being set up)."""
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        # payload_json: machine-readable context on a job (e.g. {"action": "wa_classify", "jid": ...})
        # so a bot can find and apply Aman's answer. Guarded ALTER for databases created before it.
        cols = {r[1] for r in await db.execute_fetchall("PRAGMA table_info(cos_jobs)")}
        if "payload_json" not in cols:
            await db.execute("ALTER TABLE cos_jobs ADD COLUMN payload_json TEXT DEFAULT '{}'")
        await db.commit()

    # ── runs & spend ──────────────────────────────────────────────────────
    async def record_run(bot: str, cadence: str, status: str, summary: str, report_id: int | None = None):
        db = await vdb()
        await db.execute("INSERT INTO cos_runs (bot,cadence,status,summary,report_id) VALUES (?,?,?,?,?)",
                         (bot[:60], cadence[:20], status[:20], summary[:1000], report_id))
        await db.commit()

    async def spend_summary() -> dict:
        db = await vdb()
        month = datetime.now(IST).strftime("%Y-%m")
        rows = await db.execute_fetchall(
            "SELECT COALESCE(SUM(cost_inr),0) AS inr, COUNT(*) AS calls FROM spend_ledger WHERE created_at >= ?",
            (f"{month}-01",))
        by_bot = await db.execute_fetchall(
            "SELECT bot, model, ROUND(SUM(cost_inr),2) AS inr, COUNT(*) AS calls FROM spend_ledger "
            "WHERE created_at >= ? GROUP BY bot, model ORDER BY inr DESC", (f"{month}-01",))
        mtd = float(dict(rows[0])["inr"] or 0) if rows else 0.0
        cap = spend_cap_inr()
        return {"month": month, "month_to_date_inr": round(mtd, 2), "calls": dict(rows[0])["calls"] if rows else 0,
                "cap_inr": cap, "pct_of_cap": round(mtd / cap * 100, 1) if cap else None,
                "mode": budget_mode(mtd, cap), "usd_inr": mdo_cos.usd_inr(),
                "by_bot": [dict(r) for r in by_bot]}

    @app.get("/api/spend")
    async def spend_get():
        return await spend_summary()

    @app.post("/api/spend/record")
    async def spend_record(body: dict):
        model = str(body.get("model") or "")
        inp, out, cache = (int(body.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens"))
        inr = cost_inr(model, inp, out, cache)
        db = await vdb()
        await db.execute(
            "INSERT INTO spend_ledger (bot,model,input_tokens,output_tokens,cache_read_tokens,cost_inr) VALUES (?,?,?,?,?,?)",
            (str(body.get("bot") or "unknown")[:60], model[:60], inp, out, cache, inr))
        await db.commit()
        return {"recorded": True, "cost_inr": inr, **(await spend_summary())}

    # ── fleet ─────────────────────────────────────────────────────────────
    async def fleet_status() -> dict:
        fleet = load_yaml(FLEET_PATH)
        db = await vdb()
        now = datetime.now(timezone.utc)
        out = []
        bots = list(fleet.get("bots") or [])
        if fleet.get("cos"):
            bots.insert(0, {"id": "cos", **fleet["cos"]})
        for b in bots:
            last = await db.execute_fetchall(
                "SELECT status, summary, created_at FROM cos_runs WHERE bot=? ORDER BY id DESC LIMIT 1", (b["id"],))
            last = dict(last[0]) if last else None
            last_at = _utc(last["created_at"]) if last else None
            by_push = str(b.get("reports_to", "ledger")).lower() == "push"   # Claude Routines: push notification, no ledger row
            due = next_due(str(b.get("cadence", "")), last_at, now) if b.get("enabled", True) else None
            spend = await db.execute_fetchall(
                "SELECT ROUND(COALESCE(SUM(cost_inr),0),2) AS inr FROM spend_ledger WHERE bot=? AND created_at >= ?",
                (b["id"], datetime.now(IST).strftime("%Y-%m-01")))
            out.append({
                "id": b["id"], "name": b.get("name", b["id"]), "runs_on": b.get("runs_on", ""),
                "cadence": b.get("cadence", ""), "model": b.get("model", ""), "enabled": bool(b.get("enabled", True)),
                "checks": b.get("checks") or [], "serves": b.get("serves") or [],
                "last_run": last["created_at"] if last else None,
                "last_status": last["status"] if last else "never",
                "last_summary": (last["summary"] or "")[:300] if last else "",
                "next_due": due.isoformat() if due else None,
                "reports_to": "push" if by_push else "ledger",
                "missed": (is_missed(str(b.get("cadence", "")), last_at, now) if (b.get("enabled", True) and not by_push) else False),
                "spend_inr_mtd": float(dict(spend[0])["inr"]) if spend else 0.0,
            })
        enabled = [b for b in out if b["enabled"] and b["reports_to"] == "ledger"]
        return {"bots": out, "total": len(enabled), "alive": sum(1 for b in enabled if not b["missed"]),
                "dead": [b["id"] for b in enabled if b["missed"]], "gaps": fleet.get("fleet_gaps") or [],
                "as_of": now.isoformat()}

    @app.get("/api/fleet")
    async def fleet_get():
        return await fleet_status()

    @app.post("/api/fleet/run")
    async def fleet_run_record(body: dict):
        """A bot (or the CoS) stamps a run without filing a report."""
        await record_run(str(body.get("bot") or "unknown"), str(body.get("cadence") or ""),
                         str(body.get("status") or "clean"), str(body.get("summary") or ""))
        return {"recorded": True}

    # ── agenda (mirror of the Objectives sheet) ───────────────────────────
    async def agenda_get() -> dict:
        db = await vdb()
        rows = await db.execute_fetchall("SELECT agenda_json, source, synced_at FROM cos_agenda WHERE id=1")
        if rows:
            r = dict(rows[0])
            data = json.loads(r["agenda_json"] or "{}")
            data.setdefault("objectives", [])
            data["_source"], data["_synced_at"] = r["source"], r["synced_at"]
            return data
        data = load_yaml(AGENDA_PATH)
        data.setdefault("objectives", [])
        data["_source"], data["_synced_at"] = "agenda.yaml (file)", None
        return data

    @app.get("/api/cos/agenda")
    async def cos_agenda_get():
        return await agenda_get()

    @app.put("/api/cos/agenda")
    async def cos_agenda_put(body: dict):
        """The CoS writes the mirror here after reading the Objectives sheet."""
        if not isinstance(body.get("objectives"), list):
            raise HTTPException(400, "objectives must be a list")
        db = await vdb()
        await db.execute(
            "INSERT INTO cos_agenda (id, agenda_json, source, synced_at) VALUES (1, ?, ?, datetime('now')) "
            "ON CONFLICT(id) DO UPDATE SET agenda_json=excluded.agenda_json, source=excluded.source, synced_at=datetime('now')",
            (json.dumps({k: v for k, v in body.items() if not k.startswith("_")})[:200000],
             str(body.get("_source") or "Objectives sheet")[:200]))
        await db.commit()
        return {"stored": True, "objectives": len(body["objectives"])}

    # ── jobs ──────────────────────────────────────────────────────────────
    def _job(r) -> dict:
        d = dict(r)
        d["options"] = json.loads(d.pop("options_json") or "[]")
        try:
            d["payload"] = json.loads(d.pop("payload_json", None) or "{}")
        except json.JSONDecodeError:
            d["payload"] = {}
        return d

    async def jobs_list(status: str | None = "open", limit: int = 50) -> dict:
        db = await vdb()
        q, p = "SELECT * FROM cos_jobs WHERE 1=1", []
        if status:
            q += " AND status=?"; p.append(status)
        q += " ORDER BY id DESC LIMIT ?"; p.append(min(int(limit), 200))
        rows = await db.execute_fetchall(q, p)
        return {"jobs": [_job(r) for r in rows]}

    async def job_add(body: dict, push: bool = True) -> dict:
        kind = str(body.get("kind") or "info")
        if kind not in ("info", "needs_click", "needs_choice", "proposal", "stuck", "done"):
            raise HTTPException(400, "bad kind")
        db = await vdb()
        payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
        cur = await db.execute(
            "INSERT INTO cos_jobs (title,kind,objective,bot,options_json,eta,status,payload_json) VALUES (?,?,?,?,?,?,?,?)",
            (str(body.get("title") or "")[:300], kind, str(body.get("objective") or "")[:80],
             str(body.get("bot") or "cos")[:60], json.dumps(body.get("options") or [])[:4000],
             str(body.get("eta") or "")[:60], "done" if kind == "done" else "open", json.dumps(payload)[:4000]))
        await db.commit()
        rows = await db.execute_fetchall("SELECT * FROM cos_jobs WHERE id=?", (cur.lastrowid,))
        job = _job(rows[0])
        job["line"] = job_line(job)
        job["push"] = send_cos(job["line"], legacy_send=legacy_send) if push else {"sent": False, "reason": "push=false"}
        return job

    @app.get("/api/cos/jobs")
    async def cos_jobs_get(status: str | None = "open", limit: int = 50):
        return await jobs_list(status, limit)

    @app.post("/api/cos/jobs")
    async def cos_jobs_post(body: dict):
        return await job_add(body, push=bool(body.get("push", True)))

    async def job_resolve(job_id: int, status: str, answer: str, source: str) -> dict:
        db = await vdb()
        rows = await db.execute_fetchall("SELECT * FROM cos_jobs WHERE id=?", (job_id,))
        if not rows:
            return {"ok": False, "reason": f"no job #{job_id}"}
        job = _job(rows[0])
        if job["status"] != "open":
            return {"ok": False, "reason": f"#{job_id} already {job['status']}", "job": job}
        await db.execute("UPDATE cos_jobs SET status=?, answer=?, answer_source=?, updated_at=datetime('now') WHERE id=?",
                         (status, answer[:200], source[:120], job_id))
        await db.commit()
        job.update(status=status, answer=answer)
        return {"ok": True, "job": job}

    @app.put("/api/cos/jobs/{job_id}")
    async def cos_jobs_put(job_id: int, body: dict):
        return await job_resolve(job_id, str(body.get("status") or "done"), str(body.get("answer") or ""),
                                 str(body.get("source") or "api"))

    # ── memory ────────────────────────────────────────────────────────────
    async def memory_get() -> dict:
        db = await vdb()
        agenda = await agenda_get()
        chats = await db.execute_fetchall(
            "SELECT chat_id, COUNT(*) AS turns, MAX(created_at) AS last FROM cos_chat GROUP BY chat_id")
        summaries = await db.execute_fetchall("SELECT chat_id, summary, updated_at FROM cos_chat_summary")
        bot_mem = await db.execute_fetchall(
            "SELECT bot, key, value, source, status, updated_at FROM bot_memory ORDER BY bot, key")
        jobs_open = await db.execute_fetchall("SELECT COUNT(*) AS n FROM cos_jobs WHERE status='open'")
        runs = await db.execute_fetchall("SELECT COUNT(*) AS n FROM cos_runs")
        counts = {}
        for t in ("agent_reports", "whatsapp_messages", "intel_items", "ops_tasks", "spend_ledger", "cos_chat"):
            try:
                counts[t] = dict((await db.execute_fetchall(f"SELECT COUNT(*) AS n FROM {t}"))[0])["n"]
            except Exception:
                counts[t] = None
        db_path = os.environ.get("VEGA_DB_PATH", os.environ.get("DB_PATH", "vega_data.db"))
        size = os.path.getsize(db_path) if os.path.exists(db_path) else None
        try:
            du = shutil.disk_usage(os.path.dirname(os.path.abspath(db_path)))
            disk = {"total_mb": round(du.total / 1048576), "free_mb": round(du.free / 1048576),
                    "pct_free": round(du.free / du.total * 100, 1)}
        except Exception:
            disk = None
        arch = os.environ.get("MDO_ARCHIVE_DIR", os.path.join(os.path.dirname(os.path.abspath(db_path)), "archive"))
        archives = sorted(os.listdir(arch)) if os.path.isdir(arch) else []
        return {
            "where": {
                "objectives": "Objectives sheet (Claude Doc) → mirrored to agenda.yaml and cos_agenda on every CoS run",
                "directives": "CHIEF_OF_STAFF.md in the repo", "ledger": "SQLite on the VPS (vega_data.db)",
                "decisions": "MDO_VISION.md §17 + COS_LOG.md", "chats": "cos_chat (last turns) + cos_chat_summary (rolling)",
                "bot_memory": "bot_memory table — facts each bot keeps between runs; proposed ones wait for Aman",
            },
            "agenda": {"objectives": agenda.get("objectives", []), "candidates": agenda.get("candidates", []),
                       "source": agenda.get("_source"), "synced_at": agenda.get("_synced_at")},
            "chats": [dict(r) for r in chats], "chat_summaries": [dict(r) for r in summaries],
            "bot_memory": [dict(r) for r in bot_mem],
            "open_jobs": dict(jobs_open[0])["n"] if jobs_open else 0, "runs_logged": dict(runs[0])["n"] if runs else 0,
            "rows": counts, "db_bytes": size, "disk": disk, "archives": archives,
            "purge_policy": {"reports_days": 60, "whatsapp_days": 90, "extractions_days": 180, "chat_turns_kept": 20,
                             "never": ["Objectives sheet", "agenda", "COS_LOG.md", "open items", "bot_memory"]},
        }

    @app.get("/api/cos/memory")
    async def cos_memory_get():
        return await memory_get()

    @app.post("/api/cos/memory")
    async def cos_memory_post(body: dict):
        """A bot or the CoS proposes (status=proposed) or, after Aman's yes, keeps a fact."""
        status = str(body.get("status") or "proposed")
        if status not in ("active", "proposed", "retired"):
            raise HTTPException(400, "bad status")
        db = await vdb()
        await db.execute(
            "INSERT INTO bot_memory (bot,key,value,source,status) VALUES (?,?,?,?,?) "
            "ON CONFLICT(bot,key) DO UPDATE SET value=excluded.value, source=excluded.source, status=excluded.status, updated_at=datetime('now')",
            (str(body.get("bot") or "cos")[:60], str(body.get("key") or "")[:120], str(body.get("value") or "")[:2000],
             str(body.get("source") or "")[:200], status))
        await db.commit()
        return {"stored": True}

    # ── chat memory for the brain ─────────────────────────────────────────
    async def chat_load(chat_id: str, limit: int = 20) -> dict:
        db = await vdb()
        rows = await db.execute_fetchall(
            "SELECT role, content FROM cos_chat WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit))
        summ = await db.execute_fetchall("SELECT summary FROM cos_chat_summary WHERE chat_id=?", (chat_id,))
        return {"turns": [dict(r) for r in reversed(rows)], "summary": dict(summ[0])["summary"] if summ else ""}

    async def chat_save(chat_id: str, role: str, content: str) -> None:
        db = await vdb()
        await db.execute("INSERT INTO cos_chat (chat_id, role, content) VALUES (?,?,?)",
                         (chat_id, role, content[:20000]))
        await db.commit()

    # ── inbound (two-way) ─────────────────────────────────────────────────
    def allowed_numbers() -> set[str]:
        raw = os.environ.get("COS_ALLOWED_NUMBERS", "") or os.environ.get("ALERT_WHATSAPP_TO", "")
        return {"".join(ch for ch in n if ch.isdigit()) for n in raw.split(",") if n.strip()}

    async def handle_inbound(sender: str, text: str, channel: str, message_id: str = "") -> dict:
        sender_digits = "".join(ch for ch in sender if ch.isdigit())
        allowed = allowed_numbers()
        if allowed and sender_digits not in allowed:
            return {"handled": False, "reason": "sender not allowed"}
        text = (text or "").strip()
        if not text or text.startswith(COS_PREFIX):
            return {"handled": False, "reason": "empty or own message"}
        source = f"{channel}:{message_id or 'reply'}"
        parsed = parse_reply(text)
        if parsed:
            job_id = parsed["job"]
            if parsed["kind"] == "choice" and job_id is None:
                open_choice = (await jobs_list("open", 50))["jobs"]
                open_choice = [j for j in open_choice if j["kind"] == "needs_choice"]
                if len(open_choice) == 1:
                    job_id = open_choice[0]["id"]
                elif not open_choice:
                    reply = "❓ which job? Nothing is waiting on a choice."
                    send_cos(reply, to=sender, legacy_send=legacy_send)
                    return {"handled": True, "reply": reply}
                else:
                    reply = "❓ which job? Reply like 14:2 — " + ", ".join(f"#{j['id']}" for j in open_choice)
                    send_cos(reply, to=sender, legacy_send=legacy_send)
                    return {"handled": True, "reply": reply}
            status = {"ack": "approved", "nack": "rejected", "choice": "chosen"}[parsed["kind"]]
            answer = text if parsed["kind"] != "choice" else f"option {parsed['option']}"
            res = await job_resolve(int(job_id), status, answer, source)
            if res.get("ok"):
                j = res["job"]
                reply = f"✔ #{j['id']} {status}: {j['title'][:80]}" + (f" → {answer}" if parsed["kind"] == "choice" else "")
            else:
                reply = "❓ " + res.get("reason", "which job?")
            send_cos(reply, to=sender, legacy_send=legacy_send)
            await chat_save(sender_digits, "user", text)
            await chat_save(sender_digits, "assistant", reply)
            return {"handled": True, "reply": reply, "job": res.get("job")}

        # Free text → the brain, with this chat's memory.
        mem = await chat_load(sender_digits)
        history = mem["turns"]
        try:
            result = await brain.brain_ask(text, history, chat_id=sender_digits, chat_summary=mem["summary"])
            answer = result.get("answer") or "(no answer)"
        except Exception as e:
            answer = f"Brain error: {type(e).__name__}: {e}"
        await chat_save(sender_digits, "user", text)
        await chat_save(sender_digits, "assistant", answer)
        push = send_cos(answer, to=sender, legacy_send=legacy_send)
        return {"handled": True, "reply": answer, "push": push}

    @app.post("/api/cos/inbound")
    async def cos_inbound(body: dict):
        return await handle_inbound(str(body.get("from") or ""), str(body.get("text") or ""),
                                    str(body.get("channel") or "bridge"), str(body.get("message_id") or ""))

    @app.get("/api/cos/meta-webhook")
    async def meta_verify(request: Request):
        q = request.query_params
        if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == os.environ.get("META_VERIFY_TOKEN", "").strip() != "":
            return PlainTextResponse(q.get("hub.challenge", ""))
        raise HTTPException(403, "verify token mismatch")

    @app.post("/api/cos/meta-webhook")
    async def meta_inbound(request: Request):
        raw = await request.body()
        secret = os.environ.get("META_APP_SECRET", "").strip()
        if secret:
            sig = request.headers.get("x-hub-signature-256", "")
            expect = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expect):
                raise HTTPException(403, "bad signature")
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise HTTPException(400, "bad json")
        handled = []
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                for m in (change.get("value") or {}).get("messages") or []:
                    if m.get("type") != "text":
                        continue
                    handled.append(await handle_inbound(m.get("from", ""), (m.get("text") or {}).get("body", ""),
                                                        "meta", m.get("id", "")))
        return {"handled": len(handled)}

    # ── tender inbound: a locked door for external agents (Grok task, scraper, Gmail parser) ──
    def _tender_token_ok(request: Request) -> bool:
        tok = os.environ.get("TENDER_INBOUND_TOKEN", "").strip()
        if not tok:
            return False
        got = (request.headers.get("x-tender-token") or request.query_params.get("token") or "").strip()
        return hmac.compare_digest(got, tok)

    async def tender_ingest(items: list, source_default: str = "external") -> dict:
        """The tender door's body: {buyer, title, category, due_date (YYYY-MM-DD), url, volume_mt, source, notes}
        rows into vwlr_tender_pipeline. Duplicates (same url, or same buyer + due_date + title) are ignored.
        Shared by POST /api/cos/tender-inbound (token-guarded) and the in-process mail-reader (bidsnrfp results)."""
        db = await vdb()
        added, skipped = 0, 0
        for t in items[:50]:
            if not isinstance(t, dict):
                continue
            buyer = str(t.get("buyer") or "")[:120].strip()
            title = str(t.get("title") or t.get("notes") or "")[:300].strip()
            if not buyer and not title:
                skipped += 1
                continue
            url = str(t.get("url") or "")[:500].strip()
            due = str(t.get("due_date") or "")[:10] or None
            notes = (f"[{str(t.get('source') or source_default)[:40]}] {title}" + (" — " + str(t["notes"])[:500] if t.get("notes") and t.get("title") else ""))[:800]
            dup = await db.execute_fetchall(
                "SELECT id FROM vwlr_tender_pipeline WHERE (url=? AND url!='') OR (buyer=? AND COALESCE(due_date,'')=COALESCE(?, '') AND substr(notes,1,80)=substr(?,1,80)) LIMIT 1",
                (url, buyer, due, notes))
            if dup:
                skipped += 1
                continue
            try:
                vol = float(t.get("volume_mt") or 0)
            except (TypeError, ValueError):
                vol = 0.0
            await db.execute(
                "INSERT INTO vwlr_tender_pipeline (buyer,volume_mt,category,due_date,status,url,notes,eligibility_score) VALUES (?,?,?,?,?,?,?,?)",
                (buyer or "Unknown buyer", vol, str(t.get("category") or "Other")[:60], due, str(t.get("status") or "evaluating")[:30], url, notes, 0.0))
            added += 1
        await db.commit()
        return {"added": added, "skipped": skipped}

    @app.post("/api/cos/tender-inbound")
    async def tender_inbound(request: Request):
        """Any outside agent with TENDER_INBOUND_TOKEN may post tenders here and
        nothing else. Payload: {buyer, title, category, due_date (YYYY-MM-DD),
        url, volume_mt, source, notes}. Duplicates (same url, or same buyer +
        due_date + title) are ignored. The tender bot evaluates on its next run."""
        if not _tender_token_ok(request):
            raise HTTPException(403, "bad or missing X-Tender-Token")
        try:
            body = json.loads((await request.body()) or b"{}")
        except json.JSONDecodeError:
            raise HTTPException(400, "bad json")
        items = body if isinstance(body, list) else body.get("tenders") or [body]
        res = await tender_ingest(items)
        added, skipped = res["added"], res["skipped"]
        await record_run("tender-inbound", "event", "clean", f"{added} added, {skipped} skipped")
        return {"added": added, "skipped": skipped}

    # ── vault: Aman's private files (memory/, finance/) on the VPS ────────────
    # Separate token from the app key, so a bot with the app key cannot read the
    # finance workbook. Every access is audited. No delete over HTTP.
    VAULT_DIR = os.environ.get("VAULT_DIR", os.path.join(
        os.path.dirname(os.path.abspath(os.environ.get("VEGA_DB_PATH", "/data/vega_data.db"))), "vault"))

    def _vault_ok(request: Request) -> bool:
        tok = os.environ.get("VAULT_TOKEN", "").strip()
        got = (request.headers.get("x-vault-token") or "").strip()
        return bool(tok) and hmac.compare_digest(got, tok)

    async def _audit(action: str, path: str, nbytes: int, actor: str, ok: bool, note: str = ""):
        db = await vdb()
        await db.execute("INSERT INTO vault_audit (action,path,bytes,actor,ok,note) VALUES (?,?,?,?,?,?)",
                         (action, path[:300], nbytes, actor[:80], 1 if ok else 0, note[:200]))
        await db.commit()

    def _actor(request: Request) -> str:
        return (request.headers.get("x-actor") or request.headers.get("user-agent") or "")[:80]

    @app.get("/api/vault/list")
    async def vault_list(request: Request, area: str = ""):
        if not _vault_ok(request):
            await _audit("list", area, 0, _actor(request), False, "bad token")
            raise HTTPException(403, "bad or missing X-Vault-Token")
        out = []
        for a in ("memory", "finance"):
            if area and a != area:
                continue
            base = os.path.join(VAULT_DIR, a)
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for fn in filenames:
                    if fn.startswith("."):
                        continue
                    full = os.path.join(dirpath, fn)
                    st = os.stat(full)
                    out.append({"path": os.path.relpath(full, VAULT_DIR).replace(os.sep, "/"),
                                "bytes": st.st_size, "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
        await _audit("list", area or "*", len(out), _actor(request), True)
        return {"files": sorted(out, key=lambda f: f["path"]), "root": VAULT_DIR}

    @app.get("/api/vault/get")
    async def vault_get(request: Request, path: str):
        if not _vault_ok(request):
            await _audit("get", path, 0, _actor(request), False, "bad token")
            raise HTTPException(403, "bad or missing X-Vault-Token")
        full = safe_vault_path(VAULT_DIR, path)
        if not full or not os.path.isfile(full):
            await _audit("get", path, 0, _actor(request), False, "not found or outside vault")
            raise HTTPException(404, "no such file in the vault")
        data = Path(full).read_bytes()
        await _audit("get", path, len(data), _actor(request), True)
        text_like = full.endswith((".md", ".txt", ".yaml", ".yml", ".json", ".csv"))
        import base64
        return {"path": path, "bytes": len(data), "encoding": "utf-8" if text_like else "base64",
                "content": data.decode("utf-8", "replace") if text_like else base64.b64encode(data).decode()}

    @app.put("/api/vault/put")
    async def vault_put(request: Request):
        """Body: {"path": "memory/_log.md", "content": "...", "encoding": "utf-8"|"base64", "append": false}.
        Writes atomically (temp file + rename) and keeps the previous version as <name>.prev."""
        if not _vault_ok(request):
            await _audit("put", "?", 0, _actor(request), False, "bad token")
            raise HTTPException(403, "bad or missing X-Vault-Token")
        try:
            body = json.loads((await request.body()) or b"{}")
        except json.JSONDecodeError:
            raise HTTPException(400, "bad json")
        rel = str(body.get("path") or "")
        full = safe_vault_path(VAULT_DIR, rel)
        if not full:
            await _audit("put", rel, 0, _actor(request), False, "outside vault")
            raise HTTPException(400, "path must be under memory/ or finance/, no dot-files, no ..")
        import base64
        raw = body.get("content") or ""
        data = base64.b64decode(raw) if body.get("encoding") == "base64" else str(raw).encode("utf-8")
        if len(data) > VAULT_MAX_BYTES:
            await _audit("put", rel, len(data), _actor(request), False, "too large")
            raise HTTPException(413, f"max {VAULT_MAX_BYTES} bytes")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if body.get("append") and os.path.exists(full):
            data = Path(full).read_bytes() + data
        if os.path.exists(full):
            shutil.copy2(full, full + ".prev")
        tmp = full + ".tmp"
        Path(tmp).write_bytes(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, full)
        await _audit("put", rel, len(data), _actor(request), True, "append" if body.get("append") else "")
        return {"stored": True, "path": rel, "bytes": len(data)}

    @app.get("/api/vault/audit")
    async def vault_audit(request: Request, limit: int = 50):
        if not _vault_ok(request):
            raise HTTPException(403, "bad or missing X-Vault-Token")
        db = await vdb()
        rows = await db.execute_fetchall("SELECT * FROM vault_audit ORDER BY id DESC LIMIT ?", (min(int(limit), 500),))
        return {"audit": [dict(r) for r in rows]}

    # ── off-site door: the weekly encrypted bundle, nothing else ────────────
    # Same token, same audit. Serves only *.enc files produced by
    # mdo_housekeeping.py (vault + DB snapshots, AES-256). A raw .db, a
    # snapshot .db.gz or a vault file is never served from here — the
    # backup-offsite Routine copies the bundle to Drive and never decrypts it.
    def _backup_dir() -> str:
        return os.environ.get("BACKUP_DIR", os.path.join(
            os.path.dirname(os.path.abspath(os.environ.get("VEGA_DB_PATH", "/data/vega_data.db"))), "backups"))

    def _bundles() -> list[dict]:
        """Every encrypted bundle in BACKUP_DIR, newest first. Plain files only, no dot-files, .enc only."""
        base = _backup_dir()
        if not os.path.isdir(base):
            return []
        out = []
        for fn in os.listdir(base):
            full = os.path.join(base, fn)
            if fn.startswith(".") or not fn.endswith(".enc") or not os.path.isfile(full):
                continue
            st = os.stat(full)
            out.append({"name": fn, "bytes": st.st_size,
                        "created": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()})
        return sorted(out, key=lambda b: (b["name"], b["created"]), reverse=True)

    @app.get("/api/vault/backup/list")
    async def vault_backup_list(request: Request):
        if not _vault_ok(request):
            await _audit("backup-list", "*", 0, _actor(request), False, "bad token")
            raise HTTPException(403, "bad or missing X-Vault-Token")
        bundles = _bundles()
        await _audit("backup-list", "*", len(bundles), _actor(request), True)
        return bundles

    @app.get("/api/vault/backup/latest")
    async def vault_backup_latest(request: Request):
        if not _vault_ok(request):
            await _audit("backup-latest", "?", 0, _actor(request), False, "bad token")
            raise HTTPException(403, "bad or missing X-Vault-Token")
        weekly = [b for b in _bundles() if b["name"].startswith("weekly-")]
        if not weekly:
            await _audit("backup-latest", "?", 0, _actor(request), False, "no bundle")
            raise HTTPException(404, "no weekly bundle yet — housekeeping has not produced one "
                                     "(is VAULT_BACKUP_PASSPHRASE set in .env?)")
        b = weekly[0]
        await _audit("backup-latest", b["name"], b["bytes"], _actor(request), True)
        return FileResponse(os.path.join(_backup_dir(), b["name"]), media_type="application/octet-stream",
                            filename=b["name"], headers={"X-Backup-Created": b["created"]})

    @app.post("/api/cos/send")
    async def cos_send(body: dict):
        return send_cos(str(body.get("text") or ""), to=body.get("to"), legacy_send=legacy_send)

    @app.get("/api/cos/constitution")
    async def cos_constitution():
        try:
            return {"text": CONSTITUTION_PATH.read_text(encoding="utf-8")}
        except FileNotFoundError:
            return {"text": ""}

    return {
        "ensure_schema": ensure_schema, "record_run": record_run, "send_cos": send_cos,
        "agenda": agenda_get, "jobs": jobs_list, "job_add": job_add, "job_resolve": job_resolve,
        "fleet": fleet_status, "spend": spend_summary, "spend_record": spend_record, "memory": memory_get,
        "chat_load": chat_load, "chat_save": chat_save, "tender_ingest": tender_ingest,
    }
