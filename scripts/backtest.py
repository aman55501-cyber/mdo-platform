"""Offline backtesting using historical data from yfinance.

Run: python -m scripts.backtest --ticker RELIANCE.NS --days 180
"""

import argparse
from datetime import datetime, timedelta

import pandas as pd


def run_backtest(ticker: str, days: int) -> None:
    try:
        import yfinance as yf
    except ImportError:
        print("Install backtest dependencies: pip install vega[backtest]")
        return

    end = datetime.now()
    start = end - timedelta(days=days)

    print(f"Downloading {ticker} data from {start.date()} to {end.date()}...")
    df = yf.download(ticker, start=start, end=end, interval="1d")

    if df.empty:
        print("No data found.")
        return

    from vega.strategy.indicators import compute_all_indicators
    from vega.strategy.signals import (
        compute_ema_score,
        compute_rsi_score,
        compute_vwap_score,
    )

    df = compute_all_indicators(df)

    trades = []
    in_position = False
    entry_price = 0.0
    entry_date = None

    for i in range(len(df)):
        row = df.iloc[i]
        close = float(row["Close"])
        rsi_val = float(row.get("RSI", 50))
        ema_bull = bool(row.get("EMA_bullish", False))
        vwap_val = float(row.get("VWAP", close))

        if not in_position:
            # Check buy
            if ema_bull and rsi_val < 70 and close > vwap_val and i > 0:
                entry_price = close
                entry_date = df.index[i]
                in_position = True
        else:
            # Check exit
            sl = entry_price * 0.985
            target = entry_price * 1.03
            if close <= sl or close >= target or not ema_bull or rsi_val > 70:
                pnl_pct = (close - entry_price) / entry_price * 100
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": df.index[i],
                    "entry": entry_price,
                    "exit": close,
                    "pnl_pct": pnl_pct,
                    "reason": "SL" if close <= sl else "Target" if close >= target else "Signal",
                })
                in_position = False

    if not trades:
        print("No trades generated.")
        return

    results = pd.DataFrame(trades)
    wins = len(results[results["pnl_pct"] > 0])
    losses = len(results[results["pnl_pct"] <= 0])
    total = len(results)

    print(f"\n{'='*50}")
    print(f"BACKTEST RESULTS: {ticker}")
    print(f"{'='*50}")
    print(f"Period: {days} days")
    print(f"Total trades: {total}")
    print(f"Wins: {wins} | Losses: {losses}")
    print(f"Win rate: {wins/total*100:.1f}%")
    print(f"Avg P&L per trade: {results['pnl_pct'].mean():.2f}%")
    print(f"Max win: {results['pnl_pct'].max():.2f}%")
    print(f"Max loss: {results['pnl_pct'].min():.2f}%")
    print(f"Total return: {results['pnl_pct'].sum():.2f}%")
    print(f"\nRecent trades:")
    print(results.tail(10).to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VEGA Backtest")
    parser.add_argument("--ticker", default="RELIANCE.NS", help="Yahoo Finance ticker")
    parser.add_argument("--days", type=int, default=180, help="Days of history")
    args = parser.parse_args()
    run_backtest(args.ticker, args.days)
