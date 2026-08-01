"""Access-token store — persisted to disk so logins survive container restarts.

On an always-on server the daily phone-login (/hdfc/login → /hdfc/callback) and
Angel's server-side login write the token here. Tokens are same-day, so we persist
them to the state volume with today's date and auto-discard anything older — a
container rebuild no longer forces every account to log in again.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_FILE = Path(__file__).resolve().parent / "data" / "state" / "tokens.json"
_TOKENS: dict[str, str] = {}
_FEEDS: dict[str, str] = {}          # Angel feed tokens (for the live WebSocket), same-day
_PENDING: dict[str, str] = {"key": "HDFC1"}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> None:
    """Load tokens if they're from today; otherwise start empty (expired overnight)."""
    try:
        if _FILE.exists():
            data = json.loads(_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("date") == _today():
                toks = data.get("tokens")
                if isinstance(toks, dict):
                    _TOKENS.update({k: v for k, v in toks.items() if v})
                feeds = data.get("feeds")
                if isinstance(feeds, dict):
                    _FEEDS.update({k: v for k, v in feeds.items() if v})
    except (OSError, ValueError):
        pass


def _save() -> None:
    try:
        _FILE.parent.mkdir(parents=True, exist_ok=True)
        _FILE.write_text(json.dumps({"date": _today(), "tokens": _TOKENS, "feeds": _FEEDS}),
                         encoding="utf-8")
    except OSError:
        pass


def set_feed(creds_key: str, feed_token: str) -> None:
    if feed_token:
        _FEEDS[creds_key.upper()] = feed_token
        _save()


def get_feed(creds_key: str) -> str | None:
    return _FEEDS.get(creds_key.upper())


def set_pending(creds_key: str) -> None:
    _PENDING["key"] = creds_key.upper()


def get_pending() -> str:
    return _PENDING["key"]


def armed_accounts() -> list[str]:
    return sorted(_TOKENS.keys())


def set_token(creds_key: str, access_token: str) -> None:
    _TOKENS[creds_key.upper()] = access_token
    _save()


def get_token(creds_key: str) -> str | None:
    return _TOKENS.get(creds_key.upper())


def is_armed(creds_key: str) -> bool:
    return bool(_TOKENS.get(creds_key.upper()))


_load()  # restore today's tokens on import
