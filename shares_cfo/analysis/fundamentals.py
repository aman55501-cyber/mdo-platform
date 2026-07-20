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


# Canonical units for scoring (the single convention every threshold assumes):
#   pe, pb, de  -> plain ratios     (de 0.72 means 0.72x)
#   roe, promoter_holding, pledge, dividend_yield -> PERCENT numbers (14.0 == 14%)
# Providers disagree on units, so we normalise AT INGESTION to this one convention.

def _norm_de(v) -> float | None:
    """Debt-to-equity as a ratio. yfinance reports it as a percent (72.5 -> 0.725)."""
    f = to_float(v)
    if f is None:
        return None
    return round(f / 100.0, 3) if f > 5 else round(f, 3)


def _pct_number(v) -> float | None:
    """A percentage as a plain number (14% -> 14.0).

    yfinance reports ratios as fractions (0.14); Screener reports percents (14.0).
    A value with |x| <= 1.5 is assumed a fraction and scaled up; anything larger is
    assumed already a percent. 1.5 is a deliberately low ceiling — no ROE/pledge we
    threshold on lives in the 0–1.5% band, so the two unit worlds never collide.
    """
    f = to_float(v)
    if f is None:
        return None
    return round(f * 100.0, 2) if abs(f) <= 1.5 else round(f, 2)


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
        "roe": _pct_number(info.get("returnOnEquity")),
        "dividend_yield": _pct_number(info.get("dividendYield")),
        "market_cap": to_float(info.get("marketCap")),
        "eps": to_float(info.get("trailingEps")),
    }
    return {"fields": {k: v for k, v in fields.items() if v is not None},
            "source": "yfinance", "confidence": "low"}


def _rows_from_file(path: Path) -> list[dict]:
    """Yield each data row as a dict of {header: value}. Accepts .csv or .xlsx.

    Screener's 'Export to Excel' gives an .xlsx, so we read that natively (via
    pandas) and fall back to csv for plain exports — no manual conversion needed.
    """
    if path.suffix.lower() in (".xlsx", ".xls"):
        try:
            import pandas as pd
        except ImportError:
            return []
        try:
            df = pd.read_excel(path, dtype=str).fillna("")
        except Exception:
            return []
        return df.to_dict(orient="records")
    try:
        with path.open(encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _row_name(row: dict) -> str:
    return (str(row.get("Name") or row.get("Symbol") or row.get("NSE Code") or "")).upper()


def _map_row(row: dict) -> dict:
    """Turn one export row into canonical {field: value} (de as a ratio, rest as-is)."""
    fields = {}
    for canon, headers in COLMAP.items():
        for hdr in headers:
            if hdr in row and row[hdr] not in ("", None):
                val = to_float(row[hdr])
                if val is not None:
                    fields[canon] = _norm_de(val) if canon == "de" else val
                break
    return fields


def _latest_file() -> Path | None:
    if not SCREENER_DIR.exists():
        return None
    files = sorted(p for p in SCREENER_DIR.glob("*")
                   if p.suffix.lower() in (".csv", ".xlsx", ".xls"))
    return files[-1] if files else None


def from_screener(symbol: str, exchange: str = "NSE") -> dict | None:
    """Read the latest Screener Premium export in data/screener/ (.xlsx or .csv)."""
    latest = _latest_file()
    if not latest:
        return None
    for row in _rows_from_file(latest):
        name = _row_name(row)
        if symbol.upper() in name or (name and name in symbol.upper()):
            fields = _map_row(row)
            if fields:
                return {"fields": fields, "source": "screener", "confidence": "high"}
    return None


def load_universe() -> list[dict]:
    """Every company in the latest export as [{symbol, fields}], for a broad scan."""
    latest = _latest_file()
    if not latest:
        return []
    out = []
    for row in _rows_from_file(latest):
        name = _row_name(row)
        if not name:
            continue
        fields = _map_row(row)
        if fields:
            out.append({"symbol": name.split()[0], "name": name, "fields": fields})
    return out


def screener_status() -> dict:
    """What Screener data is currently loaded — for the dashboard/status view.

    Reports the newest file (the one that actually wins), how many companies it
    covers, and which of our canonical fields its headers map to.
    """
    if not SCREENER_DIR.exists():
        return {"loaded": False, "reason": "drop-zone folder missing"}
    files = sorted(p for p in SCREENER_DIR.glob("*")
                   if p.suffix.lower() in (".csv", ".xlsx", ".xls"))
    if not files:
        return {"loaded": False, "reason": "no Screener export dropped yet",
                "drop_zone": str(SCREENER_DIR)}
    latest = files[-1]
    rows = _rows_from_file(latest)
    headers = list(rows[0].keys()) if rows else []
    mapped = {canon: next((h for h in cands if h in headers), None)
              for canon, cands in COLMAP.items()}
    name_col = next((c for c in ("Name", "Symbol", "NSE Code") if c in headers), None)
    return {
        "loaded": True,
        "active_file": latest.name,
        "format": latest.suffix.lower().lstrip("."),
        "companies": len(rows),
        "name_column": name_col,
        "fields_detected": {k: v for k, v in mapped.items() if v},
        "fields_missing": [k for k, v in mapped.items() if not v],
        "other_files": [p.name for p in files[:-1]],
    }


def get(symbol: str, exchange: str = "NSE") -> dict:
    """Merged fundamentals: later providers override earlier, with provenance."""
    merged: dict = {}
    provenance: dict = {}
    # yfinance is blocked/slow from datacenter IPs, so it hangs per holding. Only use
    # it if explicitly enabled; otherwise fundamentals come from the Screener upload.
    import os
    providers = [from_screener]
    if os.environ.get("CFO_ENABLE_YF_FUNDAMENTALS", "").strip().lower() in ("1", "true", "yes"):
        providers = [from_yfinance, from_screener]
    for provider in providers:
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
