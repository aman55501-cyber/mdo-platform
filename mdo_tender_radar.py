"""tender-radar — filters, deadline reminders and "closed without a decision" findings for the tenders Aman must not miss again.

Aman, chat 2026-10-12, after the Tender247 Missed Opportunities export (320 coal tenders, none with an alert set): "analyze my missed opportunities and
help me set reminders, filters and alerts so it doesn't happen again".

What the export showed (briefs/TENDER_MISSED_ANALYSIS_2026-10-12.md): no alert was set in the portal; the alert e-mails list only 5 tenders and say "view all (N)";
and tenders ingested into vwlr_tender_pipeline carry status 'evaluating', which the old deadline reminder (status 'active' only) never looked at. So nothing ever
reminded anyone. This module is the missing reminder: rules only, zero LLM (Directive 15), one WhatsApp message a morning, heartbeat on every run.

Tiers (from Aman's objective "tenders for ROM and washed coal, RCR and supply"):
  A  coal supply · RCR / siding · washery / beneficiation · loading / handling / crushing   → reminders at T-7, T-3, T-1, T-0
  B  mining services (OB, extraction) · coal transport by road                              → reminders at T-3, T-0
  X  civil / construction / biomass / anything with an exclusion word, or not coal           → never reminded
Commands by WhatsApp: "tenders" (open A and B), "bid 42", "skip 42" (marks the pipeline row; nothing is filed — a bid is Aman's click on the portal).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable

from mdo_cos import IST

BOT_ID = "tender-radar"
OPEN_STATUSES = ("evaluating", "active", "bidding")
REMIND_AT = {"A": (7, 3, 1, 0), "B": (3, 0)}
MAX_LINES = 12

# the Alert plan from the Tender247 export (keywords, exclusion, competitors) — Aman approves it by saying so; until then it only classifies
KEYWORDS = {
    "RCR / siding": r"\brcr\b|road[\s-]*cum[\s-]*rail|\bsiding\b|rail(?:way)? (?:mode|siding)|rapid loading",
    "Washery / beneficiation": r"washery|beneficiation|coal washing|washed coal",
    "Coal supply": r"supply of[^.|]{0,30}coal|\bdomestic coal\b|steam coal|non[\s-]*coking|\bcoal supply\b|supply of coal|e-auction|auction sale of coal",
    "Loading / handling / crushing": r"coal (?:loading|handling|crushing)|loading,? (?:and )?(?:unloading|transport)|handling (?:&|and) transport|crushing",
    "Mining services": r"\bob removal\b|overburden|coal extraction|mining service|\bocp\b|extraction of coal|mine operator|\bmdo\b",
    "Coal transport (road)": r"coal transport|transportation of coal|transport(?:ation)? of .{0,40}coal|lifting,? handling|road transport",
}
TIER_OF = {"RCR / siding": "A", "Washery / beneficiation": "A", "Coal supply": "A", "Loading / handling / crushing": "A",
           "Mining services": "B", "Coal transport (road)": "B"}
EXCLUDE = r"\bcivil\b|construction|building|\bdrain|\bcement\b|\bbridge\b|road construction|streng\w*ning|repair|renovation|hire charges|concrete|biomass|bio[\s-]*fuel|\bcoke\b"
PREFERRED_STATES = ("chhattisgarh", "jharkhand", "orissa", "odisha", "madhya pradesh", "maharashtra")
COMPETITORS = [
    "Godavari Commodities", "Ind Synergy", "Hind Group", "Harjika", "Harijika", "Vimla", "Sendoz Impex", "Kunal Transport", "Mohit Minerals", "RKTC Infratech",
    "Anoop Road Carriers", "Indermani", "Indramani", "Advika Logistics", "Omax", "KTC", "Tiwarta", "Shah Coal", "Kohli Transport", "Tirupati Minerals",
    "Orissa Stevedores", "United Coal Carriers", "Krishna Infrastructure", "Vikas Coal and Minerals", "Caliber Mining and Logistics", "Vedvyas Logistic",
    "Vivek Construction", "Fagu Jai Mangal Infra", "VFPL ASIPL JV", "Throns Infrastructure", "JARPL-AT Consortium", "BKT-PMIW JV", "Kanha Enterprises",
    "Saikrupa Coal Supplier", "Bharat Traders", "Swami Fuels", "Bharat Road Carrier", "Nkas Services", "Sangita Sales", "G K Associates", "Chandan Kumar Singh",
    "Shanker Fuels",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS tender_reminders (
    tender_id INTEGER NOT NULL, stage TEXT NOT NULL, sent_at TEXT NOT NULL, PRIMARY KEY (tender_id, stage)
);
CREATE TABLE IF NOT EXISTS tender_radar_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT NOT NULL, open_a INTEGER DEFAULT 0, open_b INTEGER DEFAULT 0, reminders INTEGER DEFAULT 0,
    new_today INTEGER DEFAULT 0, closed_undecided INTEGER DEFAULT 0, line TEXT DEFAULT '', pushed INTEGER DEFAULT 0
);
"""


def classify(text: str, buyer: str = "", state: str = "") -> dict:
    """{tier, family, why, preferred_state, competitors}. Rules only; X when an exclusion word is present or no coal family matches."""
    t = f"{text or ''} {buyer or ''}".lower()
    comps = [c for c in COMPETITORS if c.lower() in t]
    pref = any(s in (state or "").lower() or s in t for s in PREFERRED_STATES)
    if re.search(EXCLUDE, t) and not re.search(KEYWORDS["RCR / siding"] + "|" + KEYWORDS["Washery / beneficiation"], t):
        return {"tier": "X", "family": "", "why": "exclusion word (civil / construction / biomass / repair)", "preferred_state": pref, "competitors": comps}
    for fam in ("RCR / siding", "Washery / beneficiation", "Loading / handling / crushing", "Coal supply", "Mining services", "Coal transport (road)"):
        if re.search(KEYWORDS[fam], t):
            return {"tier": TIER_OF[fam], "family": fam, "why": f"matches {fam}", "preferred_state": pref, "competitors": comps}
    return {"tier": "X", "family": "", "why": "no coal family matched", "preferred_state": pref, "competitors": comps}


def days_left(due: str | None, today: date) -> int | None:
    try:
        return (date.fromisoformat(str(due)[:10]) - today).days
    except (TypeError, ValueError):
        return None


def stage_for(tier: str, days: int | None) -> str | None:
    if days is None or days < 0:
        return None
    for d in REMIND_AT.get(tier, ()):
        if days == d:
            return f"T-{d}"
    return None


def line_for(row: dict, c: dict, days: int) -> str:
    when = "TODAY" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
    title = re.sub(r"^\[[^\]]*\]\s*", "", str(row.get("notes") or ""))[:70]
    flag = " ★ near Raigarh" if c["preferred_state"] else ""
    comp = f" · rivals: {', '.join(c['competitors'][:2])}" if c["competitors"] else ""
    return f"#{row['id']} [{c['tier']}] {row.get('buyer') or '?'} — {title} — closes {when} ({str(row.get('due_date'))[:10]}){flag}{comp}"


def parse_command(text: str) -> tuple[str, int | None] | None:
    m = re.fullmatch(r"\s*(bid|skip|tenders?)(?:\s+#?(\d+))?\s*", (text or "").lower())
    if not m:
        return None
    verb = "tenders" if m.group(1).startswith("tender") else m.group(1)
    if verb in ("bid", "skip") and not m.group(2):
        return None
    return verb, int(m.group(2)) if m.group(2) else None


def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict], inbound_hooks: list | None = None) -> dict:
    async def ensure_schema():
        db = await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def _rows(today: date) -> list[dict]:
        db = await vdb()
        ph = ",".join("?" * len(OPEN_STATUSES))
        out = []
        for r in await db.execute_fetchall(
                f"SELECT id, buyer, category, due_date, status, notes, url, created_at FROM vwlr_tender_pipeline WHERE status IN ({ph}) "
                "AND due_date IS NOT NULL AND due_date >= ?", (*OPEN_STATUSES, (today - timedelta(days=3)).isoformat())):
            out.append(dict(r))
        return out

    async def open_tenders(now: datetime | None = None) -> list[dict]:
        await ensure_schema()
        today = (now or datetime.now(IST)).date()
        res = []
        for r in await _rows(today):
            c = classify(f"{r.get('notes') or ''} {r.get('category') or ''}", r.get("buyer") or "")
            d = days_left(r.get("due_date"), today)
            if c["tier"] in ("A", "B") and d is not None and d >= 0:
                res.append({**r, **c, "days_left": d})
        return sorted(res, key=lambda x: (x["days_left"], x["tier"]))

    async def run(now_v: Any = None) -> dict:
        await ensure_schema()
        now = datetime.fromisoformat(str(now_v)) if now_v else datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        today = now.date()
        db = await vdb()
        rows = await _rows(today)
        lines, reminded, open_a, open_b, new_today, undecided = [], 0, 0, 0, 0, []
        for r in rows:
            c = classify(f"{r.get('notes') or ''} {r.get('category') or ''}", r.get("buyer") or "")
            d = days_left(r.get("due_date"), today)
            if c["tier"] == "X" or d is None:
                continue
            if d < 0:
                if c["tier"] == "A" and r["status"] == "evaluating" and d >= -1:
                    seen = await db.execute_fetchall("SELECT 1 FROM tender_reminders WHERE tender_id=? AND stage='CLOSED'", (r["id"],))
                    if not seen:                                  # said once, not at every run
                        undecided.append((r, c))
                        await db.execute("INSERT INTO tender_reminders (tender_id, stage, sent_at) VALUES (?,?,?)", (r["id"], "CLOSED", now.isoformat(timespec="minutes")))
                continue
            open_a += c["tier"] == "A"
            open_b += c["tier"] == "B"
            if str(r.get("created_at") or "")[:10] == today.isoformat() and c["tier"] == "A":
                new_today += 1
            stg = stage_for(c["tier"], d)
            if stg:
                hit = await db.execute_fetchall("SELECT 1 FROM tender_reminders WHERE tender_id=? AND stage=?", (r["id"], stg))
                if not hit:
                    lines.append((d, line_for(r, c, d)))
                    await db.execute("INSERT INTO tender_reminders (tender_id, stage, sent_at) VALUES (?,?,?)", (r["id"], stg, now.isoformat(timespec="minutes")))
                    reminded += 1
        lines.sort()
        body = [l for _, l in lines][:MAX_LINES]
        if undecided:
            body.append(f"❌ Closed yesterday with no decision: " + "; ".join(f"#{r['id']} {r.get('buyer') or '?'}" for r, _ in undecided[:4]))
        text = ""
        if body:
            text = "⏰ Tenders needing you\n" + "\n".join(body) + "\nReply: bid <id> · skip <id> · tenders"
        sent = False
        if text:
            try:
                sent = bool((send_cos(text) or {}).get("sent"))
            except Exception:
                sent = False
        await db.commit()
        line = (f"{BOT_ID}: {open_a} A and {open_b} B tenders open · {reminded} reminders {'sent' if sent else ('NOT delivered' if text else 'due: none')} · "
                f"{new_today} new A today · {len(undecided)} closed undecided")
        await db.execute("INSERT INTO tender_radar_runs (ran_at, open_a, open_b, reminders, new_today, closed_undecided, line, pushed) VALUES (?,?,?,?,?,?,?,?)",
                         (now.isoformat(timespec="minutes"), open_a, open_b, reminded, new_today, len(undecided), line, 1 if sent else 0))
        await db.commit()
        return {"open_a": open_a, "open_b": open_b, "reminders": reminded, "new_today": new_today, "closed_undecided": len(undecided), "pushed": 1 if sent else 0,
                "text": text, "line": line, "status": "clean" if (sent or not text) else "warning"}

    async def handle_text(sender: str, text: str):
        cmd = parse_command(text)
        if not cmd:
            return None
        verb, tid = cmd
        await ensure_schema()
        if verb == "tenders":
            ts = await open_tenders()
            if not ts:
                return "No open A or B tenders on file. Nothing is waiting."
            return "Open tenders:\n" + "\n".join(line_for(t, t, t["days_left"]) for t in ts[:MAX_LINES])
        db = await vdb()
        row = await db.execute_fetchall("SELECT id, buyer, status FROM vwlr_tender_pipeline WHERE id=?", (tid,))
        if not row:
            return f"No tender #{tid} on file."
        new = "bidding" if verb == "bid" else "skipped"
        await db.execute("UPDATE vwlr_tender_pipeline SET status=?, updated_at=datetime('now') WHERE id=?", (new, tid))
        await db.commit()
        return (f"#{tid} {dict(row[0])['buyer']}: marked {new}." + (" Filing the bid is your click on the portal; I will remind you at T-1 and T-0." if verb == "bid" else ""))

    if inbound_hooks is not None:
        inbound_hooks.append(handle_text)

    @app.post("/api/tender-radar/run")
    async def api_run(body: dict | None = None):
        return await run((body or {}).get("now"))

    @app.get("/api/tender-radar/open")
    async def api_open():
        ts = await open_tenders()
        return {"count": len(ts), "tenders": [{k: t.get(k) for k in ("id", "tier", "family", "buyer", "due_date", "days_left", "status", "preferred_state", "competitors", "url")} for t in ts]}

    return {"ensure_schema": ensure_schema, "run": run, "open_tenders": open_tenders, "handle_text": handle_text}
