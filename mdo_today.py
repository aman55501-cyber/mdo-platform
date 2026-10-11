"""/api/today — one small JSON for Aman's phone: what is waiting on him, today's plan, objectives, the system in one line,
tenders, volume. Read-only except through the existing /api/plan endpoints. No LLM.

Aman, chat 2026-10-11: "an interface for mobile (Android) to help me keep track and further progress from my phone, because I
can't be in front of a laptop all the time." The page is /today in the app (installable from Chrome: Add to Home screen).
"""
from __future__ import annotations

import json
import asyncio
import os
import re
from datetime import datetime
from typing import Any, Awaitable, Callable

import yaml

from mdo_cos import IST
from mdo_plan import REASONS, short_objectives

ROOT = os.path.dirname(os.path.abspath(__file__))


def parse_pending(md: str) -> list[dict]:
    """AMAN_PENDING.md table rows '| A27 | item | why | since |' → [{id, item, why, since}]. Header and separator rows skipped."""
    out = []
    for ln in str(md or "").splitlines():
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 4 or not re.fullmatch(r"A\d+", cells[0]):
            continue
        if re.match(r"(WITHDRAWN|ANSWERED|DONE|CLOSED|SUPERSEDED)\b", cells[1]):     # closed rows stay in the file but are not "waiting on you"
            continue
        out.append({"id": cells[0], "item": cells[1], "why": cells[2], "since": cells[3]})
    return out


def register(app, vdb: Callable[[], Awaitable[Any]], cos: dict, credit_guard: dict | None = None,
             agenda_path: str | None = None, pending_path: str | None = None, logins: Callable[[], dict] | None = None) -> dict:
    agenda_file = agenda_path or os.path.join(ROOT, "agenda.yaml")
    pending_file = pending_path or os.path.join(ROOT, "AMAN_PENDING.md")

    async def _table(db, name: str) -> bool:
        return bool(await db.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)))

    async def today() -> dict:
        now = datetime.now(IST)
        day = now.date().isoformat()
        db = await vdb()
        out: dict[str, Any] = {"as_of": now.isoformat(timespec="minutes"), "date": day, "reasons": list(REASONS)}
        # plan
        if await _table(db, "plan_items"):
            names = {r["key"]: r["name"] for r in await db.execute_fetchall("SELECT key, name FROM plan_projects")}
            items = [dict(r) for r in await db.execute_fetchall("SELECT * FROM plan_items WHERE plan_date=? ORDER BY project, id", (day,))]
            out["plan"] = {"projects": names, "items": items,
                           "done": sum(1 for i in items if i["status"] == "done"), "total": len(items)}
        else:
            out["plan"] = {"projects": {}, "items": [], "done": 0, "total": 0}
        # objectives
        try:
            out["objectives"] = short_objectives(yaml.safe_load(open(agenda_file, encoding="utf-8")) or {}, 14)
        except Exception:
            out["objectives"] = []
        # waiting on Aman
        try:
            out["pending"] = parse_pending(open(pending_file, encoding="utf-8").read())
        except Exception:
            out["pending"] = []
        # system in one glance
        try:
            f = await cos["fleet"]()
            bots = [b for b in f.get("bots", []) if b.get("enabled")]
            late = [b.get("name", b.get("id", "?"))[:30] for b in bots if b.get("missed")]
            out["system"] = {"enabled": len(bots), "late": late}
        except Exception:
            out["system"] = {"enabled": None, "late": ["fleet status unavailable"]}
        if credit_guard:
            try:
                st = await credit_guard["status"]()
                out["credits"] = st.get("line", "")
            except Exception:
                out["credits"] = ""
        # daily broker logins: status per account and the one link that logs in (HDFC needs a fresh OTP every day, so it stays a tap)
        out["logins"] = {"accounts": [], "login_url": "", "error": ""}
        if logins:
            try:
                out["logins"] = await asyncio.to_thread(logins)
            except Exception as e:
                out["logins"]["error"] = str(e)[:120]
        # tenders and volume
        out["tenders"] = []
        if await _table(db, "vwlr_tender_pipeline"):
            out["tenders"] = [dict(r) for r in await db.execute_fetchall(
                "SELECT buyer, category, due_date, status, substr(notes,1,120) AS notes, url FROM vwlr_tender_pipeline "
                "WHERE status='evaluating' ORDER BY COALESCE(due_date,'9999') ASC, id DESC LIMIT 6")]
        out["volume"] = ""
        if await _table(db, "volume_runs"):
            r = await db.execute_fetchall("SELECT line FROM volume_runs ORDER BY id DESC LIMIT 1")
            out["volume"] = r[0][0] if r else ""
        out["competitors"] = ""
        if await _table(db, "t247_results"):
            r = await db.execute_fetchall("SELECT COUNT(*) FROM t247_results WHERE relevant=1")
            out["competitors"] = f"{r[0][0]} coal/washery/RCR results on file (GET /api/t247/intel)"
        return out

    @app.get("/api/today")
    async def api_today():
        return await today()

    return {"today": today}
