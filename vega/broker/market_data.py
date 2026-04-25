"""Market data polling and OHLCV construction."""

from __future__ import annotations

import asyncio
from datetime import datetime

import pandas as pd

from ..config import HdfcConfig
from ..data.cache import TTLCache
from ..events import EventBus, MarketDataEvent
from ..utils.logging import get_logger
from ..utils.time import is_market_open, now_ist
from . import endpoints
from .client import HdfcClient

log = get_logger("market_data")


class MarketDataService:
    """Polls HDFC API for market quotes and publishes events."""

    def __init__(
        self, client: HdfcClient, event_bus: EventBus,
        poll_interval: float = 30.0,
    ) -> None:
        self._client = client
        self._event_bus = event_bus
        self._poll_interval = poll_interval
        self._cache = TTLCache(maxsize=100, ttl_seconds=15)
        self._running = False
        # Store accumulated ticks for building candles
        self._tick_store: dict[str, list[dict]] = {}

    async def get_ltp(self, tickers: list[str]) -> dict[str, float]:
        """Get Last Traded Price for multiple tickers."""
        cached = {}
        to_fetch = []
        for t in tickers:
            val = self._cache.get(f"ltp:{t}")
            if val is not None:
                cached[t] = val
            else:
                to_fetch.append(t)

        if not to_fetch:
            return cached

        try:
            data = await self._client.get(
                endpoints.LTP,
                params={"symbols": ",".join(to_fetch), "exchange": "NSE"},
            )
            quotes = data.get("data", data.get("quotes", []))
            if isinstance(quotes, dict):
                quotes = [quotes]

            result = dict(cached)
            for q in quotes:
                ticker = q.get("symbol", q.get("tradingSymbol", ""))
                ltp = float(q.get("ltp", q.get("lastPrice", 0)))
                result[ticker] = ltp
                self._cache.set(f"ltp:{ticker}", ltp)
                # Accumulate tick for candle building
                self._accumulate_tick(ticker, ltp)
            return result
        except Exception as exc:
            log.error("ltp_fetch_error", error=str(exc))
            return cached

    def _accumulate_tick(self, ticker: str, price: float) -> None:
        if ticker not in self._tick_store:
            self._tick_store[ticker] = []
        self._tick_store[ticker].append({
            "timestamp": now_ist(),
            "price": price,
        })
        # Keep only last 2 hours of ticks
        cutoff = now_ist().timestamp() - 7200
        self._tick_store[ticker] = [
            t for t in self._tick_store[ticker]
            if t["timestamp"].timestamp() > cutoff
        ]

    def build_candles(self, ticker: str, interval_minutes: int = 5) -> pd.DataFrame:
        """Build OHLCV candles from accumulated tick data."""
        ticks = self._tick_store.get(ticker, [])
        if not ticks:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

        df = pd.DataFrame(ticks)
        df.set_index("timestamp", inplace=True)
        rule = f"{interval_minutes}min"
        ohlc = df["price"].resample(rule).ohlc()
        ohlc.columns = ["Open", "High", "Low", "Close"]
        ohlc["Volume"] = df["price"].resample(rule).count()
        ohlc.dropna(inplace=True)
        return ohlc

    async def poll_loop(self, tickers: list[str]) -> None:
        """Continuous polling loop. Publishes MarketDataEvent to EventBus."""
        self._running = True
        log.info("market_data_polling_started", tickers=tickers, interval=self._poll_interval)

        while self._running:
            if not is_market_open():
                await asyncio.sleep(10)
                continue

            try:
                prices = await self.get_ltp(tickers)
                for ticker, ltp in prices.items():
                    candles = self.build_candles(ticker)
                    event = MarketDataEvent(
                        ticker=ticker,
                        timeframe="5m",
                        ohlcv=candles,
                        ltp=ltp,
                        timestamp=now_ist(),
                    )
                    await self._event_bus.publish(event)
            except Exception as exc:
                log.error("poll_error", error=str(exc))

            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
