"""Exception hierarchy for Shares CFO.

Kept deliberately small and read-only: there is no OrderError here because this
package never places orders.
"""

from __future__ import annotations


class SharesCFOError(Exception):
    """Base for all Shares CFO errors."""


class ConfigError(SharesCFOError):
    """Missing or malformed configuration (usually a missing .env value)."""


class BrokerError(SharesCFOError):
    """Error talking to a broker API."""


class AuthenticationError(BrokerError):
    """Login / token exchange failed."""


class TokenExpiredError(AuthenticationError):
    """The access token is missing or expired (HDFC tokens are same-day).

    Carries a plain-language instruction telling the user exactly how to fix it,
    so the app can surface it verbatim instead of failing silently.
    """

    def __init__(self, creds_key: str, message: str | None = None) -> None:
        self.creds_key = creds_key
        self.action = (
            f"Your HDFC session for {creds_key} has expired (they expire the same day). "
            f"Re-login by running:  python scripts/hdfc_login.py {creds_key}"
        )
        super().__init__(message or self.action)


class RateLimitError(BrokerError):
    """Broker API rate limit hit."""
