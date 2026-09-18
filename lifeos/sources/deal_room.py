"""Deal Room sources — the sales spine (brief's Operations tab, Sales-first focus).

Two fault-isolated fetchers over the real Notion schemas:

  actions        — ANS Route · Actions. Surfaces every action awaiting Aman's
                   click (rule 4 autonomy), each with days-late; and the overdue set.
  counterparties — ANS Route · Counterparties. Stage breakdown, next actions due,
                   and anyone silent more than 7 working days.

Both return a Result whose ``extra['rows']`` is a list of display rows the template
renders with a left-gutter figure and a severity stripe (colour carries the days-late
signal). Nil states are spelled out in words (rule 1). A raised Notion error is
converted to UNREACHABLE upstream by guarded().
"""

from __future__ import annotations

from datetime import date, datetime

from . import BLOCKED, NIL, OK, Result  # noqa: F401
from ..config import IST
from . import notion_client as nc

ACTIONS_DS = "25613c58-1480-4096-b557-96a9e48bab81"
COUNTERPARTIES_DS = "5e5919d2-185b-42f6-8503-4abb8625f96c"

# Hotel ANS Track-A decision date named in the brief ("the 20 Oct decision").
DECISION_DATE = date(2026, 10, 20)

_DONE = {"Done", "Dropped"}
_STAGE_CLOSED = {"Dropped"}
_SILENT_WORKING_DAYS = 7


def _today() -> date:
    return datetime.now(IST).date()


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _days_late(due: date | None, today: date) -> int | None:
    """Positive = overdue by N days; 0 = due today; negative = due in future."""
    if due is None:
        return None
    return (today - due).days


def _working_days_between(start: date, end: date) -> int:
    """Count Mon-Fri days in (start, end]. Used for 'silent > 7 working days'."""
    if end <= start:
        return 0
    days = 0
    cur = start
    while cur < end:
        cur = date.fromordinal(cur.toordinal() + 1)
        if cur.weekday() < 5:  # 0=Mon .. 4=Fri
            days += 1
    return days


def _gutter(days_late: int | None) -> tuple[str, str]:
    """(text, severity) for the left gutter. Severity drives the stripe colour."""
    if days_late is None:
        return "—", "quiet"
    if days_late > 0:
        return f"+{days_late}d", ("critical" if days_late >= 3 else "warning")
    if days_late == 0:
        return "today", "warning"
    return f"{days_late}d", "quiet"


# ── Actions ───────────────────────────────────────────────────────────────────
def fetch_actions() -> Result:
    pages = nc.query_data_source(ACTIONS_DS)
    today = _today()

    awaiting: list[dict] = []
    overdue = 0
    for p in pages:
        step = nc.title(p, "Step")
        st = nc.select(p, "Status")
        if st in _DONE:
            continue
        due = _parse_date(nc.date_start(p, "Due"))
        dl = _days_late(due, today)
        if dl is not None and dl > 0:
            overdue += 1
        # "My click" unchecked + not done == an action still awaiting Aman's authority.
        if not nc.checkbox(p, "My click"):
            g_text, sev = _gutter(dl)
            awaiting.append(
                {
                    "gutter": g_text,
                    "severity": sev,
                    "text": step or "(untitled action)",
                    "meta": " · ".join(
                        x for x in [nc.select(p, "Owner"), nc.select(p, "Phase"), st] if x
                    ),
                    "_sort": dl if dl is not None else -9999,
                }
            )

    awaiting.sort(key=lambda r: r["_sort"], reverse=True)
    for r in awaiting:
        r.pop("_sort", None)

    days_to_decision = (DECISION_DATE - today).days
    if awaiting:
        summary = (
            f"{len(awaiting)} action(s) awaiting your click, {overdue} overdue. "
            f"Track-A decision in {days_to_decision} days ({DECISION_DATE:%d %b})."
        )
        status = OK
    else:
        summary = (
            f"0 actions awaiting your click. {overdue} overdue in progress. "
            f"Track-A decision in {days_to_decision} days ({DECISION_DATE:%d %b})."
        )
        status = NIL
    return Result(
        name="deal_room_actions",
        status=status,
        summary=summary,
        data={"awaiting": len(awaiting), "overdue": overdue, "total": len(pages)},
        extra={"rows": awaiting, "days_to_decision": days_to_decision},
    )


# ── Counterparties ────────────────────────────────────────────────────────────
def fetch_counterparties() -> Result:
    pages = nc.query_data_source(COUNTERPARTIES_DS)
    today = _today()

    by_stage: dict[str, int] = {}
    silent: list[dict] = []
    live = 0
    for p in pages:
        stage = nc.select(p, "Stage") or "Not contacted"
        by_stage[stage] = by_stage.get(stage, 0) + 1
        if stage in _STAGE_CLOSED:
            continue
        live += 1
        last = _parse_date(nc.date_start(p, "Last touch"))
        if last is not None:
            wd = _working_days_between(last, today)
            if wd > _SILENT_WORKING_DAYS:
                silent.append(
                    {
                        "gutter": f"{wd}wd",
                        "severity": "critical" if wd > 12 else "warning",
                        "text": nc.title(p, "Party") or "(unnamed party)",
                        "meta": " · ".join(
                            x for x in [stage, nc.text(p, "Next action")] if x
                        ),
                        "_sort": wd,
                    }
                )

    silent.sort(key=lambda r: r["_sort"], reverse=True)
    for r in silent:
        r.pop("_sort", None)

    stage_line = ", ".join(f"{k}: {v}" for k, v in sorted(by_stage.items())) or "none"
    if silent:
        summary = f"{live} live counterparties. {len(silent)} silent >7 working days. Stages — {stage_line}."
        status = OK
    elif live:
        summary = f"{live} live counterparties, none silent beyond 7 working days. Stages — {stage_line}."
        status = OK
    else:
        summary = "0 live counterparties in the deal room."
        status = NIL
    return Result(
        name="deal_room_counterparties",
        status=status,
        summary=summary,
        data={"live": live, "silent": len(silent), "by_stage": by_stage},
        extra={"rows": silent},
    )
