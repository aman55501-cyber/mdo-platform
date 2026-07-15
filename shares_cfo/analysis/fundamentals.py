"""Fundamentals with a provider chain + confidence flag.

Chain: yfinance (free, confidence=low) then Screener CSV (confidence=high) —
later providers override earlier field-by-field, with provenance. Every field is
normalised so providers that disagree on units can't fire false alerts (the
classic D/E 1.5 vs 0.72 bug: yfinance reports debt/equity as a percentage).
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..normalise import to_float

SCREENER_DIR = Path(__file__).resolve().parent.parent / "data" / "screener"

# canonical field -> candidate Screener CSV headers (map to your export's columns)
COLMAP = {
    "pe": ["Price to Earning", "P/E", "PE"],
    "pb": ["Price to book value", "P/B"],
    "de": ["Debt to equity", "D/E"],
    "roe": ["Return on equity", "ROE %", "ROE"],
    "promoter_holding": ["Promoter holding %", "Promoter holding", "Promoter"],
    "pledge": ["Pledged percentage", "Promoter pledge", "Pledged"],
    "dividend_yield": ["Dividend yield", "Div Yld %"],
}


def _norm_de(v) -> float | None:
    f = to_float(v)
    if f is None:
        return None
    return round(f / 100.0, 3) if f > 5 else round(f, 3)  # yfinance gives % (72.5 -> 0.725)


def _norm_pct(v) -> float | None:
    f = to_float(v)
    if f is None:
        return None
    return round(f, 4) if abs(f) <= 1.5 else round(f / 100.0, 4)


def from_yfinance(symbol: str, exchange: str = "NSE") -> dict | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        info = yf.Ticker(symbol.upper() + (".NS" if exchange == "NSE" else ".BO")).info or {}
    except Exception:
        return None
    fields = {
        "pe": to_float(info.get("trailingPE")),
        "pb": to_float(info.get("priceToBook")),
        "de": _norm_de(info.get("debtToEquity")),
        "roe": _norm_pct(info.get("returnOnEquity")),
        "dividend_yield": _norm_pct(info.get("dividendYield")),
        "market_cap": to_float(info.get("marketCap")),
        "eps": to_float(info.get("trailingEps")),
    }
    return {"fields": {k: v for k, v in fields.items() if v is not None},
            "source": "yfinance", "confidence": "low"}


def from_screener(symbol: str, exchange: str = "NSE") -> dict | None:
    """Read the latest Screener Premium CSV export in data/screener/ (if present)."""
    if not SCREENER_DIR.exists():
        return None
    files = sorted(SCREENER_DIR.glob("*.csv"))
    for path in reversed(files):
        try:
            with path.open(encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    name = (row.get("Name") or row.get("Symbol") or row.get("NSE Code") or "").upper()
                    if symbol.upper() in name or name in symbol.upper():
                        fields = {}
                        for canon, headers in COLMAP.items():
                            for hdr in headers:
                                if hdr in row and row[hdr] not in ("", None):
                                    val = to_float(row[hdr])
                                    if val is not None:
                                        fields[canon] = _norm_de(val) if canon == "de" else val
                                    break
                        if fields:
                            return {"fields": fields, "source": "screener", "confidence": "high"}
        except OSError:
            continue
    return None


def get(symbol: str, exchange: str = "NSE") -> dict:
    """Merged fundamentals: later providers override earlier, with provenance."""
    merged: dict = {}
    provenance: dict = {}
    for provider in (from_yfinance, from_screener):
        res = provider(symbol, exchange)
        if not res:
            continue
        for k, v in res["fields"].items():
            merged[k] = v
            provenance[k] = res["source"]
    confidence = "high" if any(p == "screener" for p in provenance.values()) else "low"
    return {"symbol": symbol.upper(), "fields": merged, "provenance": provenance,
            "confidence": confidence}


def combine(technicals: dict, fundamentals: dict) -> dict:
    """Fold technicals + fundamentals into a stance, and flag where they disagree."""
    above200 = technicals.get("above_200dma")
    dma = technicals.get("dma_signal")
    if above200 and dma in ("golden_cross", "above_slow"):
        tech = "bullish"
    elif above200 is False:
        tech = "bearish"
    else:
        tech = "neutral"

    f = fundamentals.get("fields", {})
    flags = []
    if f.get("de") is not None and f["de"] > 1.0:
        flags.append(f"high debt (D/E {f['de']})")
    if f.get("pe") is not None and f["pe"] > 40:
        flags.append(f"expensive (P/E {f['pe']:.0f})")
    if f.get("pledge") is not None and f["pledge"] > 20:
        flags.append(f"promoter pledge {f['pledge']}%")
    fund = "caution" if flags else "ok"

    conflict = (tech == "bullish" and fund == "caution") or (tech == "bearish" and fund == "ok")
    return {
        "technical": tech,
        "fundamental": fund,
        "fundamental_flags": flags,
        "conflict": conflict,
        "confidence": fundamentals.get("confidence", "low"),
        "note": "fundamentals & technicals disagree — verify before acting" if conflict else "",
    }
