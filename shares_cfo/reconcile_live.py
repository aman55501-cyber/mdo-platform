"""Live execution & risk reconciliation across every connected broker account.

The console reads holdings/positions live from the brokers, so 'console vs broker'
is the same source and always agrees. The reconciliation that MATTERS for a trading
terminal is integrity between what we *did* and what the broker *has*:

  1. Order integrity — every order we recorded sending (the audit log) is matched
     against the broker's real order book: confirmed, rejected, or unaccounted-for.
  2. Protective-stop integrity — every order that carried a stop-loss actually has
     that stop resting at the broker (a failed SL is a naked bet).
  3. Naked positions — every OPEN position has a protective opposite-side stop
     resting at the broker; the ones that don't are the real risk.

Pure functions here (no I/O) so the matching logic is unit-testable; the server
gathers the live data and calls them.
"""

from __future__ import annotations


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def match_orders(sent_events: list[dict], broker_orders: list[dict]) -> dict:
    """Cross-check recorded SENT orders against the live broker order book.

    sent_events: audit events where event == 'SENT' ({ts, order, result}).
    broker_orders: the unified order-book rows from every account.
    Returns matched / rejected / unaccounted, plus stop-loss integrity issues.
    """
    idx = {str(o.get("orderid")): o for o in broker_orders if o.get("orderid")}
    matched, rejected, unaccounted, sl_issues = [], [], [], []
    for ev in sent_events:
        res = ev.get("result") or {}
        order = ev.get("order") or {}
        oid = str(res.get("orderid") or "")
        base = {
            "ts": ev.get("ts"),
            "symbol": order.get("symbol") or res.get("tradingsymbol"),
            "side": order.get("side"),
            "qty": order.get("quantity"),
            "account": res.get("account") or order.get("creds_key"),
            "orderid": oid or None,
        }
        if not oid:
            unaccounted.append({**base, "why": "recorded SENT but the broker returned no order id"})
        elif oid in idx:
            st = (idx[oid].get("status") or "").lower()
            if "reject" in st:
                rejected.append({**base, "status": st, "reason": idx[oid].get("reason")})
            else:
                matched.append({**base, "status": st or "seen"})
        else:
            unaccounted.append({**base, "why": "order id not in the broker's order book today"})

        # protective stop-loss: was one required, and did it actually land?
        if _f(order.get("stop_loss")) > 0:
            sl_oid = str(res.get("stop_loss_orderid") or "")
            if res.get("stop_loss_error"):
                sl_issues.append({**base, "issue": "stop-loss order FAILED to place",
                                  "detail": str(res.get("stop_loss_error"))[:160]})
            elif not sl_oid:
                sl_issues.append({**base, "issue": "no stop-loss order id was recorded"})
            elif sl_oid not in idx:
                sl_issues.append({**base, "issue": "stop-loss order id not in the broker book",
                                  "sl_orderid": sl_oid})
    return {"matched": matched, "rejected": rejected,
            "unaccounted": unaccounted, "sl_issues": sl_issues}


def _instrument_key(ticker: str) -> str:
    """'VEDL FUT 28-JUL-26' / 'RELIANCE-EQ' -> 'VEDL' / 'RELIANCE' for loose matching."""
    return (ticker or "").upper().split()[0].split("-")[0] if ticker else ""


def _order_matches(o: dict, token, ticker: str) -> bool:
    tok = str(o.get("symboltoken") or "")
    if token and tok and tok == str(token):
        return True  # exact token match — the strong signal
    base = _instrument_key(ticker)
    osym = (o.get("symbol") or "").upper()
    return bool(base and osym and base in osym)


_OPEN = ("open", "trigger", "pending", "modif")


def naked_positions(positions: list[dict], broker_orders: list[dict]) -> list[dict]:
    """Open positions with NO protective opposite-side stop resting at the broker.

    positions: [{creds_key, account, ticker, token, quantity, kind}] (quantity signed).
    A long needs a resting SELL stop; a short needs a resting BUY stop, in the SAME
    account. Matching is by token, falling back to the underlying name.
    """
    protective = [o for o in broker_orders
                  if _f(o.get("trigger")) > 0
                  and any(s in (o.get("status") or "").lower() for s in _OPEN)]
    out = []
    for p in positions:
        qty = p.get("quantity") or 0
        if not qty:
            continue
        need_side = "SELL" if qty > 0 else "BUY"
        ck = p.get("creds_key")
        covered = any(
            (o.get("side") or "").upper() == need_side
            and (o.get("creds_key") == ck if ck and o.get("creds_key") else True)
            and _order_matches(o, p.get("token"), p.get("ticker"))
            for o in protective
        )
        if not covered:
            out.append({
                "account": p.get("account") or p.get("creds_key"),
                "symbol": p.get("ticker"),
                "quantity": qty,
                "side": "long" if qty > 0 else "short",
                "needs": f"{need_side} stop",
                "kind": p.get("kind"),
            })
    return out


def summarize(orders: dict, naked: list[dict], suspect: list[dict],
              order_errors: list[dict]) -> dict:
    """Roll the sections into a headline: is the book clean, and how many flags."""
    flags = (len(orders.get("rejected", [])) + len(orders.get("unaccounted", []))
             + len(orders.get("sl_issues", [])) + len(naked) + len(suspect)
             + len(order_errors))
    return {
        "clean": flags == 0,
        "flags": flags,
        "counts": {
            "orders_matched": len(orders.get("matched", [])),
            "orders_rejected": len(orders.get("rejected", [])),
            "orders_unaccounted": len(orders.get("unaccounted", [])),
            "stop_loss_issues": len(orders.get("sl_issues", [])),
            "naked_positions": len(naked),
            "suspect_cost_basis": len(suspect),
            "account_read_errors": len(order_errors),
        },
    }
