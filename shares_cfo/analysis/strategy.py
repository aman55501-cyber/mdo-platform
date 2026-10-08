"""Rule that turns technicals into a concrete, risk-defined live bet.

A starter momentum rule (long-only): take a trade only when the trend is up and
it's not overbought, with a fixed stop and a target set for a chosen reward:risk.
Size is derived FROM the risk budget so every bet risks a small, fixed ₹ — this is
the "small bets, R:R shown" discipline. It proposes; it never places.
"""

from __future__ import annotations


def signal(symbol: str, technicals: dict, last_price: float, risk_budget: float,
           stop_pct: float = 0.05, reward_risk: float = 2.0) -> dict:
    """Return a BUY bet with entry/stop/target/size, or action NONE with a reason."""
    t = technicals
    rsi = t.get("rsi14")
    setup_ok = (
        t.get("above_200dma") is True
        and t.get("dma_signal") in ("golden_cross", "above_slow")
        and (rsi is None or rsi < 70)  # don't chase overbought
    )
    if not last_price or last_price <= 0:
        return {"action": "NONE", "reason": "no price"}
    if not setup_ok:
        return {"action": "NONE",
                "reason": "no bullish setup (need price>200-DMA, DMA trend up, RSI<70)",
                "technicals": {"above_200dma": t.get("above_200dma"),
                               "dma_signal": t.get("dma_signal"), "rsi14": rsi}}

    entry = round(last_price, 2)
    stop = round(entry * (1 - stop_pct), 2)
    target = round(entry * (1 + stop_pct * reward_risk), 2)
    per_unit_risk = entry - stop
    qty = int(risk_budget / per_unit_risk) if per_unit_risk > 0 else 0
    return {
        "action": "BUY",
        "symbol": symbol.upper(),
        "entry": entry,
        "stop_loss": stop,
        "target": target,
        "reward_risk": reward_risk,
        "suggested_qty": qty,
        "risk_rupees": round(qty * per_unit_risk, 2),
        "reward_rupees": round(qty * (target - entry), 2),
        "rationale": "price above 200-DMA, DMA trend up, RSI not overbought",
        "note": "Proposal only. Feed to /execution/propose to review + confirm (nothing auto-fires).",
    }
