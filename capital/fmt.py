"""Display helpers: Indian number grouping, percentages, and ages. Pure functions, no I/O."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .config import IST


def _num(x: Any) -> float | None:
    if x is None:
        return None
    return float(x) if isinstance(x, (int, float, Decimal)) else None


def inr(x: Any, compact: bool = True) -> str:
    """₹ with Indian units: 4.36 Cr, 33.82 L, 8,450. Negative values keep their sign."""
    v = _num(x)
    if v is None:
        return "—"
    sign = "−" if v < 0 else ""
    a = abs(v)
    if compact and a >= 1e7:
        return f"{sign}₹{a / 1e7:.2f} Cr"
    if compact and a >= 1e5:
        return f"{sign}₹{a / 1e5:.2f} L"
    return f"{sign}₹{_group(round(a))}"


def _group(n: int) -> str:
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def price(x: Any) -> str:
    v = _num(x)
    if v is None:
        return "—"
    s = f"{v:,.2f}"
    if s.endswith(".00"):
        return s[:-3]
    return s.rstrip("0") if "." in s else s


def pct(x: Any, *, signed: bool = True) -> str:
    v = _num(x)
    if v is None:
        return "—"
    sign = "+" if v > 0 and signed else ("−" if v < 0 else "")
    return f"{sign}{abs(v):.2f}%"


def tone(x: Any) -> str:
    v = _num(x)
    if v is None or v == 0:
        return "flat"
    return "up" if v > 0 else "down"


def age(ts: datetime | None, now: datetime | None = None) -> str:
    """'4h', '2d', 'just now' — how old an input is."""
    if ts is None:
        return "never"
    now = now or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    mins = (now - ts).total_seconds() / 60
    if mins < 2:
        return "just now"
    if mins < 90:
        return f"{int(mins)}m"
    if mins < 60 * 36:
        return f"{int(mins // 60)}h"
    return f"{int(mins // 1440)}d"


def ist_clock(ts: datetime | None) -> str:
    if ts is None:
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(IST).strftime("%d %b %H:%M")


def market_open(now: datetime | None = None) -> bool:
    """NSE cash session, IST, Mon-Fri 09:15-15:30. Exchange holidays are not modelled here."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minutes <= 15 * 60 + 30


def range_bar(now: Any, low: Any, high: Any, mark: Any = None) -> dict | None:
    """Position of a price between a stop (low) and a target (high), as 0-100 for a progress bar.

    Returns None unless both ends are known and low < high: no guessed ends. `mark` (usually the entry) is
    placed on the same scale. `state` says if the price has left the range."""
    lo, hi, px, mk = _num(low), _num(high), _num(now), _num(mark)
    if lo is None or hi is None or hi <= lo:
        return None

    def at(v):
        return None if v is None else max(0.0, min(100.0, (v - lo) / (hi - lo) * 100))

    state = None
    if px is not None:
        state = "below_stop" if px <= lo else "at_target" if px >= hi else "inside"
    return {"now": at(px), "mark": at(mk), "state": state, "low": lo, "high": hi}


def bar_width(value: Any, scale: float) -> float:
    v = _num(value)
    if v is None or not scale:
        return 0.0
    return max(2.0, min(100.0, abs(v) / scale * 100))
