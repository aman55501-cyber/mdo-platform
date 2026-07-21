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


# --- Option chain (NFO index options: NIFTY / BANKNIFTY) ----------------------
_OPT_CACHE = Path(__file__).resolve().parent.parent / "data" / "state" / "angel_nfo_options.json"
QUOTE = "/rest/secure/angelbroking/market/v1/quote/"


def _load_options() -> dict:
    """{underlying: {expiry: {strike: {'CE': token, 'PE': token, 'lot': n}}}}, cached daily."""
    today = datetime.now().strftime("%Y-%m-%d")
    if _OPT_CACHE.exists():
        try:
            c = json.loads(_OPT_CACHE.read_text(encoding="utf-8"))
            if c.get("date") == today:
                return c.get("idx", {})
        except (OSError, ValueError):
            pass
    try:
        rows = httpx.get(SCRIP_URL, timeout=60.0).json()
    except Exception:
        return {}
    idx: dict = {}
    for it in rows:
        if it.get("exch_seg") != "NFO" or it.get("instrumenttype") != "OPTIDX":
            continue
        name = str(it.get("name", "")).upper()
        if name not in ("NIFTY", "BANKNIFTY"):
            continue
        sym = str(it.get("symbol", ""))
        typ = "CE" if sym.endswith("CE") else "PE" if sym.endswith("PE") else None
        if not typ:
            continue
        try:
            strike = str(int(float(it["strike"]) / 100))
        except (KeyError, ValueError):
            continue
        exp = str(it.get("expiry", ""))
        idx.setdefault(name, {}).setdefault(exp, {}).setdefault(strike, {})[typ] = str(it["token"])
        idx[name][exp][strike]["lot"] = int(float(it.get("lotsize", 0) or 0))
    if idx:
        try:
            _OPT_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _OPT_CACHE.write_text(json.dumps({"date": today, "idx": idx}), encoding="utf-8")
        except OSError:
            pass
    return idx


def nearest_expiry(underlying: str) -> str | None:
    idx = _load_options().get(underlying.upper(), {})
    today = datetime.now().date()
    fut = []
    for exp in idx:
        try:
            d = datetime.strptime(exp, "%d%b%Y").date()
            if d >= today:
                fut.append((d, exp))
        except ValueError:
            continue
    return min(fut)[1] if fut else None


def option_ltps(underlying: str, expiry: str, strikes: list[int]) -> dict:
    """{(strike, 'CE'|'PE'): ltp} for the given strikes/expiry via Angel's quote API."""
    from ..config import get_accounts, load_account
    from .angel import _headers
    idx = _load_options().get(underlying.upper(), {}).get(expiry, {})
    tok_map = {}  # token -> (strike, type)
    for s in strikes:
        node = idx.get(str(s), {})
        for typ in ("CE", "PE"):
            if node.get(typ):
                tok_map[str(node[typ])] = (s, typ)
    if not tok_map:
        return {}
    key = next((k for k in get_accounts() if k.upper().startswith("ANGEL")), None)
    if not key:
        return {}
    acc = load_account(key)
    jwt, _ = _login(acc)
    if not jwt:
        return {}
    body = {"mode": "LTP", "exchangeTokens": {"NFO": list(tok_map.keys())}}
    try:
        r = httpx.post(acc.base_url + QUOTE, headers=_headers(acc, jwt), json=body, timeout=20.0)
        fetched = ((r.json() or {}).get("data") or {}).get("fetched") or []
    except Exception:
        return {}
    out = {}
    for f in fetched:
        t = str(f.get("symbolToken") or f.get("symboltoken") or "")
        if t in tok_map and f.get("ltp") not in (None, "NA"):
            out[tok_map[t]] = float(f["ltp"])
    return out


# --- Stock (single-stock) F&O options: OPTSTK -------------------------------
# For covered calls on holdings + cash-secured puts. Indexed like the index chain
# but only future expiries are kept, so the cache stays small.
_STK_CACHE = Path(__file__).resolve().parent.parent / "data" / "state" / "angel_nfo_stkopts.json"


def _load_stock_options() -> dict:
    """{underlying: {expiry: {strike: {'CE':tok,'PE':tok,'lot':n}}}} for OPTSTK, cached daily."""
    today = datetime.now().strftime("%Y-%m-%d")
    if _STK_CACHE.exists():
        try:
            c = json.loads(_STK_CACHE.read_text(encoding="utf-8"))
            if c.get("date") == today:
                return c.get("stk", {})
        except (OSError, ValueError):
            pass
    try:
        rows = httpx.get(SCRIP_URL, timeout=60.0).json()
    except Exception:
        return {}
    tdate = datetime.now().date()
    stk: dict = {}
    for it in rows:
        if it.get("exch_seg") != "NFO" or it.get("instrumenttype") != "OPTSTK":
            continue
        exp = str(it.get("expiry", ""))
        try:  # keep only future expiries to bound cache size
            if datetime.strptime(exp, "%d%b%Y").date() < tdate:
                continue
        except ValueError:
            continue
        sym = str(it.get("symbol", ""))
        typ = "CE" if sym.endswith("CE") else "PE" if sym.endswith("PE") else None
        if not typ:
            continue
        name = str(it.get("name", "")).upper()
        try:
            strike = str(int(float(it["strike"]) / 100))
        except (KeyError, ValueError):
            continue
        node = stk.setdefault(name, {}).setdefault(exp, {}).setdefault(strike, {})
        node[typ] = str(it["token"])
        node[typ + "sym"] = sym  # the NFO tradingsymbol, needed to place the order
        node["lot"] = int(float(it.get("lotsize", 0) or 0))
    if stk:
        try:
            _STK_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _STK_CACHE.write_text(json.dumps({"date": today, "stk": stk}), encoding="utf-8")
        except OSError:
            pass
    return stk


def _nearest_future_expiry(chain: dict) -> str | None:
    today = datetime.now().date()
    fut = []
    for exp in chain:
        try:
            d = datetime.strptime(exp, "%d%b%Y").date()
            if d >= today:
                fut.append((d, exp))
        except ValueError:
            continue
    return min(fut)[1] if fut else None


def fno_meta(symbol: str) -> dict | None:
    """Nearest-expiry F&O metadata for a stock, or None if it isn't F&O-eligible.

    {lot, expiry, dte, strikes:[int], tokens:{"<strike>_CE":tok, "<strike>_PE":tok}}
    """
    chain = _load_stock_options().get(symbol.strip().upper())
    if not chain:
        return None
    exp = _nearest_future_expiry(chain)
    if not exp:
        return None
    node = chain[exp]
    try:
        dte = max(0, (datetime.strptime(exp, "%d%b%Y").date() - datetime.now().date()).days)
    except ValueError:
        dte = 30
    lot = 0
    strikes, tokens, symbols = [], {}, {}
    for sk, v in node.items():
        try:
            ski = int(sk)
        except ValueError:
            continue
        strikes.append(ski)
        for typ in ("CE", "PE"):
            if v.get(typ):
                tokens[f"{ski}_{typ}"] = v[typ]
                symbols[f"{ski}_{typ}"] = v.get(typ + "sym", "")
        lot = lot or int(v.get("lot") or 0)
    if not strikes:
        return None
    return {"lot": lot, "expiry": exp, "dte": dte, "strikes": sorted(strikes),
            "tokens": tokens, "symbols": symbols}


_FUT_CACHE = Path(__file__).resolve().parent.parent / "data" / "state" / "angel_nfo_fut.json"


def _load_futures() -> dict:
    """{underlying: {'token':..,'expiry':..,'lot':..}} for the NEAREST FUTSTK, cached daily."""
    today = datetime.now().strftime("%Y-%m-%d")
    if _FUT_CACHE.exists():
        try:
            c = json.loads(_FUT_CACHE.read_text(encoding="utf-8"))
            if c.get("date") == today:
                return c.get("fut", {})
        except (OSError, ValueError):
            pass
    try:
        rows = httpx.get(SCRIP_URL, timeout=60.0).json()
    except Exception:
        return {}
    tdate = datetime.now().date()
    best: dict = {}
    for it in rows:
        if it.get("exch_seg") != "NFO" or it.get("instrumenttype") != "FUTSTK":
            continue
        exp = str(it.get("expiry", ""))
        try:
            d = datetime.strptime(exp, "%d%b%Y").date()
        except ValueError:
            continue
        if d < tdate:
            continue
        name = str(it.get("name", "")).upper()
        cur = best.get(name)
        if not cur or d < cur["_d"]:
            best[name] = {"token": str(it.get("token")), "expiry": exp,
                          "lot": int(float(it.get("lotsize", 0) or 0)), "_d": d}
    fut = {k: {"token": v["token"], "expiry": v["expiry"], "lot": v["lot"]} for k, v in best.items()}
    if fut:
        try:
            _FUT_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _FUT_CACHE.write_text(json.dumps({"date": today, "fut": fut}), encoding="utf-8")
        except OSError:
            pass
    return fut


def fut_token(symbol: str) -> str | None:
    f = _load_futures().get(symbol.strip().upper())
    return f["token"] if f else None


def option_full(tokens: list[str]) -> dict:
    """{token: {'ltp':float,'oi':int}} via Angel FULL quote (LTP + open interest)."""
    from ..config import get_accounts, load_account
    from .angel import _headers
    tokens = [str(t) for t in tokens if t]
    if not tokens:
        return {}
    key = next((k for k in get_accounts() if k.upper().startswith("ANGEL")), None)
    if not key:
        return {}
    acc = load_account(key)
    jwt, _ = _login(acc)
    if not jwt:
        return {}
    out: dict = {}
    # FULL quote caps at ~50 tokens/call; chunk to be safe.
    for i in range(0, len(tokens), 45):
        chunk = tokens[i:i + 45]
        body = {"mode": "FULL", "exchangeTokens": {"NFO": chunk}}
        try:
            r = httpx.post(acc.base_url + QUOTE, headers=_headers(acc, jwt), json=body, timeout=20.0)
            fetched = ((r.json() or {}).get("data") or {}).get("fetched") or []
        except Exception:
            continue
        for f in fetched:
            t = str(f.get("symbolToken") or f.get("symboltoken") or "")
            if not t:
                continue
            ltp = f.get("ltp")
            oi = f.get("opnInterest") or f.get("openInterest") or f.get("oi")
            vol = f.get("tradeVolume") or f.get("volume") or f.get("totBuyQuan")
            netchg = f.get("netChange") or f.get("changePercentage") or f.get("percentChange")
            out[t] = {"ltp": float(ltp) if ltp not in (None, "NA", "") else None,
                      "oi": int(float(oi)) if oi not in (None, "NA", "") else None,
                      "volume": int(float(vol)) if vol not in (None, "NA", "") else None,
                      "change_pct": float(netchg) if netchg not in (None, "NA", "") else None}
    return out


def resolve_nfo_token(name: str, opt: str = "", strike: str = "", expiry: str = "") -> str | None:
    """Best-effort Angel NFO instrument token for an F&O contract from a broker label.

    Matches an OPTSTK/OPTIDX (opt=CE/PE, strike) or FUTSTK/FUTIDX (opt empty) by
    underlying name + strike, taking the nearest future expiry when the exact expiry
    can't be matched. Returns None if nothing plausible is found.
    """
    name = (name or "").strip().upper()
    if not name:
        return None
    opt = (opt or "").strip().upper()
    try:
        strike_i = int(float(strike)) if strike not in ("", None) else None
    except (TypeError, ValueError):
        strike_i = None
    if opt in ("CE", "PE"):
        chain = _load_stock_options().get(name)
        if chain and strike_i is not None:
            exp = _nearest_future_expiry(chain)
            node = chain.get(exp, {}).get(str(strike_i), {}) if exp else {}
            if node.get(opt):
                return str(node[opt])
        # index options (NIFTY/BANKNIFTY)
        idx = _load_options().get(name)
        if idx and strike_i is not None:
            exp = nearest_expiry(name)
            node = idx.get(exp, {}).get(str(strike_i), {}) if exp else {}
            if node.get(opt):
                return str(node[opt])
        return None
    # futures
    f = _load_futures().get(name)
    return f["token"] if f else None


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


# --- Live order placement (Angel SmartAPI) -----------------------------------
# Reached ONLY from execution.engine after every guardrail passes and the master
# switch is ON. Places the entry order, then a stop-loss order so no bet is naked.
PLACE_ORDER = "/rest/secure/angelbroking/order/v1/placeOrder"
_PRODUCT = {"CNC": "DELIVERY", "MIS": "INTRADAY", "NRML": "CARRYFORWARD", "MARGIN": "MARGIN"}


def _place(acc, jwt, body: dict) -> dict:
    from .angel import _headers
    r = httpx.post(acc.base_url + PLACE_ORDER, headers=_headers(acc, jwt), json=body, timeout=30.0)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400 or (isinstance(j, dict) and j.get("status") is False):
        raise RuntimeError(f"Angel rejected order [{r.status_code}]: {r.text[:200]}")
    return (j.get("data") or {}) if isinstance(j, dict) else {}


def place_order(order) -> dict:
    """Place a guarded order via the Angel account. `order` is an OrderRequest."""
    from ..config import get_accounts, load_account
    key = next((k for k in get_accounts() if k.upper().startswith("ANGEL")), None)
    if not key:
        raise RuntimeError("No Angel account configured — connect ANGEL1 to place orders.")
    acc = load_account(key)
    jwt, note = _login(acc)
    if not jwt:
        raise RuntimeError(f"Angel login failed: {note}")

    exch = (order.exchange or "NSE").upper()
    if exch == "NFO":
        # Option/future: the caller supplies the exact NFO tradingsymbol + token.
        tradingsymbol = order.symbol
        symboltoken = order.token
        if not symboltoken or not tradingsymbol:
            raise RuntimeError(f"NFO order needs tradingsymbol + token ({order.symbol})")
    else:
        sym = order.symbol.upper().split("-")[0]
        tradingsymbol = f"{sym}-EQ" if exch == "NSE" else order.symbol
        symboltoken = token_for(sym) or order.token
        if not symboltoken:
            raise RuntimeError(f"No Angel instrument token for {sym}")

    entry = {
        "variety": "NORMAL", "tradingsymbol": tradingsymbol, "symboltoken": str(symboltoken),
        "transactiontype": order.side, "exchange": exch,
        "ordertype": order.order_type, "producttype": _PRODUCT.get(order.product, "DELIVERY"),
        "duration": "DAY", "quantity": str(int(order.quantity)),
        "price": str(order.price) if order.order_type == "LIMIT" else "0",
    }
    data = _place(acc, jwt, entry)
    result = {"broker": "angel", "account": key, "orderid": data.get("orderid"),
              "tradingsymbol": tradingsymbol}

    # protective stop-loss on the opposite side (so the bet is never naked)
    if order.stop_loss and order.stop_loss > 0:
        opp = "SELL" if order.side == "BUY" else "BUY"
        sl = {
            "variety": "STOPLOSS", "tradingsymbol": tradingsymbol, "symboltoken": str(symboltoken),
            "transactiontype": opp, "exchange": exch, "ordertype": "STOPLOSS_MARKET",
            "producttype": _PRODUCT.get(order.product, "DELIVERY"), "duration": "DAY",
            "quantity": str(int(order.quantity)), "price": "0",
            "triggerprice": str(order.stop_loss),
        }
        try:
            sld = _place(acc, jwt, sl)
            result["stop_loss_orderid"] = sld.get("orderid")
        except Exception as exc:
            result["stop_loss_error"] = str(exc)[:160]
    return result
