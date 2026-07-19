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


def _digits(value: Any) -> str:
    """Numeric part of an id, e.g. 'NSEDNL67605' -> '67605' (fetch-ltp token)."""
    return "".join(c for c in str(value or "") if c.isdigit())


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
        self.last_holdings_excluded = 0  # F&O contracts filtered out of holdings
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
        # Real HDFC schema (confirmed by probe): company_name, sector_name, isin,
        # quantity, average_price, close_price, pnl, day_change, day_change_percentage.
        #
        # IMPORTANT: HDFC returns F&O contracts inside /portfolio/holdings, priced at
        # the UNDERLYING spot x lot qty (e.g. "NIFTY Options" = 3510 x 23962 = 8.4Cr).
        # That is NOT an equity holding value and would inflate net worth ~4x. We
        # exclude them here (they are represented under positions). Discriminator:
        # real equity has an ISIN (INE...); F&O contracts have isin "0" and a
        # company_name ending in " Options"/" Futures".
        self.last_holdings_excluded = 0
        data = await self._get(ep.HOLDINGS)
        out = []
        for h in self._rows(data, "holdings", "data", "holding"):
            isin = str(_first(h, "isin", "ISIN", default="")).strip()
            name = str(_first(h, "company_name", "companyName", default="")).strip()
            is_derivative = isin in ("", "0") or name.endswith((" Options", " Futures"))
            if is_derivative:
                self.last_holdings_excluded += 1
                continue
            # Capture any MTF / margin-funding fields HDFC exposes so the MTF view
            # can subtract the loan. Field names vary; we keep whatever looks relevant.
            _mtf_terms = ("mtf", "margin", "fund", "collateral", "loan", "pledge",
                          "emargin", "product", "financed", "leverage")
            raw_mtf = {k: v for k, v in h.items()
                       if isinstance(k, str) and any(t in k.lower() for t in _mtf_terms)}
            iv = _first(h, "investment_value", "investmentValue")  # for the MTF loan estimate
            if iv is not None:
                raw_mtf["investment_value"] = iv
            qty = int(to_float(_first(h, "quantity", "totalQty", "qty", "netQty")) or 0)
            avg = to_float(_first(h, "average_price", "averagePrice", "avgPrice", "buyAvg")) or 0.0
            last = to_float(_first(h, "close_price", "closePrice", "lastPrice", "ltp", "currentPrice", "marketPrice")) or 0.0
            out.append({
                "ticker": _first(h, "company_name", "companyName", "symbol", "tradingsymbol", "tradingSymbol", "scripName", default=""),
                "exchange": _first(h, "exchange", "exch", default="NSE"),
                "quantity": qty,
                "average_price": avg,
                "last_price": last,
                # HDFC's holdings pnl reads 0 pre-market; compute unrealised ourselves.
                "pnl": round(qty * (last - avg), 2),
                "sector": _first(h, "sector_name", "sectorName", "sector", default=""),
                "day_change": to_float(_first(h, "day_change", "dayChange")) or 0.0,
                "day_change_pct": to_float(_first(h, "day_change_percentage", "dayChangePercentage", "day_change_pct")) or 0.0,
                "isin": _first(h, "isin", "ISIN", default=""),
                "security_id": str(_first(h, "security_id", "securityId", "instrument_token", default="")),
                "token": _digits(_first(h, "instrument_token", "security_id", default="")),
                "raw_mtf": raw_mtf,
            })
        return out

    async def get_positions(self) -> list[dict]:
        # HDFC returns positions under data.net[] (and possibly data.day[]).
        data = await self._get(ep.POSITIONS)
        container = data.get("data", data)
        rows: list[dict] = []
        if isinstance(container, dict):
            for key in ("net", "day", "overall", "positions"):
                v = container.get(key)
                if isinstance(v, list):
                    rows.extend(v)
            if not rows and any(k in container for k in ("net_qty", "security_id", "netQty")):
                rows = [container]
        elif isinstance(container, list):
            rows = container

        out = []
        for p in rows:
            net_qty = int(to_float(_first(p, "net_qty", "netQty", "t_day_net_qty", "tdayNetQty")) or 0)
            if net_qty == 0:
                continue  # squared-off / closed position — not an open holding
            # average price on the side the net position sits
            if net_qty > 0:
                avg = _first(p, "average_buy_price", "tdayAverageBuyPrice", "average_sell_price")
            else:
                avg = _first(p, "average_sell_price", "t_day_avg_sell_price", "average_buy_price")
            # build a readable instrument label
            underlying = _first(p, "underlying_symbol", "security_id", default="")
            opt = str(_first(p, "option_type", default="") or "").upper()
            strike = _first(p, "strike_price", default="")
            expiry = _first(p, "expiry_date", default="")
            if opt in ("CE", "PE"):
                label = f"{underlying} {strike}{opt} {expiry}".strip()
            elif expiry:
                label = f"{underlying} FUT {expiry}".strip()
            else:
                label = str(underlying)
            out.append({
                "ticker": label,
                "exchange": _first(p, "exchange", "instrument_segment", "exch", default="NSE"),
                "product_type": _first(p, "product", "productType", default="NRML"),
                "quantity": net_qty,
                "average_price": to_float(avg) or 0.0,
                "last_price": 0.0,  # cumulative-positions has no LTP; needs a quotes call (later)
                "pnl": to_float(_first(p, "realised_pl_overall_position", "realised_pl", "pnl")) or 0.0,
                "day_pnl": to_float(_first(p, "realised_pl_t_day_position", "realised_pl_t_day")) or 0.0,
                "token": _digits(_first(p, "instrument_token", "security_id", default="")),
            })
        return out

    async def fetch_ltp(self, instruments: list[dict]) -> dict:
        """Live last-traded prices via PUT /fetch-ltp.

        instruments: [{"token": "67605", "exchange": "NSE"}, ...]
        returns: {"67605": {"ltp": 216.3, "prev_close": 214.0}, ...}
        Batches requests; failures are swallowed (caller treats missing tokens as
        "no live price"). Never places an order.
        """
        result: dict[str, dict] = {}
        clean = [
            {"exchange": (i.get("exchange") or "NSE"), "token": str(i["token"])}
            for i in instruments if i.get("token")
        ]
        CHUNK = 50
        for start in range(0, len(clean), CHUNK):
            body = {"data": clean[start:start + CHUNK]}
            try:
                resp = await self._http.put(
                    ep.FETCH_LTP,
                    params=self._auth_params(),
                    headers=self._auth_headers(),
                    json=body,
                )
            except httpx.HTTPError:
                continue
            if resp.status_code != 200:
                continue
            try:
                rows = resp.json().get("data", [])
            except ValueError:
                continue
            for row in rows:
                tok = str(row.get("token"))
                result[tok] = {
                    "ltp": to_float(row.get("ltp")) or 0.0,
                    "prev_close": to_float(row.get("prev_close")) or 0.0,
                }
        return result

    async def get_funds(self) -> dict:
        # Real schema: data.equity{ total_available_limit, total_utilised_limit,
        # total_limit, totalAvailableLimitDetails{cash,...}, totalLimitDetails{ledger_balance,...} }
        data = await self._get(ep.FUNDS)
        d = data.get("data", data)
        eq = d.get("equity", d) if isinstance(d, dict) else {}
        if not isinstance(eq, dict):
            eq = {}
        avail_details = eq.get("totalAvailableLimitDetails") or {}
        limit_details = eq.get("totalLimitDetails") or {}
        return {
            "available": to_float(_first(eq, "total_available_limit", "totalAvailableLimit", "available")) or 0.0,
            "used_margin": to_float(_first(eq, "total_utilised_limit", "total_utilized_limit", "totalUtilisedLimit")) or 0.0,
            "total": to_float(_first(eq, "total_limit", "totalLimit")) or 0.0,
            "cash": to_float(_first(avail_details, "cash")) or 0.0,
            "ledger_balance": to_float(_first(limit_details, "ledger_balance", "ledgerBalance")) or 0.0,
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
