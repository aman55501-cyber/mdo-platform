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
          day_pnl: float | None, kill: bool) -> bool:
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

    # --- size + segment-specific caps (equity vs derivatives) ---
    if order.is_fno:
        _check_fno(order, cfg)
    else:
        _check_equity(order, cfg)

    # --- shared discipline: mandatory stop-loss + hard ₹ risk cap ---
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

    # --- shared daily limits ---
    if cfg.max_orders_per_day <= 0:
        raise GuardrailError("No daily order cap set (CFO_MAX_ORDERS_PER_DAY) — refusing.")
    if orders_today >= cfg.max_orders_per_day:
        raise GuardrailError(f"Daily order cap reached ({cfg.max_orders_per_day}).")

    if cfg.daily_loss_halt:
        if day_pnl is None:
            # Fail CLOSED: if we can't compute today's P&L we can't prove we're under the
            # halt, so refuse rather than trade blind on the day it matters most.
            raise GuardrailError(
                "Cannot verify today's P&L (book/positions unavailable) — refusing while a "
                "daily-loss halt is set. Retry, or clear CFO_DAILY_LOSS_HALT to override."
            )
        if day_pnl <= -abs(cfg.daily_loss_halt):
            raise GuardrailError(
                f"Daily loss ₹{day_pnl:,.0f} has hit the halt limit ₹{-abs(cfg.daily_loss_halt):,.0f} — halted."
            )

    return True


def _check_equity(order: OrderRequest, cfg: TradingConfig) -> None:
    """Equity caps: per-order quantity + notional value, against the equity allow-list."""
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

    if not cfg.allowed_underlyings:
        raise GuardrailError("No underlyings are allow-listed (CFO_ALLOWED_UNDERLYINGS) — refusing.")
    if order.underlying.upper() not in cfg.allowed_underlyings:
        raise GuardrailError(
            f"Underlying '{order.underlying}' is not on the allow-list {list(cfg.allowed_underlyings)}."
        )


def _check_fno(order: OrderRequest, cfg: TradingConfig) -> None:
    """Derivatives caps: a dedicated switch, whole-lot sizing, a lot cap, and a
    premium (option buy) or notional (futures / short option) cap — because a
    contract's notional and its cash/margin cost are wildly different numbers."""
    if not cfg.fno_enabled:
        raise GuardrailError(
            "F&O trading is OFF (set CFO_FNO_ENABLED) — a separate switch from equity.")

    allow = cfg.fno_underlyings()
    if not allow:
        raise GuardrailError(
            "No F&O underlyings are allow-listed (CFO_FNO_ALLOWED_UNDERLYINGS) — refusing.")
    if order.underlying.upper() not in allow:
        raise GuardrailError(
            f"F&O underlying '{order.underlying}' is not on the allow-list {list(allow)}.")

    # F&O trades in whole lots only.
    lot = int(order.lot_size or 0)
    if lot <= 0:
        raise GuardrailError(
            f"Unknown lot size for {order.underlying} — cannot size an F&O order safely.")
    if int(order.quantity) % lot != 0:
        raise GuardrailError(
            f"F&O quantity {int(order.quantity)} must be a whole multiple of the lot size "
            f"({lot}) for {order.underlying}.")

    # Cap the order in LOTS (natural F&O unit), not raw quantity.
    if cfg.max_lots_per_order <= 0:
        raise GuardrailError("No per-order lot cap set (CFO_MAX_LOTS_PER_ORDER) — refusing.")
    lots = int(order.quantity) // lot
    if lots > cfg.max_lots_per_order:
        raise GuardrailError(
            f"{lots} lots exceeds the F&O cap of {cfg.max_lots_per_order} lots per order.")

    # Cash/exposure cap shaped to the instrument.
    if order.is_option and order.side == "BUY":
        # Buying an option: max loss is the premium — cap the cash outlay.
        if cfg.max_premium_per_order <= 0:
            raise GuardrailError(
                "No option-premium cap set (CFO_MAX_PREMIUM_PER_ORDER) — refusing.")
        outlay = order.premium_outlay()
        if outlay > cfg.max_premium_per_order:
            raise GuardrailError(
                f"Premium outlay ₹{outlay:,.0f} exceeds the cap of "
                f"₹{cfg.max_premium_per_order:,.0f}.")
    else:
        # Futures or SHORT options carry margin/unbounded risk — cap by notional if set.
        if cfg.max_notional_fno > 0 and order.notional() > cfg.max_notional_fno:
            raise GuardrailError(
                f"Notional ₹{order.notional():,.0f} exceeds the F&O cap of "
                f"₹{cfg.max_notional_fno:,.0f}.")
