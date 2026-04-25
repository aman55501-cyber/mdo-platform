"""Watchlist management."""

from __future__ import annotations

from ..utils.logging import get_logger

log = get_logger("watchlist")


class Watchlist:
    """Manages the list of tickers to monitor."""

    def __init__(self, tickers: list[str] | None = None) -> None:
        self._tickers: list[str] = [t.upper() for t in (tickers or [])]

    @property
    def tickers(self) -> list[str]:
        return list(self._tickers)

    @property
    def count(self) -> int:
        return len(self._tickers)

    def add(self, ticker: str) -> bool:
        t = ticker.upper()
        if t in self._tickers:
            return False
        self._tickers.append(t)
        log.info("watchlist_add", ticker=t)
        return True

    def remove(self, ticker: str) -> bool:
        t = ticker.upper()
        if t not in self._tickers:
            return False
        self._tickers.remove(t)
        log.info("watchlist_remove", ticker=t)
        return True

    def contains(self, ticker: str) -> bool:
        return ticker.upper() in self._tickers
