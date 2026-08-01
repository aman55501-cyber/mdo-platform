"""Daily reconciliation — diff today's book vs the last snapshot.

Surfaces what actually changed: new positions, exits, quantity changes (trades),
and cash moves — corporate-action aware isn't modelled yet, so a split shows as a
qty change and is flagged for review rather than silently trusted.
"""

from __future__ import annotations

from . import persist


def diff(today: dict, prev: dict) -> dict:
    th, ph = today.get("holdings", {}), prev.get("holdings", {})
    holding_changes = []
    for key in sorted(set(th) | set(ph)):
        tq = th.get(key, {}).get("qty", 0)
        pq = ph.get(key, {}).get("qty", 0)
        if tq != pq:
            kind = "new_position" if pq == 0 else ("exited" if tq == 0 else "qty_change")
            holding_changes.append({
                "instrument": key, "type": kind,
                "prev_qty": pq, "new_qty": tq, "delta": tq - pq,
            })

    tp, pp = today.get("positions", {}), prev.get("positions", {})
    position_changes = []
    for key in sorted(set(tp) | set(pp)):
        tq = tp.get(key, {}).get("qty", 0)
        pq = pp.get(key, {}).get("qty", 0)
        if tq != pq:
            kind = "opened" if pq == 0 else ("closed" if tq == 0 else "changed")
            position_changes.append({
                "instrument": key, "type": kind,
                "prev_qty": pq, "new_qty": tq, "delta": tq - pq,
            })

    return {
        "since": prev.get("date"),
        "net_worth_change": round(today.get("net_worth", 0) - prev.get("net_worth", 0), 2),
        "cash_move": round(today.get("cash", 0) - prev.get("cash", 0), 2),
        "holding_changes": holding_changes,
        "position_changes": position_changes,
        "note": "Quantity changes may be trades OR a corporate action (split/bonus). "
                "Verify large deltas against contract notes." if holding_changes else "",
    }


def run_daily(book: dict) -> dict:
    """Snapshot today's book, diff against the previous snapshot, and save today's."""
    today = persist.snapshot_from_book(book)
    prev = persist.latest(exclude_date=today["date"])
    persist.save(today)
    if not prev:
        return {"cadence": "daily", "first_run": True,
                "message": "Saved today's snapshot. Reconciliation compares from tomorrow."}
    return {"cadence": "daily", "as_of": book.get("as_of"), **diff(today, prev)}
