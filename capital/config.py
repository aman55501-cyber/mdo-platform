"""Environment-only configuration. Missing required values fail loudly, naming the variable (never a value)."""
from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # same idiom as the rest of the repo; a no-op where the platform injects variables
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

IST = ZoneInfo("Asia/Kolkata")

# Demat accounts the owner has named in the build spec. Used only to tell the Desk how much of the book the
# "already held" check can actually see. (code, owner label, broker)
KNOWN_DEMATS = [
    ("HDFC1", "Aman", "hdfc"),
    ("HDFC2", "Sudha", "hdfc"),
    ("HDFC3", "Ashok", "hdfc"),
    ("A1504046", "Aditi Investments", "angelone"),
]


class ConfigError(RuntimeError):
    """Raised when required configuration is missing. The message names the variable only."""


def require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise ConfigError(f"Required environment variable {name} is missing or blank. Add it to .env and restart.")
    return val


def optional(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def database_url() -> str:
    return require("DATABASE_URL")


def auth_credentials() -> tuple[str, str]:
    """The single HTTP Basic user and secret. Both are required: the app never starts ungated."""
    return require("CAPITAL_USER"), require("CAPITAL_PASSWORD")


def unlock_code() -> str:
    """PIN for the Net worth page. Empty means the page stays locked (fail closed)."""
    return optional("CAPITAL_PIN")


def cookie_key() -> str:
    return require("CAPITAL_COOKIE_SECRET")


def port() -> int:
    try:
        return int(os.environ.get("PORT") or os.environ.get("CAPITAL_PORT") or "8700")
    except ValueError:
        return 8700
