"""Options payoff engine — multi-leg P&L at expiry, breakevens, and net Greeks.

A Sensibull-style "what if" builder: define legs (buy/sell CE/PE at a strike) and it
returns the payoff curve, max profit/loss, breakevens and net position Greeks. Preset
strategies are priced with Black-Scholes using India VIX as the IV proxy, so you get
realistic numbers without a live option chain; every premium can be overridden with
the real traded price. It computes and shows — it never places anything.
"""

from __future__ import annotations

from math import erf, exp, log, sqrt

R = 0.065  # risk-free rate (India ~6.5%)


def _cdf(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def _pdf(x: float) -> float:
    return exp(-x * x / 2) / sqrt(2 * 3.141592653589793)


def bs_price(S: float, K: float, T: float, sigma: float, typ: str, r: float = R) -> float:
    """Black-Scholes price for a European CE/PE."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, S - K) if typ == "CE" else max(0.0, K - S)
    d1 = (log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    if typ == "CE":
        return S * _cdf(d1) - K * exp(-r * T) * _cdf(d2)
    return K * exp(-r * T) * _cdf(-d2) - S * _cdf(-d1)


def bs_greeks(S: float, K: float, T: float, sigma: float, typ: str, r: float = R) -> dict:
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    d1 = (log(S / K) + (r + sigma * sigma / 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    delta = _cdf(d1) if typ == "CE" else _cdf(d1) - 1
    gamma = _pdf(d1) / (S * sigma * sqrt(T))
    vega = S * _pdf(d1) * sqrt(T) / 100          # per 1% IV
    theta_c = (-S * _pdf(d1) * sigma / (2 * sqrt(T)) - r * K * exp(-r * T) * _cdf(d2))
    theta_p = (-S * _pdf(d1) * sigma / (2 * sqrt(T)) + r * K * exp(-r * T) * _cdf(-d2))
    theta = (theta_c if typ == "CE" else theta_p) / 365   # per day
    return {"delta": round(delta, 3), "gamma": round(gamma, 6),
            "theta": round(theta, 2), "vega": round(vega, 2)}


def _leg_payoff(spot: float, leg: dict) -> float:
    qty = leg["lots"] * leg["lot_size"]
    intrinsic = max(0.0, spot - leg["strike"]) if leg["type"] == "CE" else max(0.0, leg["strike"] - spot)
    if leg["side"] == "BUY":
        return (intrinsic - leg["premium"]) * qty
    return (leg["premium"] - intrinsic) * qty


def analyze(legs: list[dict], spot: float, iv: float | None = None,
            dte: int = 30, lot_size: int = 75) -> dict:
    """Payoff curve + metrics for a set of legs (each: side, type, strike, premium, lots)."""
    for leg in legs:
        leg.setdefault("lots", 1)
        leg.setdefault("lot_size", lot_size)
    lo, hi = spot * 0.85, spot * 1.15
    steps = 61
    curve = []
    for k in range(steps):
        px = lo + (hi - lo) * k / (steps - 1)
        curve.append({"underlying": round(px, 2), "pnl": round(sum(_leg_payoff(px, l) for l in legs), 2)})

    pnls = [p["pnl"] for p in curve]
    max_profit, max_loss = max(pnls), min(pnls)
    # breakevens: sign changes along the curve (linear interpolation)
    bes = []
    for i in range(1, len(curve)):
        a, b = curve[i - 1], curve[i]
        if (a["pnl"] <= 0 <= b["pnl"]) or (a["pnl"] >= 0 >= b["pnl"]):
            if b["pnl"] != a["pnl"]:
                x = a["underlying"] + (0 - a["pnl"]) * (b["underlying"] - a["underlying"]) / (b["pnl"] - a["pnl"])
                bes.append(round(x, 2))
    net_premium = sum((-1 if l["side"] == "BUY" else 1) * l["premium"] * l["lots"] * l["lot_size"] for l in legs)

    greeks = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    if iv and dte:
        T = dte / 365.0
        for l in legs:
            g = bs_greeks(spot, l["strike"], T, iv, l["type"])
            sgn = (1 if l["side"] == "BUY" else -1) * l["lots"] * l["lot_size"]
            for k in greeks:
                greeks[k] = round(greeks[k] + sgn * g[k], 3)

    return {
        "spot": round(spot, 2),
        "legs": legs,
        "net_premium": round(net_premium, 2),
        "max_profit": round(max_profit, 2),
        "max_loss": round(max_loss, 2),
        "max_profit_capped": max_profit == pnls[-1] or max_profit == pnls[0],
        "breakevens": sorted(set(bes)),
        "reward_risk": round(abs(max_profit / max_loss), 2) if max_loss < 0 else None,
        "greeks": greeks,
        "curve": curve,
    }


STRATEGIES = {
    "bull_call_spread": "Bullish, defined risk — buy ATM call, sell OTM call",
    "bear_put_spread": "Bearish, defined risk — buy ATM put, sell OTM put",
    "bull_put_spread": "Mildly bullish credit — sell ATM put, buy OTM put",
    "long_straddle": "Big move either way — buy ATM call + ATM put",
    "long_strangle": "Cheaper big-move bet — buy OTM call + OTM put",
    "iron_condor": "Rangebound income — sell OTM call+put, buy wings",
    "covered_call": "Own stock, sell an OTM call for income",
    "protective_put": "Own stock, buy a put as insurance",
}


def build_strategy(name: str, spot: float, iv: float, dte: int = 30,
                   lot_size: int = 75, step: float = 50.0) -> list[dict]:
    """Preset legs priced with Black-Scholes at the current spot + IV."""
    T = dte / 365.0
    atm = round(spot / step) * step

    def price(K, typ):
        return round(bs_price(spot, K, T, iv, typ), 2)

    def leg(side, typ, K):
        return {"side": side, "type": typ, "strike": K, "premium": price(K, typ),
                "lots": 1, "lot_size": lot_size}

    s = step
    if name == "bull_call_spread":
        return [leg("BUY", "CE", atm), leg("SELL", "CE", atm + 2 * s)]
    if name == "bear_put_spread":
        return [leg("BUY", "PE", atm), leg("SELL", "PE", atm - 2 * s)]
    if name == "bull_put_spread":
        return [leg("SELL", "PE", atm), leg("BUY", "PE", atm - 2 * s)]
    if name == "long_straddle":
        return [leg("BUY", "CE", atm), leg("BUY", "PE", atm)]
    if name == "long_strangle":
        return [leg("BUY", "CE", atm + 2 * s), leg("BUY", "PE", atm - 2 * s)]
    if name == "iron_condor":
        return [leg("SELL", "CE", atm + 2 * s), leg("BUY", "CE", atm + 4 * s),
                leg("SELL", "PE", atm - 2 * s), leg("BUY", "PE", atm - 4 * s)]
    if name == "covered_call":
        return [leg("SELL", "CE", atm + 2 * s)]  # paired with owned stock (shown as note)
    if name == "protective_put":
        return [leg("BUY", "PE", atm - s)]
    raise ValueError(f"unknown strategy '{name}'")
