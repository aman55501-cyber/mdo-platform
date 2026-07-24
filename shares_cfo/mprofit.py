"""MProfit reconciliation — import an MProfit holdings export and diff it against
the live broker book, so the two records of truth are proven to agree.

MProfit is the book of record (all accounts, manually curated); the broker feed is
live. A mismatch means either a trade MProfit hasn't ingested, a corporate action,
or a data error — all worth surfacing. Drop-zone: data/mprofit/ (.xlsx or .csv).
"""

from __future__ import annotations

from pathlib import Path

from .analysis.fundamentals import _rows_from_file
from .normalise import to_float

MPROFIT_DIR = Path(__file__).resolve().parent / "data" / "mprofit"

# canonical field -> candidate MProfit export headers (extend as your export shows)
COLMAP = {
    "name": ["Scrip Name", "Company Name", "Company", "Scrip", "Stock Name", "Name", "Security"],
    "symbol": ["Symbol", "NSE Symbol", "NSE Code", "Ticker", "Scrip Code"],
    "qty": ["Qty", "Quantity", "Units", "Holding Qty", "Closing Qty", "Balance"],
    "avg_cost": ["Avg Cost", "Buy Avg Rate", "Average Rate", "Avg Rate", "Avg Buy Price",
                 "Purchase Price", "Cost Price", "Avg. Cost"],
}


def _series_suffix_strip(sym: str) -> str:
    s = (sym or "").upper().strip()
    for suf in ("-EQ", "-BE", "-BZ", "-BL", "-SM", "-ST", "-IQ"):
        if s.endswith(suf):
            return s[:-len(suf)]
    return s.split("-")[0] if "-" in s else s


def _pick(row: dict, headers: list[str]):
    for h in headers:
        if h in row and row[h] not in ("", None):
            return row[h]
    return None


def _latest_file() -> Path | None:
    if not MPROFIT_DIR.exists():
        return None
    files = sorted((p for p in MPROFIT_DIR.glob("*")
                    if p.suffix.lower() in (".csv", ".xlsx", ".xls")),
                   key=lambda p: p.stat().st_mtime)  # NEWEST, not alphabetical
    return files[-1] if files else None


def load_holdings() -> list[dict]:
    """Every position in the latest MProfit export as [{symbol, name, qty, avg_cost}]."""
    latest = _latest_file()
    if not latest:
        return []
    out = []
    for row in _rows_from_file(latest):
        raw_sym = _pick(row, COLMAP["symbol"])
        name = _pick(row, COLMAP["name"])
        qty = to_float(_pick(row, COLMAP["qty"]))
        avg = to_float(_pick(row, COLMAP["avg_cost"]))
        sym = _series_suffix_strip(str(raw_sym or name or "")).split()[0] if (raw_sym or name) else ""
        if not sym or qty is None:
            continue
        out.append({"symbol": sym, "name": str(name or sym), "qty": qty,
                    "avg_cost": round(avg, 2) if avg is not None else None})
    return out


def status() -> dict:
    latest = _latest_file()
    if not latest:
        return {"loaded": False, "reason": "no MProfit export uploaded yet",
                "drop_zone": str(MPROFIT_DIR)}
    rows = load_holdings()
    return {"loaded": True, "active_file": latest.name,
            "format": latest.suffix.lower().lstrip("."), "positions": len(rows)}


def reconcile(broker_holdings: list[dict], qty_tol: float = 0.0,
              cost_tol_pct: float = 1.0) -> dict:
    """Diff live broker holdings against the latest MProfit export.

    broker_holdings: [{symbol, quantity, average_price}] already aggregated per symbol.
    Returns matches, quantity mismatches, cost mismatches, and one-sided holdings.
    """
    mp = load_holdings()
    if not mp:
        return {"loaded": False,
                "error": "No MProfit export loaded — upload one first.",
                "broker_symbols": len(broker_holdings)}

    mp_by = {r["symbol"]: r for r in mp}
    bk_by: dict[str, dict] = {}
    for h in broker_holdings:
        sym = _series_suffix_strip(h["symbol"])
        slot = bk_by.setdefault(sym, {"symbol": sym, "quantity": 0.0, "average_price": h.get("average_price")})
        slot["quantity"] += h.get("quantity") or 0.0

    matched, qty_diff, cost_diff = [], [], []
    only_broker, only_mprofit = [], []

    for sym, bk in bk_by.items():
        mpr = mp_by.get(sym)
        if not mpr:
            only_broker.append({"symbol": sym, "broker_qty": bk["quantity"]})
            continue
        qd = bk["quantity"] - mpr["qty"]
        entry = {"symbol": sym, "broker_qty": bk["quantity"], "mprofit_qty": mpr["qty"],
                 "qty_diff": round(qd, 2)}
        if abs(qd) > qty_tol:
            qty_diff.append(entry)
        else:
            # quantities agree — now check average cost if both present
            bc, mc = bk.get("average_price"), mpr.get("avg_cost")
            if bc and mc and mc > 0:
                pct = abs(bc - mc) / mc * 100.0
                if pct > cost_tol_pct:
                    cost_diff.append({"symbol": sym, "broker_avg": round(bc, 2),
                                      "mprofit_avg": round(mc, 2), "diff_pct": round(pct, 2)})
                else:
                    matched.append(sym)
            else:
                matched.append(sym)

    for sym, mpr in mp_by.items():
        if sym not in bk_by:
            only_mprofit.append({"symbol": sym, "mprofit_qty": mpr["qty"]})

    total = len(set(bk_by) | set(mp_by))
    clean = len(matched)
    return {
        "loaded": True,
        "in_sync": not (qty_diff or only_broker or only_mprofit),
        "summary": {
            "symbols_total": total, "matched": clean,
            "qty_mismatches": len(qty_diff), "cost_mismatches": len(cost_diff),
            "only_in_broker": len(only_broker), "only_in_mprofit": len(only_mprofit),
        },
        "quantity_mismatches": sorted(qty_diff, key=lambda x: -abs(x["qty_diff"])),
        "cost_mismatches": sorted(cost_diff, key=lambda x: -x["diff_pct"]),
        "only_in_broker": only_broker,
        "only_in_mprofit": only_mprofit,
        "matched_symbols": sorted(matched),
    }
