"""LIFEOS configuration — read from the environment, fail loudly if missing.

Rule 6 of the brief: secrets live ONLY in .env. This module never prints a secret
and never hard-codes a default credential value. Two access patterns:

  require("NAME")   -> value, or raise ConfigError if unset/blank.
  optional("NAME")  -> value or a supplied non-secret default.

Boot-critical secrets (the HTTP Basic credentials) are validated at server start
via ``auth_credentials()`` so the process fails loudly rather than coming up open.
Per-source secrets (Notion, Gmail, Supabase, ...) are read lazily *inside* their
source fetcher, so a missing one degrades that one panel to UNREACHABLE (rule 2)
instead of aborting the whole run.

.env loading mirrors the existing repo idiom (see mdo_server.py / shares_cfo):
load the project-root .env for local dev; on Railway the vars are injected and the
load is a harmless no-op.
"""

from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # pragma: no cover - trivial import guard, matches mdo_server.py
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass


class ConfigError(RuntimeError):
    """Raised when a required environment value is missing. Message never
    contains the secret's value — only its name."""


# ── time ──────────────────────────────────────────────────────────────────────
# Everything Aman sees is Asia/Kolkata. The run fires at 06:30 IST.
IST = ZoneInfo("Asia/Kolkata")
RUN_HOUR = 6
RUN_MINUTE = 30


# ── primitive accessors ───────────────────────────────────────────────────────
def require(name: str) -> str:
    """Return env var ``name`` or raise ConfigError. Blank counts as missing."""
    val = os.environ.get(name, "").strip()
    if not val:
        raise ConfigError(
            f"Required environment variable {name} is missing or blank. "
            f"Add it to your .env (never to code) and restart."
        )
    return val


def optional(name: str, default: str = "") -> str:
    """Return env var ``name`` or a non-secret default. Use only for
    non-credential values (paths, ports, toggles)."""
    val = os.environ.get(name, "").strip()
    return val or default


def has(name: str) -> bool:
    """True if a source's credential is present, without reading its value."""
    return bool(os.environ.get(name, "").strip())


# ── boot-critical: the auth gate ──────────────────────────────────────────────
def auth_credentials() -> tuple[str, str]:
    """The single HTTP Basic user/password. Both required — the app must never
    come up ungated. Raises ConfigError (loudly) if either is missing."""
    return require("LIFEOS_USER"), require("LIFEOS_PASSWORD")


# ── non-secret runtime config (defaults are paths/ports, never credentials) ────
def db_path() -> Path:
    """SQLite location. Defaults to the Railway volume mount, then a local file.
    A path is not a credential, so a default here does not violate rule 6."""
    override = os.environ.get("LIFEOS_DB_PATH", "").strip()
    if override:
        return Path(override)
    # /data is the Railway persistent volume (see Dockerfile.lifeos). Fall back
    # to a repo-local file for laptop dev.
    railway_vol = Path("/data")
    if railway_vol.is_dir():
        return railway_vol / "lifeos.db"
    return Path(__file__).resolve().parent / "data" / "lifeos.db"


def port() -> int:
    """Railway injects PORT; fall back to LIFEOS_PORT then 8600 for local dev."""
    raw = os.environ.get("PORT") or os.environ.get("LIFEOS_PORT") or "8600"
    try:
        return int(raw)
    except ValueError:
        return 8600
