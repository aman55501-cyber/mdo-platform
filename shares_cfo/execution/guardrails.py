"""Guardrail checks — the safety gate every order must pass, twice.

Pure function: given an order, the trading config, and current state, it either
returns True or raises GuardrailError with a plain-language reason. Runs at BOTH
propose and confirm so nothing changes underneath a pending order.
"""

from __future__ import annotations

from ..config import TradingConfig
from .models import OrderRequest


class GuardrailError(Exception):
    """An order was blocked by a guardrail. The message is safe to show the user."""


def check(order: OrderRequest, cfg: TradingConfig, orders_today: int,
          day_pnl: float, kill: bool) -> bool:
    if kill:
        raise GuardrailError("Kill-switch is ENGAGED — all trading is halted.")
    if not cfg.enabled:
        raise GuardrailError("Trading is OFF (master switch CFO_TRADING_ENABLED is not set).")

    if order.side not in ("BUY", "SELL"):
        raise GuardrailError(f"Invalid side '{order.side}' (must be BUY or SELL).")
    if order.quantity <= 0:
        raise GuardrailError("Quantity must be positive.")
    if order.order_type == "LIMIT" and order.price <= 0:
        raise GuardrailError("LIMIT order needs a price.")

    if cfg.max_qty_per_order <= 0:
        raise GuardrailError("No per-order quantity cap set (CFO_MAX_QTY_PER_ORDER) — refusing.")
    if order.quantity > cfg.max_qty_per_order:
        raise GuardrailError(f"Quantity {order.quantity} exceeds the cap of {cfg.max_qty_per_order}.")

    if cfg.max_value_per_order <= 0:
        raise GuardrailError("No per-order value cap set (CFO_MAX_VALUE_PER_ORDER) — refusing.")
    if order.est_value() > cfg.max_value_per_order:
        raise GuardrailError(
            f"Order value ₹{order.est_value():,.0f} exceeds the cap of ₹{cfg.max_value_per_order:,.0f}."
        )

    # small-bet discipline: a stop-loss is mandatory and the ₹ risk is hard-capped
    if cfg.max_risk_per_trade <= 0:
        raise GuardrailError("No per-trade risk cap set (CFO_MAX_RISK_PER_TRADE) — refusing.")
    if order.stop_loss <= 0:
        raise GuardrailError("A stop-loss is required on every bet — no naked risk.")
    risk = order.max_loss()
    if risk <= 0:
        raise GuardrailError("Cannot compute risk (need entry price + stop-loss).")
    if risk > cfg.max_risk_per_trade:
        raise GuardrailError(
            f"This bet risks ₹{risk:,.0f}, over your per-trade cap of ₹{cfg.max_risk_per_trade:,.0f}."
        )

    if cfg.max_orders_per_day <= 0:
        raise GuardrailError("No daily order cap set (CFO_MAX_ORDERS_PER_DAY) — refusing.")
    if orders_today >= cfg.max_orders_per_day:
        raise GuardrailError(f"Daily order cap reached ({cfg.max_orders_per_day}).")

    if cfg.daily_loss_halt and day_pnl <= -abs(cfg.daily_loss_halt):
        raise GuardrailError(
            f"Daily loss ₹{day_pnl:,.0f} has hit the halt limit ₹{-abs(cfg.daily_loss_halt):,.0f} — halted."
        )

    if not cfg.allowed_underlyings:
        raise GuardrailError("No underlyings are allow-listed (CFO_ALLOWED_UNDERLYINGS) — refusing.")
    if order.underlying.upper() not in cfg.allowed_underlyings:
        raise GuardrailError(
            f"Underlying '{order.underlying}' is not on the allow-list {list(cfg.allowed_underlyings)}."
        )

    return True
