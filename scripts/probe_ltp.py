"""Discover the HDFC /fetch-ltp request/response format (read-only).

fetch-ltp is a PUT with a body listing instruments. We don't know the exact body
shape, so this tries several common shapes against a couple of your real
instruments and prints which returns 200 + the response, so we can wire live
prices. It never places an order.

Usage (after login):
    python scripts/probe_ltp.py HDFC1
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from shares_cfo.brokers.hdfc import HdfcAdapter  # noqa: E402
from shares_cfo.config import get_user_agent, load_account  # noqa: E402
from shares_cfo.exceptions import SharesCFOError  # noqa: E402


async def main() -> int:
    creds_key = (sys.argv[1] if len(sys.argv) > 1 else "HDFC1").upper()
    try:
        account = load_account(creds_key)
    except SharesCFOError as exc:
        print(f"\n[X] {exc}\n")
        return 1
    if not account.access_token:
        print(f"\n[X] No access token. Run:  python scripts/hdfc_login.py {creds_key}\n")
        return 1

    # grab a couple of real instruments from RAW holdings — we need instrument_token
    from shares_cfo.brokers import hdfc_endpoints as ep  # noqa: E402
    adapter = HdfcAdapter(account)
    try:
        raw = await adapter._get(ep.HOLDINGS)
    finally:
        await adapter.close()
    rows = (raw.get("data") or [])[:2]
    toks = []
    for r in rows:
        tok = r.get("instrument_token") or r.get("security_id")
        toks.append({"token": tok, "exchange": r.get("exchange", "NSE")})
    if not toks:
        print("[X] No instruments found to probe with.")
        return 1
    print(f"\n=== Probing /fetch-ltp for {creds_key} with tokens {[t['token'] for t in toks]} ===\n")

    http = httpx.AsyncClient(
        base_url=account.base_url,
        timeout=30.0,
        headers={
            "User-Agent": get_user_agent(),
            "Content-Type": "application/json",
            "Authorization": f"Bearer {account.access_token}",
        },
    )

    # We now know the body is {"data":[{"token":..., ...}]} — try token type/field variants.
    tok_str = [{"token": str(t["token"]), "exchange": t["exchange"]} for t in toks]
    tok_int = [{"token": int(t["token"]), "exchange": t["exchange"]} for t in toks if str(t["token"]).isdigit()]
    candidates = {
        "data[{token:str, exchange}]": {"data": tok_str},
        "data[{token:int, exchange}]": {"data": tok_int or tok_str},
        "data[{token, exchange_segment}]": {"data": [{"token": str(t["token"]), "exchange_segment": t["exchange"]} for t in toks]},
        "data[{token} only]": {"data": [{"token": str(t["token"])} for t in toks]},
    }

    winners = []
    try:
        for name, body in candidates.items():
            try:
                r = await http.put("/fetch-ltp", params={"api_key": account.api_key}, json=body)
                snippet = r.text[:400].replace("\n", " ")
                print(f"[{r.status_code}] {name}")
                print(f"       body: {json.dumps(body)[:160]}")
                print(f"       resp: {snippet}\n")
                if r.status_code == 200:
                    winners.append(name)
            except httpx.HTTPError as exc:
                print(f"[ERR] {name}: {exc}\n")
    finally:
        await http.aclose()

    if winners:
        print(f"WORKING body shape(s): {winners}")
        print("Paste the full output here and I'll wire live F&O mark-to-market.")
    else:
        print("None returned 200 — but the response text above usually names the expected")
        print("field. Paste it all here and I'll adjust the body shape.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
