"""Price history provider. yfinance now (free), EODHD later (paid, accurate).

Isolated so the analysis math never depends on where prices come from. yfinance
is patchy for Indian small/mid caps — that's why EODHD replaces it later, field
by field, with a confidence flag. For NSE large caps and the watchlist it's fine.
"""

from __future__ import annotations


class PriceDataUnavailable(Exception):
    """Raised when the price provider (or its deps) can't return data."""


# Friendly index display names -> the caret symbols the providers resolve.
_INDEX_ALIASES = {
    "NIFTY": "^NSEI", "NIFTY 50": "^NSEI", "NIFTY50": "^NSEI", "NIFTY-50": "^NSEI",
    "BANKNIFTY": "^NSEBANK", "BANK NIFTY": "^NSEBANK", "NIFTY BANK": "^NSEBANK",
    "INDIA VIX": "^INDIAVIX", "INDIAVIX": "^INDIAVIX", "INDIA_VIX": "^INDIAVIX",
    "SENSEX": "^BSESN", "NIFTY MIDCAP": "^CNXMIDCAP", "NIFTY SMALLCAP": "^CNXSC",
}


def get_ohlcv(symbol: str, exchange: str = "NSE", period: str = "1y") -> dict:
    """Return {'closes': [...], 'volumes': [...], 'source': 'yfinance', 'confidence': ...}.

    `symbol` is a clean NSE symbol (e.g. 'COALINDIA'). yfinance wants a suffix.
    """
    symbol = _INDEX_ALIASES.get(symbol.strip().upper(), symbol)  # 'NIFTY 50' -> '^NSEI'
    # Provider chain: EODHD (great for indices), then Angel (NSE stocks — EODHD
    # doesn't license NSE equity data), then yfinance as a last resort.
    tried: list[str] = []  # why each source was skipped/failed, for an actionable error
    from . import eodhd
    if eodhd.enabled():
        try:
            res = eodhd.get_ohlcv(symbol, exchange, period)
            # EODHD doesn't license NSE equity — it can return an EMPTY series without
            # error. Only accept a non-empty result, else fall through to Angel (which
            # DOES serve NSE stocks). Returning empty here 500s the chart downstream.
            if res and res.get("closes"):
                return res
            tried.append("EODHD returned no closes (NSE equity unlicensed?)")
        except Exception as exc:
            tried.append(f"EODHD failed ({str(exc)[:60]})")
    else:
        tried.append("EODHD off (no CFO_EODHD_API_KEY)")
    if not symbol.startswith("^"):  # stocks: try Angel candles
        try:
            from ..brokers import angel_scrip
            days = {"5y": 1900, "2y": 760, "1y": 380}.get(period, 380)
            res = angel_scrip.get_candles(symbol, days=days)
            if res and res.get("closes"):
                return res
            tried.append("Angel returned no candles (logged in?)")
        except Exception as exc:
            tried.append(f"Angel candles failed ({str(exc)[:60]})")

    try:
        import yfinance as yf  # lazy: keeps the core server runnable without it
    except ImportError as exc:  # pragma: no cover
        raise PriceDataUnavailable(
            "yfinance not installed. On your PC run:  pip install yfinance pandas numpy"
        ) from exc

    # Indices (^NSEI, ^NSEBANK) are used as-is by Yahoo — no exchange suffix.
    if symbol.startswith("^"):
        yf_symbol = symbol
    else:
        suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
        yf_symbol = f"{symbol.upper()}{suffix}"
    try:
        # timeout so a throttled/blocked Yahoo (common from datacenter IPs) fails fast
        # instead of hanging the request; threads=False keeps it predictable.
        df = yf.download(yf_symbol, period=period, progress=False, auto_adjust=True,
                         timeout=8, threads=False)
    except Exception as exc:  # network / symbol errors
        tried.append(f"yfinance failed ({str(exc)[:50]})")
        raise PriceDataUnavailable(
            f"No chart source for {symbol.upper()}. Tried: {'; '.join(tried)}. "
            "On a VPS, Yahoo is often blocked — log in to Angel (NSE stocks) or set "
            "CFO_EODHD_API_KEY (indices) for a reliable feed.") from exc

    if df is None or df.empty:
        tried.append(f"yfinance empty for {yf_symbol}")
        raise PriceDataUnavailable(
            f"No chart source for {symbol.upper()}. Tried: {'; '.join(tried)}. "
            "On a VPS, Yahoo is often blocked/empty — log in to Angel (NSE stocks) or set "
            "CFO_EODHD_API_KEY (indices) for a reliable feed.")

    closes = [float(x) for x in df["Close"].dropna().tolist()]
    volumes = [float(x) for x in df["Volume"].fillna(0).tolist()]
    highs = [float(x) for x in df["High"].fillna(df["Close"]).tolist()]
    lows = [float(x) for x in df["Low"].fillna(df["Close"]).tolist()]
    return {
        "symbol": symbol.upper(),
        "yf_symbol": yf_symbol,
        "closes": closes,
        "volumes": volumes,
        "highs": highs,
        "lows": lows,
        "bars": len(closes),
        "source": "yfinance",
        "confidence": "low",  # free feed; upgrade to EODHD for high-confidence
    }


def get_spot(yf_symbol: str) -> float:
    """Latest price for a raw Yahoo symbol (e.g. '^NSEI' for NIFTY)."""
    from . import eodhd
    if eodhd.enabled():
        try:
            return eodhd.get_spot(yf_symbol)
        except Exception:
            pass  # fall through to yfinance

    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise PriceDataUnavailable("yfinance not installed (pip install yfinance).") from exc
    try:
        df = yf.download(yf_symbol, period="5d", progress=False, auto_adjust=True,
                         timeout=8, threads=False)
    except Exception as exc:
        raise PriceDataUnavailable(f"spot fetch failed for {yf_symbol}: {exc}") from exc
    if df is None or df.empty:
        raise PriceDataUnavailable(f"no spot data for {yf_symbol}")
    return float(df["Close"].dropna().iloc[-1])
