"""Income / 'spread-making' engine — sell option premium against what you own.

Two low-churn ways to pull steady cash ("liquidity") out of a long book:
  • Covered calls — for each F&O-eligible holding you own >=1 lot of, sell an OTM
    call. You keep the premium; you're only obligated to deliver shares you already
    hold if the stock rips past the strike (and even then you sell at a profit).
  • Cash-secured puts — on cash you're happy to deploy, sell an OTM put on a stock
    you'd be glad to own cheaper. You keep the premium; worst case you buy the stock
    at the strike (below today's price), which you wanted anyway.

Premiums are live from the Angel NFO chain when available, else Black-Scholes with
India VIX as the IV proxy, so numbers are always sensible. This module only computes
and proposes — placement goes through the guarded execution path.
"""

from __future__ import annotations

from .options import bs_price, bs_greeks

# How far OTM to target, and the IV multiplier applied to index VIX for single stocks
# (single-stock IV runs richer than the index). Both deliberately conservative.
_CALL_CUSHION = 0.03      # sell the call ~3% above spot -> room for upside + low assignment
_PUT_CUSHION = 0.04       # sell the put ~4% below spot -> buy the dip, not the top
_STOCK_IV_MULT = 1.20


def _india_vix() -> float:
    """India VIX as a fraction (0.14 == 14%). Best-effort; 0.15 fallback."""
    try:
        from .eodhd import get_spot
        v = get_spot("INDIAVIX.INDX")
        if v and v > 3:
            return float(v) / 100.0
    except Exception:
        pass
    return 0.15


def _step(strikes: list[int]) -> int:
    """Smallest gap between adjacent strikes = the strike interval for this stock."""
    gaps = [b - a for a, b in zip(strikes, strikes[1:]) if b > a]
    return min(gaps) if gaps else 0


def _pick_strike(strikes: list[int], target: float, above: bool) -> int | None:
    """Nearest available strike on the required side of `target`."""
    cands = [s for s in strikes if (s >= target if above else s <= target)]
    if not cands:
        return None
    return min(cands) if above else max(cands)


def _premium(spot: float, strike: int, dte: int, iv: float, typ: str,
             tokens: dict, quotes: dict) -> tuple[float, str, int | None]:
    """(premium, source, oi) — live NFO quote if usable, else Black-Scholes."""
    tok = tokens.get(f"{strike}_{typ}")
    q = quotes.get(str(tok)) if tok else None
    oi = q.get("oi") if q else None
    if q and q.get("ltp"):
        return round(q["ltp"], 2), "live", oi
    theo = bs_price(spot, strike, max(dte, 1) / 365.0, iv, typ)
    return round(theo, 2), "theoretical", oi


def _annualise(premium: float, base: float, dte: int) -> float:
    if base <= 0 or dte <= 0:
        return 0.0
    return round(premium / base * (365.0 / dte) * 100.0, 1)


def covered_calls(holdings: list[dict], scrip) -> list[dict]:
    """One covered-call proposal per F&O holding you own at least a lot of."""
    iv0 = _india_vix()
    out = []
    for h in holdings:
        sym = h.get("sym") or h.get("ticker") or ""
        spot = float(h.get("last_price") or 0)
        qty = int(h.get("quantity") or 0)
        if not sym or spot <= 0 or qty <= 0:
            continue
        meta = scrip.fno_meta(sym)
        if not meta or meta["lot"] <= 0:
            continue
        contracts = qty // meta["lot"]
        if contracts < 1:
            continue  # not enough shares for even one contract
        strike = _pick_strike(meta["strikes"], spot * (1 + _CALL_CUSHION), above=True)
        if not strike:
            continue
        iv = min(max(iv0 * _STOCK_IV_MULT, 0.08), 1.5)
        quotes = scrip.option_full([meta["tokens"].get(f"{strike}_CE")])
        prem, src, oi = _premium(spot, strike, meta["dte"], iv, "CE", meta["tokens"], quotes)
        if prem <= 0:
            continue
        shares = contracts * meta["lot"]
        income = round(prem * shares, 0)
        delta = bs_greeks(spot, strike, max(meta["dte"], 1) / 365.0, iv, "CE").get("delta", 0)
        out.append({
            "strategy": "covered_call", "symbol": sym, "holder": h.get("holder", ""),
            "account": h.get("account", ""), "spot": round(spot, 2), "strike": strike,
            "token": meta["tokens"].get(f"{strike}_CE", ""),
            "tradingsymbol": meta["symbols"].get(f"{strike}_CE", ""),
            "expiry": meta["expiry"], "dte": meta["dte"], "lot": meta["lot"],
            "contracts": contracts, "shares_covered": shares,
            "premium": prem, "premium_source": src, "oi": oi,
            "income": income, "yield_pct": round(prem / spot * 100, 2),
            "annualised_pct": _annualise(prem, spot, meta["dte"]),
            "cushion_pct": round((strike - spot) / spot * 100, 1),
            "assignment_prob_pct": round(max(0.0, min(1.0, delta)) * 100, 0),
            "note": f"Keep ₹{income:,.0f}. Only deliver your {shares} shares if {sym} closes "
                    f"above {strike} on {meta['expiry']} — a {round((strike-spot)/spot*100,1)}% gain first.",
        })
    out.sort(key=lambda x: x["income"], reverse=True)
    return out


def cash_secured_puts(candidates: list[dict], cash: float, scrip,
                      max_ideas: int = 6) -> list[dict]:
    """Sell OTM puts on stocks you'd own cheaper, sized to available cash."""
    iv0 = _india_vix()
    budget = max(0.0, float(cash or 0))
    out = []
    for h in candidates:
        sym = h.get("sym") or h.get("ticker") or ""
        spot = float(h.get("last_price") or 0)
        if not sym or spot <= 0:
            continue
        meta = scrip.fno_meta(sym)
        if not meta or meta["lot"] <= 0:
            continue
        strike = _pick_strike(meta["strikes"], spot * (1 - _PUT_CUSHION), above=False)
        if not strike:
            continue
        capital_per = strike * meta["lot"]  # cash to reserve per contract if assigned
        if capital_per <= 0 or capital_per > budget:
            continue
        iv = min(max(iv0 * _STOCK_IV_MULT, 0.08), 1.5)
        quotes = scrip.option_full([meta["tokens"].get(f"{strike}_PE")])
        prem, src, oi = _premium(spot, strike, meta["dte"], iv, "PE", meta["tokens"], quotes)
        if prem <= 0:
            continue
        contracts = int(budget // capital_per)
        if contracts < 1:
            continue
        contracts = min(contracts, 3)  # don't concentrate all cash into one name
        capital = capital_per * contracts
        income = round(prem * meta["lot"] * contracts, 0)
        out.append({
            "strategy": "cash_secured_put", "symbol": sym, "spot": round(spot, 2),
            "strike": strike, "token": meta["tokens"].get(f"{strike}_PE", ""),
            "tradingsymbol": meta["symbols"].get(f"{strike}_PE", ""),
            "expiry": meta["expiry"], "dte": meta["dte"],
            "lot": meta["lot"], "contracts": contracts, "premium": prem,
            "premium_source": src, "oi": oi, "income": income,
            "capital_reserved": capital, "discount_pct": round((spot - strike) / spot * 100, 1),
            "yield_on_cash_pct": round(income / capital * 100, 2) if capital else 0,
            "annualised_pct": _annualise(prem, strike, meta["dte"]),
            "note": f"Keep ₹{income:,.0f}. Worst case you buy {sym} at {strike} "
                    f"({round((spot-strike)/spot*100,1)}% below today) — using ₹{capital:,.0f} cash.",
        })
    out.sort(key=lambda x: x["income"], reverse=True)
    return out[:max_ideas]


def summarise(ccs: list[dict], csps: list[dict]) -> dict:
    """Portfolio-level income roll-up for the header."""
    cc_income = sum(x["income"] for x in ccs)
    csp_income = sum(x["income"] for x in csps)
    total = cc_income + csp_income
    # crude monthly-equivalent (most premium is weekly/near-month)
    return {
        "covered_call_income": round(cc_income, 0),
        "csp_income": round(csp_income, 0),
        "total_premium": round(total, 0),
        "covered_call_count": len(ccs),
        "csp_count": len(csps),
    }
