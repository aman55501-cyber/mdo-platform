"""NSE-specific constants: lot sizes, circuit limits, holidays."""

from __future__ import annotations

from datetime import date

# F&O lot sizes — verified against NSE contract specs Apr/May/Jun 2026 series
# Source: Dhan NSE F&O lot size list, cross-checked with HDFC Sky / NSE circulars
# ⚠ NSE revises lot sizes periodically. Re-verify before live F&O trading.
# Last verified: 2026-04-24
LOT_SIZES: dict[str, int] = {
    # Indices (effective Jan 2026 — reduced from Nov 2024 sizes)
    "NIFTY": 65,          # was 75 (Nov 2024–Dec 2025)
    "BANKNIFTY": 30,      # was 35 (Nov 2024–Dec 2025)
    "FINNIFTY": 60,       # was 65 (Nov 2024–Dec 2025)
    "MIDCPNIFTY": 120,    # was 140 (Nov 2024–Dec 2025)
    # Individual stocks (verified Apr 2026)
    "RELIANCE": 500,
    "TCS": 175,
    "INFY": 400,
    "HDFCBANK": 550,
    "ICICIBANK": 700,
    "SBIN": 750,
    "ITC": 1600,
    "BHARTIARTL": 475,
    "LT": 175,
    "KOTAKBANK": 2000,
    "AXISBANK": 625,
    "HINDUNILVR": 300,
    "BAJFINANCE": 750,
    "TATAMOTORS": 575,    # ⚠ not confirmed in Apr 2026 contract list — verify before use
    "TATASTEEL": 5500,
    "WIPRO": 3000,
    "MARUTI": 50,
    "SUNPHARMA": 350,
    "ADANIENT": 309,
    "ADANIPORTS": 475,
}

# Circuit limit bands
CIRCUIT_BANDS = [2, 5, 10, 20]

# NSE holidays 2026 (update annually)
NSE_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 26),   # Republic Day
    date(2026, 2, 17),   # Maha Shivaratri
    date(2026, 3, 10),   # Holi
    date(2026, 3, 31),   # Id-Ul-Fitr
    date(2026, 4, 2),    # Ram Navami
    date(2026, 4, 3),    # Good Friday
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 6, 7),    # Bakri Id
    date(2026, 7, 7),    # Muharram
    date(2026, 8, 15),   # Independence Day
    date(2026, 8, 19),   # Janmashtami
    date(2026, 9, 5),    # Milad-Un-Nabi
    date(2026, 10, 2),   # Mahatma Gandhi Jayanti
    date(2026, 10, 20),  # Dussehra
    date(2026, 11, 9),   # Diwali (Lakshmi Puja)
    date(2026, 11, 10),  # Diwali (Balipratipada)
    date(2026, 11, 19),  # Guru Nanak Jayanti
    date(2026, 12, 25),  # Christmas
}


def get_lot_size(ticker: str) -> int:
    """Get F&O lot size. Returns 1 for cash segment tickers not in F&O."""
    return LOT_SIZES.get(ticker.upper(), 1)


def is_fo_stock(ticker: str) -> bool:
    return ticker.upper() in LOT_SIZES
