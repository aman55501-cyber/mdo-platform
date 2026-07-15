"""Order request model — only exists inside the guarded execution module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderRequest:
    creds_key: str            # which account
    exchange: str             # NSE / NFO / BSE
    symbol: str               # human tradingsymbol (for the confirm summary)
    token: str                # instrument token the broker keys on
    side: str                 # BUY / SELL
    quantity: int
    product: str = "NRML"     # NRML / MIS / CNC
    order_type: str = "LIMIT"  # LIMIT / MARKET
    price: float = 0.0
    trigger_price: float = 0.0
    underlying: str = ""      # for the allow-list check (e.g. NIFTY)

    def est_value(self) -> float:
        return abs(self.quantity) * (self.price or 0.0)

    def to_dict(self) -> dict:
        return {
            "creds_key": self.creds_key,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "token": self.token,
            "side": self.side,
            "quantity": self.quantity,
            "product": self.product,
            "order_type": self.order_type,
            "price": self.price,
            "trigger_price": self.trigger_price,
            "underlying": self.underlying,
            "est_value": round(self.est_value(), 2),
        }
