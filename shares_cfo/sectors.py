"""Symbol -> sector map + consolidated concentration.

Charter warning honoured: *without* a working sector map, sector-concentration
alerts are silently dead. So an unmapped symbol resolves to "UNKNOWN" AND is
recorded in `missing()` — the gap is visible, never silent.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .normalise import normalise

log = logging.getLogger("shares_cfo.sectors")

_DATA = Path(__file__).resolve().parent / "data" / "sectors.json"

# Aman's real 15-stock business-context watchlist (from MDO_VISION §7).
DEFAULT_WATCHLIST = [
    "COALINDIA", "NTPC", "JSPL", "SAIL", "NALCO", "VEDL",
    "ADANIPOWER", "JSWENERGY", "HAL", "TATAMOTORS", "MSTC",
    "IRCON", "RITES", "RELIANCE", "HDFCBANK",
]


class SectorMap:
    def __init__(self, path: Path | None = None) -> None:
        raw = json.loads((path or _DATA).read_text(encoding="utf-8"))
        self._map = {k.upper(): v for k, v in raw.items() if not k.startswith("_")}
        self._missing: set[str] = set()

    def sector_of(self, ticker: str) -> str:
        key = (ticker or "").upper().strip()
        # Brokers append NSE series suffixes ("TATASTEEL-EQ", "SARVESHWAR-BE");
        # the map stores base symbols. Without this strip, every suffixed ticker
        # resolved UNKNOWN and sector-concentration alerts ran on noise.
        key = re.sub(r"-(EQ|BE|BZ|BL|SM|ST|IQ)$", "", key)
        sector = self._map.get(key)
        if sector is None:
            self._missing.add(key)
            log.warning("sector_unmapped ticker=%s -> UNKNOWN (add to sectors.json)", key)
            return "UNKNOWN"
        return sector

    def missing(self) -> list[str]:
        """Tickers seen that have no sector — surface these so the map stays honest."""
        return sorted(self._missing)

    def concentration(self, holdings: list) -> list[dict]:
        """Return sector weights as a fraction of total holdings value.

        Every value passes normalise() before it could be compared to a threshold.
        """
        by_sector: dict[str, float] = {}
        total = 0.0
        for h in holdings:
            mv = normalise("market_value", getattr(h, "market_value", 0.0)) or 0.0
            sector = getattr(h, "sector", None)
            if not sector or sector == "UNKNOWN":
                sector = self.sector_of(getattr(h, "ticker", ""))
            by_sector[sector] = by_sector.get(sector, 0.0) + mv
            total += mv

        rows = []
        for sector, value in sorted(by_sector.items(), key=lambda kv: kv[1], reverse=True):
            pct = normalise("sector_pct", (value / total) if total else 0.0) or 0.0
            rows.append({
                "sector": sector,
                "value": round(value, 2),
                "pct": round(pct, 4),
            })
        return rows
