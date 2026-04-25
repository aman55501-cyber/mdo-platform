"""Pydantic/dataclass models for broker operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"


class ProductType(str, Enum):
    CNC = "CNC"      # Cash and Carry (delivery)
    MIS = "MIS"      # Margin Intraday Settlement
    NRML = "NRML"    # Normal (F&O)


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    ticker: str
    exchange: Exchange = Exchange.NSE
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.MIS
    quantity: int = 0
    price: float | None = None
    trigger_price: float | None = None
    disclosed_qty: int = 0
    validity: str = "DAY"


@dataclass
class OrderResponse:
    order_id: str
    status: OrderStatus
    message: str = ""
    ticker: str = ""
    side: str = ""
    quantity: int = 0
    price: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Position:
    ticker: str
    exchange: str = "NSE"
    product_type: str = "MIS"
    quantity: int = 0
    average_price: float = 0.0
    last_price: float = 0.0
    pnl: float = 0.0
    day_pnl: float = 0.0

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
class Holding:
    ticker: str
    exchange: str = "NSE"
    quantity: int = 0
    average_price: float = 0.0
    last_price: float = 0.0
    pnl: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "exchange": self.exchange,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "last_price": self.last_price,
            "pnl": self.pnl,
        }


@dataclass
class FundInfo:
    available: float = 0.0
    used_margin: float = 0.0
    total: float = 0.0

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "used_margin": self.used_margin,
            "total": self.total,
        }


@dataclass
class SessionToken:
    access_token: str
    expires_at: datetime
    refresh_token: str | None = None

    @property
    def is_expired(self) -> bool:
        return datetime.now() >= self.expires_at
