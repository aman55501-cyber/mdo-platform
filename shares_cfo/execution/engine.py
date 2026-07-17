"""Execution engine: propose -> confirm -> (send), plus kill-switch and audit.

The broker SEND is deliberately a stub that raises until wired from the official
Place Order docs. So even with the master switch ON and a valid confirmation, no
order can leave the building until that final, docs-driven step is added.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path

from ..config import TradingConfig, get_trading_config
from . import guardrails
from .models import OrderRequest

log = logging.getLogger("shares_cfo.execution")
_AUDIT = Path(__file__).resolve().parent.parent / "data" / "state" / "execution_audit.jsonl"

# In-process state (resets on restart — fine for same-day trading).
_STATE = {"kill": False, "orders_today": 0}
_PROPOSALS: dict[str, dict] = {}


def _audit(event: str, detail: dict) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **detail}
    log.info("execution_audit %s", rec)
    try:
        _AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        pass  # never let audit I/O block or crash an order decision


def status(cfg: TradingConfig | None = None) -> dict:
    cfg = cfg or get_trading_config()
    return {
        "trading_enabled": cfg.enabled,
        "kill_switch": _STATE["kill"],
        "orders_today": _STATE["orders_today"],
        "caps": {
            "max_qty_per_order": cfg.max_qty_per_order,
            "max_value_per_order": cfg.max_value_per_order,
            "max_orders_per_day": cfg.max_orders_per_day,
            "daily_loss_halt": cfg.daily_loss_halt,
            "allowed_underlyings": list(cfg.allowed_underlyings),
        },
        "can_trade": cfg.enabled and not _STATE["kill"],
    }


def engage_kill() -> dict:
    _STATE["kill"] = True
    _audit("KILL_SWITCH", {"engaged": True})
    return {"kill_switch": True, "message": "Kill-switch ENGAGED. All trading halted."}


def propose(order: OrderRequest, day_pnl: float = 0.0) -> dict:
    """Validate an order against every guardrail and return a confirmation summary.
    Does NOT send anything."""
    cfg = get_trading_config()
    guardrails.check(order, cfg, _STATE["orders_today"], day_pnl, _STATE["kill"])
    pid = secrets.token_hex(8)
    confirm_code = secrets.token_hex(4)
    _PROPOSALS[pid] = {"order": order, "confirm_code": confirm_code}
    _audit("PROPOSE", {"proposal_id": pid, "order": order.to_dict()})
    return {
        "proposal_id": pid,
        "confirm_code": confirm_code,
        "order": order.to_dict(),
        "review": (
            f"{order.side} {order.quantity} {order.symbol} @ "
            f"{'MKT' if order.order_type == 'MARKET' else order.price} | "
            f"SL {order.stop_loss} → risk ₹{order.max_loss():,.0f} | "
            f"target {order.target} → reward ₹{order.max_gain():,.0f} | "
            f"R:R {order.risk_reward()}:1. Confirm to place."
        ),
        "risk_reward": {
            "entry": order.price,
            "stop_loss": order.stop_loss,
            "target": order.target,
            "max_loss": round(order.max_loss(), 2),
            "max_gain": round(order.max_gain(), 2),
            "ratio": order.risk_reward(),
        },
        "note": "Reviewed only. Nothing has been sent. POST /execution/confirm with the confirm_code to place.",
    }


def confirm(proposal_id: str, confirm_code: str, day_pnl: float = 0.0) -> dict:
    prop = _PROPOSALS.get(proposal_id)
    if not prop:
        raise guardrails.GuardrailError("Unknown or expired proposal.")
    if confirm_code != prop["confirm_code"]:
        raise guardrails.GuardrailError("Confirmation code does not match.")
    order: OrderRequest = prop["order"]
    cfg = get_trading_config()
    guardrails.check(order, cfg, _STATE["orders_today"], day_pnl, _STATE["kill"])  # re-check at send time

    result = _send_to_broker(order)  # <-- the only step that needs the Place Order docs
    _STATE["orders_today"] += 1
    _PROPOSALS.pop(proposal_id, None)
    _audit("SENT", {"proposal_id": proposal_id, "order": order.to_dict(), "result": result})
    return {"placed": True, "order": order.to_dict(), "broker_result": result}


def _send_to_broker(order: OrderRequest) -> dict:
    """PENDING: wire the broker's official Place Order endpoint here.

    Until the HDFC/Angel Place Order docs are provided and this is implemented, we
    refuse to send — guessing an order format with real money is not acceptable.
    """
    raise NotImplementedError(
        "Order endpoint not wired yet. Provide the broker's Place Order docs "
        "(request + response) and this send step will be implemented against them."
    )
