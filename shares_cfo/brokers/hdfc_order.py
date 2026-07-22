"""HDFC Securities OApi order placement (sync — reached from the guarded engine).

The read endpoints in this package were all confirmed against the live API via a
probe; HDFC's *place-order* path is not yet verified, so this module is written to
be probe-corrected the same way:

  * the endpoint path is HDFC_ORDER_PATH (env) or the best-guess default below,
  * `preview(order)` returns the exact request (method/url/body, secrets omitted)
    WITHOUT sending — use it to verify the shape against HDFC's docs first,
  * `place_order(order)` sends it, and on any non-success surfaces the raw response
    so the path/fields can be corrected — it never claims success it didn't get.

Reached only after guardrails pass and the master switch is on. Never logs secrets.
"""

from __future__ import annotations

import os

import httpx

from ..config import load_account
from .. import token_store

# Best-guess HDFC OApi order path; override with HDFC_ORDER_PATH once the probe/docs
# confirm it. Kept in one place so correcting it is a one-line change.
ORDER_PATH = os.environ.get("HDFC_ORDER_PATH", "/orders/place").strip()

# app product -> HDFC product type (best-guess names; correct from a live reject)
_PRODUCT = {"CNC": "DELIVERY", "MIS": "INTRADAY", "NRML": "CARRYFORWARD", "MARGIN": "MARGIN"}


def _headers(acc, token: str) -> dict:
    from ..config import get_user_agent
    from .hdfc_endpoints import AUTH_STYLE
    h = {"User-Agent": get_user_agent(), "Content-Type": "application/json"}
    if AUTH_STYLE == "header":
        h["access-token"] = token
    else:
        h["Authorization"] = f"Bearer {token}"
    return h


def _tradingsymbol(order) -> str:
    exch = (order.exchange or "NSE").upper()
    if exch == "NSE":
        s = order.symbol.upper()
        return s if s.endswith("-EQ") else f"{s.split('-')[0]}-EQ"
    return order.symbol  # NFO: caller supplies the exact contract tradingsymbol


def _payload(order) -> dict:
    exch = (order.exchange or "NSE").upper()
    return {
        "exchange": exch,
        "trading_symbol": _tradingsymbol(order),
        "security_id": str(order.token or ""),
        "transaction_type": order.side,                 # BUY / SELL
        "quantity": int(order.quantity),
        "order_type": order.order_type,                 # MARKET / LIMIT
        "product_type": _PRODUCT.get(order.product, "DELIVERY"),
        "price": str(order.price) if order.order_type == "LIMIT" else "0",
        "trigger_price": str(order.trigger_price or 0),
        "validity": "DAY",
        "disclosed_quantity": "0",
    }


def preview(order) -> dict:
    """The exact request that WOULD be sent — no secrets, nothing placed."""
    acc = load_account(order.creds_key)
    return {"method": "POST", "url": acc.base_url + ORDER_PATH,
            "auth": "Bearer <token> + api_key (not shown)", "body": _payload(order),
            "note": "Verify against HDFC OApi docs, then set HDFC_ORDER_PATH if the path differs."}


def _extract_orderid(j) -> str | None:
    if not isinstance(j, dict):
        return None
    for k in ("order_id", "orderId", "orderid", "nOrdNo", "orderNumber"):
        if j.get(k):
            return str(j[k])
    d = j.get("data")
    if isinstance(d, dict):
        return _extract_orderid(d)
    return None


def place_order(order) -> dict:
    """Place a guarded order via the HDFC account that owns it. Raises on any failure."""
    key = order.creds_key
    acc = load_account(key)
    token = token_store.get_token(key)
    if not token:
        raise RuntimeError(f"{key} not logged in — no HDFC access token. Re-login first.")
    body = _payload(order)
    try:
        r = httpx.post(acc.base_url + ORDER_PATH, params={"api_key": acc.api_key},
                       headers=_headers(acc, token), json=body, timeout=30.0)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"HDFC order network error: {exc}") from exc
    try:
        j = r.json()
    except ValueError:
        j = {}
    oid = _extract_orderid(j)
    if r.status_code >= 400 or not oid:
        # Nothing confirmed placed — surface the shape so path/fields can be corrected.
        raise RuntimeError(
            f"HDFC order not confirmed [HTTP {r.status_code}] at {ORDER_PATH}: {r.text[:300]}")
    return {"broker": "hdfc", "account": key, "orderid": oid,
            "tradingsymbol": body["trading_symbol"]}
