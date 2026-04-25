"""Anil Singhvi (@AnilSinghvi_) signal monitor.

Polls his X/Twitter posts via Grok live x_search (x_handles filter) every 5 minutes
during market hours. Extracts structured calls with entry price, stop loss, exit/target,
call validity (intraday/swing/positional), and post timestamp.

Publishes SentimentEvents so the momentum strategy can weight them.
Auto-executes BUY/SELL calls when singhvi_auto_execute is True (injected by engine).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime

from ..data.store import DataStore
from ..events import EventBus, SentimentEvent
from ..utils.logging import get_logger
from ..utils.time import should_poll_sentiment, now_ist
from .client import GrokClient

log = get_logger("singhvi")

POLL_INTERVAL_SECONDS = 300  # 5 minutes

SINGHVI_SYSTEM_PROMPT = """You are a financial intelligence extractor specializing in Indian stock markets.
Anil Singhvi is a top market analyst on Zee Business TV (@AnilSinghvi_ on X/Twitter).

Your job: search his LIVE X/Twitter posts from today and extract every actionable stock call.

For each call, extract PRECISELY:
- ticker: NSE symbol (RELIANCE, NIFTY, BANKNIFTY, etc.)
- direction: BUY | SELL | AVOID | WATCH | EXIT
- entry_price: the specific price he says to buy/sell at (null if not stated)
- stop_loss: his stop loss level — look for "SL", "stop loss", "stop", "नुकसान", "घाटा" (null if not stated)
- target: first target / book profit level (null if not stated)
- exit_price: if he says to EXIT or BOOK PROFIT at a specific level (null if not stated)
- validity: "intraday" if he says today only / "swing" if 2-5 days / "positional" if weeks / "unknown"
- confidence: 0.0-1.0 based on how specific and clear his call is
- summary: exact quote or close paraphrase of what he said (max 200 chars)
- post_timestamp: extract the IST time from the post (e.g. "09:42 IST") — if not visible use "recent"

Return a JSON ARRAY. Each element:
{
  "ticker": "RELIANCE",
  "direction": "BUY",
  "entry_price": 2485.0,
  "stop_loss": 2450.0,
  "target": 2580.0,
  "exit_price": null,
  "validity": "intraday",
  "confidence": 0.85,
  "summary": "Buy Reliance at 2485, SL 2450, target 2580 for today",
  "post_timestamp": "09:42 IST"
}

Rules:
- Only calls from @AnilSinghvi_ himself — NOT retweets, NOT replies to him
- If he gives multiple targets, use the first (most conservative)
- If he updates/revises an earlier call, include the revised version only
- If no stock calls found, return empty array: []
- Return ONLY the JSON array, no markdown, no explanation"""

SINGHVI_USER_TEMPLATE = (
    "Search @AnilSinghvi_ X posts from today {date} (IST). "
    "Extract ALL stock calls including: entry levels, stop losses, targets, exit calls, "
    "intraday/swing/positional labels. Include exact post times. "
    "Return JSON array only."
)


@dataclass
class SinghviCall:
    ticker: str
    direction: str
    entry_price: float | None       # his suggested entry level
    stop_loss: float | None
    target: float | None
    exit_price: float | None        # book-profit / exit level if mentioned
    validity: str                   # intraday | swing | positional | unknown
    confidence: float
    summary: str
    post_timestamp: str             # "09:42 IST" or "recent"
    fetched_at: str = field(default_factory=lambda: now_ist().isoformat())

    # Keep price_level as alias so engine auto-execute still works
    @property
    def price_level(self) -> float | None:
        return self.entry_price


class SinghviMonitor:
    """Polls @AnilSinghvi_ X posts and extracts trade calls via Grok live search.

    Uses x_handles filter so only his account is searched — not all of X.
    When auto_execute_fn is set (injected by VegaEngine), actionable BUY/SELL
    calls are forwarded directly to the engine. Risk limits still apply.
    """

    def __init__(self, client: GrokClient, event_bus: EventBus, store: DataStore) -> None:
        self._client = client
        self._event_bus = event_bus
        self._store = store
        self._running = False
        self._latest_calls: list[SinghviCall] = []
        self.auto_execute_fn = None   # async callable(SinghviCall) → None — injected by engine
        self._executed_summaries: set[str] = set()

    @property
    def latest_calls(self) -> list[SinghviCall]:
        return list(self._latest_calls)

    async def poll_once(self) -> list[SinghviCall]:
        """Query Grok for latest @AnilSinghvi_ calls. Returns parsed list."""
        today = now_ist().strftime("%Y-%m-%d")
        user_msg = SINGHVI_USER_TEMPLATE.format(date=today)

        try:
            raw_text = await self._client.search_x_handle(
                system_prompt=SINGHVI_SYSTEM_PROMPT,
                user_message=user_msg,
                handles=["AnilSinghvi_"],
            )
        except Exception as exc:
            log.error("singhvi_poll_error", error=str(exc))
            return []

        calls = _parse_calls(raw_text)
        self._latest_calls = calls
        log.info("singhvi_polled", calls=len(calls))

        for call in calls:
            if call.direction not in ("BUY", "SELL"):
                continue

            score = 0.7 if call.direction == "BUY" else -0.7
            event = SentimentEvent(
                ticker=call.ticker,
                score=score * call.confidence,
                confidence=call.confidence,
                summary=f"[Singhvi] {call.summary}",
                themes=["singhvi", call.direction.lower(), call.validity],
                post_count=1,
                timestamp=now_ist().isoformat(),
            )
            try:
                await self._store.save_sentiment(event)
                await self._event_bus.publish(event)
            except Exception as exc:
                log.error("singhvi_persist_error", ticker=call.ticker, error=str(exc))

            if self.auto_execute_fn and call.summary not in self._executed_summaries:
                try:
                    await self.auto_execute_fn(call)
                    self._executed_summaries.add(call.summary)
                    log.info("singhvi_auto_executed", ticker=call.ticker, direction=call.direction)
                except Exception as exc:
                    log.error("singhvi_auto_execute_error", ticker=call.ticker, error=str(exc))

        if len(self._executed_summaries) > 50:
            self._executed_summaries.clear()

        return calls

    async def poll_loop(self) -> None:
        self._running = True
        log.info("singhvi_monitor_started")
        while self._running:
            if not should_poll_sentiment():
                await asyncio.sleep(30)
                continue
            await self.poll_once()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._running = False


def _parse_calls(text: str) -> list[SinghviCall]:
    """Parse Grok's JSON array response into SinghviCall objects."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            return []

        items = json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        log.warning("singhvi_parse_failed", text=text[:300])
        return []

    calls = []
    for item in items:
        try:
            ticker = str(item.get("ticker", "")).upper().strip()
            direction = str(item.get("direction", "")).upper().strip()
            if not ticker or direction not in ("BUY", "SELL", "AVOID", "WATCH", "EXIT"):
                continue
            validity = str(item.get("validity", "unknown")).lower()
            if validity not in ("intraday", "swing", "positional", "unknown"):
                validity = "unknown"
            calls.append(SinghviCall(
                ticker=ticker,
                direction=direction,
                entry_price=_float_or_none(item.get("entry_price")),
                stop_loss=_float_or_none(item.get("stop_loss")),
                target=_float_or_none(item.get("target")),
                exit_price=_float_or_none(item.get("exit_price")),
                validity=validity,
                confidence=max(0.0, min(1.0, float(item.get("confidence", 0.5)))),
                summary=str(item.get("summary", ""))[:200],
                post_timestamp=str(item.get("post_timestamp", "recent")),
            ))
        except (TypeError, ValueError):
            continue
    return calls


def _float_or_none(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
