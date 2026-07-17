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
    stop_loss: float = 0.0    # mandatory for a live bet — defines the risk
    target: float = 0.0       # for the reward / R:R

    def est_value(self) -> float:
        return abs(self.quantity) * (self.price or 0.0)

    def max_loss(self) -> float:
        """₹ at risk if the stop is hit."""
        if not self.stop_loss or not self.price:
            return 0.0
        return abs(self.quantity) * abs(self.price - self.stop_loss)

    def max_gain(self) -> float:
        if not self.target or not self.price:
            return 0.0
        return abs(self.quantity) * abs(self.target - self.price)

    def risk_reward(self) -> float:
        ml = self.max_loss()
        return round(self.max_gain() / ml, 2) if ml else 0.0

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
            "stop_loss": self.stop_loss,
            "target": self.target,
            "est_value": round(self.est_value(), 2),
            "max_loss": round(self.max_loss(), 2),
            "max_gain": round(self.max_gain(), 2),
            "risk_reward": self.risk_reward(),
        }
