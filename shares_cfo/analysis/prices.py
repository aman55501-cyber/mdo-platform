"""Price history provider. yfinance now (free), EODHD later (paid, accurate).

Isolated so the analysis math never depends on where prices come from. yfinance
is patchy for Indian small/mid caps — that's why EODHD replaces it later, field
by field, with a confidence flag. For NSE large caps and the watchlist it's fine.
"""

from __future__ import annotations


class PriceDataUnavailable(Exception):
    """Raised when the price provider (or its deps) can't return data."""


def get_ohlcv(symbol: str, exchange: str = "NSE", period: str = "1y") -> dict:
    """Return {'closes': [...], 'volumes': [...], 'source': 'yfinance', 'confidence': ...}.

    `symbol` is a clean NSE symbol (e.g. 'COALINDIA'). yfinance wants a suffix.
    """
    # Prefer EODHD when a key is set (reliable server-side); fall back to yfinance.
    from . import eodhd
    if eodhd.enabled():
        try:
            return eodhd.get_ohlcv(symbol, exchange, period)
        except Exception:
            pass  # fall through to yfinance

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
        raise PriceDataUnavailable(f"yfinance fetch failed for {yf_symbol}: {exc}") from exc

    if df is None or df.empty:
        raise PriceDataUnavailable(
            f"No price data for {yf_symbol} (symbol may differ on Yahoo, or it's a small cap)."
        )

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
