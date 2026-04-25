"""In-memory LRU cache for market data and sentiment."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any


class TTLCache:
    """Simple TTL + LRU cache for caching API responses."""

    def __init__(self, maxsize: int = 256, ttl_seconds: int = 60) -> None:
        self._maxsize = maxsize
        self._ttl = timedelta(seconds=ttl_seconds)
        self._cache: OrderedDict[str, tuple[Any, datetime]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        value, ts = self._cache[key]
        if datetime.now() - ts > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, datetime.now())
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)
