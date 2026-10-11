"""Tender247 "Participation Insights" — the competitor-analysis mail, turned into a table you can ask questions of.

Aman, chat 2026-10-11: "have a different account on Tender247 … competitor analysis subscribed … use that to gain more insight."
The mail (sender bidsnrfp.com, subject "(N) New Tender Results : Participation Insights - dd-mm-yyyy") carries two tables:
  - "Update on Yours Competitors Participation": bidder, participated, awarded, lost, financial stage, technical stage
  - "Fresh Results": result id, brief, department, stage, WINNER, all PARTICIPANTS, contract value, city/state, date
Before 2026-10-11 these were filed as pipeline rows with "Unknown buyer". Now: t247_results (one row per result id, with winner,
participants, value) and t247_competitors (a daily snapshot), plus the questions Aman actually has: who wins coal-handling,
washery, RCR and coal-supply work, at what values, against how many bidders, from which departments. Zero LLM.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from mdo_tenders_direct import classify

SCHEMA = """
CREATE TABLE IF NOT EXISTS t247_results (
    result_id TEXT PRIMARY KEY, brief TEXT, dept TEXT, stage TEXT, winner TEXT, participants_json TEXT, n_participants INTEGER,
    value_text TEXT, value_cr REAL, city TEXT, state TEXT, contract_date TEXT, relevant INTEGER DEFAULT 0, keywords TEXT DEFAULT '',
    first_seen TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_t247_results_date ON t247_results(contract_date);
CREATE TABLE IF NOT EXISTS t247_competitors (
    day TEXT NOT NULL, bidder TEXT NOT NULL, participated INTEGER, awarded INTEGER, lost INTEGER, financial INTEGER, technical INTEGER,
    PRIMARY KEY (day, bidder)
);
"""

COAL_WORDS = re.compile(r"\b(coal|coalfields?|lignite|washery|washeries|beneficiation|rcr|road[- ]cum[- ]rail|rakes?|sidings?|coal handling)\b", re.I)
_ID_LINE = re.compile(r"^(\d{6,10}) \| ")
_DATE = re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$")


def value_to_cr(text: str) -> float | None:
    """'29.94 Lacs' → 0.2994, '1.2 Cr' → 1.2, '16,402' (rupees) → 0.0016402, '' → None. Crores."""
    t = str(text or "").strip().lower().replace(",", "")
    m = re.match(r"^(?:rs\.?|₹)?\s*([\d.]+)\s*(cr|crore|crores|lac|lacs|lakh|lakhs|k)?$", t)
    if not m:
        return None
    try:
        n = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2) or ""
    if unit.startswith("cr"):
        return n
    if unit.startswith(("lac", "lakh")):
        return n / 100
    if unit == "k":
        return n / 10000
    return n / 1e7


def parse_results(text: str) -> list[dict]:
    """The 'Fresh Results' block of the mail text (html_to_text output) → one dict per result id. Parsed from the right,
    because a brief can contain extra ' | ' cells (for example 'quantity - 2000')."""
    lines = str(text or "").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().lower() == "fresh results")
    except StopIteration:
        start = 0
    blocks: list[list[str]] = []
    for ln in lines[start + 1:]:
        if _ID_LINE.match(ln):
            blocks.append([ln])
        elif blocks:
            if ln.lower().startswith(("click here", "thank", "regards", "to unsubscribe")):
                break
            blocks[-1].append(ln)
    out = []
    for b in blocks:
        flat = " ".join(" ".join(b).split())
        cells = [c.strip() for c in flat.split(" | ")]
        if len(cells) < 9 or not _DATE.match(cells[-1]):
            continue
        rid = cells[0]
        date_s, place, value, parts, winner, stage, dept = cells[-1], cells[-2], cells[-3], cells[-4], cells[-5], cells[-6], cells[-7]
        brief = " ".join(cells[1:-7]).strip(" ,")
        city, _, state = place.rpartition(",")
        participants = sorted({p.strip(" ,") for p in re.split(r",\s*(?=[^,]*)", parts) if p.strip(" ,")})
        try:
            iso = datetime.strptime(date_s, "%d-%m-%Y").date().isoformat()
        except ValueError:
            iso = ""
        c = classify({"title": brief, "org": dept, "value_text": ""})
        # whole words only: "washing" alone (hospital kits) and "siding" inside other words are not our work
        coalish = bool(COAL_WORDS.search(f"{brief} {dept}"))
        out.append({"result_id": rid, "brief": brief[:600], "dept": dept[:160], "stage": stage[:20], "winner": winner[:160],
                    "participants": participants[:40], "n_participants": len(participants), "value_text": value[:40],
                    "value_cr": value_to_cr(value), "city": city.strip()[:80], "state": (state or city).strip()[:60], "contract_date": iso,
                    "relevant": 1 if coalish else 0, "keywords": ", ".join(c["keywords"])})
    return out


def parse_competitors(text: str) -> list[dict]:
    """'Update on Yours Competitors Participation' → [{bidder, participated, awarded, lost, financial, technical}]."""
    lines = str(text or "").splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if "competitors participation" in l.lower())
    except StopIteration:
        return []
    out = []
    for ln in lines[start + 1:]:
        if ln.lower().startswith(("click here", "fresh results")):
            break
        cells = [c.strip() for c in ln.split(" | ")]
        if len(cells) == 6 and all(c.isdigit() for c in cells[1:]):
            out.append({"bidder": cells[0], "participated": int(cells[1]), "awarded": int(cells[2]), "lost": int(cells[3]),
                        "financial": int(cells[4]), "technical": int(cells[5])})
    return out


def headline(text: str) -> dict:
    """'New Result | Competitors' → '10 | 41'."""
    m = re.search(r"New Result \| Competitors\s*\n\s*(\d+) \| (\d+)", str(text or ""))
    return {"new_results": int(m.group(1)), "total_competitors": int(m.group(2))} if m else {}


def register(app, vdb: Callable[[], Awaitable[Any]]) -> dict:
    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def ingest(text: str, day: str) -> dict:
        """Store one mail's tables. Idempotent (result id and (day, bidder) are keys). Returns counts and the relevant new rows."""
        db = await vdb()
        await ensure_schema(db)
        results, comps = parse_results(text), parse_competitors(text)
        new_rel: list[dict] = []
        added = 0
        for r in results:
            cur = await db.execute(
                "INSERT OR IGNORE INTO t247_results (result_id, brief, dept, stage, winner, participants_json, n_participants, value_text, value_cr, "
                "city, state, contract_date, relevant, keywords) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["result_id"], r["brief"], r["dept"], r["stage"], r["winner"], json.dumps(r["participants"]), r["n_participants"],
                 r["value_text"], r["value_cr"], r["city"], r["state"], r["contract_date"], r["relevant"], r["keywords"]))
            if cur.rowcount:
                added += 1
                if r["relevant"]:
                    new_rel.append(r)
            else:        # a rebuild re-applies the current relevance rule to rows stored earlier
                await db.execute("UPDATE t247_results SET relevant=?, keywords=? WHERE result_id=?", (r["relevant"], r["keywords"], r["result_id"]))
        for c in comps:
            await db.execute("INSERT OR REPLACE INTO t247_competitors (day, bidder, participated, awarded, lost, financial, technical) VALUES (?,?,?,?,?,?,?)",
                             (day, c["bidder"], c["participated"], c["awarded"], c["lost"], c["financial"], c["technical"]))
        await db.commit()
        return {"results": len(results), "added": added, "relevant_new": new_rel, "competitors": len(comps), **headline(text)}

    async def results(days: int = 30, relevant: int = 1, limit: int = 100) -> dict:
        db = await vdb()
        await ensure_schema(db)
        since = (date.today() - timedelta(days=max(1, min(int(days), 400)))).isoformat()
        q = "SELECT * FROM t247_results WHERE contract_date >= ?" + (" AND relevant=1" if relevant else "") + " ORDER BY contract_date DESC, result_id DESC LIMIT ?"
        rows = [dict(r) for r in await db.execute_fetchall(q, (since, max(1, min(int(limit), 500))))]
        for r in rows:
            r["participants"] = json.loads(r.pop("participants_json") or "[]")
        return {"since": since, "count": len(rows), "items": rows}

    async def intel(days: int = 90) -> dict:
        """Who wins what: winners ranked by wins in the relevant (coal/washery/RCR/handling) results, with total value, typical
        number of bidders, departments, plus the competitor snapshot. Facts only; no guesses about margins."""
        db = await vdb()
        await ensure_schema(db)
        since = (date.today() - timedelta(days=max(1, min(int(days), 400)))).isoformat()
        rows = [dict(r) for r in await db.execute_fetchall("SELECT * FROM t247_results WHERE relevant=1 AND contract_date >= ?", (since,))]
        win: dict[str, dict] = {}
        depts: dict[str, int] = {}
        for r in rows:
            w = win.setdefault(r["winner"] or "(none)", {"winner": r["winner"] or "(none)", "wins": 0, "value_cr": 0.0, "bidders": [], "depts": set()})
            w["wins"] += 1
            w["value_cr"] += r["value_cr"] or 0
            w["bidders"].append(r["n_participants"] or 0)
            w["depts"].add(r["dept"])
            depts[r["dept"]] = depts.get(r["dept"], 0) + 1
        leaders = sorted(({"winner": w["winner"], "wins": w["wins"], "value_cr": round(w["value_cr"], 3),
                           "avg_bidders": round(sum(w["bidders"]) / len(w["bidders"]), 1), "depts": sorted(w["depts"])[:4]} for w in win.values()),
                         key=lambda x: (-x["wins"], -x["value_cr"]))[:15]
        snap_day = (await db.execute_fetchall("SELECT MAX(day) FROM t247_competitors"))[0][0]
        snap = [dict(r) for r in await db.execute_fetchall(
            "SELECT * FROM t247_competitors WHERE day=? ORDER BY awarded DESC, participated DESC LIMIT 20", (snap_day,))] if snap_day else []
        vals = sorted(r["value_cr"] for r in rows if r["value_cr"])
        return {"days": days, "relevant_results": len(rows), "median_value_cr": vals[len(vals) // 2] if vals else None,
                "avg_bidders": round(sum(r["n_participants"] or 0 for r in rows) / len(rows), 1) if rows else None,
                "leaders": leaders, "top_departments": sorted(depts.items(), key=lambda kv: -kv[1])[:8],
                "competitor_snapshot": {"day": snap_day, "rows": snap}}

    async def rebuild(days: int = 60) -> dict:
        """Re-read the stored mail bodies in the vault (finance/mail/*Participation*/body.html) and fill the tables."""
        from mdo_mail import html_to_text
        root = os.environ.get("VAULT_DIR", os.path.join(
            os.path.dirname(os.path.abspath(os.environ.get("VEGA_DB_PATH", "/data/vega_data.db"))), "vault"))
        base = os.path.join(root, "finance", "mail")
        done, added = 0, 0
        if os.path.isdir(base):
            for name in sorted(os.listdir(base)):
                if "Participation" not in name:
                    continue
                p = os.path.join(base, name, "body.html")
                if not os.path.isfile(p):
                    continue
                m = re.match(r"(\d{4}-\d{2}-\d{2})_", name)
                text = html_to_text(open(p, encoding="utf-8", errors="replace").read())
                res = await ingest(text, m.group(1) if m else date.today().isoformat())
                done += 1
                added += res["added"]
        return {"mails_read": done, "results_added": added}

    @app.get("/api/t247/results")
    async def t247_results(days: int = 30, relevant: int = 1, limit: int = 100):
        return await results(days, relevant, limit)

    @app.get("/api/t247/intel")
    async def t247_intel(days: int = 90):
        return await intel(days)

    @app.post("/api/t247/rebuild")
    async def t247_rebuild(body: dict | None = None):
        return await rebuild(int((body or {}).get("days") or 60))

    return {"ensure_schema": ensure_schema, "ingest": ingest, "results": results, "intel": intel, "rebuild": rebuild}
