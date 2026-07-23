"""
Business OS — data model + KPIs.

Import-driven: every dataset is a list of ``{header: value}`` rows persisted to
``data/state/business/<dataset>.json`` on the mounted volume. Columns are
auto-detected by keyword, so no manual field mapping is needed at import time.

KPIs computed here:
  - receivables : aging buckets 0-30 / 31-60 / 61-90 / 90+ and total outstanding
  - tenders     : pipeline count, total value, upcoming deadlines
  - hotel       : RevPAR, occupancy, MTD revenue
  - <any sheet> : a generic numeric summary (sum/avg/count per numeric column)

Open item #14: the KEYWORD_MAPS below are first-pass guesses. Once Aman imports
a real sheet, tune each dataset's keyword lists to his actual headers.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .helpers import normalise, read_table

log = logging.getLogger("business_os")

# The seven datasets the console imports. "generic" is the fallback KPI.
DATASETS = [
    "tenders",
    "receivables",
    "hotel",
    "cash-flow",
    "tasks",
    "projects",
    "compliance",
]


def data_dir() -> Path:
    """Persistent volume path for dataset JSON. Overridable via env.

    Defaults to ``<repo>/data/state/business`` so it works out of the box in
    dev; in Docker mount a volume at this path (see Dockerfile / README).
    """
    base = os.getenv("BUSINESS_DATA_DIR")
    if base:
        path = Path(base)
    else:
        path = Path(__file__).resolve().parent.parent / "data" / "state" / "business"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _dataset_file(dataset: str) -> Path:
    safe = re.sub(r"[^a-z0-9_\-]", "", dataset.lower())
    if not safe:
        raise ValueError(f"invalid dataset name: {dataset!r}")
    return data_dir() / f"{safe}.json"


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def save_dataset(dataset: str, rows: list[dict[str, Any]]) -> int:
    """Replace a dataset's rows on the volume. Returns the row count saved."""
    path = _dataset_file(dataset)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=0, default=str))
    tmp.replace(path)  # atomic swap
    log.info("saved dataset %s: %d rows", dataset, len(rows))
    return len(rows)


def load_dataset(dataset: str) -> list[dict[str, Any]]:
    path = _dataset_file(dataset)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text() or "[]")
    except json.JSONDecodeError:
        log.warning("dataset %s is corrupt; returning empty", dataset)
        return []


def import_bytes(dataset: str, data: bytes, filename: str = "") -> dict[str, Any]:
    """Parse an uploaded sheet and save it as ``dataset`` (save + replace)."""
    rows = read_table(data, filename)
    count = save_dataset(dataset, rows)
    return {
        "dataset": dataset,
        "rows": count,
        "columns": list(rows[0].keys()) if rows else [],
        "kpi": compute_kpi(dataset, rows),
    }


def dataset_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(data_dir().glob("*.json")):
        try:
            rows = json.loads(path.read_text() or "[]")
            counts[path.stem] = len(rows)
        except json.JSONDecodeError:
            counts[path.stem] = 0
    return counts


# ---------------------------------------------------------------------------
# Column auto-detection  (#14 — tune these to real headers)
# ---------------------------------------------------------------------------

# For each logical field, a list of case-insensitive substrings to look for in
# the sheet's headers. First matching column wins.
KEYWORD_MAPS: dict[str, dict[str, list[str]]] = {
    "receivables": {
        "party": ["party", "customer", "client", "name", "debtor", "account"],
        "amount": ["outstanding", "balance", "due", "receivable", "amount", "pending"],
        "date": ["invoice date", "bill date", "date", "invoice"],
        "due_date": ["due date", "duedate", "maturity"],
        "age": ["age", "days", "ageing", "aging", "overdue"],
    },
    "tenders": {
        # Tuned to GeM Tender-Summary export headers (#14).
        "name": ["boq title", "boq", "title", "tender", "bid details", "project",
                 "description", "work", "name"],
        # EMD deliberately REMOVED — the pipeline total must never sum EMD.
        "value": ["estimated bid value", "bid value", "contract value", "estimated",
                  "value", "amount", "worth", "cost"],
        "emd": ["emd"],
        # Bare "submission" is LAST so "Hard Copy Submission" (not a date) can't win;
        # no bare "end date"/"state" — they false-match "Bid Offer Validity
        # (From End Date)" and "Ministry/State Name/".
        "deadline": ["submission deadline", "submission date", "bid end", "closing",
                     "last date", "due date", "deadline", "bid opening", "opening date",
                     "date", "submission"],
        "status": ["status", "stage"],
        "department": ["department", "ministry", "office"],
        "min_turnover": ["turnover"],
    },
    "hotel": {
        "date": ["date", "day", "business date"],
        "rooms_available": ["available", "total rooms", "inventory", "room nights"],
        "rooms_sold": ["sold", "occupied", "rooms sold", "occ rooms"],
        "revenue": ["revenue", "room revenue", "sales", "amount", "total"],
        "adr": ["adr", "avg rate", "average rate", "rate"],
        "occupancy": ["occupancy", "occ %", "occ"],
    },
    "cash-flow": {
        "date": ["date", "month", "period"],
        "inflow": ["inflow", "credit", "receipt", "in", "income"],
        "outflow": ["outflow", "debit", "payment", "out", "expense"],
        "balance": ["balance", "closing", "net"],
    },
    "tasks": {
        "title": ["task", "title", "description", "item", "activity"],
        "owner": ["owner", "assigned", "responsible", "person"],
        "due_date": ["due", "deadline", "target date", "date"],
        "status": ["status", "state", "done", "complete"],
    },
    "projects": {
        "name": ["project", "name", "title"],
        "milestone": ["milestone", "stage", "phase", "deliverable"],
        "due_date": ["due", "deadline", "target", "date", "completion"],
        "status": ["status", "state", "progress"],
    },
    "compliance": {
        "name": ["filing", "return", "compliance", "statutory", "name", "type", "form"],
        "due_date": ["due", "deadline", "date", "last date"],
        "status": ["status", "filed", "state"],
    },
}


def _find_col(headers: list[str], keywords: list[str]) -> str | None:
    low = {h: h.lower() for h in headers}
    # Prefer exact-ish matches before loose substring matches.
    for kw in keywords:
        for h, hl in low.items():
            if hl == kw:
                return h
    for kw in keywords:
        for h, hl in low.items():
            if kw in hl:
                return h
    return None


def _map_columns(dataset: str, rows: list[dict[str, Any]]) -> dict[str, str | None]:
    if not rows:
        return {}
    headers = list(rows[0].keys())
    fields = KEYWORD_MAPS.get(dataset, {})
    return {field: _find_col(headers, kws) for field, kws in fields.items()}


# ---------------------------------------------------------------------------
# Date + numeric parsing
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d %b %Y",
    "%d-%b-%y", "%d/%m/%y", "%Y/%m/%d", "%d.%m.%Y", "%b %d, %Y", "%d %B %Y",
]


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Fallback: pull the first dd<sep>mm<sep>yyyy triplet (day/month/year) out of
    # a messy cell like "20:02.2026 from 15:30 Hrs" -> 2026-02-20.
    m = re.search(r"\b(\d{1,2})[.:/-](\d{1,2})[.:/-](\d{4})\b", s)
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(yy, mm, dd)
        except ValueError:
            return None
    return None


def _num(row: dict[str, Any], col: str | None, default: float | None = None):
    """Fetch a cell and run it through the normaliser (hard rule)."""
    if not col:
        return default
    return normalise(row.get(col), default)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def compute_kpi(dataset: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if rows is None:
        rows = load_dataset(dataset)
    cols = _map_columns(dataset, rows)
    if dataset == "receivables":
        return _kpi_receivables(rows, cols)
    if dataset == "tenders":
        return _kpi_tenders(rows, cols)
    if dataset == "hotel":
        return _kpi_hotel(rows, cols)
    return _kpi_generic(rows)


def _kpi_receivables(rows, cols) -> dict[str, Any]:
    today = date.today()
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    total = 0.0
    for r in rows:
        amt = _num(r, cols.get("amount"), 0.0) or 0.0
        total += amt
        # Age: prefer an explicit age column, else derive from invoice/due date.
        age = _num(r, cols.get("age"))
        if age is None:
            ref = _parse_date(r.get(cols.get("due_date") or "")) or \
                _parse_date(r.get(cols.get("date") or ""))
            age = (today - ref).days if ref else None
        if age is None:
            buckets["0-30"] += amt  # unknown age -> treat as current
        elif age <= 30:
            buckets["0-30"] += amt
        elif age <= 60:
            buckets["31-60"] += amt
        elif age <= 90:
            buckets["61-90"] += amt
        else:
            buckets["90+"] += amt
    return {
        "kind": "receivables",
        "total_outstanding": round(total, 2),
        "aging": {k: round(v, 2) for k, v in buckets.items()},
        "overdue_60_plus": round(buckets["61-90"] + buckets["90+"], 2),
        "count": len(rows),
        "columns_used": cols,
    }


def _kpi_tenders(rows, cols) -> dict[str, Any]:
    today = date.today()
    total_value = 0.0
    total_emd = 0.0
    upcoming: list[dict[str, Any]] = []
    for r in rows:
        val = _num(r, cols.get("value"), 0.0) or 0.0
        total_value += val
        total_emd += _num(r, cols.get("emd"), 0.0) or 0.0
        dl = _parse_date(r.get(cols.get("deadline") or ""))
        if dl:
            days = (dl - today).days
            if days >= 0:
                upcoming.append({
                    "name": r.get(cols.get("name") or "", ""),
                    "deadline": dl.isoformat(),
                    "days_left": days,
                    "value": val,
                })
    upcoming.sort(key=lambda x: x["days_left"])
    return {
        "kind": "tenders",
        "pipeline_count": len(rows),
        "total_value": round(total_value, 2),
        "total_emd": round(total_emd, 2),
        "upcoming_deadlines": upcoming[:10],
        "closing_this_week": sum(1 for u in upcoming if u["days_left"] <= 7),
        "columns_used": cols,
    }


def _kpi_hotel(rows, cols) -> dict[str, Any]:
    today = date.today()
    total_rev = mtd_rev = 0.0
    rooms_avail = rooms_sold = 0.0
    for r in rows:
        rev = _num(r, cols.get("revenue"), 0.0) or 0.0
        total_rev += rev
        d = _parse_date(r.get(cols.get("date") or ""))
        if d and d.year == today.year and d.month == today.month:
            mtd_rev += rev
        rooms_avail += _num(r, cols.get("rooms_available"), 0.0) or 0.0
        rooms_sold += _num(r, cols.get("rooms_sold"), 0.0) or 0.0
    revpar = (total_rev / rooms_avail) if rooms_avail else None
    adr = (total_rev / rooms_sold) if rooms_sold else None
    occ = (rooms_sold / rooms_avail * 100) if rooms_avail else None
    return {
        "kind": "hotel",
        "revpar": round(revpar, 2) if revpar is not None else None,
        "adr": round(adr, 2) if adr is not None else None,
        "occupancy_pct": round(occ, 1) if occ is not None else None,
        "mtd_revenue": round(mtd_rev, 2),
        "total_revenue": round(total_rev, 2),
        "count": len(rows),
        "columns_used": cols,
    }


def _kpi_generic(rows) -> dict[str, Any]:
    """A numeric summary for any sheet: for each column that looks numeric,
    report count / sum / avg."""
    if not rows:
        return {"kind": "generic", "count": 0, "numeric": {}}
    headers = list(rows[0].keys())
    numeric: dict[str, dict[str, float]] = {}
    for h in headers:
        vals = [normalise(r.get(h)) for r in rows]
        vals = [v for v in vals if v is not None]
        # Only treat as numeric if a majority of populated cells parsed.
        populated = sum(1 for r in rows if str(r.get(h, "")).strip() != "")
        if populated and len(vals) >= max(1, populated * 0.6):
            numeric[h] = {
                "count": len(vals),
                "sum": round(sum(vals), 2),
                "avg": round(sum(vals) / len(vals), 2),
            }
    return {"kind": "generic", "count": len(rows), "numeric": numeric}


# ---------------------------------------------------------------------------
# Summary  ("the Brief")
# ---------------------------------------------------------------------------

def summary() -> dict[str, Any]:
    """Datasets present + a computed KPI for each. Powers GET /business/summary
    and the morning MIS digest."""
    counts = dataset_counts()
    out: dict[str, Any] = {"datasets": counts, "kpis": {}}
    for name in counts:
        try:
            out["kpis"][name] = compute_kpi(name)
        except Exception as exc:  # a bad sheet must not break the whole brief
            log.warning("KPI failed for %s: %s", name, exc)
            out["kpis"][name] = {"kind": "error", "error": str(exc)}
    return out
