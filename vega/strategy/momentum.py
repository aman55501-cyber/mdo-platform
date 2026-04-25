"""Core momentum strategy combining technical + sentiment signals."""

from __future__ import annotations

import pandas as pd

from ..config import StrategyConfig
from ..events import SignalEvent
from ..sentiment.models import SentimentSignal
from ..utils.logging import get_logger
from ..utils.time import now_ist
from .indicators import compute_all_indicators
from .risk import RiskManager
from .signals import (
    TechnicalScore,
    compute_combined_score,
    compute_ema_score,
    compute_rsi_score,
    compute_vwap_score,
)

log = get_logger("momentum")


class MomentumStrategy:
    """
    Combines technical indicators with social sentiment for trade signals.

    BUY when ALL true:
      1. EMA_9 > EMA_21 (bullish)
      2. RSI < 70 (not overbought)
      3. Price > VWAP
      4. Sentiment score > +0.3 with confidence > 0.5
      5. No existing position
      6. Risk manager approves

    EXIT when ANY true:
      1. EMA_9 < EMA_21 (bearish)
      2. RSI > 70 (overbought)
      3. Target/stop-loss hit
      4. Sentiment drops below -0.2
    """

    def __init__(self, config: StrategyConfig, risk_manager: RiskManager) -> None:
        self._config = config
        self._risk = risk_manager

    def evaluate(
        self,
        ticker: str,
        ohlcv: pd.DataFrame,
        ltp: float,
        sentiment: SentimentSignal | None,
        available_capital: float,
    ) -> SignalEvent | None:
        """Run strategy evaluation. Returns SignalEvent or None."""

        if ohlcv.empty or len(ohlcv) < self._config.ema_slow + 2:
            return None

        # Compute indicators
        df = compute_all_indicators(
            ohlcv,
            ema_fast=self._config.ema_fast,
            ema_slow=self._config.ema_slow,
            rsi_period=self._config.rsi_period,
        )

        latest = df.iloc[-1]
        ema_bullish = bool(latest.get("EMA_bullish", False))
        rsi_val = float(latest.get("RSI", 50.0))
        vwap_val = float(latest.get("VWAP", ltp))
        atr_val = float(latest.get("ATR", 0.0)) if "ATR" in latest else None

        # Technical scoring
        tech = TechnicalScore(
            ema_score=compute_ema_score(ema_bullish),
            rsi_score=compute_rsi_score(rsi_val, self._config.rsi_overbought, self._config.rsi_oversold),
            vwap_score=compute_vwap_score(ltp, vwap_val),
        )

        # Sentiment scoring
        sent_score = 0.0
        if sentiment and sentiment.confidence >= 0.5:
            sent_score = sentiment.score

        combined = compute_combined_score(tech.combined, sent_score)

        # Check BUY conditions
        buy_conditions = [
            ema_bullish,
            rsi_val < self._config.rsi_overbought,
            ltp > vwap_val,
            (sentiment is None) or (sent_score > 0.3 and sentiment.confidence >= 0.5),
            combined >= 0.65,
        ]

        if not all(buy_conditions):
            return None

        # Calculate risk parameters
        stop_loss = self._risk.calculate_stop_loss(ltp, atr_val)
        target = self._risk.calculate_target(ltp, stop_loss)
        qty = self._risk.calculate_position_size(ltp, stop_loss, available_capital, ticker)

        if qty <= 0:
            return None

        # Build rationale
        rationale_parts = [f"EMA{self._config.ema_fast} > EMA{self._config.ema_slow}"]
        rationale_parts.append(f"RSI={rsi_val:.0f}")
        if ltp > vwap_val:
            rationale_parts.append("Price > VWAP")
        if sentiment and sentiment.confidence >= 0.5:
            rationale_parts.append(f"Sentiment={sent_score:+.2f}")
            if sentiment.themes:
                rationale_parts.append(f"({', '.join(sentiment.themes[:2])})")

        signal = SignalEvent(
            ticker=ticker,
            action="BUY",
            technical_score=tech.combined,
            sentiment_score=sent_score,
            combined_score=combined,
            entry_price=ltp,
            target_price=round(target, 2),
            stop_loss=round(stop_loss, 2),
            quantity=qty,
            rationale=". ".join(rationale_parts),
            timestamp=now_ist(),
        )

        # Risk validation
        valid, reason = self._risk.validate_signal(signal)
        if not valid:
            log.info("signal_rejected_by_risk", ticker=ticker, reason=reason)
            return None

        log.info(
            "signal_generated",
            ticker=ticker,
            action=signal.action,
            score=combined,
            entry=ltp,
            target=target,
            sl=stop_loss,
        )
        return signal

    def check_exit(
        self,
        ticker: str,
        ohlcv: pd.DataFrame,
        ltp: float,
        entry_price: float,
        target: float,
        stop_loss: float,
        sentiment: SentimentSignal | None,
    ) -> tuple[bool, str]:
        """Check if an existing position should be exited."""

        # Price-based exits
        should_exit, reason = self._risk.should_exit(
            ticker, ltp, entry_price, target, stop_loss
        )
        if should_exit:
            return True, reason

        # Technical exits
        if not ohlcv.empty and len(ohlcv) >= self._config.ema_slow + 2:
            df = compute_all_indicators(ohlcv, self._config.ema_fast, self._config.ema_slow)
            latest = df.iloc[-1]

            if not latest.get("EMA_bullish", True):
                return True, "EMA bearish crossover"

            rsi_val = float(latest.get("RSI", 50.0))
            if rsi_val > self._config.rsi_overbought:
                return True, f"RSI overbought ({rsi_val:.0f})"

        # Sentiment exit
        if sentiment and sentiment.confidence >= 0.5 and sentiment.score < -0.2:
            return True, f"Sentiment turned bearish ({sentiment.score:+.2f})"

        return False, ""
