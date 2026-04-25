"""Portfolio Intelligence Agent — 24/7 Grok scanner for position/holding impact.

For every open position and long-term holding, this agent searches X/Twitter,
news, and the web for developments that could affect P&L. It runs continuously:
- Every 15 minutes during market hours (9:00–15:45 IST)
- Every 45 minutes off-hours (global news and FII activity don't stop)

Alert routing is delegated to AlertRouter (core/alerts.py) — no local dedup logic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from ..core.alerts import Alert, AlertRouter, AlertTier
from ..utils.logging import get_logger
from ..utils.time import is_market_open, now_ist
from .client import GrokClient
from .prompts import HOLDINGS_WATCH_PROMPT, PORTFOLIO_WATCH_PROMPT

log = get_logger("portfolio_watch")

POLL_MARKET_SECONDS = 15 * 60    # 15 min during market hours
POLL_OFFHOURS_SECONDS = 45 * 60  # 45 min off-hours


@dataclass
class WatchAlert:
    ticker: str
    impact_level: str        # HIGH | MEDIUM | LOW | NONE
    position_bias: str       # favourable | adverse | neutral
    action_suggestion: str
    revised_sl: float | None
    alert_summary: str
    findings: list[dict]
    is_holding: bool = False
    created_at: datetime = field(default_factory=now_ist)


class PortfolioWatchAgent:
    """Continuously monitors positions and holdings for impactful news via Grok.

    Injected with:
      get_positions_fn  — async () → list[dict]  (intraday positions)
      get_holdings_fn   — async () → list[dict]  (long-term holdings)
      alert_router      — AlertRouter instance (shared with other agents)
    """

    def __init__(
        self,
        grok: GrokClient,
        get_positions_fn,
        get_holdings_fn,
        alert_router: AlertRouter,
    ) -> None:
        self._grok = grok
        self._get_positions = get_positions_fn
        self._get_holdings = get_holdings_fn
        self._router = alert_router
        self._running = False

    async def watch_loop(self) -> None:
        self._running = True
        log.info("portfolio_watch_started")
        while self._running:
            try:
                await self._scan_all()
            except Exception as exc:
                log.error("portfolio_watch_error", error=str(exc))

            interval = POLL_MARKET_SECONDS if is_market_open() else POLL_OFFHOURS_SECONDS
            await asyncio.sleep(interval)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------ #

    async def _scan_all(self) -> None:
        now = now_ist()
        lookback = 1 if is_market_open() else 4  # hours to search back

        # Positions (intraday / short-term)
        try:
            positions = await self._get_positions()
        except Exception:
            positions = []

        for pos in positions:
            ticker = pos.get("ticker", "")
            if not ticker:
                continue
            try:
                alert = await self._check_position(pos, lookback)
                if alert:
                    await self._handle_alert(alert)
            except Exception as exc:
                log.error("position_watch_error", ticker=ticker, error=str(exc))

        # Holdings (only every hour off-market to save cost)
        if not is_market_open() and now.minute < 10:
            try:
                holdings = await self._get_holdings()
            except Exception:
                holdings = []

            for h in holdings:
                ticker = h.get("ticker", "")
                if not ticker:
                    continue
                try:
                    alert = await self._check_holding(h)
                    if alert:
                        await self._handle_alert(alert)
                except Exception as exc:
                    log.error("holding_watch_error", ticker=ticker, error=str(exc))

        # Send hourly MEDIUM digest
        await self._maybe_send_digest(now)

    async def _check_position(self, pos: dict, lookback_hours: int) -> WatchAlert | None:
        ticker = pos.get("ticker", "")
        direction = pos.get("side", pos.get("direction", "BUY")).upper()
        long_short = "long position" if direction == "BUY" else "short position"
        entry_price = float(pos.get("entry_price", 0) or 0)
        stop_loss = float(pos.get("stop_loss", 0) or 0)
        target = float(pos.get("target", 0) or 0)
        entered_at = pos.get("entered_at", pos.get("created_at", "today"))
        pnl = float(pos.get("pnl", 0) or 0)
        pnl_str = f"₹{pnl:+,.0f}" if pnl else "unknown"

        system = PORTFOLIO_WATCH_PROMPT.format(
            ticker=ticker,
            direction=direction,
            long_short=long_short,
            entry_price=f"{entry_price:,.2f}" if entry_price else "unknown",
            stop_loss=f"{stop_loss:,.2f}" if stop_loss else "not set",
            target=f"{target:,.2f}" if target else "not set",
            entered_at=entered_at,
            pnl_str=pnl_str,
            lookback_hours=lookback_hours,
        )
        user = (
            f"Scan right now for any new developments about {ticker} "
            f"that could affect my {long_short}. "
            f"Search X, news, and web. Return JSON."
        )

        raw = await self._grok.market_overview(system, user)
        return _parse_position_alert(raw, ticker, is_holding=False)

    async def _check_holding(self, h: dict) -> WatchAlert | None:
        ticker = h.get("ticker", "")
        qty = int(h.get("quantity", 0) or 0)
        avg_price = float(h.get("average_price", h.get("avg_price", 0)) or 0)
        ltp = float(h.get("ltp", avg_price) or avg_price)
        current_value = qty * ltp
        held_since = h.get("held_since", "unknown")

        system = HOLDINGS_WATCH_PROMPT.format(
            ticker=ticker,
            quantity=qty,
            avg_price=f"{avg_price:,.2f}" if avg_price else "unknown",
            current_value=f"{current_value:,.0f}" if current_value else "unknown",
            held_since=held_since,
        )
        user = (
            f"Search for HIGH impact news about {ticker} in the last 4 hours. "
            f"Return JSON."
        )

        raw = await self._grok.market_overview(system, user)
        return _parse_holding_alert(raw, ticker)

    async def _handle_alert(self, watch_alert: WatchAlert) -> None:
        tier = AlertTier.HIGH if watch_alert.impact_level == "HIGH" else (
               AlertTier.MEDIUM if watch_alert.impact_level == "MEDIUM" else AlertTier.LOW)
        await self._router.route(Alert(
            source="portfolio_watch",
            tier=tier,
            ticker=watch_alert.ticker,
            title=_title(watch_alert),
            body=_format_position_alert(watch_alert),
            action=_ACTION_LABEL.get(watch_alert.action_suggestion, watch_alert.action_suggestion),
        ))

    async def _maybe_send_digest(self, now: datetime) -> None:
        await self._router.flush_digest()


# ------------------------------------------------------------------ #
#  Parsers                                                             #
# ------------------------------------------------------------------ #

def _parse_position_alert(raw: dict, ticker: str, is_holding: bool) -> WatchAlert | None:
    if not raw.get("has_findings"):
        return None
    level = str(raw.get("overall_impact", "NONE")).upper()
    if level == "NONE" or level == "LOW":
        return None
    return WatchAlert(
        ticker=ticker,
        impact_level=level,
        position_bias=str(raw.get("position_bias", "neutral")),
        action_suggestion=str(raw.get("action_suggestion", "hold")),
        revised_sl=_float_or_none(raw.get("revised_sl")),
        alert_summary=str(raw.get("alert_summary", ""))[:300],
        findings=raw.get("findings", [])[:5],
        is_holding=is_holding,
    )


def _parse_holding_alert(raw: dict, ticker: str) -> WatchAlert | None:
    if not raw.get("has_alert"):
        return None
    level = str(raw.get("impact_level", "NONE")).upper()
    if level == "NONE":
        return None
    return WatchAlert(
        ticker=ticker,
        impact_level=level,
        position_bias="adverse" if raw.get("impact_level") == "HIGH" else "neutral",
        action_suggestion=str(raw.get("action_suggestion", "hold")),
        revised_sl=None,
        alert_summary=str(raw.get("alert_summary", raw.get("headline", "")))[:300],
        findings=[{"headline": raw.get("headline", ""), "detail": raw.get("detail", ""),
                   "source": raw.get("source", "")}],
        is_holding=True,
    )


# ------------------------------------------------------------------ #
#  Formatters                                                          #
# ------------------------------------------------------------------ #

_BIAS_EMOJI = {"favourable": "✅", "adverse": "🚨", "neutral": "ℹ️"}
_ACTION_LABEL = {
    "hold": "Hold position",
    "tighten_sl": "Tighten stop loss",
    "exit_now": "EXIT immediately",
    "add_more": "Consider adding",
    "monitor": "Monitor closely",
    "review": "Review position",
    "consider_exit": "Consider exiting",
}


def _format_position_alert(alert: WatchAlert) -> str:
    bias_e = _BIAS_EMOJI.get(alert.position_bias, "ℹ️")
    label = "Holding" if alert.is_holding else "Position"
    action = _ACTION_LABEL.get(alert.action_suggestion, alert.action_suggestion)

    lines = [
        f"<b>{bias_e} Portfolio Watch — {alert.ticker}</b>  [{alert.impact_level}]",
        f"<i>{label} alert · {now_ist().strftime('%H:%M IST')}</i>\n",
        alert.alert_summary,
    ]

    if alert.findings:
        lines.append("\n<b>What Grok found:</b>")
        for f in alert.findings[:3]:
            src = f.get("source", "")
            time_str = f.get("time", "")
            src_time = f" [{src}" + (f" · {time_str}" if time_str else "") + "]" if src else ""
            lines.append(f"  • {f.get('headline', '')}{src_time}")
            detail = f.get("detail", "")
            if detail:
                lines.append(f"    <i>{detail[:120]}</i>")

    lines.append(f"\n<b>Suggested action:</b> {action}")
    if alert.revised_sl:
        lines.append(f"<b>Revised SL:</b> ₹{alert.revised_sl:,.2f}")

    return "\n".join(lines)


def _title(alert: WatchAlert) -> str:
    label = "Holding" if alert.is_holding else "Position"
    bias = {"favourable": "✅", "adverse": "🚨", "neutral": "ℹ️"}.get(alert.position_bias, "ℹ️")
    return f"Portfolio Watch — {alert.ticker} {label} {bias}"


def _float_or_none(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
