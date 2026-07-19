"""EODHD market-data provider — reliable, server-side prices for NSE + indices.

The free Yahoo feed throttles datacenter IPs, so on an always-on VPS it hangs or
returns nothing. EODHD is a paid API with a stable server-side contract and good
NSE coverage. When CFO_EODHD_API_KEY is set, the price layer prefers EODHD and
falls back to yfinance only if a call fails — so nothing breaks if a symbol is
missing, and everything "just works" once the key is present.

Docs: https://eodhd.com/financial-apis/  (EOD + real-time endpoints)
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

BASE = "https://eodhd.com/api"

# Raw index symbols (yfinance-style) -> EODHD symbols. Extend as coverage is verified.
INDEX_MAP = {
    "^NSEI": "NSEI.INDX",        # NIFTY 50
    "^NSEBANK": "NSEBANK.INDX",  # BANK NIFTY
    "^INDIAVIX": "INDIAVIX.INDX",
    "^GSPC": "GSPC.INDX",        # S&P 500
    "^IXIC": "IXIC.INDX",        # Nasdaq Composite
    "^DJI": "DJI.INDX",          # Dow
    "^N225": "N225.INDX",        # Nikkei
    "GC=F": "XAUUSD.FOREX",      # Gold (spot proxy)
    "BZ=F": "BRENT.COMM",        # Brent (best-effort)
    "INR=F": "USDINR.FOREX",
    "INR=X": "USDINR.FOREX",
}


def api_key() -> str:
    return os.environ.get("CFO_EODHD_API_KEY", "").strip()


def enabled() -> bool:
    return bool(api_key())


def _symbol(raw: str, exchange: str = "NSE") -> str:
    """Map a symbol to EODHD's convention. '^NSEI' -> index; 'RELIANCE' -> RELIANCE.NSE."""
    raw = raw.strip()
    if raw in INDEX_MAP:
        return INDEX_MAP[raw]
    if raw.startswith("^"):
        return raw.lstrip("^") + ".INDX"
    if "." in raw:  # already qualified
        return raw
    ex = "NSE" if exchange.upper() == "NSE" else "BSE"
    return f"{raw.upper()}.{ex}"


def _get(path: str, params: dict) -> object:
    import httpx
    params = {**params, "api_token": api_key(), "fmt": "json"}
    r = httpx.get(f"{BASE}/{path}", params=params, timeout=10.0)
    r.raise_for_status()
    return r.json()


def get_ohlcv(symbol: str, exchange: str = "NSE", period: str = "1y") -> dict:
    """Daily closes + volumes from EODHD, same shape as prices.get_ohlcv."""
    days = {"5y": 1900, "2y": 760, "1y": 380}.get(period, 380)
    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    sym = _symbol(symbol, exchange)
    data = _get(f"eod/{sym}", {"period": "d", "order": "a", "from": start})
    if not isinstance(data, list) or not data:
        raise ValueError(f"EODHD returned no EOD data for {sym}")
    closes = [float(x["close"]) for x in data if x.get("close") is not None]
    volumes = [float(x.get("volume") or 0) for x in data]
    return {"symbol": symbol.upper(), "eodhd_symbol": sym, "closes": closes,
            "volumes": volumes, "bars": len(closes), "source": "eodhd",
            "confidence": "high"}


def quote(raw_symbol: str, exchange: str = "NSE") -> dict | None:
    """{'last', 'change_pct'} for the global-markets strip, or None if unavailable."""
    sym = _symbol(raw_symbol, exchange)
    try:
        j = _get(f"real-time/{sym}", {})
    except Exception:
        return None
    if not isinstance(j, dict):
        return None
    last = j.get("close")
    chg = j.get("change_p")
    if last in (None, "NA", "N/A"):
        return None
    try:
        return {"last": round(float(last), 2),
                "change_pct": round(float(chg), 2) if chg not in (None, "NA", "N/A") else None}
    except (TypeError, ValueError):
        return None


def get_spot(raw_symbol: str, exchange: str = "NSE") -> float:
    """Latest price for a symbol or index (e.g. '^NSEI', 'RELIANCE')."""
    sym = _symbol(raw_symbol, exchange)
    j = _get(f"real-time/{sym}", {})
    if isinstance(j, dict):
        for k in ("close", "previousClose"):
            v = j.get(k)
            if v not in (None, "NA", "N/A"):
                return float(v)
    raise ValueError(f"EODHD real-time gave no price for {sym}")
