"""Net exposure + hedge sizing (advisory).

Combines equity holdings and F&O into one market-exposure view and sizes an index
hedge. Deliberately simple and transparent: it assumes portfolio beta ~= 1 (moves
with NIFTY) unless a beta is supplied, and it does not yet model option delta
precisely. Every number is framed for YOU to act on — it never places a trade.
"""

from __future__ import annotations

# NIFTY F&O lot size. Exchanges revise this occasionally — keep it current.
NIFTY_LOT = 75


def hedge_with_nifty_futures(
    equity_value: float,
    nifty_spot: float,
    hedge_fraction: float = 0.5,
    beta: float = 1.0,
    lot_size: int = NIFTY_LOT,
) -> dict:
    """How many NIFTY lots to SHORT to hedge `hedge_fraction` of your equity.

    lots = (equity_value * beta * hedge_fraction) / (nifty_spot * lot_size)
    """
    lot_value = nifty_spot * lot_size
    to_hedge = equity_value * beta * hedge_fraction
    lots = round(to_hedge / lot_value) if lot_value else 0
    hedged_value = lots * lot_value
    return {
        "hedge_fraction": hedge_fraction,
        "beta_assumed": beta,
        "nifty_spot": round(nifty_spot, 2),
        "lot_size": lot_size,
        "lot_value": round(lot_value, 2),
        "lots_to_short": lots,
        "hedged_value": round(hedged_value, 2),
        "hedged_pct_of_book": round(100 * hedged_value / equity_value, 1) if equity_value else 0.0,
        "action": (
            f"To hedge ~{int(hedge_fraction*100)}% of your equity, SHORT {lots} NIFTY "
            f"future lot(s) (each ~₹{lot_value:,.0f} notional). You execute this yourself."
        ),
    }


def net_exposure(holdings_value: float, positions: list[dict]) -> dict:
    """Combine equity (all long) with F&O notional to show net long/short tilt.

    F&O notional uses quantity * last_price (signed by quantity). Options are
    counted at premium notional here — a delta-aware view comes later.
    """
    fno_notional = 0.0
    long_fno = short_fno = 0.0
    for p in positions:
        val = (p.get("quantity", 0) or 0) * (p.get("last_price", 0) or 0)
        fno_notional += val
        if val >= 0:
            long_fno += val
        else:
            short_fno += val
    net = holdings_value + fno_notional
    return {
        "equity_long": round(holdings_value, 2),
        "fno_net_notional": round(fno_notional, 2),
        "fno_long_notional": round(long_fno, 2),
        "fno_short_notional": round(short_fno, 2),
        "net_market_exposure": round(net, 2),
        "tilt": "net long" if net >= 0 else "net short",
    }
