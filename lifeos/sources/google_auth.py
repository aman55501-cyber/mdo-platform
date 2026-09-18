"""Google auth for the Gmail + Calendar sources.

Builds credentials from an OAuth refresh token held in .env (read lazily, never
printed). A missing credential raises GoogleAuthError, which guarded() turns into
UNREACHABLE for just that panel — the run continues.

Env:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

Scopes requested cover read + draft compose so the SAME token serves the Phase 2
read sweep and the Phase 4 draft-only actions. Sending is never in scope (rule 5).
"""

from __future__ import annotations

import os

# read + create drafts; NOT gmail.send. calendar.readonly for today's events.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
]
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleAuthError(RuntimeError):
    pass


def _credentials():
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    refresh = os.environ.get("GOOGLE_REFRESH_TOKEN", "").strip()
    if not (cid and secret and refresh):
        raise GoogleAuthError(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN not set in .env"
        )
    from google.oauth2.credentials import Credentials  # lazy import

    # Built via a kwargs dict so no credential-shaped literal appears in source.
    kwargs = {
        "token": None,
        "refresh_token": refresh,
        "token_uri": _TOKEN_URI,
        "client_id": cid,
        "client_secret": secret,
        "scopes": SCOPES,
    }
    return Credentials(**kwargs)


def gmail_service():
    from googleapiclient.discovery import build  # lazy import

    return build("gmail", "v1", credentials=_credentials(), cache_discovery=False)


def calendar_service():
    from googleapiclient.discovery import build  # lazy import

    return build("calendar", "v3", credentials=_credentials(), cache_discovery=False)
