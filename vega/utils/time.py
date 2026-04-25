"""IST timezone helpers and market hours checker."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .nse import NSE_HOLIDAYS_2026

IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PREMARKET_START = time(9, 0)
POSTMARKET_END = time(16, 0)
SENTIMENT_START = time(8, 45)  # start sentiment before pre-market


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> date:
    return now_ist().date()


def is_weekend(d: date | None = None) -> bool:
    d = d or today_ist()
    return d.weekday() >= 5


def is_holiday(d: date | None = None) -> bool:
    d = d or today_ist()
    return d in NSE_HOLIDAYS_2026


def is_trading_day(d: date | None = None) -> bool:
    d = d or today_ist()
    return not is_weekend(d) and not is_holiday(d)


def is_market_open() -> bool:
    now = now_ist()
    if not is_trading_day(now.date()):
        return False
    t = now.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


def is_premarket() -> bool:
    now = now_ist()
    if not is_trading_day(now.date()):
        return False
    t = now.time()
    return PREMARKET_START <= t < MARKET_OPEN


def should_poll_sentiment() -> bool:
    now = now_ist()
    if not is_trading_day(now.date()):
        return False
    t = now.time()
    return SENTIMENT_START <= t <= MARKET_CLOSE


def next_market_open() -> datetime:
    now = now_ist()
    d = now.date()
    opening = datetime.combine(d, MARKET_OPEN, tzinfo=IST)

    if now < opening and is_trading_day(d):
        return opening

    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return datetime.combine(d, MARKET_OPEN, tzinfo=IST)


def seconds_until_market_open() -> float:
    delta = next_market_open() - now_ist()
    return max(0.0, delta.total_seconds())


def format_ist(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%d-%b-%Y %I:%M:%S %p IST")
