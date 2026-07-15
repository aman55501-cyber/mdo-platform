"""Configuration for Shares CFO — multi-account aware, read from environment.

Secrets live ONLY in the .env file (gitignored). This module never prints them.

Per-account env var pattern (matches the charter's naming):
    HDFC_HDFC1_API_KEY, HDFC_HDFC1_API_SECRET, HDFC_HDFC1_ACCESS_TOKEN
    HDFC_HDFC1_REDIRECT_URL, HDFC_HDFC1_CLIENT_CODE, HDFC_HDFC1_STATIC_IP
Angel accounts use the ANGEL_ prefix (ANGEL_ANGEL1_API_KEY, ...).

Shared:
    HDFC_BASE_URL              (default https://developer.hdfcsec.com/oapi/v1)
    SHARES_CFO_USER_AGENT      (default shares-cfo/1.0)  -- MANDATORY on every call
    CFO_API_TOKEN              -- protects the local server
    CFO_ACCOUNTS               -- comma list of creds_keys to load (default HDFC1)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .exceptions import ConfigError

# Verified from HDFC docs (trusted over any convention in old code):
#   - base URL includes /oapi/v1
#   - a User-Agent header is MANDATORY on every call
DEFAULT_BASE_URL = "https://developer.hdfcsec.com/oapi/v1"
DEFAULT_ANGEL_BASE_URL = "https://apiconnect.angelbroking.com"
DEFAULT_USER_AGENT = "shares-cfo/1.0"

# Client codes + human labels (labels are cosmetic — the API keys on client_code).
# 4016900 = Aman's PERSONAL HDFC account (confirmed). Aditi Investments is the
# Angel One account (A1504046), added in Phase 3.
# Real client/customer codes for the accounts Aman manages.
# Note: HDFC5 in the family list is actually an Angel One account -> ANGEL1.
DEFAULT_CLIENT_CODES = {
    "HDFC1": "4016900",     # Aman (personal)
    "HDFC2": "189737306",   # Sudha
    "HDFC3": "190837559",   # Ashok
    "HDFC4": "53612658",    # Aditi
    "HDFC6": "178601202",   # Jahnavi
    "ANGEL1": "288924176",  # Aditi Investment (Angel One)
}
ACCOUNT_LABELS = {
    "HDFC1": "Aman (personal)",
    "HDFC2": "Sudha",
    "HDFC3": "Ashok",
    "HDFC4": "Aditi",
    "HDFC6": "Jahnavi",
    "ANGEL1": "Aditi Investment",
}


def _find_env_path() -> Path:
    """Prefer backend/.env (the charter layout), else project-root .env."""
    override = os.environ.get("SHARES_CFO_ENV_PATH")
    if override:
        return Path(override)
    root = Path(__file__).resolve().parent.parent
    backend = root / "backend" / ".env"
    return backend if backend.exists() else root / ".env"


ENV_PATH = _find_env_path()
load_dotenv(ENV_PATH)


def _infer_broker(creds_key: str) -> str:
    k = creds_key.upper()
    if k.startswith("HDFC"):
        return "hdfc"
    if k.startswith("ANGEL"):
        return "angel"
    raise ConfigError(f"Cannot infer broker from creds_key '{creds_key}'.")


@dataclass
class AccountConfig:
    creds_key: str
    broker: str
    api_key: str
    api_secret: str
    access_token: str = ""
    redirect_url: str = "http://localhost:8080/callback"
    client_code: str = ""
    static_ip: str = ""
    base_url: str = DEFAULT_BASE_URL
    label: str = ""
    # Angel-only (SmartAPI logs in server-side with a TOTP secret + MPIN)
    totp_secret: str = ""
    mpin: str = ""

    @property
    def env_prefix(self) -> str:
        return f"{self.broker.upper()}_{self.creds_key.upper()}_"


def load_account(creds_key: str) -> AccountConfig:
    """Load one account's config from the environment. Raises if key/secret missing."""
    creds_key = creds_key.upper()
    broker = _infer_broker(creds_key)
    prefix = f"{broker.upper()}_{creds_key}_"

    def get(name: str, default: str = "") -> str:
        return os.environ.get(prefix + name, default).strip()

    api_key = get("API_KEY")
    api_secret = get("API_SECRET")
    # Angel logs in with client_code + MPIN + TOTP (no api_secret); HDFC needs both.
    if broker == "hdfc" and (not api_key or not api_secret):
        raise ConfigError(
            f"Missing {prefix}API_KEY and/or {prefix}API_SECRET in {ENV_PATH.name}. "
            f"Add them to your .env and try again."
        )
    if broker == "angel" and not api_key:
        raise ConfigError(f"Missing {prefix}API_KEY in {ENV_PATH.name}.")

    if broker == "angel":
        base_url = os.environ.get("ANGEL_BASE_URL", DEFAULT_ANGEL_BASE_URL).strip()
    else:
        base_url = os.environ.get("HDFC_BASE_URL", DEFAULT_BASE_URL).strip()

    return AccountConfig(
        creds_key=creds_key,
        broker=broker,
        api_key=api_key,
        api_secret=api_secret,
        access_token=get("ACCESS_TOKEN"),
        redirect_url=get("REDIRECT_URL", "http://localhost:8080/callback"),
        client_code=get("CLIENT_CODE", DEFAULT_CLIENT_CODES.get(creds_key, "")),
        static_ip=get("STATIC_IP"),
        base_url=base_url,
        label=ACCOUNT_LABELS.get(creds_key, creds_key),
        totp_secret=get("TOTP_SECRET"),
        mpin=get("MPIN") or get("PIN") or get("PASSWORD"),
    )


def get_user_agent() -> str:
    return os.environ.get("SHARES_CFO_USER_AGENT", DEFAULT_USER_AGENT).strip()


def get_accounts() -> list[str]:
    """Which accounts the server should load. Stage A default: HDFC1 only."""
    raw = os.environ.get("CFO_ACCOUNTS", "HDFC1")
    return [k.strip().upper() for k in raw.split(",") if k.strip()]


def get_api_token() -> str:
    """Shared secret the mobile app sends to reach the local server."""
    return os.environ.get("CFO_API_TOKEN", "").strip()


def write_env_var(key: str, value: str, env_path: Path | None = None) -> None:
    """Insert or update a single KEY=value line in .env, preserving the rest.

    Used by the login script to persist the access token. The value is written to
    disk but never returned or printed by callers.
    """
    path = env_path or ENV_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    line = f"{key}={value}"
    replaced = False
    for i, existing in enumerate(lines):
        stripped = existing.strip()
        if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
            lines[i] = line
            replaced = True
            break
    if not replaced:
        lines.append(line)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # refresh in-process env so a running script sees the new value immediately
    os.environ[key] = value
