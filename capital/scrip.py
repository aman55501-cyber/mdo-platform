"""NSE symbol master (Angel's public instrument file), cached for a day.

Used for two things only: confirming that a name in a call really is a listed ticker, and finding the token
needed to ask for its quote. If the file cannot be fetched the jobs carry on and say so in their run summary.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .config import optional

URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
MAX_AGE_SECONDS = 24 * 3600


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"-(EQ|BE|BZ|SM|ST)$", "", (s or "").upper()))


def _cache_path() -> Path:
    return Path(optional("CAPITAL_CACHE_DIR", "/tmp")) / "scrip_master_nse_eq.json"


def load(fetch=None, now: float | None = None) -> dict[str, dict]:
    """{NORMALISED_SYMBOL: {"token": "...", "symbol": "KSCL-EQ"}} for NSE cash-equity series."""
    now = now if now is not None else time.time()
    path = _cache_path()
    if path.exists() and now - path.stat().st_mtime < MAX_AGE_SECONDS:
        return json.loads(path.read_text())
    if fetch is None:
        import httpx

        def fetch():  # pragma: no cover - network
            r = httpx.get(URL, timeout=60)
            r.raise_for_status()
            return r.json()
    rows = fetch()
    out: dict[str, dict] = {}
    for r in rows:
        sym = r.get("symbol", "")
        if r.get("exch_seg") == "NSE" and sym.endswith("-EQ"):
            out[norm(sym)] = {"token": str(r.get("token")), "symbol": sym}
    try:
        path.write_text(json.dumps(out))
    except OSError:
        pass
    return out


def load_or_empty(fetch=None) -> tuple[dict[str, dict], str | None]:
    try:
        return load(fetch), None
    except Exception as exc:  # noqa: BLE001
        return {}, f"symbol master unavailable ({type(exc).__name__})"
