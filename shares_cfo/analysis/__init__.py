"""Analysis layer — technical indicators + (later) fundamentals provider chain.

Kept separate from the broker/read layer. Pure indicator math has no I/O so it
is unit-testable; data providers (yfinance now, EODHD/Screener later) are isolated.
"""
