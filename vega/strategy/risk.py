"""Risk management: position sizing, limits, stop-losses."""

from __future__ import annotations

from ..config import StrategyConfig
from ..events import SignalEvent
from ..utils.logging import get_logger
from ..utils.nse import get_lot_size, is_fo_stock
from ..utils.time import is_market_open

log = get_logger("risk")


class PortfolioState:
    """Tracks current portfolio state for risk checks."""

    def __init__(self) -> None:
        self.positions: dict[str, dict] = {}
        self.daily_pnl: float = 0.0
        self.capital: float = 0.0
        self.peak_capital: float = 0.0

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def drawdown_pct(self) -> float:
        if self.peak_capital <= 0:
            return 0.0
        return (self.peak_capital - self.capital) / self.peak_capital * 100

    def has_position(self, ticker: str) -> bool:
        return ticker in self.positions

    def update_capital(self, capital: float) -> None:
        self.capital = capital
        self.peak_capital = max(self.peak_capital, capital)


class RiskManager:
    """Enforces all risk controls before a signal becomes a trade suggestion."""

    def __init__(self, config: StrategyConfig) -> None:
        self._config = config
        self.state = PortfolioState()

    def validate_signal(self, signal: SignalEvent) -> tuple[bool, str]:
        """Returns (is_valid, reason). Checks all risk constraints."""

        if not is_market_open():
            return False, "Market is closed"

        if signal.action == "BUY":
            if self.state.has_position(signal.ticker):
                return False, f"Already have position in {signal.ticker}"

            if self.state.position_count >= self._config.max_positions:
                return False, f"Max positions ({self._config.max_positions}) reached"

            daily_loss_pct = abs(self.state.daily_pnl / self.state.capital * 100) if self.state.capital > 0 else 0
            if self.state.daily_pnl < 0 and daily_loss_pct >= self._config.daily_loss_limit_pct:
                return False, f"Daily loss limit ({self._config.daily_loss_limit_pct}%) breached"

            if signal.combined_score < 0.65:
                return False, f"Combined score {signal.combined_score:.2f} below threshold 0.65"

        return True, "OK"

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        available_capital: float,
        ticker: str = "",
    ) -> int:
        """Calculate position size based on risk-per-trade percentage."""
        risk_amount = available_capital * (self._config.risk_per_trade_pct / 100)
        risk_per_share = abs(entry_price - stop_loss)

        if risk_per_share <= 0:
            return 0

        raw_qty = int(risk_amount / risk_per_share)

        # For F&O, round to lot size
        if is_fo_stock(ticker):
            lot = get_lot_size(ticker)
            raw_qty = max(lot, (raw_qty // lot) * lot)

        # Cap at 20% of capital
        max_exposure = available_capital * 0.20
        max_qty = int(max_exposure / entry_price) if entry_price > 0 else 0
        raw_qty = min(raw_qty, max_qty)

        return max(1, raw_qty)

    def calculate_stop_loss(self, entry_price: float, atr_value: float | None = None) -> float:
        """ATR-based stop-loss if ATR available, else percentage-based."""
        if atr_value and atr_value > 0:
            return entry_price - (1.5 * atr_value)
        return entry_price * (1 - self._config.stop_loss_pct / 100)

    def calculate_target(self, entry_price: float, stop_loss: float) -> float:
        """Minimum 2:1 reward-to-risk ratio."""
        risk = entry_price - stop_loss
        min_target = entry_price + (2.0 * risk)  # 2:1 R:R
        pct_target = entry_price * (1 + self._config.target_pct / 100)
        return max(min_target, pct_target)

    def should_exit(
        self, ticker: str, current_price: float,
        entry_price: float, target: float, stop_loss: float,
    ) -> tuple[bool, str]:
        """Check if an existing position should be exited."""
        if current_price <= stop_loss:
            return True, "Stop-loss hit"
        if current_price >= target:
            return True, "Target hit"
        return False, ""
