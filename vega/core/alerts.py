"""Unified alert routing — single place for dedup, tiers, and digest batching.

Every module (portfolio_watch, tender_watch, singhvi, levels) routes alerts
through AlertRouter instead of reimplementing dedup and delivery logic.

Tiers:
  HIGH   → delivered immediately
  MEDIUM → batched into an hourly digest
  LOW    → logged only, never sent

Usage:
    router = AlertRouter(send_fn=alert_service.send_text)

    await router.route(Alert(
        source="portfolio_watch",
        tier=AlertTier.HIGH,
        ticker="RELIANCE",
        title="Regulatory probe announced",
        body="SEBI has initiated...",
        action="Consider exiting position",
    ))

    # Call once per event-loop tick (e.g. from ScheduleManager):
    await router.flush_digest()
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Awaitable, Callable

from ..utils.logging import get_logger
from ..utils.time import now_ist

log = get_logger("alert_router")

SendFn = Callable[[str], Awaitable[None]]

_DEDUP_TTL_HOURS = 4


class AlertTier(Enum):
    HIGH   = "immediate"   # fire right now
    MEDIUM = "digest"      # batch for hourly digest
    LOW    = "log_only"    # never sent to Telegram


@dataclass
class Alert:
    source: str            # "portfolio_watch" | "tender_watch" | "singhvi" | …
    tier: AlertTier
    title: str
    body: str
    ticker: str = ""
    action: str = ""
    dedup_hours: int = _DEDUP_TTL_HOURS
    created_at: datetime = field(default_factory=now_ist)

    # ── formatting ──────────────────────────────────────────────────── #

    def format(self) -> str:
        icon = {"HIGH": "🚨", "MEDIUM": "📋", "LOW": "ℹ️"}.get(self.tier.name, "ℹ️")
        parts = [f"<b>{icon} {self.title}</b>"]
        if self.ticker:
            parts[0] += f"  [{self.ticker}]"
        parts.append(self.body)
        if self.action:
            parts.append(f"\n<b>→ {self.action}</b>")
        parts.append(f"<i>{self.created_at.strftime('%H:%M IST')} · {self.source}</i>")
        return "\n".join(parts)

    def format_digest_line(self) -> str:
        action = f" → {self.action}" if self.action else ""
        ticker = f"<b>{self.ticker}</b> — " if self.ticker else ""
        return f"{ticker}{self.body[:120]}{action}"


class AlertRouter:
    """Central alert dispatcher — dedup, tier routing, hourly digest."""

    def __init__(self, send_fn: SendFn) -> None:
        self._send = send_fn
        self._seen: dict[str, datetime] = {}
        self._medium_queue: list[Alert] = []
        self._last_digest_hour: int = -1

    # ── public API ───────────────────────────────────────────────────── #

    async def route(self, alert: Alert) -> None:
        """Route an alert through the tier system with deduplication."""
        key = _dedup_key(alert.source, alert.ticker, alert.title)
        if self._is_dup(key, alert.dedup_hours):
            log.debug("alert_deduped", source=alert.source, ticker=alert.ticker)
            return
        self._mark(key)

        if alert.tier == AlertTier.HIGH:
            await self._deliver(alert.format())
            log.info("alert_high_sent", source=alert.source, ticker=alert.ticker)

        elif alert.tier == AlertTier.MEDIUM:
            self._medium_queue.append(alert)
            log.info("alert_medium_queued", source=alert.source, ticker=alert.ticker)

        # LOW → log only (already logged above)

    async def flush_digest(self) -> None:
        """Send batched MEDIUM alerts as a single digest. Call hourly."""
        if not self._medium_queue:
            return
        now = now_ist()
        if now.hour == self._last_digest_hour:
            return
        self._last_digest_hour = now.hour

        lines = [
            f"<b>📋 Digest — {now.strftime('%H:%M IST')} "
            f"({len(self._medium_queue)} items)</b>\n"
        ]
        # Group by source
        by_source: dict[str, list[Alert]] = {}
        for a in self._medium_queue:
            by_source.setdefault(a.source, []).append(a)

        for source, alerts in by_source.items():
            lines.append(f"<b>{_source_label(source)}</b>")
            for a in alerts[:5]:
                lines.append(f"  • {a.format_digest_line()}")
            if len(alerts) > 5:
                lines.append(f"  <i>… and {len(alerts) - 5} more</i>")

        self._medium_queue.clear()
        await self._deliver("\n".join(lines))
        log.info("alert_digest_sent")

    # ── internals ────────────────────────────────────────────────────── #

    async def _deliver(self, text: str) -> None:
        try:
            await self._send(text)
        except Exception as exc:
            log.error("alert_delivery_failed", error=str(exc))

    def _is_dup(self, key: str, hours: int) -> bool:
        last = self._seen.get(key)
        if last is None:
            return False
        return (now_ist() - last) < timedelta(hours=hours)

    def _mark(self, key: str) -> None:
        self._seen[key] = now_ist()
        # Prune old entries every 1000 keys
        if len(self._seen) > 1000:
            cutoff = now_ist() - timedelta(hours=24)
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}


# ── helpers ──────────────────────────────────────────────────────────── #

def _dedup_key(source: str, ticker: str, title: str) -> str:
    raw = f"{source}:{ticker}:{title}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _source_label(source: str) -> str:
    return {
        "portfolio_watch": "Portfolio Watch",
        "tender_watch":    "VWLR Tenders",
        "singhvi":         "Anil Singhvi",
        "levels":          "Price Levels",
    }.get(source, source.replace("_", " ").title())
