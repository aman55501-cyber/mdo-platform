"""SQLite-backed persistence for trade logs and state."""

from __future__ import annotations

import json
from datetime import date, datetime

import aiosqlite

from ..events import SignalEvent, SentimentEvent
from ..utils.logging import get_logger
from .models import SCHEMA_SQL

log = get_logger("store")


class DataStore:
    """Async SQLite storage for signals, executions, and sentiment."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_SQL)
        await self._db.commit()
        log.info("database_connected", path=self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def save_signal(self, signal: SignalEvent) -> None:
        await self._db.execute(
            """INSERT INTO trade_signals
               (id, ticker, action, exchange, product_type, entry_price, target_price,
                stop_loss, quantity, technical_score, sentiment_score, combined_score, rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.id, signal.ticker, signal.action, signal.exchange,
                signal.product_type, signal.entry_price, signal.target_price,
                signal.stop_loss, signal.quantity, signal.technical_score,
                signal.sentiment_score, signal.combined_score, signal.rationale,
            ),
        )
        await self._db.commit()

    async def update_signal_status(self, signal_id: str, status: str) -> None:
        await self._db.execute(
            "UPDATE trade_signals SET status = ? WHERE id = ?",
            (status, signal_id),
        )
        await self._db.commit()

    async def save_execution(
        self, signal_id: str, order_id: str, side: str,
        fill_price: float | None = None, fill_qty: int | None = None,
        status: str = "pending",
    ) -> None:
        await self._db.execute(
            """INSERT INTO trade_executions
               (signal_id, order_id, side, fill_price, fill_qty, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (signal_id, order_id, side, fill_price, fill_qty, status),
        )
        await self._db.commit()

    async def save_sentiment(self, event: SentimentEvent) -> None:
        await self._db.execute(
            """INSERT INTO sentiment_log (ticker, score, confidence, summary, themes, post_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                event.ticker, event.score, event.confidence,
                event.summary, json.dumps(event.themes), event.post_count,
            ),
        )
        await self._db.commit()

    async def get_daily_stats(self, d: date | None = None) -> dict:
        d = d or date.today()
        row = await self._db.execute_fetchall(
            "SELECT * FROM daily_pnl WHERE date = ?", (d.isoformat(),)
        )
        if row:
            r = row[0]
            total = r["total_trades"] or 0
            wins = r["wins"] or 0
            losses = r["losses"] or 0
            return {
                "total_trades": total,
                "wins": wins,
                "losses": losses,
                "win_rate": wins / total if total > 0 else 0,
                "realized_pnl": r["realized_pnl"],
                "unrealized_pnl": r["unrealized_pnl"],
            }
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0, "realized_pnl": 0, "unrealized_pnl": 0,
        }

    async def update_daily_pnl(
        self, d: date, realized: float, unrealized: float,
        total_trades: int, wins: int, losses: int,
    ) -> None:
        await self._db.execute(
            """INSERT INTO daily_pnl (date, realized_pnl, unrealized_pnl, total_trades, wins, losses)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                 realized_pnl = ?, unrealized_pnl = ?, total_trades = ?,
                 wins = ?, losses = ?, updated_at = datetime('now')""",
            (d.isoformat(), realized, unrealized, total_trades, wins, losses,
             realized, unrealized, total_trades, wins, losses),
        )
        await self._db.commit()

    async def save_level(self, level: dict) -> None:
        await self._db.execute(
            """INSERT OR REPLACE INTO price_levels
               (id, ticker, direction, price, sl, target, expiry, source, status)
               VALUES (:id, :ticker, :direction, :price, :sl, :target, :expiry, :source, :status)""",
            level,
        )
        await self._db.commit()

    async def get_active_levels(self) -> list[dict]:
        rows = await self._db.execute_fetchall(
            "SELECT * FROM price_levels WHERE status = 'active' ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    async def update_level_status(
        self, level_id: str, status: str, proximity_alerted: int | None = None
    ) -> None:
        if proximity_alerted is not None:
            await self._db.execute(
                "UPDATE price_levels SET status = ?, proximity_alerted = ? WHERE id = ?",
                (status, proximity_alerted, level_id),
            )
        else:
            triggered_col = ", triggered_at = datetime('now')" if status == "triggered" else ""
            await self._db.execute(
                f"UPDATE price_levels SET status = ?{triggered_col} WHERE id = ?",
                (status, level_id),
            )
        await self._db.commit()

    async def delete_level(self, level_id: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM price_levels WHERE id = ? AND status = 'active'", (level_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_recent_sentiment(self, ticker: str, limit: int = 10) -> list[dict]:
        rows = await self._db.execute_fetchall(
            """SELECT score, confidence, summary, post_count, queried_at
               FROM sentiment_log WHERE ticker = ?
               ORDER BY queried_at DESC LIMIT ?""",
            (ticker, limit),
        )
        return [dict(r) for r in rows]
