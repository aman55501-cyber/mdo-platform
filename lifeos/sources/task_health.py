"""task_health — the console reporting its own liveness (brief rule 3 + the
Operations 'scheduled-task health' table).

The task runner is LIFEOS's own APScheduler morning_run, and its truth lives in the
runs table. This source reads that table and classifies the scheduled task:

  ALIVE        a run completed within the schedule window and wasn't blind
  SUSPECT      a run fired and never finished, OR the last run was blind
               (every source unreachable)
  SILENT       the last completed run is older than the daily schedule implies
  UNVERIFIABLE no completed run on record yet

It also lists every source's status from the last completed run — healthy rows
included — so the Operations table shows the full picture, not just failures.

This runs *inside* a run, so the newest row is the current in-flight run; it is
reported as in-progress, never as a failure.
"""

from __future__ import annotations

from datetime import datetime

from .. import db
from ..config import IST, RUN_HOUR, RUN_MINUTE
from . import OK, Result

_SCHEDULE = f"{RUN_HOUR:02d}:{RUN_MINUTE:02d} IST daily"
_SILENT_HOURS = 26  # daily schedule + grace


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _age_hours(dt: datetime | None, now: datetime) -> float | None:
    if dt is None:
        return None
    return (now - dt).total_seconds() / 3600.0


def _classify(runs: list) -> tuple[str, str, str]:
    """Return (state, severity, detail) for the morning_run task."""
    if not runs:
        return "UNVERIFIABLE", "warning", "no runs on record"

    now = datetime.now(IST)
    current = runs[0] if runs[0]["finished_at"] is None else None
    prior = runs[1:] if current else runs

    # a prior run that started and never finished == died mid-way
    dead = next((r for r in prior if r["finished_at"] is None), None)
    last_completed = next((r for r in prior if r["finished_at"] is not None), None)

    if dead is not None:
        return "SUSPECT", "critical", f"run #{dead['id']} started {dead['started_at']} never finished"

    if last_completed is None:
        return "UNVERIFIABLE", "warning", "no completed run yet"

    age = _age_hours(_parse(last_completed["finished_at"]), now)
    ok = last_completed["sources_ok"] or 0
    unreachable = last_completed["sources_unreachable"] or 0
    total = ok + unreachable
    if total > 0 and ok == 0:
        return "SUSPECT", "critical", "last run was blind — every source unreachable"
    if age is not None and age > _SILENT_HOURS:
        return "SILENT", "critical", f"last completed run {age:.0f}h ago (schedule is daily)"
    return "ALIVE", "alive", f"last completed {age:.1f}h ago, {ok} ok / {unreachable} unreachable"


def fetch() -> Result:
    runs = db.recent_runs(30)
    state, severity, detail = _classify(runs)

    rows = [{"gutter": state, "severity": severity, "text": "morning_run", "meta": f"{_SCHEDULE} · {detail}"}]

    # Per-source status from the last completed run (full table, healthy included).
    last_completed = next((r for r in runs if r["finished_at"] is not None), None)
    if last_completed:
        for s in db.sources_for_run(last_completed["id"]):
            sev = {
                "ok": "alive", "nil": "quiet", "blocked": "warning", "unreachable": "critical",
            }.get(s["status"], "quiet")
            rows.append(
                {
                    "gutter": s["status"].upper()[:4], "severity": sev,
                    "text": s["name"],
                    "meta": (s["detail"] or "")[:80],
                }
            )

    summary = f"Scheduled task morning_run: {state}. {detail}."
    return Result(
        name="task_health",
        status=OK,  # the health source itself is always reporting
        summary=summary,
        data={"state": state},
        extra={"rows": rows},
    )
