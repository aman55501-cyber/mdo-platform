"""Global backdrop + market regime — the top-of-funnel context for the idea engine.

Regime is the north star: it classifies the market as calm / cautious / stressed
from India VIX and NIFTY's trend, and hands the idea engine a risk budget (how much
new risk to allow) so sizing shrinks automatically when conditions turn uncertain.
All data is free (yfinance); every number is live-fetched, never hard-coded.
"""

from __future__ import annotations

# raw Yahoo symbols for the global backdrop strip
GLOBAL_TICKERS = [
    ("S&P 500", "^GSPC"),
    ("Nasdaq", "^IXIC"),
    ("Dow", "^DJI"),
    ("Nikkei", "^N225"),
    ("Brent", "BZ=F"),
    ("Gold", "GC=F"),
    ("USD/INR", "INR=X"),
    ("India VIX", "^INDIAVIX"),
]


def _quote(yf_symbol: str) -> dict | None:
    """Last price + day % change for a raw Yahoo symbol, or None if unavailable."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        df = yf.download(yf_symbol, period="5d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        closes = df["Close"].dropna().tolist()
        if not closes:
            return None
        last = float(closes[-1])
        prev = float(closes[-2]) if len(closes) > 1 else last
        chg = (last / prev - 1) * 100 if prev else 0.0
        return {"last": round(last, 2), "change_pct": round(chg, 2)}
    except Exception:
        return None


def global_backdrop() -> dict:
    """Live quotes for the global markets strip."""
    out = []
    for name, sym in GLOBAL_TICKERS:
        q = _quote(sym)
        out.append({"name": name, "symbol": sym,
                    "last": q["last"] if q else None,
                    "change_pct": q["change_pct"] if q else None})
    return {"markets": out}


def regime() -> dict:
    """Classify the market regime and hand back a risk budget for new positions.

    Inputs (all free): India VIX level, NIFTY vs its 200-DMA. Kept deliberately
    simple and transparent — every input is shown so the call can be sanity-checked.
    """
    from .prices import PriceDataUnavailable, get_ohlcv, get_spot
    from .technicals import sma

    vix = None
    try:
        vix = round(get_spot("^INDIAVIX"), 2)
    except PriceDataUnavailable:
        pass

    nifty_last = nifty_200 = nifty_gap = None
    try:
        data = get_ohlcv("NIFTY 50", exchange="NSE")  # falls through if symbol differs
    except Exception:
        data = None
    if not data:
        try:
            last = get_spot("^NSEI")
            df = None
            import yfinance as yf
            df = yf.download("^NSEI", period="1y", progress=False, auto_adjust=True)
            closes = [float(x) for x in df["Close"].dropna().tolist()] if df is not None and not df.empty else []
            nifty_last = round(last, 2)
            s200 = sma(closes, 200)
            if s200:
                nifty_200 = round(s200, 2)
                nifty_gap = round((nifty_last / s200 - 1) * 100, 2)
        except Exception:
            pass

    # classify
    above_200 = (nifty_gap is not None and nifty_gap > 0)
    if vix is None and nifty_gap is None:
        label, cap, emoji = "unknown", 0.5, "❔"
    elif (vix is not None and vix >= 20) or (nifty_gap is not None and nifty_gap < -2):
        label, cap, emoji = "stressed", 0.25, "🔴"
    elif (vix is not None and vix <= 13) and above_200:
        label, cap, emoji = "calm", 1.0, "🟢"
    else:
        label, cap, emoji = "cautious", 0.5, "⚠"

    tilt = {
        "calm": "trend-following, full size; momentum + breakouts favoured",
        "cautious": "quality + defensives, half size, keep hedges handy",
        "stressed": "capital preservation: pause fresh longs, favour hedges/defined-risk",
        "unknown": "data unavailable — treat as cautious",
    }[label]

    return {
        "regime": label, "emoji": emoji,
        "risk_budget_pct": int(cap * 100),
        "inputs": {"india_vix": vix, "nifty_vs_200dma_pct": nifty_gap,
                   "nifty_last": nifty_last, "nifty_200dma": nifty_200,
                   "above_200dma": above_200},
        "tilt": tilt,
        "note": "Regime sets how much NEW risk the idea engine allows. Simple by design "
                "(VIX + trend); breadth and credit spreads come later.",
    }
