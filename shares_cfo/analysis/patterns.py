"""Pattern detection + honest per-pattern backtest (hit-rate, no look-ahead).

A pattern only earns a place in an idea if it has an edge you can measure. Each
pattern is a pure function of prices/volumes up to a day; the backtest walks every
historical occurrence and measures the forward return over a fixed horizon, so the
hit-rate shown next to an idea is computed from this symbol's own history — never a
made-up number.
"""

from __future__ import annotations


def _sma(vals: list[float], period: int, i: int) -> float | None:
    if i + 1 < period:
        return None
    w = vals[i + 1 - period:i + 1]
    return sum(w) / period


def _rsi(closes: list[float], i: int, period: int = 14) -> float | None:
    if i < period:
        return None
    gains = losses = 0.0
    for k in range(i - period + 1, i + 1):
        ch = closes[k] - closes[k - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - 100 / (1 + rs)


# Each detector returns True if the pattern fires at index i (using data <= i only).
def _above_200dma_reclaim(c, v, i) -> bool:
    s = _sma(c, 200, i)
    sp = _sma(c, 200, i - 5)
    if s is None or sp is None:
        return False
    return c[i] > s and c[i - 5] <= (sp or 0)


def _golden_cross(c, v, i) -> bool:
    f, s = _sma(c, 50, i), _sma(c, 200, i)
    fp, sp = _sma(c, 50, i - 3), _sma(c, 200, i - 3)
    if None in (f, s, fp, sp):
        return False
    return fp <= sp and f > s


def _oversold_in_uptrend(c, v, i) -> bool:
    s = _sma(c, 200, i)
    r = _rsi(c, i)
    return s is not None and r is not None and c[i] > s and r < 38


def _breakout_volume(c, v, i) -> bool:
    if i < 20:
        return False
    hi20 = max(c[i - 20:i])
    avgv = sum(v[i - 20:i]) / 20 if i >= 20 else 0
    return c[i] >= hi20 and avgv > 0 and v[i] > 1.5 * avgv


def _near_52w_high(c, v, i) -> bool:
    if i < 60:
        return False
    lo = max(0, i - 252)
    hi = max(c[lo:i + 1])
    return hi > 0 and c[i] >= 0.97 * hi and c[i] >= c[i - 1]


PATTERNS = {
    "200-DMA reclaim": _above_200dma_reclaim,
    "golden cross": _golden_cross,
    "oversold-in-uptrend": _oversold_in_uptrend,
    "breakout on volume": _breakout_volume,
    "52w-high momentum": _near_52w_high,
}


def detect(data: dict) -> list[dict]:
    """Which patterns fire TODAY (last bar), each with its backtested edge."""
    c, v = data.get("closes", []), data.get("volumes", [])
    n = len(c)
    if n < 210:
        return []
    out = []
    for name, fn in PATTERNS.items():
        try:
            if fn(c, v, n - 1):
                out.append({"pattern": name, **backtest(c, v, fn)})
        except Exception:
            continue
    return out


def backtest(c: list[float], v: list[float], fn, horizon: int = 10) -> dict:
    """Forward-return hit-rate for a detector over this series (no look-ahead)."""
    wins = occ = 0
    rets = []
    for i in range(210, len(c) - horizon):
        try:
            if fn(c, v, i):
                r = c[i + horizon] / c[i] - 1
                occ += 1
                rets.append(r)
                if r > 0:
                    wins += 1
        except Exception:
            continue
    if occ == 0:
        return {"occurrences": 0, "hit_rate": None, "avg_return_pct": None, "horizon": horizon}
    return {
        "occurrences": occ,
        "hit_rate": round(100 * wins / occ, 1),
        "avg_return_pct": round(100 * sum(rets) / len(rets), 2),
        "horizon": horizon,
    }
