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

# In-process state (resets on restart — fine for same-day counters).
_STATE = {"orders_today": 0}
_PROPOSALS: dict[str, dict] = {}

# The kill-switch MUST survive a restart — Docker autoheal can recreate the container,
# and a restart silently disarming the halt is exactly the failure the charter forbids.
# So it is persisted to disk, not held in memory.
_KILL_FILE = _AUDIT.parent / "kill_switch.engaged"


def _kill_engaged() -> bool:
    return _KILL_FILE.exists()


_PROPOSAL_TTL = 120  # seconds — a confirm older than this must re-propose, never fire stale


def _audit(event: str, detail: dict) -> None:
    rec = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **detail}
    log.info("execution_audit %s", rec)
    try:
        _AUDIT.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except OSError:
        pass  # never let audit I/O block or crash an order decision


def recent(limit: int = 50) -> list[dict]:
    """The last N audit events (proposals, sends, kills) — the trade log, newest first."""
    if not _AUDIT.exists():
        return []
    try:
        lines = _AUDIT.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines[-limit * 2:]):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out


def status(cfg: TradingConfig | None = None) -> dict:
    cfg = cfg or get_trading_config()
    return {
        "trading_enabled": cfg.enabled,
        "kill_switch": _kill_engaged(),
        "orders_today": _STATE["orders_today"],
        "caps": {
            "max_qty_per_order": cfg.max_qty_per_order,
            "max_value_per_order": cfg.max_value_per_order,
            "max_orders_per_day": cfg.max_orders_per_day,
            "daily_loss_halt": cfg.daily_loss_halt,
            "allowed_underlyings": list(cfg.allowed_underlyings),
        },
        "can_trade": cfg.enabled and not _kill_engaged(),
    }


def engage_kill() -> dict:
    try:
        _KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _KILL_FILE.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    except OSError:
        pass
    _audit("KILL_SWITCH", {"engaged": True})
    return {"kill_switch": True,
            "message": "Kill-switch ENGAGED. All trading halted (persists across restarts)."}


def release_kill() -> dict:
    """Deliberately disarm the kill-switch (removes the persisted flag). Manual only."""
    try:
        _KILL_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    _audit("KILL_SWITCH", {"engaged": False})
    return {"kill_switch": False, "message": "Kill-switch released."}


def propose(order: OrderRequest, day_pnl: float = 0.0) -> dict:
    """Validate an order against every guardrail and return a confirmation summary.
    Does NOT send anything."""
    cfg = get_trading_config()
    guardrails.check(order, cfg, _STATE["orders_today"], day_pnl, _kill_engaged())
    pid = secrets.token_hex(8)
    confirm_code = secrets.token_hex(4)
    _PROPOSALS[pid] = {"order": order, "confirm_code": confirm_code,
                       "ts": datetime.now(timezone.utc).timestamp()}
    _audit("PROPOSE", {"proposal_id": pid, "order": order.to_dict()})
    # F&O reads in lots (+ premium for an option buy); equity reads in units.
    if order.is_fno and order.lot_size:
        size = f"{int(order.lots())} lot{'s' if order.lots() != 1 else ''} ({order.quantity})"
        extra = f" | premium ₹{order.premium_outlay():,.0f}" if order.premium_outlay() else ""
    else:
        size, extra = str(order.quantity), ""
    return {
        "proposal_id": pid,
        "confirm_code": confirm_code,
        "order": order.to_dict(),
        "review": (
            f"{order.side} {size} {order.symbol} @ "
            f"{'MKT' if order.order_type == 'MARKET' else order.price}{extra} | "
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


def place_now(order: OrderRequest, day_pnl: float = 0.0) -> dict:
    """Place a single order immediately, still through every guardrail + master switch.
    Used for basket legs where the whole basket is confirmed once at the UI level."""
    cfg = get_trading_config()
    guardrails.check(order, cfg, _STATE["orders_today"], day_pnl, _kill_engaged())
    result = _send_to_broker(order)
    _STATE["orders_today"] += 1
    _audit("SENT", {"order": order.to_dict(), "result": result, "via": "basket"})
    return result


def confirm(proposal_id: str, confirm_code: str, day_pnl: float = 0.0) -> dict:
    # Pop atomically up front: two concurrent confirms for the same proposal must not
    # both pass a get() and double-fire the order. The loser gets None.
    prop = _PROPOSALS.pop(proposal_id, None)
    if not prop:
        raise guardrails.GuardrailError("Unknown or expired proposal.")
    if confirm_code != prop["confirm_code"]:
        _PROPOSALS[proposal_id] = prop  # wrong code — restore so the real caller can retry
        raise guardrails.GuardrailError("Confirmation code does not match.")
    if (datetime.now(timezone.utc).timestamp() - prop.get("ts", 0)) > _PROPOSAL_TTL:
        raise guardrails.GuardrailError(
            f"Proposal expired (older than {_PROPOSAL_TTL}s) — re-propose to confirm.")
    order: OrderRequest = prop["order"]
    cfg = get_trading_config()
    guardrails.check(order, cfg, _STATE["orders_today"], day_pnl, _kill_engaged())  # re-check at send time

    result = _send_to_broker(order)  # <-- the only step that needs the Place Order docs
    _STATE["orders_today"] += 1
    _PROPOSALS.pop(proposal_id, None)
    _audit("SENT", {"proposal_id": proposal_id, "order": order.to_dict(), "result": result})
    return {"placed": True, "order": order.to_dict(), "broker_result": result}


def _send_to_broker(order: OrderRequest) -> dict:
    """Place the order with the broker that OWNS the account, by creds_key.

    HDFC accounts route to HDFC, Angel to Angel — so an order lands in the correct
    account (a covered call on HDFC shares no longer goes to Angel). Reached only
    after guardrails pass + the master switch is on.
    """
    key = (order.creds_key or "").upper()
    if key.startswith("HDFC"):
        from ..brokers import hdfc_order
        return hdfc_order.place_order(order)
    from ..brokers import angel_scrip
    return angel_scrip.place_order(order)  # raises RuntimeError on any broker failure
