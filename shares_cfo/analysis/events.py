"""Corporate actions + events for a symbol (free via yfinance).

Recent dividends & splits, and the next earnings date — the calendar items that
move a stock and can distort holdings/DMAs if missed. News headlines too when
available. EODHD's calendar can replace this later for higher reliability.
"""

from __future__ import annotations

from ..normalise import to_float


def get(symbol: str, exchange: str = "NSE") -> dict:
    try:
        import yfinance as yf
    except ImportError:
        return {"symbol": symbol.upper(), "error": "yfinance not installed"}

    yf_symbol = symbol.upper() + (".NS" if exchange == "NSE" else ".BO")
    out: dict = {"symbol": symbol.upper(), "source": "yfinance", "confidence": "low"}
    try:
        t = yf.Ticker(yf_symbol)
    except Exception as exc:
        return {"symbol": symbol.upper(), "error": str(exc)}

    # recent dividends / splits
    try:
        divs = t.dividends
        out["recent_dividends"] = [
            {"date": str(d.date()), "amount": round(float(v), 2)}
            for d, v in list(divs.items())[-3:]
        ] if divs is not None and len(divs) else []
    except Exception:
        out["recent_dividends"] = []
    try:
        splits = t.splits
        out["recent_splits"] = [
            {"date": str(d.date()), "ratio": float(v)}
            for d, v in list(splits.items())[-3:]
        ] if splits is not None and len(splits) else []
    except Exception:
        out["recent_splits"] = []

    # next earnings date
    try:
        cal = t.calendar
        ed = None
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, (list, tuple)) and ed:
                ed = ed[0]
        out["next_earnings_date"] = str(ed) if ed else None
    except Exception:
        out["next_earnings_date"] = None

    # headlines (best-effort)
    try:
        news = getattr(t, "news", []) or []
        out["news"] = [
            {"title": n.get("title"), "publisher": n.get("publisher")}
            for n in news[:5] if n.get("title")
        ]
    except Exception:
        out["news"] = []

    return out
