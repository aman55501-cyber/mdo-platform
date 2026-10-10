"""compliance-reminder — the statutory calendar and the week-before WhatsApp reminder. Rules only, zero LLM spend.

Aman, chat 2026-10-09: "compliance deadline [questions are] unnecessary. the compliance due dates are the
governmentally fixed dates and i need the reminder at least a week before." So: no questions, no LLM, no
invented entity. The calendar is data (data/compliance_calendar_in.json — every row carries the section or
rule its date comes from and the entity kinds it applies to; `extendable: true` marks dates CBDT/CBIC/MCA
can move by notification, and the bot never assumes an extension).

Two tables of its own:
  compliance_entities   Aman's entities with kind + flags (gst_registered, gst_qrmp, tds_deductor, audit_case,
                        pf_esi, active). Seeded EMPTY on purpose: the registry is not in this repo (CoS fills it
                        from the vault after AMAN_PENDING A15). Until then every reminder is group-level
                        ("all GST-registered entities: GSTR-3B due 20 Oct") and the heartbeat says
                        "entity list not loaded".
  compliance_reminders  one row per (entity-or-group, item, due date, stage) that was pushed; stage = week
                        (first run inside the 7-day window, which includes exactly 7 days before), eve (day
                        before), day (due date). A push happens once per stage; "done" stops later stages.

Modes, driven by `python mdo_agent.py compliance-reminder [daily|weekly]` (fleet.yaml: compliance-reminder):
  daily   08:00 IST: everything due in the next 7 days, ONE WhatsApp message grouped by date, pushed when at
          least one item reaches a stage today; nothing due → no push, heartbeat "0 items due in 7 days, next: …"
  weekly  Mon 08:05 IST: "this week: …" line, pushed even when empty.

Footer on every message (Aman's words): "Vimal Agrawal & Co (CA) handles filings; your click only for payments".
The pure helpers above register() take plain values and touch nothing — tests/test_compliance.py runs them
without a server.
"""
from __future__ import annotations

import re
import calendar as _cal
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request

from mdo_cos import IST

BOT_ID = "compliance-reminder"
MODES = ("daily", "weekly")
STAGES = ("week", "eve", "day")
WINDOW_DAYS = 7
KINDS = ("pvt_ltd", "llp", "partnership", "proprietorship", "individual")
FLAGS = ("gst_registered", "gst_qrmp", "tds_deductor", "audit_case", "pf_esi")
CALENDAR_PATH = os.environ.get("COMPLIANCE_CALENDAR_PATH",
                               os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "compliance_calendar_in.json"))
FOOTER_DEFAULT = "Vimal Agrawal & Co (CA) handles filings; your click only for payments"
NOT_LOADED = "entity list not loaded"

SCHEMA = """
CREATE TABLE IF NOT EXISTS compliance_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    kind TEXT NOT NULL,                               -- pvt_ltd | llp | partnership | proprietorship | individual
    gst_registered INTEGER NOT NULL DEFAULT 0, gst_qrmp INTEGER NOT NULL DEFAULT 0,
    tds_deductor INTEGER NOT NULL DEFAULT 0, audit_case INTEGER NOT NULL DEFAULT 0,
    pf_esi INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    source TEXT DEFAULT '', notes TEXT DEFAULT '',    -- source: where the row came from (Directive 6)
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS compliance_reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_or_group TEXT NOT NULL,
    item_id TEXT NOT NULL, item TEXT NOT NULL,        -- item_id = calendar row id; item = the dated label
    due_date TEXT NOT NULL, remind_on TEXT NOT NULL,  -- ISO dates (IST)
    stage TEXT NOT NULL,                              -- week | eve | day
    sent_at TEXT, status TEXT NOT NULL DEFAULT 'queued',   -- queued | sent | done
    message TEXT DEFAULT '', done_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(entity_or_group, item_id, due_date, stage)
);
CREATE INDEX IF NOT EXISTS idx_compliance_reminders_due ON compliance_reminders(due_date, status);
"""


# ═════════════════════════════════════════════════════════════════════════════
# Pure helpers — no database, no network
# ═════════════════════════════════════════════════════════════════════════════

def _query_tz(s: str) -> str:
    """'2026-10-09T08:00:00 05:30' → '+05:30': an unescaped '+' in a query string arrives as a space."""
    return re.sub(r" (\d\d:\d\d)$", r"+\1", s.strip())

def load_calendar(path: str | None = None) -> dict:
    with open(path or CALENDAR_PATH, encoding="utf-8") as f:
        cal = json.load(f)
    for row in cal.get("items") or []:
        for k in ("id", "item", "source", "applies_to", "cadence"):
            if not row.get(k):
                raise ValueError(f"calendar row {row.get('id')!r} lacks {k}")
        bad = [k for k in row["applies_to"] if k not in KINDS]
        if bad:
            raise ValueError(f"calendar row {row['id']!r}: unknown entity kind(s) {bad}")
    return cal


def fy_start_year(d: date) -> int:
    """Indian financial year: 1 Apr – 31 Mar. Returns the year the FY starts in."""
    return d.year if d.month >= 4 else d.year - 1


def fy_label(start_year: int) -> str:
    return f"FY{start_year}-{(start_year + 1) % 100:02d}"


def ay_label(fy_prev_start: int) -> str:
    """Assessment year for the FY starting fy_prev_start (FY2025-26 → AY2026-27)."""
    return f"AY{fy_prev_start + 1}-{(fy_prev_start + 2) % 100:02d}"


def fill(template: str, due: date, period_month: date | None = None) -> str:
    fy = fy_start_year(due)
    return (str(template or "")
            .replace("{fy_prev}", fy_label(fy - 1)).replace("{fy}", fy_label(fy))
            .replace("{ay}", ay_label(fy - 1))
            .replace("{month}", period_month.strftime("%b %Y") if period_month else ""))


def _clamp(y: int, m: int, d: int) -> date:
    return date(y, m, min(d, _cal.monthrange(y, m)[1]))


def _add_months(y: int, m: int, n: int) -> tuple[int, int]:
    k = (y * 12 + (m - 1)) + n
    return k // 12, k % 12 + 1


def _occ(row: dict, due: date, label: str) -> dict:
    return {"item_id": row["id"], "item": row["item"], "label": label, "due": due.isoformat(),
            "cadence": row.get("cadence", ""), "source": row["source"], "extendable": bool(row.get("extendable")),
            "applies_to": list(row.get("applies_to") or []), "requires": row.get("requires"),
            "requires_not": row.get("requires_not"), "always_for": list(row.get("always_for") or []),
            "group": str(row.get("group") or "all entities"), "remind_group": row.get("remind_group", True) is not False,
            "payment": bool(row.get("payment"))}


def expand(cal: dict, start: date, end: date) -> list[dict]:
    """Every dated occurrence of every calendar row with start ≤ due ≤ end, in due-date order (then calendar order)."""
    out: list[tuple[date, int, dict]] = []
    for idx, row in enumerate(cal.get("items") or []):
        if row.get("cadence") == "monthly":
            overrides = {int(k): v for k, v in (row.get("overrides") or {}).items()}
            y, m = _add_months(start.year, start.month, -2)
            while date(y, m, 1) <= end:
                period = date(y, m, 1)
                specs = overrides.get(m) or [{"months_after": 1, "day": int(row["day"]), "period": row.get("period") or row["item"]}]
                for sp in specs:
                    yy, mm = _add_months(y, m, int(sp.get("months_after", 1)))
                    due = _clamp(yy, mm, int(sp.get("day", row.get("day", 1))))
                    if start <= due <= end:
                        out.append((due, idx, _occ(row, due, fill(sp.get("period") or row.get("period") or row["item"], due, period))))
                y, m = _add_months(y, m, 1)
            continue
        for year in range(start.year - 1, end.year + 2):
            for sp in row.get("dates") or []:
                mm, dd = (int(x) for x in str(sp["mmdd"]).split("-"))
                due = _clamp(year, mm, dd)
                if start <= due <= end:
                    out.append((due, idx, _occ(row, due, fill(sp.get("period") or row["item"], due))))
    out.sort(key=lambda t: (t[0], t[1]))
    return [o for _, _, o in out]


def applies(occ: dict, entity: dict) -> bool:
    """Does this calendar row bind this entity? kind must be listed; then the flag rules."""
    if not entity.get("active", 1) or entity.get("kind") not in occ.get("applies_to", []):
        return False
    if occ.get("requires_not") and entity.get(occ["requires_not"]):
        return False
    req = occ.get("requires")
    if req and entity.get("kind") not in occ.get("always_for", []) and not entity.get(req):
        return False
    return True


def targets_for(occ: dict, entities: list[dict]) -> list[str]:
    """Entity names when the list is loaded (empty = this row binds none of them); else the group label,
    unless the row is calendar-only (remind_group: false)."""
    if entities:
        return [e["name"] for e in entities if applies(occ, e)]
    return [occ["group"]] if occ.get("remind_group", True) else []


def stage_for(days_left: int) -> str | None:
    if days_left == 0:
        return "day"
    if days_left == 1:
        return "eve"
    if 2 <= days_left <= WINDOW_DAYS:
        return "week"
    return None


def fmt_day(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return f"{d:%a} {d.day:02d} {d:%b}"


def _item_text(occ: dict, targets: list[str]) -> str:
    return f"{occ['label']}{' (payment)' if occ.get('payment') else ''} — {', '.join(targets)}"


def message_text(occs: list[dict], today: date, footer: str = FOOTER_DEFAULT, horizon: int = WINDOW_DAYS) -> str:
    """The daily message: one line per due date, everything on that date joined with ' · ', footer last.
    `occs` carry `targets` (entity names or the group label) — already filtered to what still needs a push."""
    lines = [f"Compliance · due in the next {horizon} days ({fmt_day(today)} – {fmt_day(today + timedelta(days=horizon))})"]
    by_day: dict[str, list[str]] = {}
    for o in occs:
        by_day.setdefault(o["due"], []).append(_item_text(o, o["targets"]))
    for due in sorted(by_day):
        lines.append(f"{fmt_day(due)} · " + " · ".join(by_day[due]))
    lines.append(footer)
    return "\n".join(lines)


def week_text(occs: list[dict], monday: date, nxt: dict | None, footer: str = FOOTER_DEFAULT) -> str:
    """Monday's 'this week' line — sent even when empty (Directive 5)."""
    head = f"Compliance · this week ({fmt_day(monday)} – {fmt_day(monday + timedelta(days=6))}):"
    if not occs:
        tail = f" nothing due · next: {nxt['label']} on {fmt_day(nxt['due'])}" if nxt else " nothing due · nothing dated in the next year"
        return head + tail
    by_day: dict[str, list[str]] = {}
    for o in occs:
        by_day.setdefault(o["due"], []).append(_item_text(o, o["targets"]))
    lines = [head] + [f"{fmt_day(d)} · " + " · ".join(by_day[d]) for d in sorted(by_day)] + [footer]
    return "\n".join(lines)


def _parse_now(now_v: Any) -> datetime:
    if isinstance(now_v, datetime):
        now = now_v
    else:
        try:
            now = datetime.fromisoformat(_query_tz(str(now_v).replace("Z", "+00:00"))) if now_v else datetime.now(IST)
        except ValueError:
            now = datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    return now.astimezone(IST)


def _flag(v: Any) -> int:
    return 1 if v in (True, 1, "1", "true", "yes", "y") else 0


# ═════════════════════════════════════════════════════════════════════════════
# Registration — tables, endpoints, the run the bot triggers
# ═════════════════════════════════════════════════════════════════════════════
def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict]) -> dict:
    state: dict[str, Any] = {"calendar": None}

    def calendar() -> dict:
        if state["calendar"] is None:
            state["calendar"] = load_calendar()
        return state["calendar"]

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    def _entity(r) -> dict:
        d = dict(r)
        for k in FLAGS + ("active",):
            d[k] = bool(d.get(k))
        return d

    async def entities_list(include_inactive: bool = True) -> list[dict]:
        db = await vdb()
        q = "SELECT * FROM compliance_entities" + ("" if include_inactive else " WHERE active=1") + " ORDER BY name COLLATE NOCASE"
        return [_entity(r) for r in await db.execute_fetchall(q)]

    async def entities_upsert(items: dict | list) -> dict:
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list) or not items:
            raise HTTPException(400, "send one entity or a list of them")
        db = await vdb()
        done = []
        for it in items:
            if not isinstance(it, dict):
                raise HTTPException(400, "each entity must be an object")
            name = " ".join(str(it.get("name") or "").split())
            if not name:
                raise HTTPException(400, "entity needs a name")
            cur = await db.execute_fetchall("SELECT * FROM compliance_entities WHERE name=? COLLATE NOCASE", (name,))
            cur = dict(cur[0]) if cur else None
            kind = str(it.get("kind") or (cur["kind"] if cur else "")).strip().lower()
            if kind not in KINDS:
                raise HTTPException(400, f"{name}: kind must be one of {', '.join(KINDS)}")
            merged = {k: (int(cur[k]) if cur else 0) for k in FLAGS}
            merged["active"] = int(cur["active"]) if cur else 1
            for k in FLAGS + ("active",):
                if k in it:
                    merged[k] = _flag(it[k])
            source = str(it.get("source") if "source" in it else (cur["source"] if cur else "") or "")[:200]
            notes = str(it.get("notes") if "notes" in it else (cur["notes"] if cur else "") or "")[:500]
            if cur:
                await db.execute(
                    "UPDATE compliance_entities SET kind=?, gst_registered=?, gst_qrmp=?, tds_deductor=?, audit_case=?, pf_esi=?, "
                    "active=?, source=?, notes=?, updated_at=datetime('now') WHERE id=?",
                    (kind, merged["gst_registered"], merged["gst_qrmp"], merged["tds_deductor"], merged["audit_case"],
                     merged["pf_esi"], merged["active"], source, notes, cur["id"]))
            else:
                await db.execute(
                    "INSERT INTO compliance_entities (name, kind, gst_registered, gst_qrmp, tds_deductor, audit_case, pf_esi, active, source, notes) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (name, kind, merged["gst_registered"], merged["gst_qrmp"], merged["tds_deductor"], merged["audit_case"],
                     merged["pf_esi"], merged["active"], source, notes))
            done.append(name)
        await db.commit()
        return {"upserted": done, "entities": await entities_list()}

    async def _reminders_between(db, start: date, end: date) -> list[dict]:
        return [dict(r) for r in await db.execute_fetchall(
            "SELECT * FROM compliance_reminders WHERE due_date BETWEEN ? AND ? ORDER BY due_date, id",
            (start.isoformat(), end.isoformat()))]

    async def upcoming(days: int = 30, now_v: Any = None) -> dict:
        """Every occurrence due today..today+days with its targets (entities or the group label). Rows that bind
        nothing are left out. Each occurrence carries the reminder rows already filed for it."""
        days = max(0, min(int(days or 30), 400))
        now = _parse_now(now_v)
        today = now.date()
        all_ents = await entities_list()
        active = [e for e in all_ents if e["active"]]
        loaded = bool(all_ents)
        db = await vdb()
        rem = await _reminders_between(db, today, today + timedelta(days=days))
        out = []
        for occ in expand(calendar(), today, today + timedelta(days=days)):
            targets = targets_for(occ, active if loaded else [])
            if not targets:
                continue
            due = date.fromisoformat(occ["due"])
            rows = [r for r in rem if r["item_id"] == occ["item_id"] and r["due_date"] == occ["due"] and r["entity_or_group"] in targets]
            done_for = sorted({r["entity_or_group"] for r in rows if r["status"] == "done"})
            out.append({**occ, "targets": targets, "level": "entity" if loaded else "group",
                        "days_left": (due - today).days, "stage": stage_for((due - today).days),
                        "reminders": rows, "done_for": done_for, "done": bool(done_for) and len(done_for) == len(targets)})
        return {"as_of": now.isoformat(), "today": today.isoformat(), "days": days, "items": out,
                "entities_loaded": loaded, "entity_count": len(active), "level": "entity" if loaded else "group",
                "footer": str(calendar().get("footer") or FOOTER_DEFAULT), "note": "" if loaded else NOT_LOADED}

    async def next_after(today: date, after_days: int) -> dict | None:
        """The first occurrence that binds someone beyond the window — for the 'next: …' heartbeat."""
        res = await upcoming(after_days + 400, today.isoformat())
        for it in res["items"]:
            if it["days_left"] > after_days and not it["done"]:
                return it
        return None

    async def run(mode: str = "daily", now_v: Any = None) -> dict:
        mode = str(mode or "daily").strip().lower()
        if mode not in MODES:
            raise HTTPException(400, f"mode must be one of {', '.join(MODES)}")
        now = _parse_now(now_v)
        today = now.date()
        footer = str(calendar().get("footer") or FOOTER_DEFAULT)
        db = await vdb()
        stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        if mode == "weekly":
            res = await upcoming(6, now)
            occs = []
            for it in res["items"]:
                live = [t for t in it["targets"] if t not in it["done_for"]]
                if live:
                    occs.append({**it, "targets": live})
            nxt = await next_after(today, 6) if not occs else None
            text = week_text(occs, today, nxt, footer)
            try:
                push = send_cos(text) or {}
            except Exception as e:
                push = {"sent": False, "reason": str(e)[:200]}
            sent = bool(push.get("sent"))
            line = f"{BOT_ID} weekly: {len(occs)} items this week ({'pushed' if sent else 'push NOT delivered'})"
            if not res["entities_loaded"]:
                line += f" · {NOT_LOADED} — group level"
            return {"mode": mode, "due": len(occs), "items": occs, "pushed": 1 if sent else 0, "push_failed": 0 if sent else 1,
                    "text": text, "line": line, "entities_loaded": res["entities_loaded"], "as_of": now.isoformat()}

        res = await upcoming(WINDOW_DAYS, now)
        existing = await _reminders_between(db, today, today + timedelta(days=WINDOW_DAYS))
        sent_keys = {(r["entity_or_group"], r["item_id"], r["due_date"], r["stage"]) for r in existing if r["sent_at"]}
        listing, triggers = [], []
        for it in res["items"]:
            live = [t for t in it["targets"] if t not in it["done_for"]]
            if not live:
                continue
            listing.append({**it, "targets": live})
            stage = it["stage"]
            if stage:
                for t in live:
                    if (t, it["item_id"], it["due"], stage) not in sent_keys:
                        triggers.append((it, t, stage))
        text, sent, push = "", False, {}
        if triggers:
            text = message_text(listing, today, footer)
            try:
                push = send_cos(text) or {}
            except Exception as e:
                push = {"sent": False, "reason": str(e)[:200]}
            sent = bool(push.get("sent"))
            for it, t, stage in triggers:
                await db.execute(
                    "INSERT OR IGNORE INTO compliance_reminders (entity_or_group, item_id, item, due_date, remind_on, stage, status) "
                    "VALUES (?,?,?,?,?,?,'queued')", (t, it["item_id"], it["label"], it["due"], today.isoformat(), stage))
                if sent:
                    await db.execute(
                        "UPDATE compliance_reminders SET sent_at=?, status='sent', remind_on=?, message=? "
                        "WHERE entity_or_group=? AND item_id=? AND due_date=? AND stage=? AND sent_at IS NULL",
                        (stamp, today.isoformat(), text, t, it["item_id"], it["due"], stage))
            await db.commit()
        if listing:
            line = f"{BOT_ID}: {len(listing)} items due in {WINDOW_DAYS} days"
            if triggers:
                line += f" ({len(triggers)} reminders, {'1 message pushed' if sent else 'push NOT delivered'})"
            else:
                line += " (all already reminded at this stage, nothing pushed)"
        else:
            nxt = await next_after(today, WINDOW_DAYS)
            line = f"{BOT_ID}: 0 items due in {WINDOW_DAYS} days, next: " + (f"{nxt['label']} on {fmt_day(nxt['due'])}" if nxt else "nothing dated in the next year")
        if not res["entities_loaded"]:
            line += f" · {NOT_LOADED} — group level"
        return {"mode": mode, "due": len(listing), "items": listing, "reminders": len(triggers),
                "pushed": 1 if (triggers and sent) else 0, "push_failed": 1 if (triggers and not sent) else 0,
                "push": push, "text": text, "line": line, "entities_loaded": res["entities_loaded"], "as_of": now.isoformat()}

    async def reminders_list(status: str = "", limit: int = 100) -> list[dict]:
        db = await vdb()
        q, params = "SELECT * FROM compliance_reminders", []
        if status:
            q += " WHERE status=?"; params.append(status)
        q += " ORDER BY due_date DESC, id DESC LIMIT ?"; params.append(max(1, min(int(limit or 100), 1000)))
        return [dict(r) for r in await db.execute_fetchall(q, params)]

    async def reminder_done(rid: int) -> dict:
        db = await vdb()
        rows = await db.execute_fetchall("SELECT * FROM compliance_reminders WHERE id=?", (int(rid),))
        if not rows:
            raise HTTPException(404, f"reminder {rid} not found")
        r = dict(rows[0])
        # done is per (target, item, due): every stage row for it is closed, so no eve/day push follows
        await db.execute("UPDATE compliance_reminders SET status='done', done_at=datetime('now') "
                         "WHERE entity_or_group=? AND item_id=? AND due_date=?",
                         (r["entity_or_group"], r["item_id"], r["due_date"]))
        await db.commit()
        return {"ok": True, "id": int(rid), "status": "done", "entity_or_group": r["entity_or_group"],
                "item_id": r["item_id"], "due_date": r["due_date"]}

    # ── endpoints ─────────────────────────────────────────────────────────────
    @app.get("/api/compliance/calendar")
    async def compliance_calendar():
        cal = calendar()
        return {"calendar": cal.get("calendar"), "prepared": cal.get("prepared"), "fy_start": cal.get("fy_start"),
                "fy_end": cal.get("fy_end"), "entity_kinds": cal.get("entity_kinds"), "footer": cal.get("footer"),
                "how_to_read": cal.get("how_to_read"), "items": cal.get("items"), "count": len(cal.get("items") or [])}

    @app.get("/api/compliance/upcoming")
    async def compliance_upcoming(days: int = 30, now: str | None = None):
        return await upcoming(days, now)

    @app.get("/api/compliance/entities")
    async def compliance_entities_get():
        ents = await entities_list()
        return {"entities": ents, "kinds": list(KINDS), "loaded": bool(ents), "note": "" if ents else NOT_LOADED}

    @app.post("/api/compliance/entities")
    async def compliance_entities_post(request: Request):
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "body must be JSON: one entity or a list of them")
        return await entities_upsert(body)

    @app.get("/api/compliance/reminders")
    async def compliance_reminders_get(status: str = "", limit: int = 100):
        return {"reminders": await reminders_list(status, limit)}

    @app.post("/api/compliance/reminders/{rid}/done")
    async def compliance_reminder_done(rid: int):
        return await reminder_done(rid)

    @app.post("/api/compliance/run")
    async def compliance_run(body: dict | None = None):
        body = body or {}
        return await run(body.get("mode") or "daily", body.get("now"))

    return {"ensure_schema": ensure_schema, "run": run, "upcoming": upcoming, "entities": entities_list,
            "entities_upsert": entities_upsert, "reminder_done": reminder_done, "reminders": reminders_list,
            "calendar": calendar}
