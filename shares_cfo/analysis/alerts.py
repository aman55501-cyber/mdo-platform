"""Alert engine — evaluates the consolidated book against thresholds.

Charter rules honoured:
  * every value passes normalise() before it is compared to a threshold, and
  * alerts are classified 🔴 critical / 🟡 important / 🟢 info with a plain
    "what / why / action" message.

Pure function of the /portfolio dict, so it's fully testable and has no I/O.
Thresholds are the agreed standard defaults; override via env (CFO_ALERT_*).
"""

from __future__ import annotations

import os

from ..normalise import normalise


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _thresholds() -> dict:
    return {
        "stock_warn": _f("CFO_ALERT_STOCK_WARN", 0.10),   # 10% of book
        "stock_crit": _f("CFO_ALERT_STOCK_CRIT", 0.15),
        "sector_warn": _f("CFO_ALERT_SECTOR_WARN", 0.30),
        "sector_crit": _f("CFO_ALERT_SECTOR_CRIT", 0.40),
        "stoploss_warn": _f("CFO_ALERT_STOPLOSS_WARN", 0.20),  # down 20% from cost
        "stoploss_crit": _f("CFO_ALERT_STOPLOSS_CRIT", 0.30),
        "drawdown_warn": _f("CFO_ALERT_DRAWDOWN_WARN", 0.10),  # book unrealised -10%
        "drawdown_crit": _f("CFO_ALERT_DRAWDOWN_CRIT", 0.20),
    }


def _alert(sev: str, category: str, what: str, why: str, action: str) -> dict:
    return {"severity": sev, "category": category, "what": what, "why": why, "action": action}


def evaluate(portfolio: dict) -> list[dict]:
    t = _thresholds()
    out: list[dict] = []
    net_worth = normalise("market_value", portfolio.get("net_worth")) or 0.0

    # --- degraded accounts (book incomplete) ---
    degraded = portfolio.get("book_health", {}).get("degraded_accounts", [])
    for d in degraded:
        out.append(_alert("🟡", "book", f"{d.get('creds_key')} not fresh",
                          "part of the book is missing, so totals are understated",
                          "log in that account from the login hub"))

    # --- single-stock concentration ---
    holdings = [h for acc in portfolio.get("accounts", []) for h in acc.get("holdings", [])]
    if net_worth > 0:
        for h in holdings:
            mv = normalise("market_value", h.get("market_value")) or 0.0
            pct = normalise("stock_pct", mv / net_worth) or 0.0
            if pct >= t["stock_crit"]:
                out.append(_alert("🔴", "concentration", f"{h['ticker']} is {pct*100:.0f}% of the book",
                                  "one stock this large is a single point of failure",
                                  "consider trimming to reduce single-name risk"))
            elif pct >= t["stock_warn"]:
                out.append(_alert("🟡", "concentration", f"{h['ticker']} is {pct*100:.0f}% of the book",
                                  "getting concentrated in one name", "watch / consider trimming"))

    # --- sector concentration ---
    for s in portfolio.get("sector_concentration", []):
        pct = normalise("sector_pct", s.get("pct")) or 0.0
        if pct >= t["sector_crit"]:
            out.append(_alert("🔴", "sector", f"{s['sector']} is {pct*100:.0f}% of the book",
                              "heavy sector bet — a sector shock hits hard", "diversify across sectors"))
        elif pct >= t["sector_warn"]:
            out.append(_alert("🟡", "sector", f"{s['sector']} is {pct*100:.0f}% of the book",
                              "sector getting large", "watch sector exposure"))

    # --- per-holding stop-loss (down from cost) ---
    for h in holdings:
        avg = normalise("average_price", h.get("average_price")) or 0.0
        last = normalise("last_price", h.get("last_price")) or 0.0
        if avg > 0 and last > 0:
            drop = (avg - last) / avg
            if drop >= t["stoploss_crit"]:
                out.append(_alert("🔴", "stop-loss", f"{h['ticker']} down {drop*100:.0f}% from cost",
                                  "a large unrealised loss", "review your thesis / stop"))
            elif drop >= t["stoploss_warn"]:
                out.append(_alert("🟡", "stop-loss", f"{h['ticker']} down {drop*100:.0f}% from cost",
                                  "approaching a typical stop level", "review"))

    # --- overall book drawdown (unrealised) ---
    dd = -(normalise("drawdown_pct", portfolio.get("unrealised_pnl_pct")) or 0.0)  # loss as positive
    if dd >= t["drawdown_crit"]:
        out.append(_alert("🔴", "drawdown", f"book unrealised down {dd*100:.0f}%",
                          "meaningful drawdown on the equity book", "review sizing / hedge"))
    elif dd >= t["drawdown_warn"]:
        out.append(_alert("🟡", "drawdown", f"book unrealised down {dd*100:.0f}%",
                          "drawdown building", "watch / consider a hedge (see /exposure)"))

    order = {"🔴": 0, "🟡": 1, "🟢": 2}
    out.sort(key=lambda a: order.get(a["severity"], 3))
    return out
