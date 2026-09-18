"""Single-user HTTP Basic gate.

Chosen over a login form / Cloudflare Access because it is the simplest thing that
works on Railway: one username + password in .env, checked on *every* route
including /ask (which costs money per call, so it must be behind the same gate).
The phone's browser remembers it after the first prompt.

Only /healthz is exempt — it returns a bare "ok" with no data, so Railway's health
check can reach it without a credential. Nothing sensitive is ever unguarded.

Comparisons use hmac.compare_digest to avoid leaking timing information.
"""

from __future__ import annotations

import base64
import binascii
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import auth_credentials

# Paths reachable without auth. Keep this list tiny and data-free.
_OPEN_PATHS = {"/healthz"}

_UNAUTHORIZED = Response(
    "Authentication required.",
    status_code=401,
    headers={"WWW-Authenticate": 'Basic realm="LIFEOS", charset="UTF-8"'},
)


def _check(header: str | None) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:].strip()).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user, _, secret = raw.partition(":")
    want_user, want_secret = auth_credentials()
    # compare_digest on both fields; use it even for the username to keep it constant-time
    user_ok = hmac.compare_digest(user, want_user)
    pass_ok = hmac.compare_digest(secret, want_secret)
    return user_ok and pass_ok


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _OPEN_PATHS:
            return await call_next(request)
        if not _check(request.headers.get("Authorization")):
            return _UNAUTHORIZED
        return await call_next(request)
