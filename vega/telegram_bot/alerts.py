"""Push alert service for trade suggestions."""

from __future__ import annotations

from telegram import Bot
from telegram.constants import ParseMode

from ..events import SignalEvent, SentimentEvent, OrderUpdateEvent
from ..utils.logging import get_logger
from .formatters import format_trade_signal, format_order_update, format_daily_summary
from .keyboards import trade_confirmation_keyboard

log = get_logger("alerts")


class AlertService:
    """Sends formatted trade suggestions and status updates via Telegram."""

    def __init__(self, bot: Bot, chat_id: str) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._pending_signals: dict[str, SignalEvent] = {}

    async def send_trade_suggestion(self, signal: SignalEvent) -> int:
        self._pending_signals[signal.id] = signal
        message = format_trade_signal(signal)
        keyboard = trade_confirmation_keyboard(signal.id)

        sent = await self._bot.send_message(
            chat_id=self._chat_id,
            text=message,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        log.info("trade_alert_sent", ticker=signal.ticker, signal_id=signal.id)
        return sent.message_id

    async def send_order_update(self, event: OrderUpdateEvent) -> None:
        message = format_order_update(event)
        await self._bot.send_message(
            chat_id=self._chat_id,
            text=message,
            parse_mode=ParseMode.HTML,
        )

    async def send_daily_summary(self, stats: dict) -> None:
        message = format_daily_summary(stats)
        await self._bot.send_message(
            chat_id=self._chat_id,
            text=message,
            parse_mode=ParseMode.HTML,
        )

    async def send_text(self, text: str, html: bool = True) -> None:
        await self._bot.send_message(
            chat_id=self._chat_id,
            text=text,
            parse_mode=ParseMode.HTML if html else None,
        )

    def get_pending_signal(self, signal_id: str) -> SignalEvent | None:
        return self._pending_signals.get(signal_id)

    def remove_pending_signal(self, signal_id: str) -> None:
        self._pending_signals.pop(signal_id, None)
