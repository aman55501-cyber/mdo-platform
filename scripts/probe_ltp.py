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

    # grab a couple of real instruments (security_id + exchange) from holdings
    adapter = HdfcAdapter(account)
    try:
        holdings = await adapter.get_holdings()
    finally:
        await adapter.close()
    samples = [
        {"security_id": h["security_id"], "exchange": h.get("exchange", "NSE")}
        for h in holdings if h.get("security_id")
    ][:2]
    if not samples:
        print("[X] No instruments with a security_id found to probe with.")
        return 1
    sids = [s["security_id"] for s in samples]
    print(f"\n=== Probing /fetch-ltp for {creds_key} with instruments {sids} ===\n")

    http = httpx.AsyncClient(
        base_url=account.base_url,
        timeout=30.0,
        headers={
            "User-Agent": get_user_agent(),
            "Content-Type": "application/json",
            "Authorization": f"Bearer {account.access_token}",
        },
    )

    # candidate body shapes (the error message often reveals the expected field)
    candidates = {
        "instruments[{security_id,exchange}]": {"instruments": samples},
        "data[{security_id,exchange}]": {"data": samples},
        "bare list": samples,
        "symbols[security_id]": {"symbols": sids},
        "instrument_tokens[]": {"instrument_tokens": sids},
        "instruments[{security_id,exchange_segment}]": {
            "instruments": [{"security_id": s["security_id"], "exchange_segment": s["exchange"]} for s in samples]
        },
        "ltp[{security_id,exchange}]": {"ltp": samples},
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
        await http.close()

    if winners:
        print(f"WORKING body shape(s): {winners}")
        print("Paste the full output here and I'll wire live F&O mark-to-market.")
    else:
        print("None returned 200 — but the response text above usually names the expected")
        print("field. Paste it all here and I'll adjust the body shape.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
