"""Daily broker login board. Drives the existing shares_cfo login (it already does this safely) and adds nothing new
that touches credentials: the HDFC login happens on HDFC's own page, 2FA on the account holder's phone, and the
shares_cfo server arms itself on the callback. This app never sees an HDFC password, PIN or request token.

Server-to-server only: the shares_cfo API token is sent in a header from here and never reaches the browser.
"""
from __future__ import annotations

import httpx

from .config import optional

_REDIRECTS = {301, 302, 303, 307, 308}


def settings() -> tuple[str, str, list[str]]:
    base, tok = optional("CAPITAL_CFO_URL").rstrip("/"), optional("CFO_API_TOKEN")
    missing = [n for n, v in (("CAPITAL_CFO_URL", base), ("CFO_API_TOKEN", tok)) if not v]
    return base, tok, missing


def accounts(client: httpx.Client, base: str, tok: str) -> list[dict]:
    r = client.get(f"{base}/accounts", headers={"X-CFO-Token": tok})
    r.raise_for_status()
    return r.json().get("accounts", [])


def start(client: httpx.Client, base: str, tok: str, key: str) -> str:
    """Ask shares_cfo to begin the HDFC login for one account; return HDFC's own login URL for the browser."""
    r = client.get(f"{base}/hdfc/login", params={"key": key}, headers={"X-CFO-Token": tok}, follow_redirects=False)
    loc = r.headers.get("location", "")
    if r.status_code not in _REDIRECTS or not loc.startswith("https://"):
        raise RuntimeError(f"login service did not return a secure HDFC login address (HTTP {r.status_code})")
    return loc


def board(db, client: httpx.Client | None, now=None) -> dict:
    """Today's login status for every account the login service knows, plus the Angel pull's age."""
    from . import fmt
    base, tok, missing = settings()
    out = {"missing": missing, "rows": [], "error": None, "need": 0, "done": 0, "pct": 0, "pull_age": None}
    try:
        fresh = {r["source"]: r["last_at"] for r in db.query("select source, last_at from wb.desk_freshness")}
        out["pull_age"] = fmt.age(fresh.get("holdings_pull"), now)
    except Exception:  # noqa: BLE001 - the board still works without the freshness line
        pass
    if missing:
        return out
    try:
        rows = accounts(client, base, tok)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return out
    for a in rows:
        manual = (a.get("broker") == "hdfc")
        out["rows"].append({"key": a.get("key"), "label": a.get("label") or a.get("key"), "code": a.get("client_code") or "",
                            "broker": a.get("broker"), "logged_in": bool(a.get("logged_in")), "manual": manual,
                            "needs_setup": bool(a.get("needs_setup"))})
    manual_rows = [r for r in out["rows"] if r["manual"]]
    out["need"], out["done"] = len(manual_rows), sum(r["logged_in"] for r in manual_rows)
    out["pct"] = round(out["done"] / out["need"] * 100) if out["need"] else 0
    return out
