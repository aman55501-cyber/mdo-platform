"""HTML message formatting for Telegram trade alerts."""

from __future__ import annotations

from ..events import SignalEvent, SentimentEvent, OrderUpdateEvent


def format_trade_signal(signal: SignalEvent) -> str:
    action_emoji = {"BUY": "\u2b06\ufe0f", "SELL": "\u2b07\ufe0f", "HOLD": "\u23f8\ufe0f"}
    emoji = action_emoji.get(signal.action, "")

    target_pct = ((signal.target_price - signal.entry_price) / signal.entry_price) * 100
    sl_pct = ((signal.stop_loss - signal.entry_price) / signal.entry_price) * 100
    rr_ratio = abs(target_pct / sl_pct) if sl_pct != 0 else 0

    return (
        f"<b>{emoji} VEGA TRADE SIGNAL - {signal.action}</b>\n"
        f"\n"
        f"<b>Ticker:</b> {signal.ticker}\n"
        f"<b>Exchange:</b> {signal.exchange} | <b>Product:</b> {signal.product_type}\n"
        f"\n"
        f"<b>Entry:</b> <code>\u20b9{signal.entry_price:,.2f}</code>\n"
        f"<b>Target:</b> <code>\u20b9{signal.target_price:,.2f}</code> ({target_pct:+.1f}%)\n"
        f"<b>Stop Loss:</b> <code>\u20b9{signal.stop_loss:,.2f}</code> ({sl_pct:+.1f}%)\n"
        f"<b>Qty:</b> <code>{signal.quantity}</code>\n"
        f"\n"
        f"<b>Technical:</b> {signal.technical_score:.2f} | "
        f"<b>Sentiment:</b> {signal.sentiment_score:+.2f}\n"
        f"<b>Combined:</b> {signal.combined_score:.2f} | "
        f"<b>R:R:</b> {rr_ratio:.1f}\n"
        f"\n"
        f"<b>Rationale:</b> {signal.rationale}\n"
    )


def format_sentiment(event: SentimentEvent) -> str:
    bar = _sentiment_bar(event.score)
    return (
        f"<b>Sentiment: {event.ticker}</b>\n"
        f"\n"
        f"<b>Score:</b> {event.score:+.2f} {bar}\n"
        f"<b>Confidence:</b> {event.confidence:.0%}\n"
        f"<b>Posts analyzed:</b> {event.post_count}\n"
        f"<b>Themes:</b> {', '.join(event.themes) if event.themes else 'N/A'}\n"
        f"\n"
        f"<i>{event.summary}</i>\n"
    )


def format_order_update(event: OrderUpdateEvent) -> str:
    status_emoji = {
        "placed": "\u23f3",
        "filled": "\u2705",
        "cancelled": "\u274c",
        "rejected": "\u26a0\ufe0f",
    }
    emoji = status_emoji.get(event.status, "\u2139\ufe0f")
    msg = (
        f"{emoji} <b>Order {event.status.upper()}</b>\n"
        f"<b>Ticker:</b> {event.ticker}\n"
        f"<b>Order ID:</b> <code>{event.order_id}</code>\n"
    )
    if event.fill_price:
        msg += f"<b>Fill Price:</b> <code>\u20b9{event.fill_price:,.2f}</code>\n"
    if event.fill_qty:
        msg += f"<b>Fill Qty:</b> <code>{event.fill_qty}</code>\n"
    if event.message:
        msg += f"<b>Message:</b> {event.message}\n"
    return msg


def format_position_list(positions: list[dict]) -> str:
    if not positions:
        return "<b>No open positions</b>"

    lines = ["<b>Open Positions</b>\n"]
    total_pnl = 0.0
    for p in positions:
        pnl = p.get("pnl", 0.0)
        total_pnl += pnl
        pnl_str = f"\u20b9{pnl:+,.2f}"
        lines.append(
            f"<code>{p['ticker']:>12}</code> "
            f"Qty: {p['quantity']:>4} "
            f"Avg: \u20b9{p['average_price']:,.2f} "
            f"P&L: {pnl_str}"
        )
    lines.append(f"\n<b>Total P&L:</b> \u20b9{total_pnl:+,.2f}")
    return "\n".join(lines)


def format_daily_summary(stats: dict) -> str:
    return (
        f"<b>VEGA Daily Summary</b>\n"
        f"\n"
        f"<b>Total Trades:</b> {stats.get('total_trades', 0)}\n"
        f"<b>Wins:</b> {stats.get('wins', 0)} | "
        f"<b>Losses:</b> {stats.get('losses', 0)}\n"
        f"<b>Win Rate:</b> {stats.get('win_rate', 0):.0%}\n"
        f"<b>Realized P&L:</b> <code>\u20b9{stats.get('realized_pnl', 0):+,.2f}</code>\n"
        f"<b>Unrealized P&L:</b> <code>\u20b9{stats.get('unrealized_pnl', 0):+,.2f}</code>\n"
    )


def _sentiment_bar(score: float) -> str:
    if score >= 0.5:
        return "\U0001f7e2\U0001f7e2\U0001f7e2"
    elif score >= 0.2:
        return "\U0001f7e2\U0001f7e2"
    elif score >= 0:
        return "\U0001f7e2"
    elif score >= -0.2:
        return "\U0001f534"
    elif score >= -0.5:
        return "\U0001f534\U0001f534"
    else:
        return "\U0001f534\U0001f534\U0001f534"
