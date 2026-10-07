"""Intraday quotes for held, watched, idea and call symbols -> wb.quotes (latest per symbol).

READ-ONLY toward the broker: this job logs in and asks for prices. It touches no order, funds or holdings
endpoint (a test pins the allowed URLs). It writes one wb.run_log row per run, including 'market closed'.

NOT YET RUN AGAINST THE LIVE BROKER API. The endpoint and field names follow Angel's documented quote API; the
first run on the server must be watched (`python -m capital.jobs.quote_poll --force`) before the cron is enabled.
Credentials come from the server .env under a configurable prefix; missing names are reported by name, never value.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

import httpx

from .. import fmt, scrip
from ..config import IST, ConfigError, optional
from ..db import DB

JOB = "quote_poll"
BASE = "https://apiconnect.angelbroking.com"
LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
QUOTE_PATH = "/rest/secure/angelbroking/market/v1/quote/"
ALLOWED_PATHS = {LOGIN_PATH, QUOTE_PATH}
BATCH = 50


def credential_names(prefix: str) -> dict[str, str]:
    return {"api_key": f"{prefix}API_KEY", "client": f"{prefix}CLIENT_ID", "pin": f"{prefix}PIN", "totp": f"{prefix}TOTP_SECRET"}


def load_credentials(env=os.environ, prefix: str | None = None) -> dict[str, str]:
    prefix = prefix or optional("CAPITAL_ANGEL_PREFIX", "ANGEL_ADITI_")
    names = credential_names(prefix)
    if not (env.get(names["pin"], "").strip()) and env.get(f"{prefix}MPIN", "").strip():
        names["pin"] = f"{prefix}MPIN"
    missing = [n for n in names.values() if not env.get(n, "").strip()]
    if missing:
        raise ConfigError("missing in .env: " + ", ".join(missing))
    return {k: env[n].strip() for k, n in names.items()}


def _headers(api_key: str, public_ip: str, jwt: str | None = None) -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json", "X-UserType": "USER", "X-SourceID": "WEB",
         "X-ClientLocalIP": optional("ANGEL_LOCAL_IP", public_ip), "X-ClientPublicIP": public_ip,
         "X-MACAddress": optional("ANGEL_MAC", "AA:BB:CC:DD:EE:FF"), "X-PrivateKey": api_key}
    if jwt:
        h["Authorization"] = f"Bearer {jwt}"
    return h


def public_ip(client: httpx.Client) -> str:
    return optional("CAPITAL_ANGEL_PUBLIC_IP") or client.get("https://api.ipify.org", timeout=10).text.strip()


def login(client: httpx.Client, creds: dict, ip: str) -> str:
    import pyotp

    body = {"clientcode": creds["client"], "password": creds["pin"], "totp": pyotp.TOTP(creds["totp"]).now()}
    r = client.post(BASE + LOGIN_PATH, headers=_headers(creds["api_key"], ip), json=body)
    r.raise_for_status()
    jwt = (r.json().get("data") or {}).get("jwtToken")
    if not jwt:
        raise RuntimeError("broker login returned no token")
    return jwt


def wanted(db, master: dict) -> dict[str, dict]:
    """{symbol: {token, exchange, isin}} for everything the Desk wants priced."""
    out: dict[str, dict] = {}
    for r in db.query("select symbol, symboltoken, exchange, isin from wb.holdings_raw where symboltoken is not null"):
        out[r["symbol"]] = {"token": r["symboltoken"], "exchange": r["exchange"] or "NSE", "isin": r["isin"]}
    for r in db.query("select wb.norm_symbol(symbol) symbol, symboltoken, exchange from public.watchlist where active and symboltoken is not null"):
        out.setdefault(r["symbol"], {"token": r["symboltoken"], "exchange": r["exchange"] or "NSE", "isin": None})
    extra = db.query("select wb.norm_symbol(symbol) symbol from public.desk_ideas where status in ('proposed','approved','open') "
                     "union select coalesce(symbol, wb.norm_symbol(symbol_raw)) from wb.calls where status in ('open','watching')")
    for r in extra:
        s = r["symbol"]
        if s and s not in out and s in master:
            out[s] = {"token": master[s]["token"], "exchange": "NSE", "isin": None}
    return out


def _quote_time(raw: str | None) -> datetime:
    for f in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw or "", f).replace(tzinfo=IST).astimezone(timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def fetch_quotes(client: httpx.Client, creds: dict, ip: str, jwt: str, want: dict[str, dict], sleep=time.sleep) -> tuple[list[dict], int]:
    by_tok = {v["token"]: (s, v) for s, v in want.items()}
    tokens = list(by_tok)
    got: list[dict] = []
    unfetched = 0
    for i in range(0, len(tokens), BATCH):
        chunk = tokens[i:i + BATCH]
        r = client.post(BASE + QUOTE_PATH, headers=_headers(creds["api_key"], ip, jwt),
                        json={"mode": "FULL", "exchangeTokens": {"NSE": chunk}})
        r.raise_for_status()
        data = r.json().get("data") or {}
        unfetched += len(data.get("unfetched") or [])
        for q in data.get("fetched") or []:
            hit = by_tok.get(str(q.get("symbolToken")))
            ltp, close = q.get("ltp"), q.get("close")
            if hit and ltp and float(ltp) > 0:
                got.append({"symbol": hit[0], "isin": hit[1]["isin"], "ltp": float(ltp),
                            "prev_close": float(close) if close and float(close) > 0 else None,
                            "quote_time": _quote_time(q.get("exchFeedTime"))})
        sleep(1.1)   # the quote endpoint is rate limited to about one call a second
    return got, unfetched


_UPSERT = ("insert into wb.quotes (symbol, exchange, isin, ltp, prev_close, quote_time, source) values (%s,'NSE',%s,%s,%s,%s,'angel-quote') "
           "on conflict (symbol, exchange) do update set ltp=excluded.ltp, prev_close=excluded.prev_close, "
           "quote_time=excluded.quote_time, isin=coalesce(excluded.isin, wb.quotes.isin), source=excluded.source, fetched_at=now()")


def run(db: DB, *, force: bool = False, client: httpx.Client | None = None, master: dict | None = None, now: datetime | None = None,
        env=os.environ, sleep=time.sleep) -> dict:
    now = now or datetime.now(IST)

    def log(ok: bool, text: str):
        db.execute("insert into wb.run_log (job, ok, summary) values (%s, %s, %s)", (JOB, ok, text))

    if not force and not fmt.market_open(now):
        log(True, "skipped: market closed")
        return {"skipped": True}
    try:
        creds = load_credentials(env)
        own = client is None
        client = client or httpx.Client(timeout=30)
        try:
            ip = public_ip(client)
            jwt = login(client, creds, ip)
            if master is None:
                master, _ = scrip.load_or_empty()
            want = wanted(db, master)
            quotes, unfetched = fetch_quotes(client, creds, ip, jwt, want, sleep)
        finally:
            if own:
                client.close()
        for q in quotes:
            db.execute(_UPSERT, (q["symbol"], q["isin"], q["ltp"], q["prev_close"], q["quote_time"]))
        text = f"{len(quotes)} of {len(want)} symbols priced, {unfetched} not returned by the broker"
        log(True, text)
        return {"priced": len(quotes), "wanted": len(want), "unfetched": unfetched}
    except Exception as exc:
        log(False, f"FAILED: {type(exc).__name__}: {str(exc)[:150]}")
        raise


if __name__ == "__main__":  # pragma: no cover
    result = run(DB(readonly=False), force="--force" in sys.argv)
    print(result, file=sys.stderr)
