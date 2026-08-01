"""Field normalisation.

Charter rule: *any* data field must pass `normalise()` before it is compared to a
threshold. This is the single choke-point that prevents unit-mismatch false
alerts (the class of bug where a provider reports D/E as 1.5x while another
reports 0.72x, or a percentage arrives as 0.72 in one feed and 72 in another).

Every normaliser returns a value in a documented canonical unit, or None when the
input is genuinely missing/unparseable (never a silent 0, which would look like a
real value to a threshold check).
"""

from __future__ import annotations

from typing import Any

# Fields whose canonical unit is a *fraction of 1.0* (e.g. 0.72 == 72%).
# Providers disagree: some send 72 ("percent"), some send 0.72 ("fraction").
_PERCENT_FIELDS = {
    "promoter_holding_pct",
    "pledge_pct",
    "sector_pct",
    "stock_pct",
    "drawdown_pct",
    "change_pct",
}

# Fields that are plain non-negative money amounts in rupees.
_MONEY_FIELDS = {
    "available",
    "used_margin",
    "total",
    "market_value",
    "last_price",
    "average_price",
    "pnl",
    "day_pnl",
}


def to_float(value: Any) -> float | None:
    """Coerce a possibly-string, possibly-formatted number to float, else None."""
    if value is None:
        return None
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "").replace("₹", "").replace("%", "")
        if s in ("", "-", "NA", "N/A", "nan", "None", "null"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def normalise_percent(value: Any) -> float | None:
    """Return a fraction of 1.0.

    Heuristic: a value > 1.5 is assumed to already be in percent (e.g. 72 -> 0.72).
    Values in [0, 1.5] are treated as already-fractions. 1.5 (=150%) is a
    deliberately generous ceiling so ratios like promoter holding never straddle it.
    """
    f = to_float(value)
    if f is None:
        return None
    return f / 100.0 if f > 1.5 else f


def normalise(field: str, value: Any) -> float | None:
    """Dispatch a field to its canonical unit. Unknown fields fall back to float."""
    if field in _PERCENT_FIELDS:
        return normalise_percent(value)
    # Money and everything else: a plain float in native units (rupees).
    return to_float(value)
