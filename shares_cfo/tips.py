"""Calls / tips channels — advisor ideas you log, the console tracks and acts on.

Named channels (e.g. "Bantu Mausaji", "Anil Singhvi") hold two kinds of idea:

  - trade  : a buy (entry) + target (his sell) + stop. The console watches the live
             price against those levels and one-tap arms the guarded order ticket.
  - invest : an investment-grade name to ACCUMULATE — a ladder of buy levels (his
             price + lower "optimum" levels) that light up as price reaches each.

This is a ground-truth store YOU maintain (you type each call); the dashboard reads
and enriches it with live price. Nothing here places an order — arming always goes
through the existing propose -> confirm guardrails. No scraping; no accounting.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

TIPS_DIR = Path(__file__).resolve().parent / "data" / "state"
_STORE = TIPS_DIR / "tips.json"
_LOCK = threading.Lock()

# Suggested channels (free-form allowed); the UI offers these two first.
CHANNELS = ("Bantu Mausaji", "Anil Singhvi")
KINDS = ("trade", "invest")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _num(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _load() -> list[dict]:
    if not _STORE.exists():
        return []
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write(items: list[dict]) -> None:
    TIPS_DIR.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def suggest_stop(buy: float, side: str = "BUY", pct: float = 4.0) -> float:
    """A sensible default protective stop when a call doesn't name one: pct below the
    buy for a long (above for a short). Only a default — the user can override."""
    if not buy:
        return 0.0
    return round(buy * (1 - pct / 100.0), 2) if side.upper() == "BUY" else round(buy * (1 + pct / 100.0), 2)


def ladder(buy: float, rungs: int = 3, step_pct: float = 5.0) -> list[float]:
    """Accumulation levels for an investment idea: the buy price, then `rungs`-1 lower
    'optimum' levels each step_pct further down — so you add on dips, not chase."""
    if not buy or rungs < 1:
        return []
    return [round(buy * (1 - step_pct / 100.0 * i), 2) for i in range(rungs)]


def upsert(entry: dict) -> dict:
    source = str(entry.get("source", "")).strip()[:40]
    symbol = str(entry.get("symbol", "")).strip().upper()[:30]
    kind = entry.get("kind") if entry.get("kind") in KINDS else "trade"
    if not source:
        raise ValueError("source (channel) is required")
    if not symbol:
        raise ValueError("symbol is required")
    buy = _num(entry.get("buy"))
    side = (entry.get("side") or "BUY").upper()
    if side not in ("BUY", "SELL"):
        side = "BUY"
    target = _num(entry.get("target"))
    stop = _num(entry.get("stop"))
    if kind == "trade" and buy and not stop:
        stop = suggest_stop(buy, side)               # never a naked trade idea
    levels = entry.get("levels")
    if kind == "invest" and not levels and buy:
        levels = ladder(buy)                          # default accumulation ladder
    note = str(entry.get("note", "")).strip()[:280]

    with _LOCK:
        items = _load()
        tid = entry.get("id")
        rec = next((i for i in items if i.get("id") == tid), None) if tid else None
        if rec is None:
            rec = {"id": uuid.uuid4().hex[:12], "created_at": _now_iso(), "status": "open"}
            items.append(rec)
        rec.update(source=source, symbol=symbol, kind=kind, side=side, buy=buy,
                   target=target, stop=stop, levels=levels or None, note=note,
                   status=entry.get("status") or rec.get("status") or "open",
                   updated_at=_now_iso())
        _write(items)
    return rec


def delete(tip_id: str) -> bool:
    with _LOCK:
        items = _load()
        remaining = [i for i in items if i.get("id") != tip_id]
        if len(remaining) == len(items):
            return False
        _write(remaining)
    return True


def all_tips() -> list[dict]:
    return _load()


def symbols() -> list[str]:
    """Distinct symbols across all tips — for a single batched live-price fetch."""
    return sorted({t.get("symbol") for t in _load() if t.get("symbol")})


def state(tip: dict, ltp: float | None) -> dict:
    """Live read of a tip against the price: a state label + whether it's actionable now."""
    if not ltp:
        return {"state": "no price", "actionable": False}
    buy, target, stop = tip.get("buy"), tip.get("target"), tip.get("stop")
    side = (tip.get("side") or "BUY").upper()
    if tip.get("kind") == "invest":
        levels = tip.get("levels") or ([buy] if buy else [])
        hit = [lv for lv in levels if ltp <= lv]           # price at/below a rung = add zone
        if hit:
            return {"state": f"accumulate — at/below {max(hit)}", "actionable": True}
        nxt = min((lv for lv in levels if lv < ltp), default=None) if levels else None
        return {"state": (f"above rungs — next add {nxt}" if nxt else "above ladder"), "actionable": False}
    # trade idea (long)
    if stop and ltp <= stop:
        return {"state": "STOP breached", "actionable": True, "alert": True}
    if target and ltp >= target:
        return {"state": "target hit — book", "actionable": True}
    if target and ltp >= target * 0.99:
        return {"state": "near target", "actionable": True}
    if buy and side == "BUY":
        if ltp <= buy:
            return {"state": "at/below buy — entry zone", "actionable": True}
        if ltp <= buy * 1.01:
            return {"state": "in buy zone", "actionable": True}
        return {"state": "above buy — wait for a dip", "actionable": False}
    return {"state": "tracking", "actionable": False}
