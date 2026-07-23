"""Self-monitoring heartbeat registry — proof of life per module.

Every module stamps a heartbeat when it actually produces data; the status feed
reports those stamps verbatim. Nothing is ever asserted "live" — a module that hasn't
beaten shows no signal, and a stale stamp shows its real age. This is what the status
dashboard reads, so the page can never claim health the server didn't vouch for.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

# The trading-console modules the status page tracks (ids match the dashboard's array).
MODULES = ("sector_map", "holdings", "share_page", "positions", "deep", "income",
           "charts", "execution", "agent")

_HB: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def beat(*module_ids: str, ok: bool = True) -> None:
    """Record a heartbeat for one or more modules (called on real success)."""
    t = _now()
    for m in module_ids:
        _HB[m] = {"ok": bool(ok), "last": t}


def snapshot() -> dict:
    """The full health payload the status dashboard fetches. No secrets, no financials."""
    from . import token_store
    armed = {k.upper() for k in token_store.armed_accounts()}
    modules = {m: _HB.get(m, {"ok": False, "last": None}) for m in MODULES}
    return {
        "ts": _now(),
        "hdfc_session": any(k.startswith("HDFC") for k in armed),
        "angel_session": any(k.startswith("ANGEL") for k in armed),
        "modules": modules,
    }
