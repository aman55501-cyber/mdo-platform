"""Push throttle so notifications stay rare and trusted.

Only 🔴 critical, NEW alerts push, at most 5 per run, and the same standing breach
never re-pushes within a 72h cooldown. This is what stops people muting the app.
In-memory (resets on restart) — fine, since a standing breach re-alerts at most
once per cooldown anyway.
"""

from __future__ import annotations

COOLDOWN_SECONDS = 72 * 3600
MAX_PER_RUN = 5

_LAST_PUSHED: dict[str, float] = {}


def _sig(alert: dict) -> str:
    return f"{alert.get('category')}|{alert.get('what')}"


def new_pushable(alerts: list[dict], now: float) -> list[dict]:
    """Return up to MAX_PER_RUN critical alerts not pushed within the cooldown."""
    out = []
    for a in alerts:
        if a.get("severity") != "🔴":
            continue
        last = _LAST_PUSHED.get(_sig(a), 0.0)
        if now - last >= COOLDOWN_SECONDS:
            out.append(a)
        if len(out) >= MAX_PER_RUN:
            break
    return out


def mark_pushed(alerts: list[dict], now: float) -> None:
    for a in alerts:
        _LAST_PUSHED[_sig(a)] = now
