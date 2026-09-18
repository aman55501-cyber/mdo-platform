"""Compliance & Family sources (Operations + Home tabs).

Compliance: due within 21 days, then the big ones (Critical/High) within 60. EVERY
row carries a "VERIFY with Vimal" flag — the dates in that database are template
dates and nothing there is signable yet (brief). Penalty text is surfaced so the
cost of a miss is visible. Nothing here transacts (rule 4).

Family: upcoming family dates within 21 days; birthdays/anniversaries/festivals roll
to their next annual occurrence.
"""

from __future__ import annotations

from datetime import date, datetime

from . import NIL, OK, Result
from ..config import IST
from . import notion_client as nc

COMPLIANCE_DS = "ab346e91-9f0a-44ff-9757-3c97df1fa20d"
FAMILY_DS = "fd50e2c3-ec3c-4ed1-9392-c84248b7f580"

_DUE_SOON = 21
_BIG_WINDOW = 60
_BIG_PRIORITIES = {"Critical", "High"}
_RECURRING = {"Birthday", "Anniversary", "Festival"}


def _today() -> date:
    return datetime.now(IST).date()


def _pdate(s: str) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _sev_for_days(days: int, priority: str = "") -> str:
    if days < 0 or priority == "Critical":
        return "critical"
    if days <= 7 or priority == "High":
        return "warning"
    return "quiet"


# ── Compliance ────────────────────────────────────────────────────────────────
def fetch_compliance() -> Result:
    pages = nc.query_data_source(COMPLIANCE_DS)
    today = _today()

    due_soon: list[dict] = []
    big_later: list[dict] = []
    for p in pages:
        if nc.status(p, "Status") == "Done":
            continue
        due = _pdate(nc.date_start(p, "Next Due Date"))
        if due is None:
            continue
        days = (due - today).days
        priority = nc.select(p, "Priority")
        obligation = nc.title(p, "Obligation") or "(obligation)"
        penalty = nc.text(p, "Penalty / Consequence if Missed")
        cat = nc.select(p, "Category")
        gutter = f"+{-days}d" if days < 0 else (f"{days}d" if days > 0 else "today")
        meta_bits = [x for x in [cat, priority] if x]
        if penalty:
            meta_bits.append(f"penalty: {penalty[:60]}")
        meta_bits.append("VERIFY with Vimal")  # every row, until entity mapping exists
        row = {
            "gutter": gutter,
            "severity": _sev_for_days(days, priority),
            "text": obligation,
            "meta": " · ".join(meta_bits),
            "_days": days,
        }
        if days <= _DUE_SOON:
            due_soon.append(row)
        elif priority in _BIG_PRIORITIES and days <= _BIG_WINDOW:
            big_later.append(row)

    due_soon.sort(key=lambda r: r["_days"])
    big_later.sort(key=lambda r: r["_days"])
    rows = due_soon + big_later
    for r in rows:
        r.pop("_days", None)

    n21 = len(due_soon)
    summary = (
        f"{n21} obligation(s) due within 21 days, {len(big_later)} big one(s) within 60. "
        f"Dates are template dates — VERIFY with Vimal before acting; nothing here is signable yet."
    )
    status = OK if rows else NIL
    if not rows:
        summary = "0 obligations due within 21 days. (Dates are template — VERIFY with Vimal.)"
    return Result(
        name="compliance",
        status=status,
        summary=summary,
        data={"due_21": n21, "big_60": len(big_later)},
        extra={"rows": rows},
    )


# ── Family ────────────────────────────────────────────────────────────────────
def _next_occurrence(d: date, type_: str, today: date) -> date:
    """For recurring types, roll month/day to the next occurrence >= today."""
    if type_ not in _RECURRING:
        return d
    try:
        this_year = d.replace(year=today.year)
    except ValueError:  # Feb 29 etc.
        this_year = d.replace(year=today.year, day=28)
    if this_year >= today:
        return this_year
    try:
        return d.replace(year=today.year + 1)
    except ValueError:
        return d.replace(year=today.year + 1, day=28)


def fetch_family() -> Result:
    pages = nc.query_data_source(FAMILY_DS)
    today = _today()

    upcoming: list[dict] = []
    for p in pages:
        d = _pdate(nc.date_start(p, "Date"))
        if d is None:
            continue
        type_ = nc.select(p, "Type")
        occ = _next_occurrence(d, type_, today)
        days = (occ - today).days
        if 0 <= days <= _DUE_SOON:
            upcoming.append(
                {
                    "gutter": "today" if days == 0 else f"{days}d",
                    "severity": "warning" if days <= 3 else "quiet",
                    "text": nc.title(p, "Person / Occasion") or "(occasion)",
                    "meta": " · ".join(x for x in [type_, nc.select(p, "Relation")] if x),
                    "_days": days,
                }
            )
    upcoming.sort(key=lambda r: r["_days"])
    for r in upcoming:
        r.pop("_days", None)

    if upcoming:
        summary = f"{len(upcoming)} family date(s) in the next 21 days."
        status = OK
    else:
        summary = "No family dates in the next 21 days."
        status = NIL
    return Result(
        name="family",
        status=status,
        summary=summary,
        data={"count": len(upcoming)},
        extra={"rows": upcoming},
    )
