"""MTF (Margin Trading Facility) view — true net worth after the broker loan.

MTF-funded stock shows at FULL value in holdings, but you owe the broker the funded
amount plus daily interest. So true net worth = gross holdings + cash − MTF loan.
This module detects MTF positions from whatever fields HDFC exposes (captured as
`raw_mtf` on each holding) and reports honestly when the loan field isn't found yet,
rather than silently showing a wrong number.
"""

from __future__ import annotations

import os

from .normalise import to_float

# Field-name fragments that (by convention) carry the funded/loan amount.
LOAN_FIELDS = ("mtf_amount", "mtfamount", "loan_amount", "loanamount", "funded_amount",
               "fundedamount", "margin_funding", "marginfunding", "financed_amount",
               "financedamount", "mtf_value", "mtfvalue", "emargin_amount", "amount_financed")
# Fragments that flag a holding as MTF (product/segment markers).
MTF_FLAGS = ("mtf", "emargin", "margin trading", "e-margin")


def _annual_rate() -> float:
    return to_float(os.environ.get("CFO_MTF_RATE")) or 0.14  # ~14% p.a. typical MTF rate


def analyze(book: dict) -> dict:
    holdings = [h for acc in book.get("accounts", []) for h in acc.get("holdings", [])]
    gross = sum(h.get("market_value") or 0.0 for h in holdings)
    cash = book.get("cash") or 0.0

    loan = 0.0
    funded_value = 0.0
    positions = []
    fields_seen: dict[str, str] = {}

    for h in holdings:
        rm = h.get("raw_mtf") or {}
        for k, v in rm.items():
            fields_seen.setdefault(str(k), str(v)[:40])
        # loan amount from a known field
        hl = 0.0
        for k, v in rm.items():
            if any(f in str(k).lower() for f in LOAN_FIELDS):
                f = to_float(v)
                if f:
                    hl += f
        # MTF flag from a product/segment marker
        blob = " ".join(str(v).lower() for v in rm.values())
        prod = str(rm.get("product") or rm.get("product_type") or "").upper()
        is_mtf = hl > 0 or any(fl in blob for fl in MTF_FLAGS) or "MTF" in prod
        if is_mtf:
            mv = h.get("market_value") or 0.0
            funded_value += mv
            loan += hl
            positions.append({"ticker": h.get("ticker"), "value": round(mv, 2),
                              "loan": round(hl, 2) if hl else None,
                              "product": prod or None})

    rate = _annual_rate()
    daily_interest = loan * rate / 365 if loan else 0.0
    true_net_worth = gross + cash - loan

    # honesty about detection quality
    if loan > 0:
        status, note = "loan_detected", "MTF loan read from the live feed."
    elif positions:
        status = "flagged_no_amount"
        note = ("MTF positions detected, but the loan amount field isn't mapped yet — "
                "run /debug/holdings-fields and I'll map it for an exact figure.")
    elif fields_seen:
        status = "fields_only"
        note = ("Margin-related fields exist but none clearly the MTF loan — "
                "paste /debug/holdings-fields output so I map the right one.")
    else:
        status = "none_found"
        note = ("No MTF/margin fields in the feed. If you use MTF, it may come via a "
                "separate report — run /debug/holdings-fields so I can find it.")

    return {
        "status": status,
        "note": note,
        "annual_rate_pct": round(rate * 100, 2),
        "gross_holdings": round(gross, 2),
        "cash": round(cash, 2),
        "mtf_loan": round(loan, 2),
        "mtf_funded_value": round(funded_value, 2),
        "own_equity_in_mtf": round(funded_value - loan, 2) if funded_value else 0.0,
        "leverage": round(gross / (gross - loan), 2) if (gross - loan) > 0 and loan else 1.0,
        "daily_interest": round(daily_interest, 2),
        "monthly_interest": round(daily_interest * 30, 2),
        "reported_net_worth": round(gross + cash, 2),
        "true_net_worth": round(true_net_worth, 2),
        "mtf_positions": sorted(positions, key=lambda x: -(x["value"] or 0)),
        "fields_seen": fields_seen,
    }
