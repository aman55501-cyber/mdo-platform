"""Angel One (SmartAPI) read-only adapter.

Same interface as HdfcAdapter (get_holdings/get_positions/get_funds/fetch_ltp/close)
so it drops straight into the consolidated book. Angel logs in server-side with a
TOTP secret + MPIN, so no phone 2FA — the adapter arms itself on first use and
caches the JWT in the token store for the day.

Angel requires the calling IP to be a registered STATIC IP (since Apr 2026). On the
VPS that's your server's public IP — register it in the Angel developer console and
set ANGEL_PUBLIC_IP to it.

No order code here. This adapter cannot place a trade.
"""

from __future__ import annotations

import os

import httpx

from ..config import AccountConfig
from ..exceptions import AuthenticationError, BrokerError, TokenExpiredError
from ..normalise import to_float
from .. import token_store
from .hdfc import _digits, _first

LOGIN = "/rest/auth/angelbroking/user/v1/loginByPassword"
HOLDINGS = "/rest/secure/angelbroking/portfolio/v1/getAllHolding"
POSITIONS = "/rest/secure/angelbroking/order/v1/getPosition"
RMS = "/rest/secure/angelbroking/user/v1/getRMS"


_PUBLIC_IP_CACHE: str | None = None
_PUBLIC_IP_NEXT_TRY: float = 0.0  # epoch before which we won't re-attempt a failed IP lookup


def _public_ip() -> str:
    """This host's public IP for Angel's X-ClientPublicIP header.

    Angel's newer security validates this header against the app's whitelisted
    static IP, and rejects secure endpoints (AG8001 "Invalid Token") when it's
    the 127.0.0.1 default. Prefer an explicit ANGEL_PUBLIC_IP; otherwise detect
    it once (cached for the process) so no manual .env edit is needed.
    """
    global _PUBLIC_IP_CACHE, _PUBLIC_IP_NEXT_TRY
    env = os.environ.get("ANGEL_PUBLIC_IP", "").strip()
    if env:
        return env
    if _PUBLIC_IP_CACHE:
        return _PUBLIC_IP_CACHE
    # This is a SYNCHRONOUS fetch on a hot path (_headers runs on every Angel request).
    # If detection fails we used to fall back WITHOUT caching, so every subsequent call
    # re-blocked the loop for up to 2×timeout — a real source of app-wide lag when the
    # outbound proxy can't reach ipify. Now: short timeout, and on failure gate retries
    # to once every few minutes instead of hammering on each request.
    import time
    if time.time() < _PUBLIC_IP_NEXT_TRY:
        return "127.0.0.1"
    for url in ("https://api.ipify.org", "https://checkip.amazonaws.com"):
        try:
            ip = httpx.get(url, timeout=2.0).text.strip()
            if ip and ip.count(".") == 3:
                _PUBLIC_IP_CACHE = ip
                return ip
        except Exception:
            continue
    _PUBLIC_IP_NEXT_TRY = time.time() + 300  # back off 5 min; set ANGEL_PUBLIC_IP to skip entirely
    return "127.0.0.1"


def _headers(account: AccountConfig, jwt: str | None = None) -> dict:
    pub = _public_ip()
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-UserType": "USER",
        "X-SourceID": "WEB",
        "X-ClientLocalIP": os.environ.get("ANGEL_LOCAL_IP", pub),
        "X-ClientPublicIP": pub,
        "X-MACAddress": os.environ.get("ANGEL_MAC", "AA:BB:CC:DD:EE:FF"),
        "X-PrivateKey": account.api_key,
    }
    if jwt:
        h["Authorization"] = f"Bearer {jwt}"
    return h


class AngelAdapter:
    def __init__(self, account: AccountConfig) -> None:
        self._acct = account
        self.last_holdings_excluded = 0  # interface parity with HdfcAdapter
        self._http = httpx.AsyncClient(base_url=account.base_url, timeout=30.0)

    async def _ensure_login(self) -> str:
        jwt = token_store.get_token(self._acct.creds_key)
        if jwt:
            return jwt
        try:
            import pyotp
        except ImportError as exc:  # pragma: no cover
            raise AuthenticationError("pyotp not installed (pip install pyotp).") from exc
        if not (self._acct.totp_secret and self._acct.mpin):
            raise TokenExpiredError(
                self._acct.creds_key,
                f"Angel {self._acct.creds_key} needs MPIN + TOTP_SECRET in .env.",
            )
        totp = pyotp.TOTP(self._acct.totp_secret).now()
        body = {"clientcode": self._acct.client_code, "password": self._acct.mpin, "totp": totp}
        try:
            resp = await self._http.post(LOGIN, headers=_headers(self._acct), json=body)
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Angel login network error: {exc}") from exc
        if resp.status_code >= 400:
            raise AuthenticationError(f"Angel login failed [HTTP {resp.status_code}]: {resp.text[:300]}")
        payload = resp.json()
        data = payload.get("data") or {}
        jwt = data.get("jwtToken") or data.get("jwt_token")
        if not jwt:
            raise AuthenticationError(f"Angel login: no jwtToken. Body: {resp.text[:300]}")
        token_store.set_token(self._acct.creds_key, jwt)
        token_store.set_feed(self._acct.creds_key, data.get("feedToken") or "")  # for the live WS
        return jwt

    async def _get(self, path: str, _retried: bool = False) -> dict:
        jwt = await self._ensure_login()
        try:
            resp = await self._http.get(path, headers=_headers(self._acct, jwt))
        except httpx.HTTPError as exc:
            raise BrokerError(f"Angel GET {path} error: {exc}") from exc
        if resp.status_code == 401:
            token_store.set_token(self._acct.creds_key, "")  # force re-login next time
            raise TokenExpiredError(self._acct.creds_key)
        if resp.status_code >= 400:
            raise BrokerError(f"Angel GET {path} failed [HTTP {resp.status_code}]: {resp.text[:200]}")
        payload = resp.json()
        # Angel returns HTTP 200 for "Invalid Token" (AG8001) when a *cached* JWT has
        # been invalidated (e.g. a newer login elsewhere) — the 401 path never fires.
        # Clear the stale token and re-login *once*, then retry, so the book self-heals
        # instead of looping on a dead JWT forever.
        if (isinstance(payload, dict) and not _retried
                and (payload.get("errorCode") or payload.get("errorcode")) == "AG8001"):
            token_store.set_token(self._acct.creds_key, "")
            return await self._get(path, _retried=True)
        # Angel returns HTTP 200 even for logical failures (e.g. AG8001 "Invalid Token"),
        # with success/status=false and data="". Surface these instead of letting the
        # row parser read the empty data as "0 holdings" — a silent, wrong ₹0.
        if isinstance(payload, dict) and (payload.get("success") is False or payload.get("status") is False):
            msg = payload.get("message") or "request rejected"
            code = payload.get("errorCode") or payload.get("errorcode") or ""
            raise BrokerError(f"Angel {path} rejected: {msg}{f' ({code})' if code else ''}")
        return payload

    @staticmethod
    def _rows(data: dict) -> list[dict]:
        d = data.get("data", data)
        if isinstance(d, dict):
            return d.get("holdings") or d.get("data") or []
        return d if isinstance(d, list) else []

    async def get_holdings(self) -> list[dict]:
        data = await self._get(HOLDINGS)
        out = []
        for h in self._rows(data):
            qty = int(to_float(_first(h, "quantity", "qty")) or 0)
            avg = to_float(_first(h, "averageprice", "avgprice", "average_price")) or 0.0
            last = to_float(_first(h, "ltp", "lastprice", "close")) or 0.0
            prev = to_float(_first(h, "close", "previousclose")) or 0.0
            out.append({
                "ticker": _first(h, "tradingsymbol", "symbolname", "symbol", default=""),
                "exchange": _first(h, "exchange", default="NSE"),
                "quantity": qty,
                "average_price": avg,
                "last_price": last,
                "pnl": to_float(_first(h, "profitandloss", "pnl")) or round(qty * (last - avg), 2),
                "sector": "",  # Angel doesn't return sector; sector map fills it in
                "day_change": round(qty * (last - prev), 2) if prev else 0.0,
                "day_change_pct": to_float(_first(h, "pnlpercentage")) or 0.0,
                "isin": _first(h, "isin", default=""),
                "security_id": str(_first(h, "symboltoken", "token", default="")),
                "token": _digits(_first(h, "symboltoken", "token", default="")),
            })
        return out

    async def get_positions(self) -> list[dict]:
        data = await self._get(POSITIONS)
        rows = data.get("data") or []
        if not isinstance(rows, list):
            rows = []
        out = []
        for p in rows:
            net = int(to_float(_first(p, "netqty", "netQty", "quantity")) or 0)
            if net == 0:
                continue
            avg = to_float(_first(p, "buyavgprice", "netprice", "avgnetprice")) if net > 0 else to_float(_first(p, "sellavgprice", "netprice"))
            out.append({
                "ticker": _first(p, "tradingsymbol", "symbolname", default=""),
                "exchange": _first(p, "exchange", default="NFO"),
                "product_type": _first(p, "producttype", "product", default="NRML"),
                "quantity": net,
                "average_price": to_float(avg) or 0.0,
                "last_price": to_float(_first(p, "ltp", "lastprice")) or 0.0,
                "pnl": to_float(_first(p, "pnl", "realised", "unrealised")) or 0.0,
                "day_pnl": to_float(_first(p, "unrealised", "m2m")) or 0.0,
                "token": _digits(_first(p, "symboltoken", "token", default="")),
            })
        return out

    async def get_funds(self) -> dict:
        data = await self._get(RMS)
        f = data.get("data") or {}
        if not isinstance(f, dict):
            f = {}
        avail = to_float(_first(f, "availablecash", "availableCash", "net")) or 0.0
        return {
            "available": avail,
            "used_margin": to_float(_first(f, "utiliseddebits", "utilisedDebits")) or 0.0,
            "total": to_float(_first(f, "net")) or 0.0,
            "cash": to_float(_first(f, "availablecash", "availableCash")) or 0.0,
            "ledger_balance": to_float(_first(f, "net")) or 0.0,
        }

    async def fetch_ltp(self, instruments: list[dict]) -> dict:
        # Angel holdings/positions already carry ltp; live LTP feed can come later.
        return {}

    async def close(self) -> None:
        await self._http.aclose()
