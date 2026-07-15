"""In-memory access-token store for headless (Railway) deployment.

On your PC the token lives in .env. On an always-on server there's no browser and
.env isn't the pattern, so the daily phone-login flow (/hdfc/login → /hdfc/callback)
writes the freshly-exchanged token here, and request handlers read it. Tokens are
same-day, so an in-process store is enough: each morning's login re-arms it; a
process restart just needs another login.
"""

from __future__ import annotations

_TOKENS: dict[str, str] = {}
# Which account a login is currently in progress for (HDFC's callback can't carry
# our state, so /hdfc/login records it and /hdfc/callback reads it).
_PENDING: dict[str, str] = {"key": "HDFC1"}


def set_pending(creds_key: str) -> None:
    _PENDING["key"] = creds_key.upper()


def get_pending() -> str:
    return _PENDING["key"]


def armed_accounts() -> list[str]:
    return sorted(_TOKENS.keys())


def set_token(creds_key: str, access_token: str) -> None:
    _TOKENS[creds_key.upper()] = access_token


def get_token(creds_key: str) -> str | None:
    return _TOKENS.get(creds_key.upper())


def is_armed(creds_key: str) -> bool:
    return bool(_TOKENS.get(creds_key.upper()))
