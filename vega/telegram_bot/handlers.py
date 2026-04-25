"""Telegram command and callback handlers."""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ..strategy.levels import parse_level_command
from ..utils.logging import get_logger
from ..utils.time import is_market_open, is_premarket, now_ist, format_ist
from .formatters import format_sentiment, format_position_list
from .keyboards import (
    mdo_root_keyboard, mdo_node_keyboard, mdo_node_text,
    mdo_edit_keyboard, mdo_edit_text,
    autosinghvi_keyboard,
)
from .mdo_store import get_store
from ..vedanta import bridge as vedanta_bridge

log = get_logger("telegram")


class VegaHandlers:
    """Registers and handles all Telegram bot commands and callbacks."""

    def __init__(self, engine: any) -> None:
        self._engine = engine

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "<b>MDO — Management Decision Office</b>\n"
            "<i>Aman Agrawal · ANS Group · Kharsia, Raigarh</i>\n\n"
            "Tap any section to expand. Double-tap to drill in.",
            parse_mode=ParseMode.HTML,
            reply_markup=mdo_root_keyboard(),
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.cmd_start(update, context)

    async def cmd_autosinghvi(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Toggle or check Anil Singhvi auto-execute: /autosinghvi on|off|status"""
        arg = (context.args[0].lower() if context.args else "status")
        current = self._engine.singhvi_auto_execute

        if arg == "on":
            self._engine.singhvi_auto_execute = True
            await update.message.reply_text(
                "<b>Singhvi Auto-Execute: ON</b>\n\n"
                "Anil Singhvi's BUY/SELL calls from X will be executed automatically "
                "within your risk limits (2% per trade, max 5 positions).\n\n"
                "<i>Risk controls still apply — no position is taken without margin available.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=autosinghvi_keyboard(True),
            )
        elif arg == "off":
            self._engine.singhvi_auto_execute = False
            await update.message.reply_text(
                "<b>Singhvi Auto-Execute: OFF</b>\n\n"
                "Singhvi calls will appear as alerts for manual confirmation.",
                parse_mode=ParseMode.HTML,
                reply_markup=autosinghvi_keyboard(False),
            )
        else:
            state = "ON" if current else "OFF"
            await update.message.reply_text(
                f"<b>Singhvi Auto-Execute: {state}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=autosinghvi_keyboard(current),
            )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        now = now_ist()
        market = "OPEN" if is_market_open() else ("PRE-MARKET" if is_premarket() else "CLOSED")
        auth = "Connected" if self._engine.is_broker_authenticated else "Not Connected"
        watchlist = ", ".join(self._engine.config.watchlist)

        await update.message.reply_text(
            f"<b>VEGA Status</b>\n\n"
            f"<b>Time:</b> {format_ist(now)}\n"
            f"<b>Market:</b> {market}\n"
            f"<b>Broker:</b> {auth}\n"
            f"<b>Watchlist:</b> {watchlist}\n"
            f"<b>Active Positions:</b> {self._engine.active_position_count}\n",
            parse_mode=ParseMode.HTML,
        )

    async def cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        tickers = self._engine.config.watchlist
        ticker_list = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(tickers))
        await update.message.reply_text(
            f"<b>Watchlist ({len(tickers)} tickers)</b>\n\n"
            f"<code>{ticker_list}</code>\n\n"
            f"Use /add TICKER or /remove TICKER to manage.",
            parse_mode=ParseMode.HTML,
        )

    async def cmd_sentiment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /sentiment TICKER\nExample: /sentiment RELIANCE")
            return

        ticker = context.args[0].upper()
        await update.message.reply_text(f"Analyzing X sentiment for <b>{ticker}</b>...", parse_mode=ParseMode.HTML)

        try:
            event = await self._engine.get_sentiment(ticker)
            msg = format_sentiment(event)
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        except Exception as exc:
            log.error("sentiment_command_error", ticker=ticker, error=str(exc))
            await update.message.reply_text(f"Error analyzing {ticker}: {exc}")

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            positions = await self._engine.get_positions()
            msg = format_position_list(positions)
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        except Exception as exc:
            await update.message.reply_text(f"Error fetching positions: {exc}")

    async def cmd_holdings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            holdings = await self._engine.get_holdings()
            if not holdings:
                await update.message.reply_text("<b>No holdings found</b>", parse_mode=ParseMode.HTML)
                return
            lines = ["<b>Holdings</b>\n"]
            for h in holdings:
                lines.append(
                    f"<code>{h['ticker']:>12}</code> "
                    f"Qty: {h['quantity']:>4} "
                    f"Avg: \u20b9{h['average_price']:,.2f}"
                )
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as exc:
            await update.message.reply_text(f"Error fetching holdings: {exc}")

    async def cmd_funds(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            funds = await self._engine.get_funds()
            await update.message.reply_text(
                f"<b>Funds</b>\n\n"
                f"<b>Available:</b> <code>\u20b9{funds.get('available', 0):,.2f}</code>\n"
                f"<b>Used Margin:</b> <code>\u20b9{funds.get('used_margin', 0):,.2f}</code>\n"
                f"<b>Total:</b> <code>\u20b9{funds.get('total', 0):,.2f}</code>\n",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            await update.message.reply_text(f"Error fetching funds: {exc}")

    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            stats = await self._engine.get_daily_stats()
            from .formatters import format_daily_summary
            msg = format_daily_summary(stats)
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        except Exception as exc:
            await update.message.reply_text(f"Error fetching P&L: {exc}")

    async def cmd_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /add TICKER")
            return
        ticker = context.args[0].upper()
        if ticker in self._engine.config.watchlist:
            await update.message.reply_text(f"{ticker} already in watchlist.")
            return
        self._engine.config.watchlist.append(ticker)
        await update.message.reply_text(f"Added <b>{ticker}</b> to watchlist.", parse_mode=ParseMode.HTML)

    async def cmd_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args:
            await update.message.reply_text("Usage: /remove TICKER")
            return
        ticker = context.args[0].upper()
        if ticker not in self._engine.config.watchlist:
            await update.message.reply_text(f"{ticker} not in watchlist.")
            return
        self._engine.config.watchlist.remove(ticker)
        await update.message.reply_text(f"Removed <b>{ticker}</b> from watchlist.", parse_mode=ParseMode.HTML)

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        checks = await self._engine.health_check()
        lines = ["<b>System Health</b>\n"]
        for name, ok in checks.items():
            icon = "\u2705" if ok else "\u274c"
            lines.append(f"{icon} {name}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_singhvi(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show latest Anil Singhvi stock calls from X."""
        await update.message.reply_text("Fetching Anil Singhvi calls from X...")
        try:
            calls = await self._engine.get_singhvi_calls()
            if not calls:
                await update.message.reply_text(
                    "No recent calls found from @AnilSinghvi_ today.\n"
                    "(He may not have posted yet or Grok found no actionable calls.)"
                )
                return

            lines = [f"<b>📡 Anil Singhvi Calls — {len(calls)} found</b>\n"]
            for c in calls[:8]:
                # Direction icon
                d_icon = "🟢" if c.direction == "BUY" else ("🔴" if c.direction == "SELL" else "🟡")
                validity_tag = f"[{c.validity}]" if c.validity != "unknown" else ""

                # Price levels line
                price_parts = []
                if c.entry_price:
                    price_parts.append(f"Entry ₹{c.entry_price:,.0f}")
                if c.stop_loss:
                    price_parts.append(f"SL ₹{c.stop_loss:,.0f}")
                if c.target:
                    price_parts.append(f"TGT ₹{c.target:,.0f}")
                if c.exit_price:
                    price_parts.append(f"Exit ₹{c.exit_price:,.0f}")
                price_line = "  " + " | ".join(price_parts) if price_parts else ""

                conf_pct = f"{c.confidence*100:.0f}%"
                ts = c.post_timestamp if c.post_timestamp != "recent" else ""
                header = (
                    f"{d_icon} <b>{c.ticker}</b> {c.direction} {validity_tag} "
                    f"<i>{ts}</i>  ({conf_pct})"
                )
                lines.append(header)
                if price_line:
                    lines.append(f"<code>{price_line}</code>")
                lines.append(f"  <i>{c.summary}</i>")
                lines.append("")  # blank line between calls
            await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)
        except Exception as exc:
            await update.message.reply_text(f"Error fetching Singhvi calls: {exc}")

    async def cmd_level(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Add a price level: /level TICKER BUY 2500 SL 2450 TGT 2600 [EXP 25APR]"""
        if not context.args:
            await update.message.reply_text(
                "<b>Usage:</b>\n"
                "<code>/level RELIANCE BUY 2500 SL 2450 TGT 2600</code>\n"
                "<code>/level NIFTY SELL 23500 SL 23700 TGT 23000 EXP 30APR</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        parsed = parse_level_command(context.args)
        if not parsed:
            await update.message.reply_text(
                "Invalid format. Example:\n"
                "<code>/level RELIANCE BUY 2500 SL 2450 TGT 2600</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        try:
            short_id = await self._engine.add_level(**parsed)
            rr = (parsed["target"] - parsed["price"]) / (parsed["price"] - parsed["sl"])
            expiry_str = f" | Exp: {parsed['expiry']}" if parsed["expiry"] else ""
            await update.message.reply_text(
                f"<b>Level added</b> <code>[{short_id}]</code>\n\n"
                f"<b>{parsed['ticker']}</b> {parsed['direction']} @ "
                f"<code>₹{parsed['price']:,.2f}</code>\n"
                f"SL: <code>₹{parsed['sl']:,.2f}</code> | "
                f"TGT: <code>₹{parsed['target']:,.2f}</code> | "
                f"R:R <code>{rr:.1f}x</code>{expiry_str}\n\n"
                "I'll alert you when price approaches or hits this level.",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            await update.message.reply_text(f"Error adding level: {exc}")

    async def cmd_levels(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List all active price levels."""
        levels = self._engine.level_manager.list_active()
        if not levels:
            await update.message.reply_text(
                "No active levels. Add one with:\n"
                "<code>/level RELIANCE BUY 2500 SL 2450 TGT 2600</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        lines = [f"<b>Active Levels ({len(levels)})</b>\n"]
        for lvl in levels:
            expiry = f" [{lvl.expiry}]" if lvl.expiry else ""
            lines.append(
                f"<code>[{lvl.short_id}]</code> <b>{lvl.ticker}</b> "
                f"{lvl.direction} @ <code>₹{lvl.price:,.2f}</code> "
                f"SL <code>₹{lvl.sl:,.2f}</code> TGT <code>₹{lvl.target:,.2f}</code>{expiry}"
            )
        lines.append("\nUse <code>/removelevel &lt;id&gt;</code> to cancel.")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_removelevel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Remove a level by ID: /removelevel abc12345"""
        if not context.args:
            await update.message.reply_text("Usage: /removelevel <id>\nGet IDs from /levels")
            return

        level_id = context.args[0]
        try:
            deleted = await self._engine.remove_level(level_id)
            if deleted:
                await update.message.reply_text(
                    f"Level <code>{level_id}</code> removed.", parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_text(
                    f"Level <code>{level_id}</code> not found or already triggered.",
                    parse_mode=ParseMode.HTML,
                )
        except Exception as exc:
            await update.message.reply_text(f"Error: {exc}")

    async def cmd_testbroker(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Test live HDFC broker connection: authenticate + fetch funds."""
        if self._engine.is_broker_authenticated:
            await update.message.reply_text(
                "Already authenticated. Fetching funds...",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.message.reply_text(
                "<b>Testing HDFC broker connection</b>\n\n"
                "Initiating login with HDFC Securities.\n"
                "An OTP will be sent to your registered mobile.\n"
                "Reply here with the 6-digit OTP when received.",
                parse_mode=ParseMode.HTML,
            )
            asyncio.create_task(self._engine.trigger_broker_login())
            return

        try:
            funds = await self._engine.get_funds()
            await update.message.reply_text(
                "<b>HDFC Broker: Connected</b>\n\n"
                f"<b>Available Margin:</b> <code>₹{funds.get('available', 0):,.2f}</code>\n"
                f"<b>Used Margin:</b>      <code>₹{funds.get('used_margin', 0):,.2f}</code>\n"
                f"<b>Total Balance:</b>    <code>₹{funds.get('total', 0):,.2f}</code>\n",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            await update.message.reply_text(
                f"<b>Connected but funds fetch failed:</b>\n<code>{exc}</code>",
                parse_mode=ParseMode.HTML,
            )

    # ------------------------------------------------------------------ #
    #  VWLR — Vedanta Sales commands                                       #
    # ------------------------------------------------------------------ #

    async def cmd_tenders(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/tenders [BUYER|hot] — live tender pipeline from Vedanta CRM."""
        arg = " ".join(context.args).strip() if context.args else ""
        hot_only = arg.lower() == "hot"
        buyer_filter = arg if arg and not hot_only else None

        try:
            tenders = vedanta_bridge.get_tenders(
                buyer=buyer_filter, hot_only=hot_only, limit=15
            )
        except FileNotFoundError:
            await update.message.reply_text(
                "Vedanta CRM database not found. "
                "Ensure VEDANTA_DB_PATH is set or the vedanta project is at the expected path."
            )
            return

        if not tenders:
            label = f" for {buyer_filter}" if buyer_filter else (" closing within 7 days" if hot_only else "")
            await update.message.reply_text(f"No tenders found{label}.")
            return

        heading = "🔥 HOT" if hot_only else ("🏭 VWLR Tenders" + (f" — {buyer_filter.upper()}" if buyer_filter else ""))
        lines = [f"<b>{heading} ({len(tenders)})</b>\n"]
        for t in tenders:
            closing = f" | Close: {t.closing_date}" if t.closing_date else ""
            vol = f" | {t.volume_mt:,.0f} MT" if t.volume_mt else ""
            bid = f" | Our bid: ₹{t.our_bid:,.0f}" if t.our_bid else ""
            result = f" ✅" if t.result == "WON" else (" ❌" if t.result == "LOST" else "")
            lines.append(
                f"<b>{t.buyer}</b>{vol}{closing}{bid}{result}\n"
                f"<i>{t.route or t.status}</i>"
            )
        await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_leads(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/leads [all] — CRM lead pipeline."""
        arg = context.args[0].lower() if context.args else ""
        priority = None if arg == "all" else "High"

        try:
            leads = vedanta_bridge.get_leads(priority=priority, limit=15)
        except FileNotFoundError:
            await update.message.reply_text("Vedanta CRM database not found.")
            return

        if not leads:
            await update.message.reply_text("No leads found.")
            return

        heading = "All Leads" if arg == "all" else "🔥 Hot Leads (High Priority)"
        lines = [f"<b>{heading} ({len(leads)})</b>\n"]
        for l in leads:
            followup = f" | 📅 {l.next_followup}" if l.next_followup else ""
            lines.append(
                f"<b>{l.company}</b> — {l.location} ({l.distance_km:.0f}km)\n"
                f"<i>{l.potential_volume} | {l.status}{followup}</i>\n"
                f"Score: {l.tender_score} | {l.contact_person} {l.phone}"
            )
        await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_lead(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/lead COMPANY — lead detail."""
        if not context.args:
            await update.message.reply_text("Usage: /lead NTPC\nPartial company name works.")
            return
        name = " ".join(context.args)
        try:
            lead = vedanta_bridge.get_lead_detail(name)
        except FileNotFoundError:
            await update.message.reply_text("Vedanta CRM database not found.")
            return
        if not lead:
            await update.message.reply_text(f"No lead matching '{name}'.")
            return
        await update.message.reply_text(
            f"<b>{lead.company}</b>\n\n"
            f"Contact: {lead.contact_person} | {lead.phone}\n"
            f"Location: {lead.location} ({lead.distance_km:.0f} km from VWLR)\n"
            f"Volume: {lead.potential_volume}\n"
            f"Status: <b>{lead.status}</b> | Priority: {lead.priority}\n"
            f"Tender Score: {lead.tender_score}\n"
            f"Next Follow-up: {lead.next_followup or 'Not set'}\n\n"
            + (f"<i>{lead.notes}</i>" if lead.notes else ""),
            parse_mode=ParseMode.HTML,
        )

    async def cmd_followups(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/followups — leads needing follow-up today or overdue."""
        try:
            leads = vedanta_bridge.get_followups_today()
        except FileNotFoundError:
            await update.message.reply_text("Vedanta CRM database not found.")
            return
        if not leads:
            await update.message.reply_text("No follow-ups due today.")
            return
        lines = [f"<b>📅 Follow-ups Due ({len(leads)})</b>\n"]
        for l in leads:
            lines.append(
                f"<b>{l.company}</b> — {l.status}\n"
                f"{l.contact_person} {l.phone} | Due: {l.next_followup}"
            )
        await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_bid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/bid BUYER VOLUME ROUTE GATE_PRICE — bid optimizer.
        Example: /bid NTPC 50000 sipat 4200
        """
        if len(context.args) < 3:
            await update.message.reply_text(
                "<b>Usage:</b> <code>/bid BUYER VOLUME ROUTE [GATE_PRICE]</code>\n\n"
                "<b>Example:</b>\n"
                "<code>/bid NTPC 50000 sipat 4200</code>\n"
                "<code>/bid JSPL 30000 raigarh 3800</code>\n\n"
                "<b>Routes:</b> sipat, raigarh, bhilai, nagpur, raipur, korba, bilaspur",
                parse_mode=ParseMode.HTML,
            )
            return

        buyer = context.args[0]
        try:
            volume = float(context.args[1].replace(",", ""))
            route = context.args[2].lower()
            gate_price = float(context.args[3]) if len(context.args) > 3 else 4000.0
        except (ValueError, IndexError):
            await update.message.reply_text("Invalid numbers. Example: /bid NTPC 50000 sipat 4200")
            return

        result = vedanta_bridge.calculate_bid(buyer, volume, route, gate_price)
        await update.message.reply_text(
            f"<b>💰 Bid Optimizer — {result['buyer'].upper()}</b>\n\n"
            f"Volume: <code>{result['volume_mt']:,.0f} MT</code>\n"
            f"Route: <code>{result['route'].title()}</code>\n\n"
            f"Gate Price: <code>₹{result['gate_price']:,.0f}/MT</code>\n"
            f"FOIS Freight: <code>₹{result['fois_freight']:,.0f}/MT</code>\n"
            f"Landed Cost: <code>₹{result['landed_cost']:,.0f}/MT</code>\n"
            f"Volume Discount: <code>{result['volume_discount_pct']}%</code>\n\n"
            f"<b>Suggested Bid: <code>₹{result['suggested_bid']:,.0f}/MT</code></b>\n"
            f"Margin: <code>{result['margin_pct']}%</code>\n\n"
            f"Total Revenue: <code>₹{result['total_revenue']:,.0f}</code>\n"
            f"Total Margin: <code>₹{result['total_margin']:,.0f}</code>",
            parse_mode=ParseMode.HTML,
        )

    async def cmd_competitors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/competitors [threat|NAME] — competitor intel."""
        arg = " ".join(context.args).strip() if context.args else ""
        try:
            if arg.lower() == "threat":
                comps = vedanta_bridge.get_competitors(limit=15)
            elif arg:
                comp = vedanta_bridge.get_competitor_detail(arg)
                if not comp:
                    await update.message.reply_text(f"Competitor '{arg}' not found.")
                    return
                await update.message.reply_text(
                    f"<b>{comp.name}</b> [{comp.type}]\n\n"
                    f"Locations: {comp.locations}\n"
                    f"Pricing: {comp.pricing}\n"
                    f"Threat: <b>{comp.threat_level}</b>\n\n"
                    f"Strengths: <i>{comp.strengths[:200]}</i>\n"
                    f"Weaknesses: <i>{comp.weaknesses[:200]}</i>\n\n"
                    f"Recent: {comp.recent_activity[:150]}",
                    parse_mode=ParseMode.HTML,
                )
                return
            else:
                comps = vedanta_bridge.get_competitors(limit=10)
        except FileNotFoundError:
            await update.message.reply_text("Vedanta CRM database not found.")
            return

        if not comps:
            await update.message.reply_text("No competitors found.")
            return

        lines = [f"<b>🎯 Competitors ({len(comps)})</b>\n"]
        for c in comps:
            icon = "🔴" if c.threat_level in ("VERY HIGH", "HIGH") else "🟡"
            lines.append(
                f"{icon} <b>{c.name}</b> [{c.threat_level}]\n"
                f"<i>{c.locations} | {c.pricing}</i>"
            )
        await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_tender_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/tender_watch on|off — toggle real-time Grok tender monitoring."""
        arg = (context.args[0].lower() if context.args else "status")
        watch = getattr(self._engine, "_tender_watch", None)
        if watch is None:
            await update.message.reply_text(
                "Tender watch agent not initialised. Check engine setup."
            )
            return
        if arg == "on":
            watch.enabled = True
            await update.message.reply_text(
                "📋 <b>Tender Watch: ON</b>\n\n"
                "Grok will scan SECL, MCL, NTPC, JSPL, SAIL for new tenders "
                "and compliance updates every 4 hours.",
                parse_mode=ParseMode.HTML,
            )
        elif arg == "off":
            watch.enabled = False
            await update.message.reply_text("Tender Watch: OFF")
        else:
            state = "ON" if watch.enabled else "OFF"
            await update.message.reply_text(f"Tender Watch is currently <b>{state}</b>.", parse_mode=ParseMode.HTML)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        data = query.data or ""

        # -- MDO mind map navigation --
        if data.startswith("mdo_noop_"):
            return  # command label rows — no action

        # Edit mode entry
        if data.startswith("mdo_edit_"):
            node_id = data[len("mdo_edit_"):]
            await query.edit_message_text(
                mdo_edit_text(node_id),
                parse_mode="HTML",
                reply_markup=mdo_edit_keyboard(node_id),
            )
            return

        # Edit operations
        if data.startswith("mdoedit_"):
            await self._handle_mdo_edit(query, context, data)
            return

        if data.startswith("mdo_"):
            node_id = data[4:]  # strip "mdo_"
            text = mdo_node_text(node_id)
            kb   = mdo_node_keyboard(node_id) if node_id != "root" else mdo_root_keyboard()
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            return

        # -- Singhvi auto-execute toggle --
        if data.startswith("autosinghvi_"):
            action = data[len("autosinghvi_"):]
            self._engine.singhvi_auto_execute = (action == "on")
            state = "ON" if self._engine.singhvi_auto_execute else "OFF"
            await query.edit_message_text(
                f"<b>Singhvi Auto-Execute: {state}</b>",
                parse_mode="HTML",
                reply_markup=autosinghvi_keyboard(self._engine.singhvi_auto_execute),
            )
            return

        if data.startswith("confirm_"):
            signal_id = data[len("confirm_"):]
            await self._engine.confirm_trade(signal_id)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"Trade <b>{signal_id}</b> CONFIRMED. Placing order...", parse_mode=ParseMode.HTML)

        elif data.startswith("reject_"):
            signal_id = data[len("reject_"):]
            self._engine.alert_service.remove_pending_signal(signal_id)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(f"Trade <b>{signal_id}</b> rejected.", parse_mode=ParseMode.HTML)

        elif data.startswith("modify_"):
            signal_id = data[len("modify_"):]
            await query.message.reply_text(
                f"Reply with new quantity for signal <code>{signal_id}</code>:",
                parse_mode=ParseMode.HTML,
            )
            context.user_data["awaiting_qty_for"] = signal_id

        elif data.startswith("sentiment_"):
            ticker = data[len("sentiment_"):]
            await query.message.reply_text(f"Analyzing {ticker}...")
            event = await self._engine.get_sentiment(ticker)
            msg = format_sentiment(event)
            await query.message.reply_text(msg, parse_mode=ParseMode.HTML)

        elif data == "cancel_otp":
            self._engine.cancel_otp_flow()
            await query.message.reply_text("Login cancelled.")

    async def _handle_mdo_edit(self, query, context, data: str) -> None:
        """Handle all mdoedit_* callback actions."""
        store = get_store()

        # mdoedit_rename_<node_id>
        if data.startswith("mdoedit_rename_"):
            node_id = data[len("mdoedit_rename_"):]
            node = store.get(node_id)
            label = node.get("label", node_id) if node else node_id
            context.user_data["mdo_edit"] = {"action": "rename", "node_id": node_id}
            await query.message.reply_text(
                f"Enter new name for <b>{label}</b>:\n<i>(Just type it and send)</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        # mdoedit_icon_<node_id>
        if data.startswith("mdoedit_icon_"):
            node_id = data[len("mdoedit_icon_"):]
            context.user_data["mdo_edit"] = {"action": "icon", "node_id": node_id}
            await query.message.reply_text(
                "Send the new emoji icon for this section:\n<i>(e.g. 📈 💼 🏦)</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        # mdoedit_addcmd_<node_id>
        if data.startswith("mdoedit_addcmd_"):
            node_id = data[len("mdoedit_addcmd_"):]
            context.user_data["mdo_edit"] = {"action": "addcmd", "node_id": node_id}
            await query.message.reply_text(
                "Send the command to add.\n\n"
                "Format: <code>/command — description</code>\n"
                "Or just: <code>/command</code>\n\n"
                "<i>Example: /myreport — Daily summary report</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        # mdoedit_addsec_<parent_id>
        if data.startswith("mdoedit_addsec_"):
            parent_id = data[len("mdoedit_addsec_"):]
            context.user_data["mdo_edit"] = {"action": "addsec", "node_id": parent_id}
            await query.message.reply_text(
                "Send new section details.\n\n"
                "Format: <code>emoji Name of section</code>\n"
                "<i>Example: 🏢 ANS Corporate</i>",
                parse_mode=ParseMode.HTML,
            )
            return

        # mdoedit_rmcmd_<node_id>_<index>
        if data.startswith("mdoedit_rmcmd_"):
            rest = data[len("mdoedit_rmcmd_"):]
            # Split from right to get index
            parts = rest.rsplit("_", 1)
            if len(parts) == 2:
                node_id, idx_str = parts
                try:
                    idx = int(idx_str)
                    store.remove_command(node_id, idx)
                    await query.edit_message_text(
                        mdo_edit_text(node_id),
                        parse_mode="HTML",
                        reply_markup=mdo_edit_keyboard(node_id),
                    )
                except (ValueError, Exception):
                    await query.answer("Could not remove command.", show_alert=True)
            return

        # mdoedit_del_<node_id>
        if data.startswith("mdoedit_del_"):
            node_id = data[len("mdoedit_del_"):]
            node = store.get(node_id)
            label = node.get("label", node_id) if node else node_id
            # Confirm via a second tap
            pending = context.user_data.get("mdo_delete_pending")
            if pending == node_id:
                # Second tap — confirmed
                store.remove_section(node_id)
                context.user_data.pop("mdo_delete_pending", None)
                root_text = mdo_node_text("root")
                await query.edit_message_text(
                    f"<b>{label}</b> deleted.\n\n{root_text}",
                    parse_mode="HTML",
                    reply_markup=mdo_root_keyboard(),
                )
            else:
                # First tap — ask to confirm
                context.user_data["mdo_delete_pending"] = node_id
                await query.answer(f"Tap '🗑 Delete' again to confirm deleting '{label}'", show_alert=True)
            return

    async def cmd_grok(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/grok <question> — ask Grok anything with live X + news + web search."""
        if not context.args:
            await update.message.reply_text(
                "<b>Usage:</b> <code>/grok what is happening with RELIANCE today</code>\n\n"
                "Grok will search live X posts, news, and web to answer.",
                parse_mode=ParseMode.HTML,
            )
            return

        question = " ".join(context.args)
        await update.message.reply_text(
            f"<i>Asking Grok: {question[:80]}...</i>",
            parse_mode=ParseMode.HTML,
        )

        try:
            answer = await self._engine.ask_grok(question)
            # Telegram HTML max 4096 chars
            if len(answer) > 3800:
                answer = answer[:3800] + "\n\n<i>[truncated]</i>"
            await update.message.reply_text(
                f"<b>Grok</b>\n\n{answer}",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            log.error("grok_command_error", error=str(exc))
            await update.message.reply_text(f"Grok error: {exc}")

    async def cmd_brief(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/brief — morning market overview from Grok (global cues, FII, trending tickers)."""
        await update.message.reply_text(
            "<i>Fetching morning brief from Grok (live X + news)...</i>",
            parse_mode=ParseMode.HTML,
        )
        try:
            brief = await self._engine.get_morning_brief()
            await update.message.reply_text(brief, parse_mode=ParseMode.HTML)
        except Exception as exc:
            log.error("brief_command_error", error=str(exc))
            await update.message.reply_text(f"Brief error: {exc}")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (update.message.text or "").strip()

        # -- MDO edit input --
        edit_state = context.user_data.get("mdo_edit")
        if edit_state and text:
            await self._apply_mdo_edit(update, context, edit_state, text)
            return

        # Handle OTP input
        if self._engine.awaiting_otp and text.isdigit() and len(text) == 6:
            await self._engine.submit_otp(text)
            await update.message.reply_text("OTP submitted. Authenticating...")
            return

        # Handle quantity modification
        signal_id = context.user_data.get("awaiting_qty_for")
        if signal_id and text.isdigit():
            qty = int(text)
            context.user_data.pop("awaiting_qty_for", None)
            await self._engine.confirm_trade(signal_id, modified_qty=qty)
            await update.message.reply_text(
                f"Trade <b>{signal_id}</b> confirmed with qty <code>{qty}</code>. Placing order...",
                parse_mode=ParseMode.HTML,
            )
            return

    async def _apply_mdo_edit(self, update, context, edit_state: dict, text: str) -> None:
        """Apply a pending MDO edit from user text input."""
        store = get_store()
        action  = edit_state.get("action", "")
        node_id = edit_state.get("node_id", "")
        context.user_data.pop("mdo_edit", None)  # clear state

        if action == "rename":
            ok = store.rename(node_id, text)
            if ok:
                node = store.get(node_id)
                label = node.get("label", node_id) if node else node_id
                await update.message.reply_text(
                    f"✅ Renamed to <b>{label}</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=mdo_edit_keyboard(node_id),
                )
            else:
                await update.message.reply_text("Could not rename — node not found.")

        elif action == "icon":
            icon = text.strip()[:4]
            ok = store.set_icon(node_id, icon)
            if ok:
                await update.message.reply_text(
                    f"✅ Icon updated to {icon}",
                    reply_markup=mdo_edit_keyboard(node_id),
                )
            else:
                await update.message.reply_text("Could not update icon.")

        elif action == "addcmd":
            # Parse "  /cmd — description" or "/cmd"
            if "—" in text:
                parts = text.split("—", 1)
                cmd  = parts[0].strip()
                desc = parts[1].strip()
            elif "-" in text and text.index("-") > 2:
                parts = text.split("-", 1)
                cmd  = parts[0].strip()
                desc = parts[1].strip()
            else:
                cmd  = text.strip()
                desc = ""
            ok = store.add_command(node_id, cmd, desc)
            if ok:
                await update.message.reply_text(
                    f"✅ Added: <code>{cmd}</code>" + (f" — {desc}" if desc else ""),
                    parse_mode=ParseMode.HTML,
                    reply_markup=mdo_edit_keyboard(node_id),
                )
            else:
                await update.message.reply_text("Could not add command (is this a parent node?).")

        elif action == "addsec":
            # Parse "emoji Name" e.g. "🏢 ANS Corporate"
            parts = text.strip().split(" ", 1)
            if len(parts) == 2 and len(parts[0]) <= 4:
                icon  = parts[0]
                label = parts[1]
            else:
                icon  = "📌"
                label = text.strip()
            # Generate a node_id from label
            new_id = label.lower().replace(" ", "_")[:20]
            # Ensure uniqueness
            base_id = new_id
            i = 1
            while store.get(new_id) is not None:
                new_id = f"{base_id}_{i}"
                i += 1
            ok = store.add_section(node_id, new_id, label, icon)
            if ok:
                await update.message.reply_text(
                    f"✅ Section <b>{icon} {label}</b> added under this node.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=mdo_node_keyboard(node_id),
                )
            else:
                await update.message.reply_text("Could not add section.")

        else:
            await update.message.reply_text("Unknown edit action.")
