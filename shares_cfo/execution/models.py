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
    lot_size: int = 0         # F&O lot size (0 for equity); filled by the caller for NFO

    # --- Segment awareness: F&O is sized and capped differently from equity ---
    _DERIV_EXCH = ("NFO", "BFO", "MCX", "CDS", "NCX")

    @property
    def is_fno(self) -> bool:
        """True for a derivatives order (futures or options), by exchange."""
        return (self.exchange or "").upper() in self._DERIV_EXCH

    @property
    def is_option(self) -> bool:
        """Options carry premium risk (buy = debit); futures carry margin/notional."""
        s = (self.symbol or "").upper()
        return self.is_fno and (s.endswith("CE") or s.endswith("PE"))

    @property
    def segment(self) -> str:
        return "FNO" if self.is_fno else "EQ"

    def lots(self) -> float:
        """Quantity expressed in lots (0 if lot size unknown)."""
        return (abs(self.quantity) / self.lot_size) if self.lot_size else 0.0

    def premium_outlay(self) -> float:
        """Cash paid to BUY an option (qty × premium). 0 for sells/futures/equity."""
        if self.is_option and self.side == "BUY":
            return abs(self.quantity) * (self.price or 0.0)
        return 0.0

    def notional(self) -> float:
        """Contract notional (qty × price) — the exposure a futures leg controls."""
        return abs(self.quantity) * (self.price or 0.0)

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
            "lot_size": self.lot_size,
            "segment": self.segment,
            "lots": round(self.lots(), 2),
            "est_value": round(self.est_value(), 2),
            "premium_outlay": round(self.premium_outlay(), 2),
            "notional": round(self.notional(), 2),
            "max_loss": round(self.max_loss(), 2),
            "max_gain": round(self.max_gain(), 2),
            "risk_reward": self.risk_reward(),
        }
