"""Signal types and scoring utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class TechnicalScore:
    ema_score: float  # 0 or 1 - bullish EMA alignment
    rsi_score: float  # 0 to 1 - how favorable RSI is
    vwap_score: float  # 0 or 1 - price above VWAP
    combined: float = 0.0

    def __post_init__(self) -> None:
        # Weighted: EMA 40%, RSI 30%, VWAP 30%
        self.combined = (
            0.40 * self.ema_score +
            0.30 * self.rsi_score +
            0.30 * self.vwap_score
        )


def compute_ema_score(ema_bullish: bool) -> float:
    return 1.0 if ema_bullish else 0.0


def compute_rsi_score(rsi_value: float, overbought: float = 70.0, oversold: float = 30.0) -> float:
    """Score RSI for buy opportunity. Best when RSI is moderate (40-60)."""
    if rsi_value >= overbought:
        return 0.0  # Overbought, bad for buying
    elif rsi_value <= oversold:
        return 0.8  # Oversold, good for buying
    elif 40 <= rsi_value <= 60:
        return 1.0  # Sweet spot
    elif rsi_value < 40:
        return 0.9  # Still good
    else:
        # 60-70 range: linearly decrease
        return max(0.0, 1.0 - (rsi_value - 60) / 10)


def compute_vwap_score(price: float, vwap: float) -> float:
    return 1.0 if price > vwap else 0.0


def compute_combined_score(technical: float, sentiment: float) -> float:
    """Combine technical and sentiment scores. 60/40 weighting."""
    # Normalize sentiment from [-1, 1] to [0, 1]
    sentiment_normalized = (sentiment + 1.0) / 2.0
    return 0.60 * technical + 0.40 * sentiment_normalized
