"""Support/resistance levels — floor pivots + CPR (Central Pivot Range).

Levels-first trading (the disciplined, stop-loss style): decide the day around a
few objective numbers computed from the PRIOR session's high/low/close, not gut
feel. Floor pivots give S/R rungs; the CPR width flags trend vs range days (a
narrow CPR = expect a trending move). Everything is derived, nothing hard-coded.
"""

from __future__ import annotations


def pivots(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """Classic floor pivots + CPR from the previous session's H/L/C."""
    p = (prev_high + prev_low + prev_close) / 3.0
    rng = prev_high - prev_low
    r1, s1 = 2 * p - prev_low, 2 * p - prev_high
    r2, s2 = p + rng, p - rng
    r3, s3 = prev_high + 2 * (p - prev_low), prev_low - 2 * (prev_high - p)
    # CPR
    bc = (prev_high + prev_low) / 2.0
    tc = 2 * p - bc
    top, bot = max(tc, bc), min(tc, bc)
    cpr_width_pct = (top - bot) / p * 100 if p else 0.0
    return {
        "pivot": round(p, 2),
        "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
        "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
        "cpr_top": round(top, 2), "cpr_bottom": round(bot, 2),
        "cpr_width_pct": round(cpr_width_pct, 2),
        "cpr_type": "narrow (trending day likely)" if cpr_width_pct < 0.35
                    else "wide (rangebound day likely)" if cpr_width_pct > 0.75
                    else "moderate",
    }


def from_ohlcv(data: dict) -> dict | None:
    """Pivots from a get_ohlcv() dict, using the last completed bar."""
    highs, lows, closes = data.get("highs"), data.get("lows"), data.get("closes")
    if not highs or not lows or not closes or len(closes) < 2:
        return None
    lvl = pivots(highs[-1], lows[-1], closes[-1])
    lvl["last_close"] = round(closes[-1], 2)
    return lvl


def plan(last_price: float, lvl: dict) -> dict:
    """A levels-based, stop-disciplined trade plan around the pivot.

    Above pivot -> long bias toward R1/R2 with SL below the pivot/S1.
    Below pivot -> weak; long only on a reclaim. Always defines the stop.
    """
    p, r1, r2, s1, s2 = lvl["pivot"], lvl["r1"], lvl["r2"], lvl["s1"], lvl["s2"]
    above = last_price >= p
    if above:
        return {
            "bias": "positive above pivot",
            "trigger": f"hold above {p}",
            "targets": [r1, r2],
            "stop_loss": s1,
            "rule": f"Longs favoured above {p}. Add on dips holding {p}; "
                    f"targets {r1} then {r2}; hard SL {s1}. Book part at {r1}.",
        }
    return {
        "bias": "weak below pivot",
        "trigger": f"reclaim {p}",
        "targets": [p, r1],
        "stop_loss": s2,
        "rule": f"Below {p} stay light. Long only on a reclaim of {p} "
                f"(target {r1}, SL {s1}); else supports {s1}/{s2} in play.",
    }
