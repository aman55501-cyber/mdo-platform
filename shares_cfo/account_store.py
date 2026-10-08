"""In-app account store — connect broker accounts without touching the VPS .env.

Accounts added through the app are saved to a JSON in the persistent state volume
and injected into the environment at startup, so config.load_account picks them up
exactly like .env-defined accounts. .env always WINS (never overwritten), so this
only ADDS accounts. Secrets live only in this file on your server — same trust
boundary as .env; the write is chmod 0600 and the endpoint is token-protected.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

STORE = Path(__file__).resolve().parent / "data" / "state" / "accounts.json"

# canonical field -> env var suffix (prefix is <BROKER>_<KEY>_)
FIELDS = {
    "api_key": "API_KEY",
    "api_secret": "API_SECRET",
    "client_code": "CLIENT_CODE",
    "redirect_url": "REDIRECT_URL",
    "totp_secret": "TOTP_SECRET",
    "mpin": "MPIN",
}


def _broker(creds_key: str) -> str:
    k = creds_key.upper()
    if k.startswith("HDFC"):
        return "hdfc"
    if k.startswith("ANGEL"):
        return "angel"
    raise ValueError("Account name must start with HDFC or ANGEL (e.g. HDFC3, ANGEL1).")


def load() -> dict:
    try:
        return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(STORE, 0o600)  # secrets: owner-only
    except OSError:
        pass


def apply_to_env() -> list[str]:
    """Inject stored accounts into os.environ (without clobbering .env). Returns keys."""
    data = load()
    added = []
    for key, fields in data.items():
        key = key.upper()
        broker = _broker(key)
        prefix = f"{broker.upper()}_{key}_"
        for canon, suffix in FIELDS.items():
            val = fields.get(canon)
            if val and not os.environ.get(prefix + suffix):  # .env wins
                os.environ[prefix + suffix] = str(val)
        added.append(key)
    if added:  # make sure they're in the account list
        current = [x.strip().upper() for x in os.environ.get("CFO_ACCOUNTS", "HDFC1").split(",") if x.strip()]
        merged = current + [k for k in added if k not in current]
        os.environ["CFO_ACCOUNTS"] = ",".join(merged)
    return added


def add(creds_key: str, fields: dict) -> dict:
    """Validate + persist one account, then inject it into the environment."""
    key = creds_key.strip().upper()
    broker = _broker(key)  # raises if bad prefix
    if not fields.get("api_key"):
        raise ValueError("API key is required.")
    if broker == "hdfc" and not fields.get("api_secret"):
        raise ValueError("HDFC needs both API key and API secret.")
    if broker == "angel" and not (fields.get("totp_secret") and fields.get("mpin")):
        raise ValueError("Angel needs TOTP secret and MPIN as well.")

    clean = {k: str(v).strip() for k, v in fields.items() if k in FIELDS and v}
    data = load()
    data[key] = clean
    _save(data)
    apply_to_env()
    return {"account": key, "broker": broker, "stored_fields": sorted(clean.keys())}


def remove(creds_key: str) -> bool:
    data = load()
    if creds_key.upper() in data:
        del data[creds_key.upper()]
        _save(data)
        return True
    return False
