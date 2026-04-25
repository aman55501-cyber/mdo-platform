"""Main orchestrator that wires all VEGA components together."""

from __future__ import annotations

import asyncio
from datetime import date

from telegram import Bot

from .broker.auth import HdfcAuth
from .broker.client import HdfcClient
from .broker.market_data import MarketDataService
from .broker.models import Order, OrderSide, OrderType, ProductType, Exchange
from .broker.orders import OrderService
from .broker.portfolio import PortfolioService
from .config import VegaConfig
from .data.store import DataStore
from .events import (
    EventBus,
    EventType,
    MarketDataEvent,
    OrderUpdateEvent,
    SentimentEvent,
    SignalEvent,
    TradeConfirmEvent,
)
from .core.alerts import Alert, AlertRouter, AlertTier
from .core.scheduler import Schedule, ScheduleManager
from .exceptions import AuthenticationError
from .sentiment.analyzer import SentimentAnalyzer
from .sentiment.client import GrokClient
from .sentiment.models import SentimentSignal
from .sentiment.poller import SentimentPoller
from .sentiment.portfolio_watch import PortfolioWatchAgent
from .vedanta.tender_watch import TenderWatchAgent
from .sentiment.singhvi import SinghviMonitor
from .sentiment.youtube_monitor import ZeeBusinessMonitor
from .strategy.levels import LevelManager, load_levels_yaml, parse_level_command
from .strategy.momentum import MomentumStrategy
from .strategy.risk import RiskManager
from .exports.sheets import SheetsExporter
from .telegram_bot.alerts import AlertService
from .telegram_bot.bot import VegaTelegramBot
from .utils.logging import get_logger, setup_logging
from .utils.time import (
    format_ist,
    is_market_open,
    now_ist,
    seconds_until_market_open,
)

log = get_logger("engine")


class VegaEngine:
    """Central orchestrator managing the lifecycle of all VEGA services."""

    def __init__(self, config: VegaConfig) -> None:
        self.config = config

        # Core
        self._event_bus = EventBus()
        self._store = DataStore(config.db_path)

        # Broker
        self._auth = HdfcAuth(config.hdfc)
        self._broker_client = HdfcClient(config.hdfc, self._auth)
        self._orders = OrderService(self._broker_client)
        self._portfolio = PortfolioService(self._broker_client)
        self._market_data = MarketDataService(self._broker_client, self._event_bus)

        # Sentiment
        self._grok = GrokClient(config.grok)
        self._analyzer = SentimentAnalyzer()
        self._sentiment_poller = SentimentPoller(
            self._grok, self._analyzer, self._event_bus, self._store, config.grok
        )

        # Strategy
        self._risk_manager = RiskManager(config.strategy)
        self._strategy = MomentumStrategy(config.strategy, self._risk_manager)
        self.level_manager = LevelManager(self._store)

        # Singhvi + Zee Business monitors
        self._singhvi = SinghviMonitor(self._grok, self._event_bus, self._store)
        self._zee = ZeeBusinessMonitor(self._grok)

        # Cross-cutting services (wired in run() once alert_service exists)
        self._alert_router: AlertRouter | None = None
        self._scheduler: ScheduleManager | None = None
        self._portfolio_watch: PortfolioWatchAgent | None = None
        self._tender_watch: TenderWatchAgent | None = None

        # MDO Sheets exporter
        self._sheets = SheetsExporter()

        # Telegram
        self._bot: VegaTelegramBot | None = None
        self.alert_service: AlertService | None = None

        # State
        self._latest_sentiment: dict[str, SentimentSignal] = {}
        self._latest_market: dict[str, MarketDataEvent] = {}
        self._running = False

        # Feature flags
        self._singhvi_auto_execute: bool = False  # set True via /autosinghvi on

    # -- Properties for handlers --

    @property
    def is_broker_authenticated(self) -> bool:
        return self._auth.is_authenticated

    @property
    def awaiting_otp(self) -> bool:
        return self._auth.awaiting_otp

    @property
    def active_position_count(self) -> int:
        return self._risk_manager.state.position_count

    @property
    def singhvi_auto_execute(self) -> bool:
        return self._singhvi_auto_execute

    @singhvi_auto_execute.setter
    def singhvi_auto_execute(self, value: bool) -> None:
        self._singhvi_auto_execute = value
        self._singhvi.auto_execute_fn = self._auto_execute_singhvi_call if value else None
        log.info("singhvi_auto_execute_set", enabled=value)

    # -- Public interface for Telegram handlers --

    async def get_sentiment(self, ticker: str) -> SentimentEvent:
        signal = await self._sentiment_poller.poll_once(ticker)
        return SentimentEvent(
            ticker=signal.ticker,
            score=signal.score,
            confidence=signal.confidence,
            summary=signal.summary,
            themes=signal.themes,
            post_count=signal.post_count,
            timestamp=signal.timestamp,
        )

    async def get_positions(self) -> list[dict]:
        if not self._auth.is_authenticated:
            return list(self._risk_manager.state.positions.values())
        positions = await self._portfolio.get_positions()
        return [p.to_dict() for p in positions]

    async def get_holdings(self) -> list[dict]:
        if not self._auth.is_authenticated:
            return []
        holdings = await self._portfolio.get_holdings()
        return [h.to_dict() for h in holdings]

    async def get_funds(self) -> dict:
        if not self._auth.is_authenticated:
            return {"available": 0, "used_margin": 0, "total": 0}
        funds = await self._portfolio.get_funds()
        return funds.to_dict()

    async def get_daily_stats(self) -> dict:
        return await self._store.get_daily_stats()

    async def health_check(self) -> dict[str, bool]:
        return {
            "Broker Auth": self._auth.is_authenticated,
            "Grok API": self.config.grok.api_key != "",
            "Telegram Bot": self._bot is not None,
            "Database": self._store._db is not None,
            "Market Open": is_market_open(),
        }

    async def trigger_broker_login(self) -> None:
        """Public entry point for /testbroker command — runs the full auth flow."""
        await self._authenticate_broker()

    async def add_level(self, ticker: str, direction: str, price: float,
                        sl: float, target: float, expiry: str | None = None) -> str:
        """Add a price level. Returns short ID."""
        lvl = await self.level_manager.add_level(ticker, direction, price, sl, target, expiry)
        return lvl.short_id

    async def remove_level(self, level_id: str) -> bool:
        return await self.level_manager.remove_level(level_id)

    async def ask_grok(self, question: str) -> str:
        """Forward a free-form question to Grok with live X + news + web search."""
        return await self._grok.ask(question)

    async def get_morning_brief(self) -> str:
        """Fetch and format a morning market overview from Grok."""
        from .sentiment.prompts import MORNING_BRIEF_PROMPT
        today = now_ist().strftime("%Y-%m-%d %A")
        system = MORNING_BRIEF_PROMPT.format(date=today)
        user = (
            f"Give me a complete morning market brief for Indian equity traders. "
            f"Today is {today}. Search X, news, and web for the latest data."
        )
        raw = await self._grok.market_overview(system, user)
        return _format_morning_brief(raw)

    async def get_singhvi_calls(self) -> list:
        """Return latest Singhvi calls (cached). Triggers fresh poll if empty."""
        calls = self._singhvi.latest_calls
        if not calls:
            calls = await self._singhvi.poll_once()
        return calls

    async def _auto_execute_singhvi_call(self, call) -> None:
        """Called by SinghviMonitor when auto-execute is enabled.
        Places an order if: market is open, broker authenticated, risk limits allow.
        """
        from .utils.time import is_market_open as _market_open

        if not _market_open():
            log.info("singhvi_auto_skip_market_closed", ticker=call.ticker)
            return
        if not self._auth.is_authenticated:
            log.info("singhvi_auto_skip_not_authenticated", ticker=call.ticker)
            return

        # Build a minimal SignalEvent and route through confirmation-less path
        funds = await self._portfolio.get_funds()
        available = funds.available

        # Use risk manager to size the position
        side = OrderSide.BUY if call.direction == "BUY" else OrderSide.SELL
        try:
            entry = call.price_level or 0.0
            sl = call.stop_loss or (entry * 0.98 if side == OrderSide.BUY else entry * 1.02)
            qty = self._risk_manager.calculate_position_size(
                entry_price=entry,
                stop_loss=sl,
                available_capital=available,
                ticker=call.ticker,
            )
        except Exception:
            qty = 1  # fallback — 1 share

        if qty <= 0:
            log.info("singhvi_auto_skip_zero_qty", ticker=call.ticker)
            return

        order = Order(
            ticker=call.ticker,
            exchange=Exchange.NSE,
            side=side,
            order_type=OrderType.MARKET,
            product_type=ProductType.MIS,
            quantity=qty,
        )
        result = await self._orders.place_order(order)
        log.info(
            "singhvi_order_placed",
            ticker=call.ticker,
            direction=call.direction,
            qty=qty,
            order_id=result.order_id,
        )
        if self.alert_service:
            price_parts = []
            if call.entry_price:
                price_parts.append(f"Entry ₹{call.entry_price:,.0f}")
            if call.stop_loss:
                price_parts.append(f"SL ₹{call.stop_loss:,.0f}")
            if call.target:
                price_parts.append(f"TGT ₹{call.target:,.0f}")
            price_line = " | ".join(price_parts)
            ts = call.post_timestamp if call.post_timestamp != "recent" else "now"
            await self.alert_service.send_text(
                f"<b>⚡ Singhvi Auto-Execute</b>\n\n"
                f"<b>{call.ticker}</b> {call.direction} x{qty}  [{call.validity}]\n"
                f"<code>{price_line}</code>\n"
                f"Posted: <i>{ts}</i>\n\n"
                f"<i>{call.summary}</i>\n\n"
                f"Order ID: <code>{result.order_id}</code>"
            )

    async def submit_otp(self, otp: str) -> None:
        self._auth.submit_otp(otp)

    def cancel_otp_flow(self) -> None:
        self._auth.cancel_otp()

    async def confirm_trade(self, signal_id: str, modified_qty: int | None = None) -> None:
        """User confirmed a trade suggestion. Place the order."""
        if not self.alert_service:
            return

        signal = self.alert_service.get_pending_signal(signal_id)
        if not signal:
            log.warning("confirm_unknown_signal", signal_id=signal_id)
            return

        qty = modified_qty or signal.quantity

        order = Order(
            ticker=signal.ticker,
            exchange=Exchange.NSE,
            side=OrderSide.BUY if signal.action == "BUY" else OrderSide.SELL,
            order_type=OrderType.MARKET,
            product_type=ProductType.MIS,
            quantity=qty,
        )

        try:
            result = await self._orders.place_order(order)
            await self._store.save_execution(
                signal_id=signal_id,
                order_id=result.order_id,
                side=signal.action,
                status="placed",
            )
            await self._store.update_signal_status(signal_id, "executed")
            self.alert_service.remove_pending_signal(signal_id)

            update = OrderUpdateEvent(
                order_id=result.order_id,
                ticker=signal.ticker,
                status="placed",
                message=result.message,
            )
            await self.alert_service.send_order_update(update)

            # Track position in risk manager
            self._risk_manager.state.positions[signal.ticker] = {
                "ticker": signal.ticker,
                "quantity": qty,
                "entry_price": signal.entry_price,
                "target": signal.target_price,
                "stop_loss": signal.stop_loss,
                "signal_id": signal_id,
            }

        except Exception as exc:
            log.error("order_placement_error", signal_id=signal_id, error=str(exc))
            if self.alert_service:
                await self.alert_service.send_text(f"Order failed: {exc}")

    # -- Event handlers --

    async def _on_market_data(self, event: MarketDataEvent) -> None:
        self._latest_market[event.ticker] = event

        # Check user-defined price levels
        triggers = self.level_manager.check_levels(event.ticker, event.ltp)
        for trigger in triggers:
            lvl = trigger.level
            if trigger.kind == "triggered":
                await self.level_manager.mark_triggered(lvl.id)
                signal = SignalEvent(
                    ticker=lvl.ticker,
                    action=lvl.direction,
                    entry_price=event.ltp,
                    target_price=lvl.target,
                    stop_loss=lvl.sl,
                    quantity=1,  # placeholder; risk manager will size properly
                    rationale=f"Level hit: {lvl.direction} @ {lvl.price:.2f} (LTP {event.ltp:.2f})",
                )
                if self.alert_service:
                    await self.alert_service.send_trade_suggestion(signal)
                log.info("level_triggered", ticker=lvl.ticker, direction=lvl.direction, price=lvl.price)
            elif trigger.kind == "proximity":
                await self.level_manager.mark_proximity_alerted(lvl.id)
                if self.alert_service:
                    dist_pct = abs(event.ltp - lvl.price) / lvl.price * 100
                    await self.alert_service.send_text(
                        f"⚡ <b>{lvl.ticker}</b> approaching {lvl.direction} level "
                        f"₹{lvl.price:,.2f} — LTP ₹{event.ltp:,.2f} ({dist_pct:.2f}% away)"
                    )

        # Check exit conditions for open positions
        pos = self._risk_manager.state.positions.get(event.ticker)
        if pos:
            sentiment = self._latest_sentiment.get(event.ticker)
            sentiment_signal = None
            if sentiment:
                sentiment_signal = SentimentSignal(
                    ticker=event.ticker,
                    score=sentiment.score,
                    confidence=sentiment.confidence,
                )

            should_exit, reason = self._strategy.check_exit(
                event.ticker, event.ohlcv, event.ltp,
                pos["entry_price"], pos["target"], pos["stop_loss"],
                sentiment_signal,
            )
            if should_exit and self.alert_service:
                exit_signal = SignalEvent(
                    ticker=event.ticker,
                    action="SELL",
                    entry_price=event.ltp,
                    target_price=pos["target"],
                    stop_loss=pos["stop_loss"],
                    quantity=pos["quantity"],
                    rationale=f"EXIT: {reason}",
                )
                await self.alert_service.send_trade_suggestion(exit_signal)

    async def _on_sentiment(self, event: SentimentEvent) -> None:
        self._latest_sentiment[event.ticker] = event

    async def _evaluate_signals(self) -> None:
        """Run strategy on all watchlist tickers."""
        funds = await self.get_funds()
        available = funds.get("available", 0)
        if available <= 0:
            return

        for ticker in self.config.watchlist:
            market = self._latest_market.get(ticker)
            if not market:
                continue

            sent_data = self._latest_sentiment.get(ticker)
            sentiment = None
            if sent_data:
                sentiment = SentimentSignal(
                    ticker=ticker,
                    score=sent_data.score,
                    confidence=sent_data.confidence,
                    summary=sent_data.summary,
                    themes=sent_data.themes,
                    post_count=sent_data.post_count,
                )

            signal = self._strategy.evaluate(
                ticker=ticker,
                ohlcv=market.ohlcv,
                ltp=market.ltp,
                sentiment=sentiment,
                available_capital=available,
            )

            if signal and self.alert_service:
                await self._store.save_signal(signal)
                await self.alert_service.send_trade_suggestion(signal)

    # -- Lifecycle --

    async def _authenticate_broker(self) -> None:
        """Run HDFC auth flow with OTP via Telegram."""
        if self.alert_service:
            await self.alert_service.send_text(
                "HDFC Securities login required.\n"
                "An OTP will be sent to your registered phone.\n"
                "Reply with the 6-digit OTP."
            )

        try:
            await self._auth.initiate_login()
            otp = await self._auth.wait_for_otp(timeout=120.0)
            await self._auth.complete_login(otp)

            log.info("broker_authenticated")
            if self.alert_service:
                try:
                    funds = await self._portfolio.get_funds()
                    await self.alert_service.send_text(
                        "<b>HDFC Securities: Login successful!</b>\n\n"
                        f"<b>Available:</b> <code>₹{funds.available:,.2f}</code>\n"
                        f"<b>Used:</b>      <code>₹{funds.used_margin:,.2f}</code>\n"
                        f"<b>Total:</b>     <code>₹{funds.total:,.2f}</code>"
                    )
                except Exception as exc:
                    await self.alert_service.send_text(
                        f"HDFC Securities: Login successful!\n"
                        f"(Funds fetch failed: {exc})"
                    )
        except AuthenticationError as exc:
            log.error("broker_auth_failed", error=str(exc))
            if self.alert_service:
                await self.alert_service.send_text(f"Login failed: {exc}")

    async def _send_morning_brief(self) -> None:
        """Scheduled task: post morning market overview at 08:50 IST."""
        try:
            brief = await self.get_morning_brief()
            if self.alert_service:
                await self.alert_service.send_text(brief)
            log.info("morning_brief_sent")
        except Exception as exc:
            log.error("morning_brief_error", error=str(exc))

    async def _send_weekly_digest(self) -> None:
        """Scheduled task: Sunday morning business digest (VWLR + portfolio)."""
        if now_ist().weekday() != 6:   # Sunday only
            return
        try:
            lines = ["<b>📋 Weekly Digest — ANS Group</b>\n"]
            # Trading summary
            if self.alert_service and self._auth.is_authenticated:
                try:
                    stats = await self.get_daily_stats()
                    lines.append(
                        f"<b>Aditi P&L (week):</b> "
                        f"₹{stats.get('total_pnl', 0):+,.0f}"
                    )
                except Exception:
                    pass
            # VWLR follow-ups due
            try:
                from .vedanta.bridge import get_followups_today
                followups = get_followups_today()
                if followups:
                    lines.append(f"\n<b>VWLR Follow-ups due:</b> {len(followups)}")
                    for f in followups[:3]:
                        lines.append(f"  • {f.company} — {f.status}")
            except Exception:
                pass

            if self.alert_service:
                await self.alert_service.send_text("\n".join(lines))
            log.info("weekly_digest_sent")
        except Exception as exc:
            log.error("weekly_digest_error", error=str(exc))

    async def _push_to_mdo_sheets(self) -> None:
        """Push portfolio snapshot to MDO Live Sheet (tabs 4, 5, 6)."""
        if not self._sheets.is_available or not self._auth.is_authenticated:
            return
        try:
            funds = await self._portfolio.get_funds()
            positions = await self._portfolio.get_positions()
            pos_dicts = [p.to_dict() for p in positions]

            self._sheets.push_portfolio_snapshot(
                available=funds.available,
                used_margin=funds.used_margin,
                total=funds.total,
                positions=pos_dicts,
            )
            self._sheets.push_fo_positions(pos_dicts)
            self._sheets.append_investments_balance(funds.available, funds.total)
            log.info("mdo_sheets_pushed")
        except Exception as exc:
            log.error("mdo_sheets_push_error", error=str(exc))

    async def _strategy_loop(self) -> None:
        """Periodically evaluate strategy during market hours."""
        _last_sheet_push_day = None
        while self._running:
            if is_market_open() and self._auth.is_authenticated:
                try:
                    await self._evaluate_signals()
                except Exception as exc:
                    log.error("strategy_eval_error", error=str(exc))

                # Push to MDO Sheets once per day at close (~15:30)
                today = now_ist().date()
                now = now_ist()
                if (
                    _last_sheet_push_day != today
                    and now.hour == 15
                    and now.minute >= 30
                ):
                    await self._push_to_mdo_sheets()
                    _last_sheet_push_day = today

            await asyncio.sleep(60)  # Evaluate every minute

    async def run(self) -> None:
        """Main async entry point. Runs until interrupted."""
        setup_logging(self.config.log_level)
        log.info("vega_starting", version="0.1.0")

        # Initialize database
        await self._store.connect()

        # Load levels from DB + default levels.yaml
        await self.level_manager.load()
        yaml_path = "levels.yaml"
        for raw in load_levels_yaml(yaml_path):
            try:
                await self.level_manager.add_level(
                    ticker=raw["ticker"],
                    direction=raw["direction"],
                    price=float(raw["price"]),
                    sl=float(raw["sl"]),
                    target=float(raw["target"]),
                    expiry=raw.get("expiry"),
                    source="config",
                )
            except (KeyError, ValueError) as exc:
                log.warning("levels_yaml_invalid_entry", error=str(exc))

        # Subscribe to events
        self._event_bus.subscribe(EventType.MARKET_DATA, self._on_market_data)
        self._event_bus.subscribe(EventType.SENTIMENT, self._on_sentiment)

        # Build Telegram bot
        self._bot = VegaTelegramBot(self.config.telegram, self)
        app = self._bot.build()

        # Create alert service
        bot_instance = Bot(token=self.config.telegram.bot_token)
        chat_id = self.config.telegram.alert_chat_id or self.config.telegram.chat_id
        self.alert_service = AlertService(bot_instance, chat_id)

        # Shared alert router — single dedup + digest for all agents
        self._alert_router = AlertRouter(send_fn=self.alert_service.send_text)

        # Wire agents with shared router
        self._portfolio_watch = PortfolioWatchAgent(
            grok=self._grok,
            get_positions_fn=self.get_positions,
            get_holdings_fn=self.get_holdings,
            alert_router=self._alert_router,
        )
        self._tender_watch = TenderWatchAgent(
            grok=self._grok,
            alert_router=self._alert_router,
        )

        # Declare all scheduled tasks in one place
        self._scheduler = ScheduleManager()
        self._scheduler.add(Schedule(
            name="morning_brief",
            fn=self._send_morning_brief,
            at_times=["08:50"],
            weekdays_only=True,
        ))
        self._scheduler.add(Schedule(
            name="alert_digest",
            fn=self._alert_router.flush_digest,
            interval_seconds=3600,   # hourly
        ))
        self._scheduler.add(Schedule(
            name="weekly_digest",
            fn=self._send_weekly_digest,
            at_times=["08:00"],
            weekdays_only=False,     # runs on Sunday
        ))

        dashboard_url = f"http://localhost:{self.config.dashboard.port}" if self.config.dashboard.enabled else "disabled"
        await self.alert_service.send_text(
            "<b>VEGA Trading Agent Started</b>\n"
            f"Time: {format_ist(now_ist())}\n"
            f"Watchlist: {', '.join(self.config.watchlist)}\n"
            f"Dashboard: {dashboard_url}\n"
            "Type /help for commands."
        )

        # Start dashboard if enabled
        if self.config.dashboard.enabled:
            from .dashboard.server import create_app as create_dashboard
            import uvicorn

            dashboard_app = create_dashboard(self)
            dashboard_config = uvicorn.Config(
                dashboard_app,
                host=self.config.dashboard.host,
                port=self.config.dashboard.port,
                log_level="warning",
            )
            dashboard_server = uvicorn.Server(dashboard_config)
            log.info(
                "dashboard_starting",
                host=self.config.dashboard.host,
                port=self.config.dashboard.port,
            )

        # Start all concurrent tasks
        self._running = True
        tasks = [
            asyncio.create_task(self._event_bus.start(), name="event_bus"),
            asyncio.create_task(
                self._market_data.poll_loop(self.config.watchlist), name="market_data"
            ),
            asyncio.create_task(
                self._sentiment_poller.poll_loop(self.config.watchlist), name="sentiment"
            ),
            asyncio.create_task(self._singhvi.poll_loop(), name="singhvi"),
            asyncio.create_task(self._zee.poll_loop(), name="zee_business"),
            asyncio.create_task(self._strategy_loop(), name="strategy"),
            asyncio.create_task(self._portfolio_watch.watch_loop(), name="portfolio_watch"),
            asyncio.create_task(self._tender_watch.watch_loop(), name="tender_watch"),
            asyncio.create_task(self._scheduler.run(), name="scheduler"),
        ]

        if self.config.dashboard.enabled:
            tasks.append(asyncio.create_task(dashboard_server.serve(), name="dashboard"))

        # Run Telegram bot polling alongside other tasks
        async with app:
            await app.start()
            # Register command menu in Telegram (the "/" popup list)
            await self._bot.register_commands()
            updater = app.updater
            if updater:
                await updater.start_polling(drop_pending_updates=True)

            log.info("vega_running", tasks=len(tasks))

            try:
                await asyncio.gather(*tasks)
            except asyncio.CancelledError:
                log.info("vega_shutting_down")
            finally:
                self._running = False  # also stops _morning_brief_loop
                self._market_data.stop()
                self._sentiment_poller.stop()
                self._singhvi.stop()
                self._zee.stop()
                if self._portfolio_watch:
                    self._portfolio_watch.stop()
                if self._tender_watch:
                    self._tender_watch.stop()
                if self._scheduler:
                    self._scheduler.stop()
                self._event_bus.stop()

                if updater:
                    await updater.stop()
                await app.stop()

                await self._auth.logout()
                await self._auth.close()
                await self._broker_client.close()
                await self._grok.close()
                await self._store.close()

                log.info("vega_stopped")

    async def shutdown(self) -> None:
        self._running = False


def _format_morning_brief(raw: dict) -> str:
    """Format a Grok market_overview JSON dict into a Telegram-ready HTML message."""
    bias_emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}
    nifty = raw.get("nifty_bias", "neutral")
    bnf = raw.get("banknifty_bias", "neutral")

    lines = [
        f"<b>🌅 Morning Brief — {now_ist().strftime('%d %b %Y')}</b>\n",
        f"<b>Nifty:</b> {bias_emoji.get(nifty, '➡️')} {nifty.upper()}   "
        f"<b>BankNifty:</b> {bias_emoji.get(bnf, '➡️')} {bnf.upper()}\n",
    ]

    if raw.get("global_cue"):
        lines.append(f"<b>Global:</b> {raw['global_cue']}")
    if raw.get("fii_dii"):
        lines.append(f"<b>FII/DII:</b> {raw['fii_dii']}")
    if raw.get("crude_usd"):
        lines.append(f"<b>Crude/₹:</b> {raw['crude_usd']}")

    events = raw.get("key_events", [])
    if events:
        lines.append("\n<b>Key Events Today:</b>")
        for ev in events[:4]:
            lines.append(f"  • {ev}")

    trending = raw.get("trending_tickers", [])
    if trending:
        lines.append("\n<b>Trending on X:</b>")
        for t in trending[:5]:
            if isinstance(t, dict):
                lines.append(f"  📌 <b>{t.get('ticker','')}</b> — {t.get('reason','')}")
            else:
                lines.append(f"  📌 {t}")

    singhvi = raw.get("singhvi_today", "")
    if singhvi and singhvi.lower() != "no post yet":
        lines.append(f"\n<b>Singhvi:</b> <i>{singhvi}</i>")

    summary = raw.get("summary", "")
    if summary:
        lines.append(f"\n<i>{summary}</i>")

    return "\n".join(lines)
