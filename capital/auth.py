"""Single-user HTTP Basic on every route except /healthz (which returns a bare 'ok' and no data)."""
from __future__ import annotations

import base64
import binascii
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import auth_credentials

_OPEN = {"/healthz"}


def check(header: str | None) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(header[6:].strip()).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    user, _, supplied = raw.partition(":")
    want_user, want_secret = auth_credentials()
    return hmac.compare_digest(user, want_user) & hmac.compare_digest(supplied, want_secret)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _OPEN:
            return await call_next(request)
        if not check(request.headers.get("Authorization")):
            return Response("Authentication required.", status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="Capital", charset="UTF-8"'})
        return await call_next(request)
