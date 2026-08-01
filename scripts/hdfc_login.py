"""HDFC Securities daily login — obtains an access token and saves it to .env.

Usage (from the project root, with your venv active):
    python scripts/hdfc_login.py HDFC1

What it does (read-only, never trades):
  1. Opens HDFC's login page in your browser (login + 2FA + accept T&C).
  2. HDFC redirects you back to your Redirect URL with ?request_token=XXXX.
  3. You paste that redirected URL here.
  4. It exchanges the request_token for an access token and writes
     HDFC_<KEY>_ACCESS_TOKEN into your .env.

Security: this script NEVER prints your API key, secret, or access token.
You are never asked to type a key into the chat — everything comes from .env.
"""

from __future__ import annotations

import asyncio
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# make the project root importable when run as `python scripts/hdfc_login.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shares_cfo.brokers.hdfc import HdfcAdapter  # noqa: E402
from shares_cfo.config import load_account, write_env_var  # noqa: E402
from shares_cfo.exceptions import SharesCFOError  # noqa: E402


def _extract_request_token(pasted: str) -> str:
    """Accept the full redirected URL or the bare token.

    HDFC's redirect uses the param name `requestToken` (camelCase); we also accept
    `request_token` / `request-token` for safety.
    """
    pasted = pasted.strip()
    if not pasted:
        raise ValueError("Nothing pasted.")
    if "?" in pasted or "://" in pasted:
        qs = parse_qs(urlparse(pasted).query)
        for key, values in qs.items():
            if key.lower().replace("_", "").replace("-", "") == "requesttoken" and values and values[0]:
                return values[0]
    # bare token pasted on its own
    if "://" not in pasted and "?" not in pasted and "=" not in pasted and " " not in pasted:
        return pasted
    raise ValueError("Could not find a request token in what you pasted. Paste the whole address bar.")


async def main() -> int:
    creds_key = (sys.argv[1] if len(sys.argv) > 1 else "HDFC1").upper()

    try:
        account = load_account(creds_key)
    except SharesCFOError as exc:
        print(f"\n[X] {exc}\n")
        return 1

    login_url = f"{account.base_url}/login?api_key={account.api_key}"

    print(f"\n=== HDFC login for {creds_key} (client code {account.client_code or 'unknown'}) ===")
    print("Opening the HDFC login page in your browser...")
    print("  -> Log in, complete 2FA, and accept the Terms & Conditions.")
    print("  -> HDFC will then redirect you to your Redirect URL.")
    print(f"  -> That page's address will contain '?request_token=...'  (redirect: {account.redirect_url})")
    opened = False
    try:
        opened = webbrowser.open(login_url)
    except Exception:
        opened = False
    if not opened:
        print("\n(Could not auto-open a browser. Open your HDFC developer login page manually,")
        print(" log in, and copy the URL you land on.)")

    print("\nAfter you're redirected, copy the FULL address from your browser and paste it below.")
    try:
        pasted = input("Paste the redirected URL (or just the request_token): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 1

    try:
        request_token = _extract_request_token(pasted)
    except ValueError as exc:
        print(f"\n[X] {exc} Try again — paste the whole address bar.\n")
        return 1

    adapter = HdfcAdapter(account)
    try:
        print("\nExchanging request_token for an access token...")
        access_token = await adapter.exchange_request_token(request_token)
    except SharesCFOError as exc:
        print(f"\n[X] {exc}\n")
        return 1
    finally:
        await adapter.close()

    env_key = f"{account.env_prefix}ACCESS_TOKEN"  # e.g. HDFC_HDFC1_ACCESS_TOKEN
    write_env_var(env_key, access_token)

    print(f"\n[OK] Access token saved to {env_key} in your .env.")
    print("     (The token value was NOT printed here — by design.)")
    print("     You're logged in for today. HDFC tokens expire same-day; re-run this each morning.")
    print("\nNext: python scripts/probe_hdfc.py", creds_key, "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
