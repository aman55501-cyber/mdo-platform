"""daily-plan — today's objectives each morning, objective-vs-actual each evening, and where the fault lay.

Aman, chat 2026-10-11: "Daily summary must include today's objectives in the morning and the objective-vs-actual
sheet for analysing what stalled — work that would finish today. This tells me daily where the fault lay if some
work that could finish today didn't finish today. Set this up for washery, hotel renovation and any other active
project." Zero LLM, rule-based.

Flow
  morning 07:30 IST   one WhatsApp message: each live objective's next action, each project's plan for today
                      (yesterday's unfinished items carried over and marked as such), fleet health, his pending count.
                      Yesterday's items nobody reported on are closed as "missed — not reported" (never silently).
  evening 19:30 IST   one message: planned vs done vs missed per project, the faults of the day, and what is still
                      open with the exact reply to close it.
  any time            WhatsApp (his self-chat) or the app:
                        plan washery: pour slab C2 @Ramesh; fix shuttering @Suresh
                        done 3        done 3,4
                        miss 5 material          miss 5 manpower by Ramesh
                        today                    (shows the list)
Reason codes: material, manpower, machine, approval, payment, weather, design, vendor, power, our-error, other.
The sheet (GET /api/plan/sheet) and the fault tally (GET /api/plan/faults) are what the Morning page shows.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable

import yaml
from fastapi import HTTPException

from mdo_cos import IST

REASONS = ("material", "manpower", "machine", "approval", "payment", "weather", "design", "vendor", "power", "our-error", "other")
DEFAULT_PROJECTS = (("washery", "Washery — build and commissioning"), ("hotel", "Hotel ANS — renovation"))
ROOT = os.path.dirname(os.path.abspath(__file__))

SCHEMA = """
CREATE TABLE IF NOT EXISTS plan_projects (
    key TEXT PRIMARY KEY, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT NOT NULL,
    project TEXT NOT NULL,
    item TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',          -- open | done | missed
    reason TEXT NOT NULL DEFAULT '',
    fault TEXT NOT NULL DEFAULT '',                -- who or what: a name, 'unreported', or the reason's owner
    carried_from INTEGER,
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_plan_items_date ON plan_items(plan_date, project);
"""

_PROJECT_SLUG = re.compile(r"[^a-z0-9]+")


def slug(s: str) -> str:
    return _PROJECT_SLUG.sub("-", str(s or "").strip().lower()).strip("-")


def parse_ids(text: str) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", text or "")]


def parse_command(text: str) -> dict | None:
    """WhatsApp grammar → {"cmd": plan|done|miss|today, ...}, or None when the text is something else.
    plan <project>: item1; item2 @owner   ·  done 3,4  ·  miss 5 <reason> [by <name>]  ·  today"""
    t = " ".join(str(text or "").split())
    low = t.lower()
    if low in ("today", "plan", "plan?", "today?", "plans"):
        return {"cmd": "today"}
    m = re.match(r"^plan\s+([a-z0-9][a-z0-9 _-]{0,30}?)\s*:\s*(.+)$", t, re.I)
    if m:
        items = []
        for part in re.split(r"\s*;\s*", m.group(2)):
            part = part.strip()
            if not part:
                continue
            o = re.search(r"\s@\s*([A-Za-z][A-Za-z .'-]{0,30})$", part)
            items.append({"item": (part[:o.start()] if o else part).strip(), "owner": o.group(1).strip() if o else ""})
        return {"cmd": "plan", "project": slug(m.group(1)), "items": items} if items else None
    m = re.match(r"^(done|finished|complete[d]?)\s+#?([\d,\s#and]+)$", low)
    if m and parse_ids(m.group(2)):
        return {"cmd": "done", "ids": parse_ids(m.group(2))}
    m = re.match(r"^(miss|missed|stalled|not done)\s+#?(\d+)\s*([a-z-]*)\s*(?:by\s+(.+))?$", low)
    if m:
        reason = m.group(3) if m.group(3) in REASONS else ("other" if m.group(3) == "" else m.group(3))
        return {"cmd": "miss", "ids": [int(m.group(2))], "reason": reason, "by": (m.group(4) or "").strip(),
                "bad_reason": m.group(3) if m.group(3) and m.group(3) not in REASONS else ""}
    return None


def short_objectives(agenda: dict, limit: int = 12) -> list[str]:
    """One line per confirmed objective: its id and its next action (or blocker). Aman's words, nothing added."""
    out = []
    for o in (agenda or {}).get("objectives", []):
        if o.get("confirmed") is not True:
            continue
        na = (o.get("next_action") or "").strip()
        bl = (o.get("blocker") or "").strip()
        line = f"• {o['id']}: " + (na[:110] if na else (o.get("title") or "").strip()[:110]) + (f" — blocked: {bl[:70]}" if bl else "")
        out.append(line)
    return out[:limit]


def status_icon(st: str) -> str:
    return {"done": "✅", "missed": "❌", "open": "⏳"}.get(st, "•")


def fault_text(row: dict) -> str:
    if row["status"] != "missed":
        return ""
    bits = [row["reason"] or "other"]
    if row["fault"] and row["fault"] != row["reason"]:
        bits.append(row["fault"])
    return " — " + " · ".join(bits)


def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict], cos: dict | None = None,
             inbound_hooks: list | None = None, agenda_path: str | None = None) -> dict:
    cos = cos or {}
    agenda_file = agenda_path or os.path.join(ROOT, "agenda.yaml")

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        for k, n in DEFAULT_PROJECTS:
            await db.execute("INSERT OR IGNORE INTO plan_projects (key, name) VALUES (?,?)", (k, n))
        await db.commit()

    def today_ist(now: datetime | None = None) -> date:
        return (now or datetime.now(IST)).astimezone(IST).date()

    def _now(v: Any) -> datetime:
        if isinstance(v, datetime):
            d = v
        else:
            try:
                d = datetime.fromisoformat(str(v).replace("Z", "+00:00").replace(" ", "+")) if v else datetime.now(IST)
            except ValueError:
                d = datetime.now(IST)
        return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(IST)

    async def projects(active_only: bool = True) -> list[dict]:
        db = await vdb()
        await ensure_schema(db)
        q = "SELECT * FROM plan_projects" + (" WHERE active=1" if active_only else "") + " ORDER BY key"
        return [dict(r) for r in await db.execute_fetchall(q)]

    async def add_project(name: str, key: str = "") -> dict:
        k = slug(key or name)
        if not k:
            raise HTTPException(400, "project name required")
        db = await vdb()
        await ensure_schema(db)
        await db.execute("INSERT INTO plan_projects (key, name, active) VALUES (?,?,1) ON CONFLICT(key) DO UPDATE SET name=excluded.name, active=1", (k, name.strip() or k))
        await db.commit()
        return {"key": k, "name": name.strip() or k}

    async def add_items(project: str, items: list[dict], plan_date: str, source: str = "app") -> dict:
        db = await vdb()
        await ensure_schema(db)
        keys = {p["key"] for p in await projects(False)}
        k = slug(project)
        if k not in keys:
            # a short form is fine: "wash" -> washery when it is the only prefix match
            near = [x for x in keys if x.startswith(k)] if k else []
            if len(near) == 1:
                k = near[0]
            else:
                raise HTTPException(400, f"unknown project '{project}'; known: {', '.join(sorted(keys))}")
        ids = []
        for it in items:
            text = str(it.get("item") or "").strip()
            if not text:
                continue
            cur = await db.execute("INSERT INTO plan_items (plan_date, project, item, owner, source) VALUES (?,?,?,?,?)",
                                   (plan_date, k, text[:300], str(it.get("owner") or "")[:60], source))
            ids.append(cur.lastrowid)
        await db.commit()
        return {"project": k, "date": plan_date, "ids": ids}

    async def close_item(item_id: int, status: str, reason: str = "", fault: str = "", now: datetime | None = None) -> dict:
        if status not in ("done", "missed"):
            raise HTTPException(400, "status must be done or missed")
        db = await vdb()
        await ensure_schema(db)
        rows = await db.execute_fetchall("SELECT * FROM plan_items WHERE id=?", (item_id,))
        if not rows:
            return {"ok": False, "reason": f"no item #{item_id}"}
        r = dict(rows[0])
        reason = reason if reason in REASONS else ("other" if status == "missed" else "")
        fault = fault or (r["owner"] if reason in ("manpower", "our-error") and r["owner"] else reason)
        await db.execute("UPDATE plan_items SET status=?, reason=?, fault=?, closed_at=? WHERE id=?",
                         (status, "" if status == "done" else reason, "" if status == "done" else fault,
                          (now or datetime.now(IST)).isoformat(timespec="minutes"), item_id))
        await db.commit()
        return {"ok": True, "id": item_id, "status": status, "reason": reason, "fault": fault, "item": r["item"], "project": r["project"]}

    async def items_for(day: str) -> list[dict]:
        db = await vdb()
        await ensure_schema(db)
        return [dict(r) for r in await db.execute_fetchall("SELECT * FROM plan_items WHERE plan_date=? ORDER BY project, id", (day,))]

    def lines_for(items: list[dict], names: dict[str, str]) -> list[str]:
        out, cur = [], None
        for r in items:
            if r["project"] != cur:
                cur = r["project"]
                out.append(f"{names.get(cur, cur)}")
            carried = " (carried over)" if r.get("carried_from") else ""
            out.append(f"  {status_icon(r['status'])} #{r['id']} {r['item']}" + (f" @{r['owner']}" if r["owner"] else "") + carried + fault_text(r))
        return out

    async def names() -> dict[str, str]:
        return {p["key"]: p["name"] for p in await projects(False)}

    # ── the two runs ──────────────────────────────────────────────────────
    async def fleet_line() -> str:
        try:
            f = await cos["fleet"]()
            bots = [b for b in f.get("bots", []) if b.get("enabled")]
            late = [b["id"] for b in bots if b.get("missed")]
            return f"Fleet {len(bots) - len(late)}/{len(bots)} on time" + (f" · late: {', '.join(late[:4])}" if late else "")
        except Exception:
            return "Fleet: status unavailable"

    async def pending_line() -> str:
        try:
            j = await cos["jobs"]("open", 50)
            n = len(j.get("jobs", []))
            return f"Waiting on you: {n} job{'s' if n != 1 else ''}" if n else "Waiting on you: nothing in the job list"
        except Exception:
            return ""

    async def morning(now_v: Any = None) -> dict:
        now = _now(now_v)
        day = today_ist(now).isoformat()
        yday = (today_ist(now) - timedelta(days=1)).isoformat()
        db = await vdb()
        await ensure_schema(db)
        # close yesterday's unreported items honestly, then carry them forward
        carried = 0
        for r in await db.execute_fetchall("SELECT * FROM plan_items WHERE plan_date=? AND status='open'", (yday,)):
            r = dict(r)
            await db.execute("UPDATE plan_items SET status='missed', reason='other', fault='unreported', closed_at=? WHERE id=?",
                             (now.isoformat(timespec="minutes"), r["id"]))
            dup = await db.execute_fetchall("SELECT 1 FROM plan_items WHERE plan_date=? AND carried_from=?", (day, r["id"]))
            if not dup:
                await db.execute("INSERT INTO plan_items (plan_date, project, item, owner, carried_from, source) VALUES (?,?,?,?,?, 'carry-over')",
                                 (day, r["project"], r["item"], r["owner"], r["id"]))
                carried += 1
        await db.commit()
        try:
            agenda = yaml.safe_load(open(agenda_file, encoding="utf-8")) or {}
        except Exception:
            agenda = {}
        nm = await names()
        todays = await items_for(day)
        lines = [f"Good morning · {now:%a %d %b} · today's objectives", ""]
        lines += short_objectives(agenda)
        lines += ["", "Project plan for today:"]
        if todays:
            lines += lines_for(todays, nm)
        else:
            lines.append("  nothing planned yet — reply e.g.  plan washery: pour slab C2 @Ramesh; fix shuttering")
        silent = [p["key"] for p in await projects() if not any(t["project"] == p["key"] for t in todays)]
        if silent and todays:
            lines.append(f"  no plan yet for: {', '.join(silent)}")
        lines += ["", await fleet_line(), await pending_line()]
        text = "\n".join(l for l in lines if l is not None).strip()
        res = send_cos(text) or {}
        sent = bool(res.get("sent"))
        line = f"daily-plan morning: {len(todays)} item{'s' if len(todays) != 1 else ''} planned, {carried} carried over" + ("" if sent else " · push NOT delivered")
        return {"line": line, "status": "clean" if sent else "warning", "text": text, "items": len(todays), "carried": carried, "pushed": 1 if sent else 0}

    async def evening(now_v: Any = None) -> dict:
        now = _now(now_v)
        day = today_ist(now).isoformat()
        items = await items_for(day)
        nm = await names()
        done = [i for i in items if i["status"] == "done"]
        missed = [i for i in items if i["status"] == "missed"]
        openi = [i for i in items if i["status"] == "open"]
        lines = [f"Evening · {now:%a %d %b} · planned vs actual", ""]
        if not items:
            lines.append("Nothing was planned today, so there is nothing to compare. Reply  plan <project>: item; item  tomorrow morning.")
        else:
            bar = "█" * round(10 * len(done) / len(items)) + "░" * (10 - round(10 * len(done) / len(items)))
            lines.append(f"{bar} {len(done)}/{len(items)} done · {len(missed)} missed · {len(openi)} not reported")
            lines += [""] + lines_for(items, nm)
            if missed:
                tally: dict[str, int] = {}
                for m in missed:
                    tally[m["reason"] or "other"] = tally.get(m["reason"] or "other", 0) + 1
                lines += ["", "Where it stalled: " + ", ".join(f"{k} ×{v}" for k, v in sorted(tally.items(), key=lambda kv: -kv[1]))]
            if openi:
                ids = ", ".join(f"#{i['id']}" for i in openi[:6])
                lines += ["", f"Not reported: {ids}. Reply  done 3  or  miss 3 material  (reasons: {', '.join(REASONS)})."]
        text = "\n".join(lines).strip()
        res = send_cos(text) or {}
        sent = bool(res.get("sent"))
        line = (f"daily-plan evening: {len(done)}/{len(items)} done, {len(missed)} missed, {len(openi)} not reported"
                + ("" if sent else " · push NOT delivered"))
        return {"line": line, "status": "clean" if sent else "warning", "text": text, "done": len(done), "missed": len(missed),
                "open": len(openi), "pushed": 1 if sent else 0}

    async def run(mode: str = "morning", now_v: Any = None) -> dict:
        if mode not in ("morning", "evening"):
            raise HTTPException(400, "mode must be morning or evening")
        return await (morning(now_v) if mode == "morning" else evening(now_v))

    # ── WhatsApp / app commands ───────────────────────────────────────────
    async def handle_text(sender: str, text: str) -> str | None:
        cmd = parse_command(text)
        if not cmd:
            return None
        now = datetime.now(IST)
        day = today_ist(now).isoformat()
        nm = await names()
        if cmd["cmd"] == "today":
            items = await items_for(day)
            return "\n".join(["Today's plan"] + (lines_for(items, nm) if items else ["  nothing planned yet"]))
        if cmd["cmd"] == "plan":
            try:
                res = await add_items(cmd["project"], cmd["items"], day, source="whatsapp")
            except HTTPException as e:
                return f"❓ {e.detail}"
            return f"✔ planned {len(res['ids'])} for {nm.get(res['project'], res['project'])}: " + ", ".join(f"#{i}" for i in res["ids"])
        if cmd["cmd"] == "done":
            outs = [await close_item(i, "done", now=now) for i in cmd["ids"]]
            ok = [o["id"] for o in outs if o.get("ok")]
            bad = [o["reason"] for o in outs if not o.get("ok")]
            return ("✔ done " + ", ".join(f"#{i}" for i in ok) if ok else "") + (("  ❓ " + "; ".join(bad)) if bad else "")
        if cmd["cmd"] == "miss":
            if cmd.get("bad_reason"):
                return f"❓ reason '{cmd['bad_reason']}' unknown. Use one of: {', '.join(REASONS)}"
            o = await close_item(cmd["ids"][0], "missed", cmd["reason"], cmd["by"], now=now)
            return (f"✔ #{o['id']} missed — {o['reason']}" + (f" ({o['fault']})" if o["fault"] and o["fault"] != o["reason"] else "")) if o.get("ok") else f"❓ {o['reason']}"
        return None

    if inbound_hooks is not None:
        inbound_hooks.append(handle_text)

    # ── the sheet ─────────────────────────────────────────────────────────
    async def sheet(days: int = 7, project: str = "", now_v: Any = None) -> dict:
        days = max(1, min(int(days or 7), 90))
        end = today_ist(_now(now_v))
        start = end - timedelta(days=days - 1)
        db = await vdb()
        await ensure_schema(db)
        q = "SELECT * FROM plan_items WHERE plan_date BETWEEN ? AND ?" + (" AND project=?" if project else "") + " ORDER BY plan_date DESC, project, id"
        rows = [dict(r) for r in await db.execute_fetchall(q, (start.isoformat(), end.isoformat()) + ((slug(project),) if project else ()))]
        by_day: dict[str, dict] = {}
        for r in rows:
            d = by_day.setdefault(r["plan_date"], {"date": r["plan_date"], "planned": 0, "done": 0, "missed": 0, "open": 0, "items": []})
            d["planned"] += 1
            d[r["status"]] += 1
            d["items"].append(r)
        tot = {"planned": len(rows), "done": sum(1 for r in rows if r["status"] == "done"),
               "missed": sum(1 for r in rows if r["status"] == "missed"), "open": sum(1 for r in rows if r["status"] == "open")}
        tot["done_pct"] = round(100 * tot["done"] / tot["planned"]) if tot["planned"] else None
        return {"from": start.isoformat(), "to": end.isoformat(), "totals": tot, "days": list(by_day.values()), "names": await names()}

    async def faults(days: int = 30, now_v: Any = None) -> dict:
        s = await sheet(days, "", now_v)
        missed = [i for d in s["days"] for i in d["items"] if i["status"] == "missed"]
        by_reason: dict[str, int] = {}
        by_fault: dict[str, int] = {}
        by_project: dict[str, int] = {}
        for m in missed:
            by_reason[m["reason"] or "other"] = by_reason.get(m["reason"] or "other", 0) + 1
            by_fault[m["fault"] or "other"] = by_fault.get(m["fault"] or "other", 0) + 1
            by_project[m["project"]] = by_project.get(m["project"], 0) + 1
        srt = lambda d: sorted(([k, v] for k, v in d.items()), key=lambda kv: -kv[1])
        return {"days": days, "missed": len(missed), "by_reason": srt(by_reason), "by_fault": srt(by_fault), "by_project": srt(by_project),
                "totals": s["totals"]}

    # ── endpoints ─────────────────────────────────────────────────────────
    @app.get("/api/plan/today")
    async def plan_today(date_: str | None = None):
        day = date_ or today_ist().isoformat()
        nm = await names()
        return {"date": day, "items": await items_for(day), "names": nm, "reasons": list(REASONS)}

    @app.post("/api/plan/items")
    async def plan_items_post(body: dict):
        items = body.get("items") or ([{"item": body.get("item"), "owner": body.get("owner", "")}] if body.get("item") else [])
        return await add_items(str(body.get("project") or ""), items, str(body.get("date") or today_ist().isoformat())[:10], "app")

    @app.post("/api/plan/items/{item_id}/close")
    async def plan_items_close(item_id: int, body: dict):
        return await close_item(item_id, str(body.get("status") or ""), str(body.get("reason") or ""), str(body.get("fault") or ""))

    @app.get("/api/plan/projects")
    async def plan_projects_get():
        return {"projects": await projects(False)}

    @app.post("/api/plan/projects")
    async def plan_projects_post(body: dict):
        return await add_project(str(body.get("name") or ""), str(body.get("key") or ""))

    @app.get("/api/plan/sheet")
    async def plan_sheet(days: int = 7, project: str = "", now: str | None = None):
        return await sheet(days, project, now)

    @app.get("/api/plan/faults")
    async def plan_faults(days: int = 30, now: str | None = None):
        return await faults(days, now)

    @app.post("/api/plan/run")
    async def plan_run(body: dict | None = None):
        body = body or {}
        return await run(str(body.get("mode") or "morning"), body.get("now"))

    return {"ensure_schema": ensure_schema, "run": run, "handle_text": handle_text, "sheet": sheet, "faults": faults,
            "add_items": add_items, "close_item": close_item}
