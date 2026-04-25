"""Async event bus and event types for VEGA."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Literal

import pandas as pd


class EventType(str, Enum):
    MARKET_DATA = "market_data"
    SENTIMENT = "sentiment"
    SIGNAL = "signal"
    TRADE_CONFIRM = "trade_confirm"
    ORDER_UPDATE = "order_update"
    SYSTEM = "system"


@dataclass
class MarketDataEvent:
    ticker: str
    timeframe: str  # "1m", "5m", "15m"
    ohlcv: pd.DataFrame
    ltp: float
    timestamp: datetime
    event_type: EventType = field(default=EventType.MARKET_DATA, init=False)


@dataclass
class SentimentEvent:
    ticker: str
    score: float  # -1.0 to +1.0
    confidence: float  # 0.0 to 1.0
    summary: str
    themes: list[str]
    post_count: int
    timestamp: datetime
    event_type: EventType = field(default=EventType.SENTIMENT, init=False)


@dataclass
class SignalEvent:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ticker: str = ""
    action: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    exchange: str = "NSE"
    product_type: str = "MIS"  # MIS for intraday, NRML for F&O, CNC for delivery
    technical_score: float = 0.0
    sentiment_score: float = 0.0
    combined_score: float = 0.0
    entry_price: float = 0.0
    target_price: float = 0.0
    stop_loss: float = 0.0
    quantity: int = 0
    rationale: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    event_type: EventType = field(default=EventType.SIGNAL, init=False)


@dataclass
class TradeConfirmEvent:
    signal_id: str
    confirmed: bool
    modified_qty: int | None = None
    user_note: str | None = None
    event_type: EventType = field(default=EventType.TRADE_CONFIRM, init=False)


@dataclass
class OrderUpdateEvent:
    order_id: str
    ticker: str
    status: str  # "placed", "filled", "cancelled", "rejected"
    fill_price: float | None = None
    fill_qty: int | None = None
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    event_type: EventType = field(default=EventType.ORDER_UPDATE, init=False)


Event = MarketDataEvent | SentimentEvent | SignalEvent | TradeConfirmEvent | OrderUpdateEvent


class EventBus:
    """Async pub/sub event bus using asyncio.Queue per event type."""

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._queue: asyncio.Queue[Event] = asyncio.Queue()
        self._running = False

    def subscribe(self, event_type: EventType, callback: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    async def publish(self, event: Event) -> None:
        await self._queue.put(event)

    async def start(self) -> None:
        self._running = True
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            callbacks = self._subscribers.get(event.event_type, [])
            for cb in callbacks:
                try:
                    result = cb(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    import structlog

                    structlog.get_logger().error(
                        "event_handler_error",
                        event_type=event.event_type,
                        error=str(exc),
                    )

    def stop(self) -> None:
        self._running = False
