"""Snapshot store — persists a daily picture of the book for reconciliation.

File-based (data/snapshots/YYYY-MM-DD.json). On the VPS this directory is a Docker
volume so snapshots survive rebuilds. A Supabase backend can replace this later for
cross-device history without changing callers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SNAP_DIR = Path(__file__).resolve().parent / "data" / "state" / "snapshots"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def snapshot_from_book(book: dict) -> dict:
    """Reduce a /portfolio dict to the fields reconciliation compares."""
    holdings, positions = {}, {}
    for acc in book.get("accounts", []):
        for h in acc.get("holdings", []):
            holdings[f"{acc['creds_key']}:{h['ticker']}"] = {
                "qty": h.get("quantity", 0),
                "avg": h.get("average_price", 0.0),
                "value": h.get("market_value", 0.0),
            }
        for p in acc.get("positions", []):
            positions[f"{acc['creds_key']}:{p['ticker']}"] = {
                "qty": p.get("quantity", 0),
                "avg": p.get("average_price", 0.0),
            }
    return {
        "date": _today(),
        "as_of": book.get("as_of"),
        "net_worth": book.get("net_worth", 0.0),
        "cash": book.get("cash", 0.0),
        "holdings": holdings,
        "positions": positions,
    }


def save(snap: dict) -> None:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    (SNAP_DIR / f"{snap['date']}.json").write_text(json.dumps(snap), encoding="utf-8")


def latest(exclude_date: str | None = None) -> dict | None:
    """Most recent saved snapshot, optionally excluding a date (usually today)."""
    if not SNAP_DIR.exists():
        return None
    files = sorted(SNAP_DIR.glob("*.json"))
    for path in reversed(files):
        if exclude_date and path.stem == exclude_date:
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None
