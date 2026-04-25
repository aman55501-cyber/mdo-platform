"""Sentiment scoring and signal extraction from Grok responses."""

from __future__ import annotations

from datetime import datetime

from ..utils.logging import get_logger
from .models import SentimentSignal

log = get_logger("sentiment_analyzer")


class SentimentAnalyzer:
    """Parses Grok API responses into structured SentimentSignal objects."""

    def parse_response(self, ticker: str, raw: dict) -> SentimentSignal:
        score = self._clamp(float(raw.get("score", 0.0)), -1.0, 1.0)
        confidence = self._clamp(float(raw.get("confidence", 0.0)), 0.0, 1.0)

        return SentimentSignal(
            ticker=ticker,
            score=score,
            confidence=confidence,
            summary=raw.get("summary", ""),
            themes=raw.get("themes", []),
            post_count=int(raw.get("post_count", 0)),
            notable_accounts=raw.get("notable_accounts", []),
            timestamp=datetime.now(),
        )

    def is_signal_strong(self, signal: SentimentSignal, min_confidence: float = 0.5) -> bool:
        """Check if sentiment signal is strong enough to factor into trading."""
        return signal.confidence >= min_confidence and abs(signal.score) >= 0.2

    def is_bullish(self, signal: SentimentSignal, threshold: float = 0.3) -> bool:
        return signal.score >= threshold and signal.confidence >= 0.5

    def is_bearish(self, signal: SentimentSignal, threshold: float = -0.2) -> bool:
        return signal.score <= threshold and signal.confidence >= 0.5

    @staticmethod
    def _clamp(value: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, value))
