"""credit-guard — Aman never hits the Claude usage wall again (Aman, chat 2026-10-09 and 2026-10-10).

Two budgets, both watched, zero LLM spend:

1. The claude.ai plan (what ran out on 2026-10-09). No API exposes the balance; the only
   signal is each Claude session's rate_limit_info (status allowed | allowed_warning |
   rejected, the window type, resetsAt, isUsingOverage). Every Claude session on this repo
   posts it to POST /api/credits/plan at start and before spawning a worker (CLAUDE.md).
2. The fleet API cap (spend_ledger vs SPEND_CAP_INR_MONTH). mdo_cos.pace_mode switches every
   bot to the economy model as soon as the month is ON PACE to pass the cap — not at 90%.

The guard turns both into one policy the sessions obey (GET /api/credits → policy):
workers allowed or not, and which model each kind of work runs on. It pushes one WhatsApp
line per state change (deduped per window / month) and heartbeats every run, also "credits fine".
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from mdo_cos import IST

SCHEMA = """
CREATE TABLE IF NOT EXISTS credit_plan_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    session TEXT DEFAULT '',
    status TEXT NOT NULL,
    limit_type TEXT DEFAULT '',
    resets_at INTEGER,
    overage INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS credit_guard_alerts (
    key TEXT PRIMARY KEY,
    sent_at TEXT NOT NULL,
    text TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS credit_guard_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    status TEXT NOT NULL,
    line TEXT NOT NULL
);
"""

PLAN_STATUSES = ("allowed", "allowed_warning", "rejected")
STALE_HOURS = 6          # an older plan reading says nothing about the current 5-hour window

# Which model each kind of work runs on, per plan state. Aliases are the Agent tool's.
# "read" = search, summarise, parse, check; "build" = code, analysis; "hard" = money/legal/regulator reasoning,
# a failed or contradicted cheaper attempt, or the final check before anything reaches Aman; "cos" = the
# session talking to Aman (it routes; the heavy lifting is delegated).
POLICY = {
    "ok":      {"workers": "yes", "max_workers": 2, "models": {"read": "haiku", "build": "sonnet", "hard": "opus", "cos": "sonnet"}},
    "unknown": {"workers": "yes", "max_workers": 1, "models": {"read": "haiku", "build": "sonnet", "hard": "opus", "cos": "sonnet"}},
    "tight":   {"workers": "no",  "max_workers": 0, "models": {"read": "haiku", "build": "haiku", "hard": "sonnet", "cos": "sonnet"}},
    "blocked": {"workers": "no",  "max_workers": 0, "models": {"read": "haiku", "build": "haiku", "hard": "haiku", "cos": "haiku"}},
    "overage": {"workers": "no",  "max_workers": 0, "models": {"read": "haiku", "build": "haiku", "hard": "sonnet", "cos": "sonnet"}},
}


def _query_tz(s: str) -> str:
    """'2026-10-09T08:00:00 05:30' → '+05:30': an unescaped '+' in a query string arrives as a space."""
    return re.sub(r" (\d\d:\d\d)$", r"+\1", s.strip())


def parse_now(v: Any) -> datetime:
    if isinstance(v, datetime):
        d = v
    elif v:
        try:
            d = datetime.fromisoformat(_query_tz(str(v).replace("Z", "+00:00")))
        except ValueError:
            d = datetime.now(IST)
    else:
        d = datetime.now(IST)
    return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(IST)


def normalise_reading(body: dict) -> dict:
    """Accepts the rate_limit_info dict as get_session returns it, bare or under "rate_limit_info"."""
    r = body.get("rate_limit_info") if isinstance(body.get("rate_limit_info"), dict) else body
    status = str(r.get("status") or "").strip().lower()
    if status not in PLAN_STATUSES:
        raise ValueError(f"status must be one of {', '.join(PLAN_STATUSES)}")
    resets = r.get("resetsAt", r.get("resets_at"))
    try:
        resets = int(resets) if resets not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("resetsAt must be a unix timestamp")
    return {"status": status, "limit_type": str(r.get("rateLimitType") or r.get("limit_type") or "")[:40],
            "resets_at": resets, "overage": 1 if (r.get("isUsingOverage") or r.get("overage")) else 0,
            "session": str(body.get("session") or r.get("session") or "")[:80]}


def plan_state(reading: dict | None, now: datetime) -> str:
    """ok | tight | blocked | overage | unknown (no reading, stale, or its window already reset)."""
    if not reading:
        return "unknown"
    at = parse_now(reading["at"])
    if (now - at).total_seconds() > STALE_HOURS * 3600:
        return "unknown"
    if reading.get("resets_at") and reading["resets_at"] <= now.timestamp():
        return "unknown"
    if reading.get("overage"):
        return "overage"
    return {"allowed": "ok", "allowed_warning": "tight", "rejected": "blocked"}[reading["status"]]


def hhmm(ts: int | None) -> str:
    if not ts:
        return "?"
    return datetime.fromtimestamp(ts, timezone.utc).astimezone(IST).strftime("%H:%M")


def model_short(m: str) -> str:
    for k in ("fable", "opus", "sonnet", "haiku", "grok"):
        if k in (m or ""):
            return k
    return m or "?"


def build_line(state: str, reading: dict | None, spend: dict, now: datetime) -> str:
    if state == "unknown":
        plan = "plan: no live reading" + (f" (last {parse_now(reading['at']):%d %b %H:%M})" if reading else "")
    else:
        plan = f"plan: {state} · resets {hhmm(reading.get('resets_at'))} IST · overage {'yes' if reading.get('overage') else 'no'}"
    cap = spend.get("cap_inr")
    api = f"API ₹{spend.get('month_to_date_inr', 0):,.0f}"
    api += f" of ₹{cap:,.0f} ({spend.get('pct_of_cap')}%)" if cap else " (no cap set)"
    api += f" · forecast ₹{spend.get('forecast_inr', 0):,.0f} · {spend.get('mode', 'normal')}"
    if spend.get("mode_reason"):
        api += f" ({spend['mode_reason']})"
    top = (spend.get("by_bot") or [])[:1]
    if top:
        api += f" · top {top[0]['bot']} {model_short(top[0]['model'])} ₹{top[0]['inr']:,.0f}"
    verdict = "credits fine" if state in ("ok", "unknown") and spend.get("mode", "normal") == "normal" else "credits TIGHT"
    return f"credit-guard: {verdict} · {plan} · {api}"


def alerts_for(state: str, reading: dict | None, spend: dict, now: datetime) -> list[tuple[str, str]]:
    """(dedupe key, WhatsApp line). One line per state per window / month, never a repeat."""
    out: list[tuple[str, str]] = []
    window = (reading or {}).get("resets_at") or now.strftime("%Y-%m-%d")
    resets = hhmm((reading or {}).get("resets_at"))
    if state == "tight":
        out.append((f"plan-tight-{window}",
                    f"🔴 Claude plan near its limit — resets {resets} IST. Workers stopped; reads on Haiku, CoS on Sonnet until reset."))
    elif state == "blocked":
        out.append((f"plan-blocked-{window}",
                    f"🔴 Claude plan limit hit — resets {resets} IST. Nothing new starts until then; VPS bots keep running (no plan credits)."))
    elif state == "overage":
        out.append((f"plan-overage-{now:%Y-%m-%d}",
                    f"🔴 Claude sessions are on paid overage (window resets {resets} IST). Workers stopped. Reply \"overage ok\" to allow."))
    month = spend.get("month") or now.strftime("%Y-%m")
    mode = spend.get("mode", "normal")
    if mode == "economy":
        out.append((f"api-economy-{month}",
                    f"🟡 Fleet API {spend.get('mode_reason') or 'near cap'} — every bot on the economy model until month end, or raise SPEND_CAP_INR_MONTH."))
    elif mode == "paused":
        out.append((f"api-paused-{month}",
                    f"🔴 Fleet API cap reached (₹{spend.get('month_to_date_inr', 0):,.0f}) — LLM bots paused; zero-LLM bots keep running."))
    return out


def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict],
             spend_summary: Callable[[], Awaitable[dict]]) -> dict:

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def latest_reading() -> dict | None:
        db = await vdb()
        await ensure_schema(db)
        rows = await db.execute_fetchall("SELECT * FROM credit_plan_readings ORDER BY id DESC LIMIT 1")
        return dict(rows[0]) if rows else None

    async def record_reading(body: dict, now_v: Any = None) -> dict:
        r = normalise_reading(body)
        now = parse_now(now_v or body.get("now"))
        db = await vdb()
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO credit_plan_readings (at, session, status, limit_type, resets_at, overage) VALUES (?,?,?,?,?,?)",
            (now.isoformat(), r["session"], r["status"], r["limit_type"], r["resets_at"], r["overage"]))
        await db.commit()
        return await status(now)

    async def status(now: datetime | None = None) -> dict:
        now = now or datetime.now(IST)
        reading = await latest_reading()
        spend = await spend_summary()
        state = plan_state(reading, now)
        db = await vdb()
        last = await db.execute_fetchall("SELECT at, status, line FROM credit_guard_runs ORDER BY id DESC LIMIT 1")
        return {"as_of": now.isoformat(), "plan_state": state, "plan": reading, "api": spend,
                "policy": {"state": state, **POLICY[state], "fleet_api_mode": spend.get("mode", "normal")},
                "line": build_line(state, reading, spend, now), "last_run": dict(last[0]) if last else None}

    async def run(now_v: Any = None) -> dict:
        now = parse_now(now_v)
        st = await status(now)
        db = await vdb()
        pushed, failed, texts = 0, 0, []
        for key, text in alerts_for(st["plan_state"], st["plan"], st["api"], now):
            seen = await db.execute_fetchall("SELECT 1 FROM credit_guard_alerts WHERE key=?", (key,))
            if seen:
                continue
            res = send_cos(text) or {}
            if res.get("sent") is False:
                failed += 1
                continue
            await db.execute("INSERT INTO credit_guard_alerts (key, sent_at, text) VALUES (?,?,?)", (key, now.isoformat(), text))
            pushed += 1
            texts.append(text)
        line = st["line"] + (f" · {pushed} alert(s) pushed" if pushed else "") + (f" · {failed} push FAILED" if failed else "")
        run_status = "warning" if failed or "TIGHT" in line else "clean"
        await db.execute("INSERT INTO credit_guard_runs (at, status, line) VALUES (?,?,?)", (now.isoformat(), run_status, line))
        await db.commit()
        return {"line": line, "status": run_status, "pushed": pushed, "push_failed": failed, "texts": texts,
                "plan_state": st["plan_state"], "policy": st["policy"]}

    @app.post("/api/credits/plan")
    async def credits_plan(body: dict):
        from fastapi import HTTPException
        try:
            return await record_reading(body)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/credits")
    async def credits_get(now: str | None = None):
        return await status(parse_now(now) if now else None)

    @app.post("/api/credits/run")
    async def credits_run(body: dict | None = None):
        return await run((body or {}).get("now"))

    return {"ensure_schema": ensure_schema, "status": status, "run": run, "record_reading": record_reading}
