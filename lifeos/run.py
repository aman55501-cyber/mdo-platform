"""The run — gather every source, record each, render one snapshot, prove it ran.

Order of operations is deliberate (brief rules 1-3):
  1. start_run()  -> writes the started row immediately (no finish time yet).
  2. for each source: guarded() so it can never abort the run; record its Result.
  3. render the snapshot from whatever we got (even all-failed still publishes).
  4. save_snapshot() then finish_run() -> stamps the finish time + tallies.

If the process is killed between steps 1 and 4, the started row stays unfinished
and the next page shows the "previous run did not complete" banner. That is the
silent-death guard working as designed.
"""

from __future__ import annotations

from datetime import datetime

from . import db
from .config import IST
from .render import render_console
from .sources import Result, guarded
from .sources import self_check
from .sources import deal_room

# The source registry. Each entry is (name, fetch_callable); order here is display
# order on the page. Phases 2+ append Gmail, Calendar, Supabase tenders,
# scheduled-task health, brokers and per-entity ERP export parsers.
SOURCES: list[tuple[str, callable]] = [
    ("deal_room_actions", deal_room.fetch_actions),
    ("deal_room_counterparties", deal_room.fetch_counterparties),
    ("self_check", self_check.fetch),
]


def execute_run(trigger: str = "manual") -> dict:
    """Run every source and publish a snapshot. Returns a small summary dict for
    logs/health — never raises (a source failing is normal; the run still finishes)."""
    db.init_db()
    started = datetime.now(IST)
    run_id = db.start_run(trigger)

    results: list[Result] = []
    for name, fetch in SOURCES:
        result = guarded(name, fetch)
        db.record_source(run_id, result.name, result.status, result.reason or result.summary, result.ms)
        results.append(result)

    # Was a *previous* run left incomplete? (Any unfinished row that isn't this one —
    # this run's own row is still unfinished at render time, so exclude it.)
    prev = db.previous_incomplete_run(exclude_run_id=run_id)
    previous_incomplete = bool(prev)

    ok = sum(1 for r in results if r.healthy)
    unreachable = sum(1 for r in results if r.unreachable)

    html = render_console(
        results,
        started_at=started,
        previous_incomplete=previous_incomplete,
        trigger=trigger,
    )
    db.save_snapshot(run_id, html)
    db.finish_run(run_id, ok, unreachable, note=f"{len(results)} sources")

    return {
        "run_id": run_id,
        "sources_ok": ok,
        "sources_unreachable": unreachable,
        "total": len(results),
        "trigger": trigger,
    }
