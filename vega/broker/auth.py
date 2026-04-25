"""HDFC Securities OAuth2 + OTP authentication flow.

The OTP is relayed to the user via Telegram and submitted back
through the Telegram chat interface.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx

from ..config import HdfcConfig
from ..exceptions import AuthenticationError
from ..utils.logging import get_logger
from ..utils.retry import async_retry
from . import endpoints
from .models import SessionToken

log = get_logger("hdfc_auth")


class HdfcAuth:
    """Manages HDFC Securities OAuth2 + OTP authentication."""

    def __init__(self, config: HdfcConfig) -> None:
        self._config = config
        self._session: SessionToken | None = None
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=30.0,
        )
        self._otp_future: asyncio.Future[str] | None = None
        self._request_id: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self._session is not None and not self._session.is_expired

    @property
    def access_token(self) -> str | None:
        if self.is_authenticated:
            return self._session.access_token
        return None

    @property
    def awaiting_otp(self) -> bool:
        return self._otp_future is not None and not self._otp_future.done()

    async def initiate_login(self) -> str:
        """Start login flow. Returns a request_id. HDFC sends OTP to user's phone."""
        log.info("login_initiated")
        try:
            resp = await self._http.post(
                endpoints.LOGIN_INITIATE,
                json={
                    "api_key": self._config.api_key,
                    "api_secret": self._config.api_secret,
                    "redirect_url": self._config.redirect_url,
                },
            )
            log.info("login_response", status=resp.status_code, body=resp.text[:500])
            resp.raise_for_status()
            data = resp.json()
            self._request_id = data.get("request_id", data.get("requestId", ""))
            log.info("otp_sent", request_id=self._request_id)
            return self._request_id
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if exc.response else ""
            raise AuthenticationError(
                f"Login failed [HTTP {exc.response.status_code}]: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Login network error: {exc}") from exc

    async def wait_for_otp(self, timeout: float = 120.0) -> str:
        """Wait for OTP to be submitted via Telegram. Returns the OTP string."""
        loop = asyncio.get_running_loop()
        self._otp_future = loop.create_future()
        try:
            otp = await asyncio.wait_for(self._otp_future, timeout=timeout)
            return otp
        except asyncio.TimeoutError:
            self._otp_future = None
            raise AuthenticationError("OTP timeout - no OTP received within 2 minutes")

    def submit_otp(self, otp: str) -> None:
        """Called by Telegram handler when user sends OTP."""
        if self._otp_future and not self._otp_future.done():
            self._otp_future.set_result(otp)

    def cancel_otp(self) -> None:
        if self._otp_future and not self._otp_future.done():
            self._otp_future.set_exception(AuthenticationError("Login cancelled by user"))
            self._otp_future = None

    @async_retry(max_attempts=2, exceptions=(httpx.HTTPError,))
    async def complete_login(self, otp: str) -> SessionToken:
        """Submit OTP to complete authentication."""
        try:
            resp = await self._http.post(
                endpoints.LOGIN_OTP,
                json={
                    "request_id": self._request_id,
                    "otp": otp,
                    "api_key": self._config.api_key,
                },
            )
            log.info("otp_response", status=resp.status_code, body=resp.text[:500])
            resp.raise_for_status()
            data = resp.json()

            self._session = SessionToken(
                access_token=data.get("access_token", data.get("token", "")),
                expires_at=datetime.now() + timedelta(hours=8),
                refresh_token=data.get("refresh_token"),
            )
            log.info("login_successful")
            return self._session
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if exc.response else ""
            raise AuthenticationError(
                f"OTP failed [HTTP {exc.response.status_code}]: {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"OTP network error: {exc}") from exc

    async def logout(self) -> None:
        if self._session:
            try:
                await self._http.post(
                    endpoints.LOGOUT,
                    headers={"Authorization": f"Bearer {self._session.access_token}"},
                )
            except httpx.HTTPError:
                pass
            self._session = None
            log.info("logged_out")

    async def close(self) -> None:
        await self._http.aclose()
