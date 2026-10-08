"""Daily Strategy — a levels-first, stop-loss-disciplined market brief.

Inspired by the levels-based, discipline-first style of Indian market strategists
(objective support/resistance, "trade above X / SL below Y", always keep a stop,
book part at target). It is an ALGORITHMIC strategy, not a person: it never claims
to be anyone's calls. It reads the regime, computes NIFTY & BANKNIFTY pivots from
the prior session, and turns them into a disciplined plan for the day.
"""

from __future__ import annotations

INDICES = [("NIFTY", "^NSEI"), ("BANKNIFTY", "^NSEBANK")]


def build() -> dict:
    from . import levels, market
    from .prices import PriceDataUnavailable, get_ohlcv

    reg = market.regime()
    bias_map = {
        "calm": ("Constructive", "Trend is your friend — buy dips, ride winners, trail stops."),
        "cautious": ("Selective", "Stock-specific. Respect levels, keep size light, book part at targets."),
        "stressed": ("Defensive", "Capital first. Avoid fresh longs into weakness; hedges/defined-risk only."),
        "unknown": ("Neutral", "Data thin — trade only your best levels, tight stops."),
    }
    head, guidance = bias_map.get(reg.get("regime", "unknown"), bias_map["unknown"])

    idx = []
    for name, sym in INDICES:
        try:
            data = get_ohlcv(sym)
            lvl = levels.from_ohlcv(data)
            if not lvl:
                continue
            last = data["closes"][-1]
            plan = levels.plan(last, lvl)
            idx.append({"name": name, "last": round(last, 2), "levels": lvl, "plan": plan})
        except PriceDataUnavailable:
            continue

    discipline = [
        "Every position gets a stop-loss before you enter — no exceptions.",
        "Book part-profit at the first target; trail the rest.",
        "Size down when India VIX is high; don't average a loser.",
        "Miss a trade rather than chase — the level will come again.",
    ]

    return {
        "as_of": reg.get("inputs", {}).get("nifty_last"),
        "regime": reg.get("regime"),
        "regime_emoji": reg.get("emoji"),
        "market_bias": head,
        "guidance": guidance,
        "risk_budget_pct": reg.get("risk_budget_pct"),
        "vix": reg.get("inputs", {}).get("india_vix"),
        "indices": idx,
        "discipline": discipline,
        "note": "Algorithmic levels-based strategy (floor pivots + CPR). Educational, "
                "not investment advice; you decide and place every trade.",
    }
