"""Business OS data layer — import Excel/CSV, persist, and compute KPIs.

Import-driven: you upload the sheets you already keep (tenders, receivables, hotel
daily, cash-flow, tasks...). Each upload replaces that dataset; rows are stored as
plain dicts on the state volume so they survive rebuilds. Column names are detected
by keyword so it works with whatever headers your sheets use, and falls back to a
generic numeric/date summary when a dataset isn't specially handled yet.

No business secrets leave the server; nothing here touches the trading path.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

BIZ_DIR = Path(__file__).resolve().parent / "data" / "state" / "business"

# Datasets the Business OS knows about (others can still be imported generically).
KNOWN = ("tenders", "receivables", "hotel", "cashflow", "tasks", "projects", "compliance")


def _path(name: str) -> Path:
    return BIZ_DIR / f"{name.lower().strip()}.json"


def _rows_from_file(path: Path) -> list[dict]:
    """Excel (.xlsx/.xls) or CSV -> list of {header: value} (reuses the Screener reader)."""
    from .analysis.fundamentals import _rows_from_file as rf
    return rf(path)


def save(name: str, rows: list[dict]) -> dict:
    BIZ_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"dataset": name, "rows": rows, "count": len(rows),
               "columns": list(rows[0].keys()) if rows else [],
               "imported_at": datetime.utcnow().isoformat() + "Z"}
    _path(name).write_text(json.dumps(payload), encoding="utf-8")
    return {k: v for k, v in payload.items() if k != "rows"}


def load(name: str) -> dict:
    p = _path(name)
    if not p.exists():
        return {"dataset": name, "rows": [], "count": 0, "columns": [], "imported_at": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"dataset": name, "rows": [], "count": 0, "columns": [], "imported_at": None}


def datasets() -> list[dict]:
    out = []
    for name in KNOWN:
        d = load(name)
        out.append({"dataset": name, "count": d["count"], "imported_at": d.get("imported_at"),
                    "columns": d.get("columns", [])})
    # any extra imported datasets not in KNOWN
    if BIZ_DIR.exists():
        for p in BIZ_DIR.glob("*.json"):
            nm = p.stem
            if nm not in KNOWN:
                d = load(nm)
                out.append({"dataset": nm, "count": d["count"], "imported_at": d.get("imported_at"),
                            "columns": d.get("columns", [])})
    return out


# ---- column detection + parsing helpers -------------------------------------
def _num(v) -> float | None:
    from .normalise import to_float
    return to_float(v)


def _find(cols: list[str], *keywords: str) -> str | None:
    low = {c.lower(): c for c in cols}
    for kw in keywords:
        for lc, orig in low.items():
            if kw in lc:
                return orig
    return None


def _to_date(v):
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d-%b-%y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10] if len(s) >= 10 else s, fmt).date()
        except ValueError:
            continue
    return None


def _days_since(d) -> int | None:
    if not d:
        return None
    return (datetime.utcnow().date() - d).days


# ---- per-module KPIs (tolerant of whatever headers the sheet uses) ----------
def receivables_aging() -> dict:
    d = load("receivables")
    rows, cols = d["rows"], d["columns"]
    amt_c = _find(cols, "outstanding", "balance", "amount", "due", "receivable")
    date_c = _find(cols, "invoice date", "bill date", "date", "due date")
    party_c = _find(cols, "party", "buyer", "customer", "name", "client")
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    total, overdue60, items = 0.0, 0.0, []
    for r in rows:
        amt = _num(r.get(amt_c)) if amt_c else None
        if amt is None:
            continue
        total += amt
        age = _days_since(_to_date(r.get(date_c))) if date_c else None
        b = "0-30" if age is None or age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "90+"
        buckets[b] += amt
        if age is not None and age > 60:
            overdue60 += amt
            items.append({"party": r.get(party_c) if party_c else "—", "amount": round(amt, 2), "age_days": age})
    items.sort(key=lambda x: x["amount"], reverse=True)
    return {"total_outstanding": round(total, 2), "buckets": {k: round(v, 2) for k, v in buckets.items()},
            "overdue_60_plus": round(overdue60, 2), "worst": items[:8], "count": d["count"]}


def tender_pipeline() -> dict:
    d = load("tenders")
    rows, cols = d["rows"], d["columns"]
    val_c = _find(cols, "value", "amount", "worth", "estimate", "emd")
    stat_c = _find(cols, "status", "stage")
    due_c = _find(cols, "due", "deadline", "submission", "closing")
    name_c = _find(cols, "tender", "project", "name", "title", "description")
    total, by_status, upcoming = 0.0, {}, []
    for r in rows:
        val = _num(r.get(val_c)) if val_c else None
        if val:
            total += val
        st = str(r.get(stat_c) or "open").strip() if stat_c else "open"
        by_status[st] = round(by_status.get(st, 0.0) + (val or 0), 2)
        dd = _to_date(r.get(due_c)) if due_c else None
        if dd:
            days = -(_days_since(dd) or 0)  # days until due
            if days >= 0:
                upcoming.append({"tender": r.get(name_c) if name_c else "—",
                                 "value": round(val or 0, 2), "due_in_days": days})
    upcoming.sort(key=lambda x: x["due_in_days"])
    return {"pipeline_value": round(total, 2), "by_status": by_status,
            "upcoming": upcoming[:8], "count": d["count"]}


def hotel_kpis() -> dict:
    d = load("hotel")
    rows, cols = d["rows"], d["columns"]
    occ_c = _find(cols, "occupancy", "occ")
    adr_c = _find(cols, "adr", "average rate", "avg rate")
    rev_c = _find(cols, "revenue", "revpar", "room revenue", "sales")
    rooms_c = _find(cols, "rooms sold", "rooms", "nights")
    if not rows:
        return {"count": 0}
    last = rows[-1]
    occ = _num(last.get(occ_c)) if occ_c else None
    adr = _num(last.get(adr_c)) if adr_c else None
    rev = _num(last.get(rev_c)) if rev_c else None
    revpar = None
    if occ is not None and adr is not None:
        revpar = round((occ / 100.0 if occ > 1.5 else occ) * adr, 2)
    mtd_rev = sum((_num(r.get(rev_c)) or 0) for r in rows) if rev_c else None
    return {"count": d["count"], "latest_occupancy": occ, "latest_adr": adr,
            "latest_revenue": rev, "revpar": revpar,
            "mtd_revenue": round(mtd_rev, 2) if mtd_rev is not None else None}


def generic_summary(name: str) -> dict:
    """For datasets without a bespoke KPI: row count + numeric column totals + date span."""
    d = load(name)
    rows, cols = d["rows"], d["columns"]
    sums, dates = {}, []
    for c in cols:
        vals = [_num(r.get(c)) for r in rows]
        vals = [v for v in vals if v is not None]
        if vals and len(vals) >= max(1, len(rows) // 2):
            sums[c] = round(sum(vals), 2)
    date_c = _find(cols, "date", "due", "deadline")
    if date_c:
        for r in rows:
            dt = _to_date(r.get(date_c))
            if dt:
                dates.append(dt)
    return {"dataset": name, "count": d["count"], "columns": cols,
            "numeric_totals": sums,
            "date_span": [min(dates).isoformat(), max(dates).isoformat()] if dates else None,
            "imported_at": d.get("imported_at")}


def summary() -> dict:
    """Everything the Business BRIEF needs in one call."""
    return {"datasets": datasets(),
            "receivables": receivables_aging(),
            "tenders": tender_pipeline(),
            "hotel": hotel_kpis()}
