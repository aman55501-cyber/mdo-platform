"""Futures open-interest build-up — the classic price × OI read on positioning.

For each F&O stock we track near-month futures OI day-over-day and combine the OI
change with the price change:

    price up   + OI up   -> long buildup     (fresh longs, bullish)
    price down + OI up   -> short buildup     (fresh shorts, bearish)
    price up   + OI down -> short covering    (shorts exiting, bullish-ish)
    price down + OI down -> long unwinding    (longs exiting, bearish-ish)

OI change needs a prior reading, so we snapshot OI once per day to the state volume.
Deltas (and therefore signals) appear from the second day the app runs; before that
we still report the absolute OI so the chain is visibly live.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_SNAP = Path(__file__).resolve().parent.parent / "data" / "state" / "oi_snapshot.json"


def _load() -> dict:
    if _SNAP.exists():
        try:
            return json.loads(_SNAP.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {}


def _save(state: dict) -> None:
    try:
        _SNAP.parent.mkdir(parents=True, exist_ok=True)
        _SNAP.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def classify(price_chg: float, oi_chg: float | None) -> tuple[str, str]:
    """(signal, bias) from the price/OI quadrant. oi_chg is a percent, or None."""
    if oi_chg is None:
        return "baseline", "neutral"
    if abs(oi_chg) < 1.5:
        return "flat OI", "neutral"
    up_oi = oi_chg > 0
    up_px = price_chg >= 0
    if up_oi and up_px:
        return "long buildup", "bullish"
    if up_oi and not up_px:
        return "short buildup", "bearish"
    if not up_oi and up_px:
        return "short covering", "bullish"
    return "long unwinding", "bearish"


def buildup(rows: list[dict], scrip) -> list[dict]:
    """rows: [{sym, price_change_pct}]. Returns per-symbol OI + change + signal.

    Snapshots today's OI, comparing against the last DIFFERENT-day reading so the
    change is genuinely day-over-day (repeat calls within a day don't zero it out).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    state = _load()
    ref = state.get("oi", {}) if state.get("date") != today else state.get("prev_oi", {})

    tok_map = {}
    for r in rows:
        sym = (r.get("sym") or "").upper()
        t = scrip.fut_token(sym) if sym else None
        if t:
            tok_map[str(t)] = sym
    quotes = scrip.option_full(list(tok_map.keys())) if tok_map else {}

    today_oi = dict(state.get("oi", {})) if state.get("date") == today else {}
    out = []
    for r in rows:
        sym = (r.get("sym") or "").upper()
        tok = next((t for t, s in tok_map.items() if s == sym), None)
        oi = (quotes.get(tok) or {}).get("oi") if tok else None
        if oi is None:
            continue
        today_oi[sym] = oi
        prev = ref.get(sym)
        oi_chg = round((oi - prev) / prev * 100, 1) if prev else None
        sig, bias = classify(r.get("price_change_pct", 0) or 0, oi_chg)
        out.append({"sym": sym, "oi": oi, "oi_change_pct": oi_chg,
                    "price_change_pct": round(r.get("price_change_pct", 0) or 0, 2),
                    "signal": sig, "bias": bias})

    # persist: roll the day's reference forward when the date turns over
    if state.get("date") != today:
        _save({"date": today, "oi": today_oi, "prev_oi": state.get("oi", {})})
    else:
        merged = dict(state.get("oi", {}))
        merged.update(today_oi)
        _save({"date": today, "oi": merged, "prev_oi": state.get("prev_oi", {})})

    order = {"bullish": 0, "bearish": 1, "neutral": 2}
    out.sort(key=lambda x: (order.get(x["bias"], 3), -abs(x.get("oi_change_pct") or 0)))
    return out
