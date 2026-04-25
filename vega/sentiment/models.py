"""Sentiment data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SentimentSignal:
    ticker: str
    score: float  # -1.0 (very bearish) to +1.0 (very bullish)
    confidence: float  # 0.0 to 1.0
    summary: str = ""
    themes: list[str] = field(default_factory=list)
    post_count: int = 0
    notable_accounts: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
