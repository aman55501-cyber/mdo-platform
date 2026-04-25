"""Technical indicators: EMA, RSI, VWAP (pure pandas/numpy)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def vwap(df: pd.DataFrame) -> pd.Series:
    """Volume Weighted Average Price. Expects columns: High, Low, Close, Volume."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_tp_vol = (typical_price * df["Volume"]).cumsum()
    cum_vol = df["Volume"].cumsum()
    return cum_tp_vol / cum_vol


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - close).abs(),
        (low - close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Upper band, middle band (SMA), lower band."""
    middle = sma(series, period)
    std = series.rolling(window=period).std()
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    return upper, middle, lower


def compute_all_indicators(
    df: pd.DataFrame,
    ema_fast: int = 9,
    ema_slow: int = 21,
    rsi_period: int = 14,
) -> pd.DataFrame:
    """Add all indicator columns to a DataFrame with OHLCV data."""
    result = df.copy()
    close = result["Close"]

    result["EMA_fast"] = ema(close, ema_fast)
    result["EMA_slow"] = ema(close, ema_slow)
    result["RSI"] = rsi(close, rsi_period)
    result["ATR"] = atr(result)

    if "Volume" in result.columns and result["Volume"].sum() > 0:
        result["VWAP"] = vwap(result)
    else:
        result["VWAP"] = close  # Fallback if no volume data

    result["EMA_crossover"] = (
        (result["EMA_fast"] > result["EMA_slow"]) &
        (result["EMA_fast"].shift(1) <= result["EMA_slow"].shift(1))
    )
    result["EMA_crossunder"] = (
        (result["EMA_fast"] < result["EMA_slow"]) &
        (result["EMA_fast"].shift(1) >= result["EMA_slow"].shift(1))
    )
    result["EMA_bullish"] = result["EMA_fast"] > result["EMA_slow"]

    return result
