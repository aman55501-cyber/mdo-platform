"""HDFC Securities read-only adapter.

Corrected from the old Vega adapter per the verified HDFC docs:
  * base URL includes /oapi/v1
  * User-Agent header is sent on EVERY call (omitting it fails everything)
  * access token obtained via the request_token -> /access-token flow
  * 401 raises TokenExpiredError with a plain-language "re-login" instruction

This adapter has NO order methods. It cannot place, modify, or cancel a trade.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import AccountConfig, get_user_agent
from ..exceptions import AuthenticationError, BrokerError, RateLimitError, TokenExpiredError
from ..normalise import to_float
from . import hdfc_endpoints as ep


def _first(d: dict, *keys: str, default: Any = None) -> Any:
    """Return the first present key from a dict (handles field-name variants)."""
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _extract_token(payload: dict) -> str | None:
    """Pull the access token out of HDFC's response, whatever shape it uses."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    token = _first(
        data, "access_token", "accessToken", "token", "sessionToken", "jwtToken"
    )
    if not token:
        token = _first(payload, "access_token", "accessToken", "token")
    return str(token) if token else None


class HdfcAdapter:
    """Async, read-only client for one HDFC account."""

    def __init__(self, account: AccountConfig) -> None:
        self._acct = account
        # User-Agent is MANDATORY and Content-Type json is expected by the token API.
        self._http = httpx.AsyncClient(
            base_url=account.base_url,
            timeout=30.0,
            headers={
                "User-Agent": get_user_agent(),
                "Content-Type": "application/json",
            },
        )

    # ---------- auth ----------

    async def exchange_request_token(self, request_token: str) -> str:
        """Swap a browser request_token for an access token (used by hdfc_login.py).

        POST /access-token?api_key=&request_token=  body {"apiSecret": "<secret>"}
        Returns the access token string. Never logs key/secret/token values.
        """
        try:
            resp = await self._http.post(
                ep.ACCESS_TOKEN,
                params={"api_key": self._acct.api_key, "request_token": request_token},
                json={"apiSecret": self._acct.api_secret},
            )
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Token exchange network error: {exc}") from exc

        if resp.status_code >= 400:
            raise AuthenticationError(
                f"Token exchange failed [HTTP {resp.status_code}]: {resp.text[:300]}"
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AuthenticationError(
                f"Token exchange returned non-JSON: {resp.text[:300]}"
            ) from exc

        token = _extract_token(payload)
        if not token:
            # Shape didn't match — surface the JSON so the script can be corrected.
            raise AuthenticationError(
                "Token exchange succeeded but no access token found in the response. "
                f"Raw JSON keys: {list(payload.keys())}. Full body: {resp.text[:500]}"
            )
        return token

    def _auth_headers(self) -> dict[str, str]:
        t = self._acct.access_token
        if ep.AUTH_STYLE == "header":
            return {"access-token": t}
        return {"Authorization": f"Bearer {t}"}

    def _auth_params(self) -> dict[str, str]:
        if ep.AUTH_STYLE == "query":
            return {"access_token": self._acct.access_token, "api_key": self._acct.api_key}
        # api_key is commonly required alongside the token even in header styles
        return {"api_key": self._acct.api_key}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        if not self._acct.access_token:
            raise TokenExpiredError(self._acct.creds_key)

        merged = {**self._auth_params(), **(params or {})}
        try:
            resp = await self._http.get(path, params=merged, headers=self._auth_headers())
        except httpx.HTTPError as exc:
            raise BrokerError(f"GET {path} network error: {exc}") from exc

        if resp.status_code == 401:
            raise TokenExpiredError(self._acct.creds_key)
        if resp.status_code == 429:
            raise RateLimitError("HDFC API rate limit exceeded")
        if resp.status_code >= 400:
            raise BrokerError(f"GET {path} failed [HTTP {resp.status_code}]: {resp.text[:300]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise BrokerError(f"GET {path} returned non-JSON: {resp.text[:200]}") from exc

    # ---------- read-only portfolio ----------

    @staticmethod
    def _rows(data: dict, *keys: str) -> list[dict]:
        raw = _first(data, *keys, default=None)
        if raw is None and isinstance(data.get("data"), dict):
            raw = _first(data["data"], *keys, default=[])
        if isinstance(raw, dict):
            return [raw]
        return raw if isinstance(raw, list) else []

    async def get_holdings(self) -> list[dict]:
        data = await self._get(ep.HOLDINGS)
        out = []
        for h in self._rows(data, "holdings", "data", "holding"):
            out.append({
                "ticker": _first(h, "symbol", "tradingSymbol", "scripName", "nseSymbol", default=""),
                "exchange": _first(h, "exchange", "exch", default="NSE"),
                "quantity": int(to_float(_first(h, "quantity", "totalQty", "qty", "netQty")) or 0),
                "average_price": to_float(_first(h, "averagePrice", "avgPrice", "buyAvg", "costPrice")) or 0.0,
                "last_price": to_float(_first(h, "lastPrice", "ltp", "closePrice", "marketPrice")) or 0.0,
                "pnl": to_float(_first(h, "pnl", "unrealizedPnl", "profitLoss")) or 0.0,
            })
        return out

    async def get_positions(self) -> list[dict]:
        data = await self._get(ep.POSITIONS)
        out = []
        for p in self._rows(data, "positions", "data", "netPositions", "net"):
            out.append({
                "ticker": _first(p, "symbol", "tradingSymbol", "scripName", default=""),
                "exchange": _first(p, "exchange", "exch", default="NSE"),
                "product_type": _first(p, "productType", "product", "prodType", default="NRML"),
                "quantity": int(to_float(_first(p, "quantity", "netQty", "netQuantity", "qty")) or 0),
                "average_price": to_float(_first(p, "averagePrice", "avgPrice", "netAvg")) or 0.0,
                "last_price": to_float(_first(p, "lastPrice", "ltp", "marketPrice")) or 0.0,
                "pnl": to_float(_first(p, "pnl", "realizedPnl", "bookedPnl")) or 0.0,
                "day_pnl": to_float(_first(p, "dayPnl", "unrealizedPnl", "mtm", "m2m")) or 0.0,
            })
        return out

    async def get_funds(self) -> dict:
        data = await self._get(ep.FUNDS)
        f = _first(data, "funds", "data", "limits", default=data)
        if isinstance(f, list) and f:
            f = f[0]
        if not isinstance(f, dict):
            f = {}
        return {
            "available": to_float(_first(f, "availableMargin", "available", "availableCash", "netAvailable", "cashAvailable")) or 0.0,
            "used_margin": to_float(_first(f, "usedMargin", "utilized", "marginUsed", "utilised")) or 0.0,
            "total": to_float(_first(f, "totalBalance", "total", "netBalance", "openingBalance")) or 0.0,
        }

    async def get_profile(self) -> dict:
        data = await self._get(ep.PROFILE)
        p = _first(data, "profile", "data", default=data)
        if isinstance(p, list) and p:
            p = p[0]
        if not isinstance(p, dict):
            p = {}
        return {
            "client_code": _first(p, "clientCode", "clientId", "ucc", "accountId", default=""),
            "name": _first(p, "name", "clientName", "customerName", default=""),
        }

    async def close(self) -> None:
        await self._http.aclose()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
