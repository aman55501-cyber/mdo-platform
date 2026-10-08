"""Honest long/flat backtester over daily closes (positional).

No look-ahead: each day acts on the PRIOR day's signal, and returns are applied at
the next close. Reports the numbers that actually matter — total vs buy-and-hold,
trade count, win rate, and max drawdown — so a rule is judged on evidence before a
rupee is risked. This is the gate that must pass before any live execution.
"""

from __future__ import annotations

from .technicals import rsi, sma

STRATEGIES = ("dma_cross", "price_above_200dma", "rsi_meanrev")


def _signals(closes: list[float], strategy: str) -> list[int]:
    """Per-day desired position: 1 = long, 0 = flat. Uses only past+current data."""
    n = len(closes)
    sig = [0] * n
    for i in range(n):
        window = closes[: i + 1]
        if strategy == "dma_cross":
            f, s = sma(window, 50), sma(window, 200)
            sig[i] = 1 if (f is not None and s is not None and f > s) else 0
        elif strategy == "price_above_200dma":
            s = sma(window, 200)
            sig[i] = 1 if (s is not None and window[-1] > s) else 0
        elif strategy == "rsi_meanrev":
            r = rsi(window)
            if r is None:
                sig[i] = 0
            elif r < 30:
                sig[i] = 1                       # oversold -> enter
            elif r > 55:
                sig[i] = 0                       # recovered -> exit
            else:
                sig[i] = sig[i - 1] if i > 0 else 0  # hold
        else:
            raise ValueError(f"unknown strategy: {strategy}")
    return sig


def run(closes: list[float], strategy: str = "dma_cross") -> dict:
    if len(closes) < 3:
        return {"error": "not enough data"}
    sig = _signals(closes, strategy)

    equity, peak, maxdd = 1.0, 1.0, 0.0
    trades: list[float] = []
    in_pos, entry = False, 0.0

    for i in range(1, len(closes)):
        pos = sig[i - 1]                          # act on yesterday's signal (no look-ahead)
        ret = closes[i] / closes[i - 1] - 1
        if pos:
            equity *= (1 + ret)
        peak = max(peak, equity)
        maxdd = min(maxdd, equity / peak - 1)
        if pos and not in_pos:
            in_pos, entry = True, closes[i - 1]
        elif not pos and in_pos:
            in_pos = False
            trades.append(closes[i - 1] / entry - 1)
    if in_pos:
        trades.append(closes[-1] / entry - 1)

    total = equity - 1
    buy_hold = closes[-1] / closes[0] - 1
    wins = [t for t in trades if t > 0]
    return {
        "strategy": strategy,
        "bars": len(closes),
        "total_return_pct": round(total * 100, 2),
        "buy_hold_return_pct": round(buy_hold * 100, 2),
        "beats_buy_hold": total > buy_hold,
        "num_trades": len(trades),
        "win_rate_pct": round(100 * len(wins) / len(trades), 1) if trades else None,
        "avg_trade_pct": round(100 * sum(trades) / len(trades), 2) if trades else None,
        "max_drawdown_pct": round(maxdd * 100, 2),
        "time_in_market_pct": round(100 * sum(sig) / len(sig), 1),
    }
