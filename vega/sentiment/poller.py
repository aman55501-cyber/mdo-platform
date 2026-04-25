"""Periodic sentiment polling loop."""

from __future__ import annotations

import asyncio
from datetime import date

from ..config import GrokConfig
from ..data.store import DataStore
from ..events import EventBus, SentimentEvent
from ..utils.logging import get_logger
from ..utils.time import should_poll_sentiment, now_ist
from .analyzer import SentimentAnalyzer
from .client import GrokClient
from .models import SentimentSignal
from .prompts import TICKER_SENTIMENT_PROMPT

log = get_logger("sentiment_poller")


class SentimentPoller:
    """Polls Grok x_search for each watchlist ticker at configured intervals."""

    def __init__(
        self,
        client: GrokClient,
        analyzer: SentimentAnalyzer,
        event_bus: EventBus,
        store: DataStore,
        config: GrokConfig,
    ) -> None:
        self._client = client
        self._analyzer = analyzer
        self._event_bus = event_bus
        self._store = store
        self._config = config
        self._running = False
        self._latest: dict[str, SentimentSignal] = {}

    @property
    def latest_signals(self) -> dict[str, SentimentSignal]:
        return dict(self._latest)

    async def poll_once(self, ticker: str) -> SentimentSignal:
        """Run a single sentiment query for a ticker."""
        today = date.today().isoformat()
        raw = await self._client.analyze_ticker(
            ticker=ticker,
            system_prompt=TICKER_SENTIMENT_PROMPT,
            from_date=today,
            to_date=today,
        )
        signal = self._analyzer.parse_response(ticker, raw)
        self._latest[ticker] = signal

        # Persist
        event = SentimentEvent(
            ticker=signal.ticker,
            score=signal.score,
            confidence=signal.confidence,
            summary=signal.summary,
            themes=signal.themes,
            post_count=signal.post_count,
            timestamp=signal.timestamp,
        )
        await self._store.save_sentiment(event)
        await self._event_bus.publish(event)
        return signal

    async def poll_loop(self, tickers: list[str]) -> None:
        """Poll all tickers at configured interval during market hours."""
        self._running = True
        log.info(
            "sentiment_polling_started",
            tickers=tickers,
            interval=self._config.poll_interval_seconds,
        )

        while self._running:
            if not should_poll_sentiment():
                await asyncio.sleep(30)
                continue

            for ticker in tickers:
                if not self._running:
                    break
                try:
                    signal = await self.poll_once(ticker)
                    log.info(
                        "sentiment_polled",
                        ticker=ticker,
                        score=signal.score,
                        confidence=signal.confidence,
                    )
                except Exception as exc:
                    log.error("sentiment_poll_error", ticker=ticker, error=str(exc))

                # Stagger requests to avoid rate limits
                await asyncio.sleep(15)

            # Wait for next cycle
            remaining = self._config.poll_interval_seconds - (15 * len(tickers))
            if remaining > 0:
                await asyncio.sleep(remaining)

    def stop(self) -> None:
        self._running = False
