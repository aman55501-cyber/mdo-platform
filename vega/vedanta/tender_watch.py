"""Real-time Grok tender/auction/compliance monitor for VWLR.

Polls xAI Grok (web_search + x_search) every 4 hours during weekdays for:
  - New SECL / MCL / NTPC / JSPL / SAIL coal tenders
  - Coal auction announcements (MSTC, Forward Markets)
  - Regulatory / compliance updates (Pollution Board, Mining, GST)

Alert routing is delegated to AlertRouter (core/alerts.py).
Enable/disable at runtime via engine._tender_watch.enabled = True/False
or the /tender_watch Telegram command.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime

from ..core.alerts import Alert, AlertRouter, AlertTier
from ..utils.logging import get_logger

log = get_logger("tender_watch")

_POLL_INTERVAL_HOURS = 4


@dataclass
class TenderAlert:
    category: str          # tender | auction | compliance
    buyer: str
    title: str
    volume_mt: float | None
    closing_date: str | None
    portal_url: str | None
    urgency: str           # HIGH | MEDIUM | LOW
    summary: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


_SYSTEM_PROMPT = """\
You are a coal industry business intelligence agent for VWLR (Vedanta Washery, Kharsia Raigarh CG).

Search for the latest (today/this week):
1. Coal procurement tenders from: SECL, MCL, NTPC Sipat, JSPL Raigarh, SAIL Bhilai, \
Godawari Power, Monnet Ispat
2. Coal auction announcements from MSTC, Coal India subsidiaries
3. Regulatory updates: Chhattisgarh Pollution Control Board, CMPDI, Ministry of Coal

For each item found, extract:
- category: "tender" | "auction" | "compliance"
- buyer: name of the buying organisation
- title: tender/auction title (concise)
- volume_mt: volume in metric tons if mentioned (null if not)
- closing_date: ISO date string if mentioned (null if not)
- portal_url: direct URL if available (null if not)
- urgency: "HIGH" if closing within 3 days or regulatory fine risk; "MEDIUM" otherwise
- summary: 1-2 sentence description

Return a JSON array. If nothing new found, return [].
"""

_USER_MESSAGE = (
    "Search for the latest coal procurement tenders, auctions, and compliance/regulatory "
    "updates relevant to coal washeries in Chhattisgarh and central India. "
    "Focus on SECL, MCL, NTPC, JSPL, SAIL, and CG state regulators. Today: {today}."
)


class TenderWatchAgent:
    """Polls Grok for VWLR-relevant tenders, auctions, and compliance events."""

    def __init__(self, grok, alert_router: AlertRouter) -> None:
        self._grok = grok
        self._router = alert_router
        self._running = False
        self.enabled = False

    # ------------------------------------------------------------------ #
    #  Public                                                              #
    # ------------------------------------------------------------------ #

    async def watch_loop(self) -> None:
        """Main loop — runs as a background asyncio task."""
        self._running = True
        log.info("tender_watch_started")
        while self._running:
            if self.enabled and _is_weekday():
                try:
                    await self._poll_once()
                except Exception as exc:
                    log.warning("tender_watch_poll_error", error=str(exc))
            await asyncio.sleep(_POLL_INTERVAL_HOURS * 3600)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    async def _poll_once(self) -> None:
        today = datetime.now().date().isoformat()
        tools = [
            {"type": "web_search"},
            {"type": "x_search", "from_date": today, "to_date": today},
        ]
        raw = await self._grok._post_responses(
            model=self._grok._config.model,
            instructions=_SYSTEM_PROMPT,
            user=_USER_MESSAGE.format(today=today),
            tools=tools,
        )
        for ta in _parse_alerts(raw):
            tier = AlertTier.HIGH if ta.urgency == "HIGH" else AlertTier.MEDIUM
            vol_str = f" | {ta.volume_mt:,.0f} MT" if ta.volume_mt else ""
            closing_str = f" | Closes {ta.closing_date}" if ta.closing_date else ""
            portal_str = f"\nPortal: {ta.portal_url}" if ta.portal_url else ""
            body = (
                f"<b>{ta.buyer}</b> — {ta.title}"
                f"{vol_str}{closing_str}{portal_str}\n{ta.summary}"
            )
            await self._router.route(Alert(
                source="tender_watch",
                tier=tier,
                title=f"VWLR {ta.category.upper()}",
                body=body,
                dedup_hours=24,
            ))


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _parse_alerts(text: str) -> list[TenderAlert]:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        items = json.loads(text)
        if not isinstance(items, list):
            return []
    except json.JSONDecodeError:
        return []
    out = []
    for item in items:
        try:
            out.append(TenderAlert(
                category=item.get("category", "tender"),
                buyer=item.get("buyer", ""),
                title=item.get("title", ""),
                volume_mt=item.get("volume_mt"),
                closing_date=item.get("closing_date"),
                portal_url=item.get("portal_url"),
                urgency=item.get("urgency", "MEDIUM"),
                summary=item.get("summary", ""),
            ))
        except Exception:
            continue
    return out


def _is_weekday() -> bool:
    return datetime.now().weekday() < 5
