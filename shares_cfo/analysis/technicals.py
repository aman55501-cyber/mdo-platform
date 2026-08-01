"""Technical indicators — pure functions over plain lists (no pandas needed).

Positional-trader toolkit: daily moving averages (DMA), RSI, and volume surge,
plus a combined read. Keeping these dependency-free makes them trivially testable
and fast; the price data is fetched separately (see prices.py).
"""

from __future__ import annotations


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` values."""
    if len(values) < period or period <= 0:
        return None
    window = values[-period:]
    return sum(window) / period


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI over `period`. Returns 0–100, or None if not enough data."""
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    # seed with first `period` changes
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    # smooth over the rest
    for i in range(period + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(ch, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-ch, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def volume_surge(volumes: list[float], lookback: int = 20) -> float | None:
    """Latest volume as a multiple of the average of the prior `lookback` bars."""
    if len(volumes) < lookback + 1:
        return None
    avg = sum(volumes[-lookback - 1:-1]) / lookback
    if avg == 0:
        return None
    return round(volumes[-1] / avg, 2)


def dma_signal(closes: list[float], fast: int = 50, slow: int = 200) -> str:
    """Golden/death cross detection on the fast/slow DMA over the last ~5 bars."""
    if len(closes) < slow + 5:
        return "insufficient_data"
    def cross_at(offset: int) -> int:
        f = sma(closes[: len(closes) - offset], fast)
        s = sma(closes[: len(closes) - offset], slow)
        if f is None or s is None:
            return 0
        return 1 if f > s else -1
    now, prev = cross_at(0), cross_at(5)
    if prev <= 0 and now == 1:
        return "golden_cross"      # fast crossed above slow — bullish
    if prev >= 0 and now == -1:
        return "death_cross"       # fast crossed below slow — bearish
    return "above_slow" if now == 1 else "below_slow"


def analyze(closes: list[float], volumes: list[float]) -> dict:
    """Combined technical read for a positional trader."""
    last = closes[-1] if closes else None
    s50, s200 = sma(closes, 50), sma(closes, 200)
    r = rsi(closes)
    vs = volume_surge(volumes)
    signal = dma_signal(closes)

    momentum = "neutral"
    if r is not None:
        if r >= 70:
            momentum = "overbought"
        elif r <= 30:
            momentum = "oversold"
        elif r >= 55:
            momentum = "bullish"
        elif r <= 45:
            momentum = "bearish"

    return {
        "last_price": last,
        "sma50": round(s50, 2) if s50 else None,
        "sma200": round(s200, 2) if s200 else None,
        "above_50dma": (last is not None and s50 is not None and last > s50),
        "above_200dma": (last is not None and s200 is not None and last > s200),
        "rsi14": r,
        "momentum": momentum,
        "volume_surge_x": vs,
        "volume_alert": (vs is not None and vs >= 2.0),
        "dma_signal": signal,
    }
