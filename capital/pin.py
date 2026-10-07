"""PIN gate for the Net worth page.

A correct PIN sets a short-lived signed cookie. Wrong attempts are counted; after MAX_FAILS the gate locks for
LOCK_SECONDS. With no PIN configured the page stays locked: it fails closed, never open.
"""
from __future__ import annotations

import hashlib
import hmac
import time

TTL_SECONDS = 600
MAX_FAILS = 5
LOCK_SECONDS = 300
COOKIE = "cap_nw"


def make_cookie(key: str, now: float | None = None) -> str:
    exp = int((now if now is not None else time.time()) + TTL_SECONDS)
    sig = hmac.new(key.encode(), str(exp).encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def cookie_valid(value: str | None, key: str, now: float | None = None) -> bool:
    if not value or "." not in value:
        return False
    exp_s, _, sig = value.partition(".")
    if not exp_s.isdigit():
        return False
    good = hmac.new(key.encode(), exp_s.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good) and int(exp_s) > (now if now is not None else time.time())


class PinGuard:
    def __init__(self) -> None:
        self.fails = 0
        self.locked_until = 0.0

    def locked(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) < self.locked_until

    def attempt(self, supplied: str, expected: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if not expected or self.locked(now):
            return False
        if hmac.compare_digest(supplied.encode(), expected.encode()):
            self.fails = 0
            return True
        self.fails += 1
        if self.fails >= MAX_FAILS:
            self.locked_until = now + LOCK_SECONDS
            self.fails = 0
        return False
