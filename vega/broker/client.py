"""Async HTTP client wrapper for HDFC Securities API."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from ..config import HdfcConfig
from ..exceptions import BrokerError, RateLimitError
from ..utils.logging import get_logger
from ..utils.retry import async_retry
from .auth import HdfcAuth

log = get_logger("hdfc_client")


class HdfcClient:
    """Authenticated async HTTP wrapper for HDFC Securities REST API."""

    def __init__(self, config: HdfcConfig, auth: HdfcAuth) -> None:
        self._config = config
        self._auth = auth
        self._http = httpx.AsyncClient(
            base_url=config.base_url,
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )
        # Token bucket for SEBI rate limiting (10 orders/sec)
        self._rate_semaphore = asyncio.Semaphore(config.max_orders_per_sec)
        self._order_timestamps: list[float] = []

    @property
    def is_authenticated(self) -> bool:
        return self._auth.is_authenticated

    @async_retry(max_attempts=3, backoff_base=0.5, exceptions=(httpx.HTTPError,))
    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> dict:
        if not self._auth.is_authenticated:
            raise BrokerError("Not authenticated. Please login first.")

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._auth.access_token}"

        resp = await self._http.request(method, path, headers=headers, **kwargs)

        if resp.status_code == 429:
            raise RateLimitError("HDFC API rate limit exceeded")

        resp.raise_for_status()
        return resp.json()

    async def get(self, path: str, **kwargs: Any) -> dict:
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> dict:
        return await self._request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> dict:
        return await self._request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> dict:
        return await self._request("DELETE", path, **kwargs)

    async def rate_limited_post(self, path: str, **kwargs: Any) -> dict:
        """POST with SEBI-compliant rate limiting (max 10 orders/sec)."""
        async with self._rate_semaphore:
            now = asyncio.get_event_loop().time()
            # Clean old timestamps
            self._order_timestamps = [
                t for t in self._order_timestamps if now - t < 1.0
            ]
            if len(self._order_timestamps) >= self._config.max_orders_per_sec:
                wait = 1.0 - (now - self._order_timestamps[0])
                if wait > 0:
                    await asyncio.sleep(wait)
            self._order_timestamps.append(asyncio.get_event_loop().time())
            return await self.post(path, **kwargs)

    async def close(self) -> None:
        await self._http.aclose()
