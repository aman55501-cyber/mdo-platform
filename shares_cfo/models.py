"""Read-only data models for Shares CFO.

There is intentionally no Order / OrderResponse model here — this package cannot
express the concept of placing a trade.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Holding:
    ticker: str
    exchange: str = "NSE"
    quantity: int = 0
    average_price: float = 0.0
    last_price: float = 0.0
    pnl: float = 0.0
    sector: str = "UNKNOWN"
    day_change: float = 0.0        # today's rupee change for this holding (from HDFC)
    day_change_pct: float = 0.0    # today's % change (from HDFC)
    isin: str = ""
    security_id: str = ""
    token: str = ""                # numeric instrument token (for fetch-ltp)

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "exchange": self.exchange,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "last_price": self.last_price,
            "pnl": self.pnl,
            "sector": self.sector,
            "day_change": self.day_change,
            "day_change_pct": self.day_change_pct,
            "isin": self.isin,
            "security_id": self.security_id,
            "market_value": round(self.market_value, 2),
        }


@dataclass
class Position:
    """F&O / intraday position."""

    ticker: str
    exchange: str = "NSE"
    product_type: str = "NRML"
    quantity: int = 0
    average_price: float = 0.0
    last_price: float = 0.0
    pnl: float = 0.0
    day_pnl: float = 0.0
    token: str = ""                # numeric instrument token (for fetch-ltp)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "exchange": self.exchange,
            "product_type": self.product_type,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "last_price": self.last_price,
            "pnl": self.pnl,
            "day_pnl": self.day_pnl,
        }


@dataclass
class FundInfo:
    available: float = 0.0        # total available limit/margin
    used_margin: float = 0.0      # total utilised limit
    total: float = 0.0            # total limit
    cash: float = 0.0             # free cash (totalAvailableLimitDetails.cash)
    ledger_balance: float = 0.0   # broker ledger balance

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "used_margin": self.used_margin,
            "total": self.total,
            "cash": self.cash,
            "ledger_balance": self.ledger_balance,
        }


@dataclass
class AccountBook:
    """One account's holdings/positions/cash, plus its health.

    `ok=False` means this account failed to fetch — its numbers are absent and the
    consolidated book must be flagged incomplete (never silently dropped).
    """

    creds_key: str
    client_code: str = ""
    label: str = ""
    ok: bool = True
    status: str = "ok"          # "ok" | "degraded"
    reason: str = ""            # plain-language reason when degraded
    notes: list[str] = field(default_factory=list)  # partial-data notes (book still ok)
    holdings: list[Holding] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    funds: FundInfo = field(default_factory=FundInfo)
    fetched_at: str = ""        # ISO timestamp of the successful pull

    @property
    def holdings_value(self) -> float:
        return sum(h.market_value for h in self.holdings)

    def to_dict(self) -> dict:
        return {
            "creds_key": self.creds_key,
            "client_code": self.client_code,
            "label": self.label,
            "ok": self.ok,
            "status": self.status,
            "reason": self.reason,
            "notes": self.notes,
            "fetched_at": self.fetched_at,
            "holdings": [h.to_dict() for h in self.holdings],
            "positions": [p.to_dict() for p in self.positions],
            "funds": self.funds.to_dict(),
            "holdings_value": round(self.holdings_value, 2),
        }
