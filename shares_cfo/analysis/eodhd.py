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

# Raw index symbols (yfinance-style) -> ordered EODHD candidates. The first that
# returns data wins (self-healing across EODHD's naming variants for indices).
INDEX_CANDIDATES = {
    "^NSEI": ["NSEI.INDX", "NIFTY50.INDX", "N50.INDX", "CNXN.INDX"],
    "^NSEBANK": ["NSEBANK.INDX", "BANKNIFTY.INDX", "NIFTYBANK.INDX", "CNXBANK.INDX"],
    "^INDIAVIX": ["INDIAVIX.INDX", "NIFVIX.INDX", "INDIA_VIX.INDX", "VIX.INDX"],
    "^BSESN": ["BSESN.INDX", "SENSEX.INDX", "GSPC.BSE"],
    "^CNXMIDCAP": ["CNXMIDCAP.INDX", "NIFTYMIDCAP150.INDX", "NIFMDCP50.INDX"],
    "^CNXSC": ["CNXSC.INDX", "NIFTYSMLCAP250.INDX", "NIFSMCP50.INDX"],
    "^GSPC": ["GSPC.INDX"],
    "^IXIC": ["IXIC.INDX"],
    "^DJI": ["DJI.INDX"],
    "^N225": ["N225.INDX"],
    "GC=F": ["XAUUSD.FOREX", "GOLD.COMM"],
    "BZ=F": ["BRENT.COMM", "BRN.COMM"],
    "INR=F": ["USDINR.FOREX"],
    "INR=X": ["USDINR.FOREX", "INR.FOREX"],
}
# back-compat: primary symbol for each raw index
INDEX_MAP = {k: v[0] for k, v in INDEX_CANDIDATES.items()}


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
    r = httpx.get(f"{BASE}/{path}", params=params, timeout=6.0)  # fail fast; strip degrades
    r.raise_for_status()
    return r.json()


def _candidates(raw: str, exchange: str = "NSE") -> list[str]:
    """Ordered EODHD symbols to try (indices have several naming variants)."""
    if raw in INDEX_CANDIDATES:
        return INDEX_CANDIDATES[raw]
    return [_symbol(raw, exchange)]


def get_ohlcv(symbol: str, exchange: str = "NSE", period: str = "1y") -> dict:
    """Daily closes + volumes from EODHD, same shape as prices.get_ohlcv."""
    days = {"5y": 1900, "2y": 760, "1y": 380}.get(period, 380)
    start = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    data, sym = None, None
    for cand in _candidates(symbol, exchange):
        try:
            d = _get(f"eod/{cand}", {"period": "d", "order": "a", "from": start})
        except Exception:
            continue
        if isinstance(d, list) and d:
            data, sym = d, cand
            break
    if not data:
        raise ValueError(f"EODHD returned no EOD data for {symbol}")
    rows = [x for x in data if x.get("close") is not None]
    closes = [float(x["close"]) for x in rows]
    volumes = [float(x.get("volume") or 0) for x in rows]
    highs = [float(x.get("high") or x["close"]) for x in rows]
    lows = [float(x.get("low") or x["close"]) for x in rows]
    return {"symbol": symbol.upper(), "eodhd_symbol": sym, "closes": closes,
            "volumes": volumes, "highs": highs, "lows": lows,
            "bars": len(closes), "source": "eodhd", "confidence": "high"}


def quote(raw_symbol: str, exchange: str = "NSE") -> dict | None:
    """{'last', 'change_pct'} for the global-markets strip, or None if unavailable."""
    for sym in _candidates(raw_symbol, exchange):
        try:
            j = _get(f"real-time/{sym}", {})
        except Exception:
            continue
        if not isinstance(j, dict):
            continue
        last, chg = j.get("close"), j.get("change_p")
        if last in (None, "NA", "N/A"):
            continue
        try:
            return {"last": round(float(last), 2),
                    "change_pct": round(float(chg), 2) if chg not in (None, "NA", "N/A") else None}
        except (TypeError, ValueError):
            continue
    return None


def get_spot(raw_symbol: str, exchange: str = "NSE") -> float:
    """Latest price for a symbol or index. Tries real-time, then the EOD close
    (NSE stocks aren't on EODHD real-time but are on EOD)."""
    for sym in _candidates(raw_symbol, exchange):
        try:
            j = _get(f"real-time/{sym}", {})
        except Exception:
            continue
        if isinstance(j, dict):
            for k in ("close", "previousClose"):
                v = j.get(k)
                if v not in (None, "NA", "N/A"):
                    return float(v)
    # fall back to the latest end-of-day close
    try:
        d = get_ohlcv(raw_symbol, exchange, period="1y")
        if d["closes"]:
            return float(d["closes"][-1])
    except Exception:
        pass
    raise ValueError(f"EODHD gave no price for {raw_symbol}")


def feed_check() -> dict:
    """Probe key symbols so the feed can be verified from the app (no key printed)."""
    tests = [("NIFTY", "^NSEI"), ("BANKNIFTY", "^NSEBANK"), ("INDIA VIX", "^INDIAVIX"),
             ("RELIANCE", "RELIANCE"), ("S&P 500", "^GSPC")]
    results = []
    for label, raw in tests:
        entry = {"label": label, "resolved": None, "price": None, "via": None}
        for sym in _candidates(raw):
            try:
                j = _get(f"real-time/{sym}", {})
                px = j.get("close") if isinstance(j, dict) else None
                if px not in (None, "NA", "N/A"):
                    entry.update(resolved=sym, price=round(float(px), 2), via="real-time")
                    break
            except Exception as exc:
                entry["error"] = str(exc)[:80]
        if entry["resolved"] is None:  # NSE stocks: fall back to end-of-day
            try:
                d = get_ohlcv(raw)
                if d.get("closes"):
                    entry.update(resolved=d.get("eodhd_symbol"),
                                 price=round(d["closes"][-1], 2), via="eod", error=None)
            except Exception as exc:
                entry.setdefault("error", str(exc)[:80])
        results.append(entry)
    return {"enabled": enabled(), "results": results}
