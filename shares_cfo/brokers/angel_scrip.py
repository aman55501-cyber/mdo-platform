"""Angel SmartAPI historical candles for NSE stocks (the per-stock OHLC source).

EODHD serves indices but not NSE stock data on the standard plan, so stock charts
and technicals use Angel's documented getCandleData API instead. Two pieces:
  1. token_for(symbol) — maps 'RELIANCE' -> Angel's instrument token via the public
     scrip master (cached to the state volume).
  2. get_candles(symbol) — pulls daily OHLCV with the Angel account's JWT + headers.
Sync (httpx) so it slots into prices.get_ohlcv alongside EODHD/yfinance.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx

SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
HISTORICAL = "/rest/secure/angelbroking/historical/v1/getCandleData"
_CACHE = Path(__file__).resolve().parent.parent / "data" / "state" / "angel_nse_tokens.json"


def _load_map() -> dict:
    """symbol(name) -> token for NSE equity, cached; fetched once from the scrip master."""
    if _CACHE.exists():
        try:
            return json.loads(_CACHE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    try:
        r = httpx.get(SCRIP_URL, timeout=60.0)
        r.raise_for_status()
        rows = r.json()
    except Exception:
        return {}
    m = {}
    for it in rows:
        if it.get("exch_seg") == "NSE" and str(it.get("symbol", "")).endswith("-EQ"):
            name = str(it.get("name", "")).upper()
            if name and it.get("token"):
                m[name] = str(it["token"])
    if m:
        try:
            _CACHE.parent.mkdir(parents=True, exist_ok=True)
            _CACHE.write_text(json.dumps(m), encoding="utf-8")
        except OSError:
            pass
    return m


def token_for(symbol: str) -> str | None:
    return _load_map().get(symbol.strip().upper())


LOGIN = "/rest/auth/angelbroking/user/v1/loginByPassword"


def _angel_account():
    from ..config import get_accounts, load_account
    key = next((k for k in get_accounts() if k.upper().startswith("ANGEL")), None)
    return load_account(key) if key else None


def _login(acc) -> tuple[str | None, str]:
    """Server-side Angel login (TOTP + MPIN). Returns (jwt, debug_note)."""
    from .. import token_store
    from .angel import _headers
    jwt = token_store.get_token(acc.creds_key)
    if jwt:
        return jwt, "cached jwt"
    if not (acc.totp_secret and acc.mpin):
        return None, "ANGEL1 missing TOTP_SECRET/MPIN — add them in the Login tab"
    try:
        import pyotp
    except ImportError:
        return None, "pyotp not installed"
    try:
        body = {"clientcode": acc.client_code, "password": acc.mpin,
                "totp": pyotp.TOTP(acc.totp_secret).now()}
        r = httpx.post(acc.base_url + LOGIN, headers=_headers(acc), json=body, timeout=30.0)
        data = (r.json() or {}).get("data") or {}
        jwt = data.get("jwtToken") or data.get("jwt_token")
        if jwt:
            token_store.set_token(acc.creds_key, jwt)
            return jwt, "logged in"
        return None, f"login {r.status_code}: {r.text[:120]}"
    except Exception as exc:
        return None, f"login error: {str(exc)[:120]}"


def fetch(symbol: str, days: int = 380, interval: str = "ONE_DAY") -> tuple[dict | None, dict]:
    """Core: (ohlcv | None, debug). Self-logs-in to Angel (server-side)."""
    from .angel import _headers
    dbg = {"symbol": symbol.upper()}
    acc = _angel_account()
    if not acc:
        dbg["stage"] = "no Angel account configured"
        return None, dbg
    tok = token_for(symbol)
    dbg["token"] = tok
    if not tok:
        dbg["stage"] = "symbol not in NSE scrip master"
        return None, dbg
    jwt, note = _login(acc)
    dbg["login"] = note
    if not jwt:
        dbg["stage"] = "login failed"
        return None, dbg
    to = datetime.now()
    frm = to - timedelta(days=days)
    body = {"exchange": "NSE", "symboltoken": tok, "interval": interval,
            "fromdate": frm.strftime("%Y-%m-%d 09:15"), "todate": to.strftime("%Y-%m-%d 15:30")}
    try:
        r = httpx.post(acc.base_url + HISTORICAL, headers=_headers(acc, jwt), json=body, timeout=30.0)
        dbg["candle_status"] = r.status_code
        dbg["candle_snippet"] = r.text[:160]
        rows = (r.json() or {}).get("data") or [] if r.status_code < 400 else []
    except Exception as exc:
        dbg["stage"] = f"candle error: {str(exc)[:120]}"
        return None, dbg
    if not rows:
        dbg["stage"] = "no candle rows"
        return None, dbg
    closes = [float(x[4]) for x in rows]
    return ({"symbol": symbol.upper(), "closes": closes,
             "highs": [float(x[2]) for x in rows], "lows": [float(x[3]) for x in rows],
             "volumes": [float(x[5]) for x in rows], "bars": len(closes),
             "source": "angel", "confidence": "high"}, dbg)


def get_candles(symbol: str, days: int = 380, interval: str = "ONE_DAY") -> dict | None:
    """Daily OHLCV for an NSE stock via Angel, shaped like prices.get_ohlcv, or None."""
    res, _ = fetch(symbol, days, interval)
    return res
