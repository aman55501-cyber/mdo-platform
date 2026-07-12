"""HDFC endpoint prober — finds which read endpoints work, and their JSON shape.

Usage (after a successful login):
    python scripts/probe_hdfc.py HDFC1

It GETs candidate Holdings / Positions / Funds / Profile paths (it NEVER places,
modifies, or cancels an order — there is no order code in this project) and prints:
  * which path returned HTTP 200
  * the top-level JSON keys it returned
  * a suggested mapping to paste into shares_cfo/brokers/hdfc_endpoints.py

If nothing returns 200: open https://developer.hdfcsec.com/ir-docs/ , read the
Holdings / Positions / Funds-Limits / Profile pages, add the correct paths to the
CANDIDATES dict in hdfc_endpoints.py, and re-run.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shares_cfo.brokers import hdfc_endpoints as ep  # noqa: E402
from shares_cfo.brokers.hdfc import HdfcAdapter  # noqa: E402
from shares_cfo.config import load_account  # noqa: E402
from shares_cfo.exceptions import SharesCFOError, TokenExpiredError  # noqa: E402


def _shape(payload) -> str:
    if isinstance(payload, dict):
        keys = list(payload.keys())
        inner = ""
        if "data" in payload and isinstance(payload["data"], (list, dict)):
            d = payload["data"]
            if isinstance(d, list) and d and isinstance(d[0], dict):
                inner = f"  data[0] keys: {list(d[0].keys())}"
            elif isinstance(d, dict):
                inner = f"  data keys: {list(d.keys())}"
        return f"dict keys: {keys}{inner}"
    if isinstance(payload, list):
        head = payload[0] if payload else None
        return f"list[{len(payload)}]" + (f" item keys: {list(head.keys())}" if isinstance(head, dict) else "")
    return type(payload).__name__


async def main() -> int:
    creds_key = (sys.argv[1] if len(sys.argv) > 1 else "HDFC1").upper()
    try:
        account = load_account(creds_key)
    except SharesCFOError as exc:
        print(f"\n[X] {exc}\n")
        return 1

    if not account.access_token:
        print(f"\n[X] No access token for {creds_key}. Run:  python scripts/hdfc_login.py {creds_key}\n")
        return 1

    adapter = HdfcAdapter(account)
    suggestions: dict[str, str] = {}
    print(f"\n=== Probing HDFC read endpoints for {creds_key} (User-Agent + AUTH_STYLE='{ep.AUTH_STYLE}') ===\n")

    try:
        for concept, paths in ep.CANDIDATES.items():
            print(f"[{concept}]")
            hit = None
            for path in paths:
                try:
                    payload = await adapter._get(path)
                    print(f"   200  {path}   ->   {_shape(payload)}")
                    if hit is None:
                        hit = path
                except TokenExpiredError:
                    print(f"   401  {path}   (token expired — re-run hdfc_login.py)")
                    await adapter.close()
                    return 1
                except SharesCFOError as exc:
                    msg = str(exc)
                    code = msg.split("HTTP ")[1][:3] if "HTTP " in msg else "ERR"
                    print(f"   {code:>3}  {path}")
            if hit:
                suggestions[concept] = hit
            print()
    finally:
        await adapter.close()

    if not suggestions:
        print("No endpoint returned 200.")
        print("-> Read https://developer.hdfcsec.com/ir-docs/ (Holdings, Positions, Funds/Limits,")
        print("   Profile), add the correct paths to CANDIDATES in hdfc_endpoints.py, and re-run.")
        print("-> If everything returned 401, your token expired: python scripts/hdfc_login.py", creds_key)
        return 1

    print("=== Suggested edits for shares_cfo/brokers/hdfc_endpoints.py ===")
    name = {"holdings": "HOLDINGS", "positions": "POSITIONS", "funds": "FUNDS", "profile": "PROFILE"}
    for concept, path in suggestions.items():
        print(f'   {name[concept]} = "{path}"')
    print("\nUpdate those constants to match, then: curl your local /portfolio.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
