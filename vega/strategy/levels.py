"""Price-level based trading: watch user-defined support/resistance levels
and fire signals when price touches them.

Telegram usage:
  /level RELIANCE BUY 2500 SL 2450 TGT 2600
  /level NIFTY SELL 23500 SL 23700 TGT 23000 EXP 25APR
  /levels          - list active levels
  /removelevel <id>
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils.logging import get_logger

if TYPE_CHECKING:
    from ..data.store import DataStore

log = get_logger("levels")

PROXIMITY_PCT = 0.005  # alert when price is within 0.5% of level


@dataclass
class Level:
    id: str
    ticker: str
    direction: str   # "BUY" or "SELL"
    price: float
    sl: float
    target: float
    expiry: str | None
    source: str      # "telegram" or "config"
    status: str = "active"
    proximity_alerted: int = 0

    @property
    def short_id(self) -> str:
        return self.id[:8]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "direction": self.direction,
            "price": self.price,
            "sl": self.sl,
            "target": self.target,
            "expiry": self.expiry,
            "source": self.source,
            "status": self.status,
            "proximity_alerted": self.proximity_alerted,
        }


@dataclass
class LevelTrigger:
    level: Level
    ltp: float
    kind: str  # "triggered" or "proximity"


class LevelManager:
    """Manages user-defined price levels and fires alerts/signals when hit."""

    def __init__(self, store: DataStore) -> None:
        self._store = store
        self._levels: dict[str, Level] = {}  # id → Level

    async def load(self) -> None:
        """Load active levels from DB (called at engine startup)."""
        rows = await self._store.get_active_levels()
        for r in rows:
            lvl = Level(
                id=r["id"],
                ticker=r["ticker"],
                direction=r["direction"],
                price=r["price"],
                sl=r["sl"],
                target=r["target"],
                expiry=r.get("expiry"),
                source=r.get("source", "config"),
                status=r.get("status", "active"),
                proximity_alerted=r.get("proximity_alerted", 0),
            )
            self._levels[lvl.id] = lvl
        log.info("levels_loaded", count=len(self._levels))

    async def add_level(
        self,
        ticker: str,
        direction: str,
        price: float,
        sl: float,
        target: float,
        expiry: str | None = None,
        source: str = "telegram",
    ) -> Level:
        lvl = Level(
            id=str(uuid.uuid4()),
            ticker=ticker.upper(),
            direction=direction.upper(),
            price=price,
            sl=sl,
            target=target,
            expiry=expiry,
            source=source,
        )
        await self._store.save_level(lvl.to_dict())
        self._levels[lvl.id] = lvl
        log.info("level_added", ticker=lvl.ticker, direction=lvl.direction, price=lvl.price)
        return lvl

    async def remove_level(self, level_id: str) -> bool:
        """Remove by full or short (8-char) ID. Returns True if found."""
        target_id = self._find_id(level_id)
        if not target_id:
            return False
        deleted = await self._store.delete_level(target_id)
        if deleted:
            self._levels.pop(target_id, None)
        return deleted

    def list_active(self) -> list[Level]:
        return [l for l in self._levels.values() if l.status == "active"]

    def check_levels(self, ticker: str, ltp: float) -> list[LevelTrigger]:
        """Check all active levels for ticker against current LTP.
        Returns a list of triggered or proximity-alert events.
        """
        results: list[LevelTrigger] = []
        for lvl in self.list_active():
            if lvl.ticker != ticker.upper():
                continue

            distance_pct = abs(ltp - lvl.price) / lvl.price

            # Hard trigger: price crosses/touches the level
            if _is_triggered(lvl.direction, ltp, lvl.price):
                results.append(LevelTrigger(level=lvl, ltp=ltp, kind="triggered"))

            # Proximity alert: within 0.5%, not yet alerted
            elif distance_pct <= PROXIMITY_PCT and not lvl.proximity_alerted:
                results.append(LevelTrigger(level=lvl, ltp=ltp, kind="proximity"))

        return results

    async def mark_triggered(self, level_id: str) -> None:
        if level_id in self._levels:
            self._levels[level_id].status = "triggered"
        await self._store.update_level_status(level_id, "triggered")

    async def mark_proximity_alerted(self, level_id: str) -> None:
        if level_id in self._levels:
            self._levels[level_id].proximity_alerted = 1
        await self._store.update_level_status(level_id, "active", proximity_alerted=1)

    def _find_id(self, partial: str) -> str | None:
        if partial in self._levels:
            return partial
        for lid in self._levels:
            if lid.startswith(partial):
                return lid
        return None

    @property
    def active_count(self) -> int:
        return len(self.list_active())


def _is_triggered(direction: str, ltp: float, level_price: float) -> bool:
    if direction == "BUY":
        return ltp <= level_price
    if direction == "SELL":
        return ltp >= level_price
    return False


def parse_level_command(args: list[str]) -> dict | None:
    """Parse /level TICKER BUY 2500 SL 2450 TGT 2600 [EXP 25APR] args.
    Returns dict with keys: ticker, direction, price, sl, target, expiry
    or None if invalid.
    """
    if len(args) < 5:
        return None
    try:
        ticker = args[0].upper()
        direction = args[1].upper()
        if direction not in ("BUY", "SELL"):
            return None
        price = float(args[2])

        # Parse SL and TGT keywords (case-insensitive)
        upper = [a.upper() for a in args]
        sl, target, expiry = None, None, None

        for i, tok in enumerate(upper):
            if tok == "SL" and i + 1 < len(upper):
                sl = float(args[i + 1])
            elif tok in ("TGT", "TARGET") and i + 1 < len(upper):
                target = float(args[i + 1])
            elif tok == "EXP" and i + 1 < len(upper):
                expiry = args[i + 1].upper()

        if sl is None or target is None:
            return None

        return {
            "ticker": ticker,
            "direction": direction,
            "price": price,
            "sl": sl,
            "target": target,
            "expiry": expiry,
        }
    except (ValueError, IndexError):
        return None


def load_levels_yaml(path: str | Path) -> list[dict]:
    """Load default levels from a YAML config file."""
    try:
        import yaml  # optional dep
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return data.get("levels", [])
    except FileNotFoundError:
        return []
    except Exception as exc:
        log.warning("levels_yaml_load_error", error=str(exc))
        return []
