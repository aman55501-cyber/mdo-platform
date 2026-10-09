"""Public health check — the one alarm that fires when the fleet itself is dead. Zero LLM spend.

GET /api/health/public is the only unauthenticated read in the backend (the auth middleware exempts it; Caddy
already proxies /api/* to the backend). It answers 200 {"ok": true, "last_heartbeat_age_min": N, "bridges":
{"wa1": "connected"|"down", "wa2": ...}} only when BOTH hold:
  - the newest fleet heartbeat (cos_runs, filed by every bot run and by deploy_vps.sh --auto every 10 min) is
    younger than MAX_HEARTBEAT_AGE_MIN (45) minutes, and
  - the backend database opens and answers a query.
Otherwise HTTP 503 with {"ok": false, "reason": ...}. Nothing else is in the reply: no bot names, no summaries,
no tokens, no paths (Directive 9). A bridge that is down does NOT make the check fail — the WhatsApp bridges
have their own pairing state on the app; the external watchdog is about the VPS and the cron.

Wire-up: an UptimeRobot (free) HTTPS keyword monitor on https://<domain>/api/health/public every 5 min, keyword
"ok":true, alerting Aman by email + the UptimeRobot app (DEPLOY_HOSTINGER.md §"External watchdog"). When the
whole VPS is gone, the monitor sees a timeout, which is the same alarm.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

MAX_HEARTBEAT_AGE_MIN = 45
PUBLIC_PATH = "/api/health/public"
BRIDGES = (("wa1", "WA_BRIDGE_URL"), ("wa2", "WA_BRIDGE2_URL"))


# ── pure helpers ──────────────────────────────────────────────────────────────
def parse_stamp(s: Any) -> datetime | None:
    """cos_runs.created_at is sqlite's datetime('now') (UTC, no zone); ISO stamps with a zone are honoured."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def heartbeat_age_min(newest: Any, now: datetime | None = None) -> int | None:
    d = parse_stamp(newest)
    if d is None:
        return None
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return max(0, int((now - d).total_seconds() // 60))


def verdict(age_min: int | None, db_ok: bool, db_error: str = "", max_age: int = MAX_HEARTBEAT_AGE_MIN) -> tuple[bool, str]:
    """(ok, reason). Reason is empty when ok."""
    if not db_ok:
        return False, f"database not answering{': ' + db_error[:80] if db_error else ''}"
    if age_min is None:
        return False, "no fleet heartbeat on record"
    if age_min >= max_age:
        return False, f"last fleet heartbeat {age_min} min ago (limit {max_age})"
    return True, ""


def bridge_state(url: str, timeout: float = 4.0) -> str:
    """'connected' | 'down' — reads the bridge's own /api/whatsapp/qr (connected flag). Never raises."""
    if not url:
        return "down"
    try:
        with urllib.request.urlopen(urllib.request.Request(url.rstrip("/") + "/api/whatsapp/qr"), timeout=timeout) as r:
            data = json.loads(r.read() or b"{}")
        return "connected" if isinstance(data, dict) and data.get("connected") is True else "down"
    except Exception:
        return "down"


# ── registration ──────────────────────────────────────────────────────────────
def register(app, vdb: Callable[[], Awaitable[Any]]) -> dict:
    import asyncio

    from starlette.responses import JSONResponse

    hooks: dict[str, Any] = {"bridge_state": bridge_state}

    async def probe(now: datetime | None = None) -> tuple[int, dict]:
        db_ok, db_err, newest = True, "", None
        try:
            db = await vdb()
            rows = await db.execute_fetchall("SELECT MAX(created_at) AS t FROM cos_runs")
            newest = dict(rows[0])["t"] if rows else None
        except Exception as e:
            db_ok, db_err = False, f"{type(e).__name__}"
        age = heartbeat_age_min(newest, now)
        ok, reason = verdict(age, db_ok, db_err)
        bridges = {}
        for name, env_key in BRIDGES:
            url = os.environ.get(env_key, "").strip()
            bridges[name] = await asyncio.to_thread(hooks["bridge_state"], url) if url else "down"
        body: dict[str, Any] = {"ok": ok, "last_heartbeat_age_min": age, "bridges": bridges}
        if not ok:
            body["reason"] = reason
        return (200 if ok else 503), body

    @app.get(PUBLIC_PATH)
    async def health_public():
        code, body = await probe()
        return JSONResponse(body, status_code=code, headers={"Cache-Control": "no-store"})

    return {"probe": probe, "hooks": hooks}
