"""Proactive market-hours agent — watches the book and pushes alerts to your phone.

Runs inside the always-on app as a background task. During NSE hours (09:15–15:30
IST, Mon–Fri) it wakes every few minutes and pushes only *noteworthy* changes —
big moves, a regime shift, a pre-open brief and an end-of-day summary — via the
same ntfy/Telegram channels used elsewhere. Every alert is de-duplicated with a
cooldown so it informs without spamming. Quiet when the market is closed.

Enable with a notification channel set (CFO_NTFY_TOPIC or Telegram) and
CFO_PROACTIVE_ENABLED != "0". Tunables: CFO_ALERT_MOVE_PCT (default 4).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

log = logging.getLogger("shares_cfo.proactive")

IST = timezone(timedelta(hours=5, minutes=30))
_SENT: dict[str, float] = {}   # alert key -> last-sent epoch (cooldown/dedup)
_STATE: dict = {"regime": None}


def _now() -> datetime:
    return datetime.now(IST)


def _epoch() -> float:
    return _now().timestamp()


def _market_open(now: datetime) -> bool:
    if now.weekday() > 4:  # Sat/Sun
        return False
    mins = now.hour * 60 + now.minute
    return 555 <= mins <= 930  # 09:15–15:30 IST


def _fresh(key: str, cooldown: float) -> bool:
    """True if this alert key hasn't fired within `cooldown` seconds."""
    last = _SENT.get(key)
    if last is not None and (_epoch() - last) < cooldown:
        return False
    _SENT[key] = _epoch()
    return True


async def _push(title: str, body: str) -> None:
    from . import notify
    try:
        await asyncio.to_thread(notify.send, title, body)
        log.info("proactive push: %s", title)
    except Exception as exc:  # never let a push crash the loop
        log.warning("proactive push failed: %s", exc)


def _inr(n: float) -> str:
    if n is None:
        return "₹—"
    a, s = abs(n), "-" if n < 0 else ""
    if a >= 1e7:
        return f"{s}₹{a/1e7:.2f}Cr"
    if a >= 1e5:
        return f"{s}₹{a/1e5:.2f}L"
    return f"{s}₹{round(a):,}"


def _holdings(book: dict) -> list[dict]:
    m: dict = {}
    for a in book.get("accounts", []):
        if a.get("ok") is False:
            continue
        lbl = a.get("label") or a.get("creds_key")
        for h in a.get("holdings", []):
            sym = (h.get("ticker") or "").upper().split("-")[0]
            if not sym:
                continue
            o = m.setdefault(sym, {"sym": sym, "mv": 0.0, "dc": 0.0, "holder": lbl})
            o["mv"] += h.get("market_value") or 0
            o["dc"] += h.get("day_change") or 0
    out = []
    for o in m.values():
        prev = o["mv"] - o["dc"]
        o["pct"] = (o["dc"] / prev * 100) if prev else 0.0
        out.append(o)
    return out


async def _alert_movers(book: dict) -> None:
    thr = float(os.environ.get("CFO_ALERT_MOVE_PCT", "4") or 4)
    for h in _holdings(book):
        if abs(h["mv"]) < 50000 or abs(h["pct"]) < thr:
            continue
        # bucket the threshold so a stock only re-alerts on a bigger move, not every tick
        bucket = int(abs(h["pct"]) // 2)
        key = f"move:{h['sym']}:{'up' if h['pct']>=0 else 'dn'}:{bucket}"
        if _fresh(key, cooldown=3 * 3600):
            arrow = "▲" if h["pct"] >= 0 else "▼"
            await _push(f"{arrow} {h['sym']} {h['pct']:+.1f}%",
                        f"{h['holder']} · {_inr(h['mv'])} · day {_inr(h['dc'])}")


async def _alert_regime() -> None:
    from .analysis import market
    try:
        r = await asyncio.to_thread(market.regime)
    except Exception:
        return
    label = r.get("regime")
    if label and label != _STATE["regime"]:
        prev = _STATE["regime"]
        _STATE["regime"] = label
        if prev is not None and _fresh(f"regime:{label}", cooldown=6 * 3600):
            await _push(f"Regime → {label.upper()}",
                        f"{r.get('emoji','')} risk budget {r.get('risk_budget_pct')}% · {r.get('tilt','')}")


async def _daily(book: dict, now: datetime) -> None:
    """Pre-open brief (~09:05) and end-of-day summary (~15:35), once each per day."""
    d = now.strftime("%Y-%m-%d")
    mins = now.hour * 60 + now.minute
    nw = book.get("net_worth")
    if now.weekday() <= 4 and 540 <= mins <= 555 and _fresh(f"preopen:{d}", cooldown=12 * 3600):
        await _push("Pre-open brief", f"Net worth {_inr(nw)}. Market opens 09:15. "
                    f"{book.get('book_health',{}).get('degraded',0)} account(s) logged out.")
    if now.weekday() <= 4 and 935 <= mins <= 965 and _fresh(f"eod:{d}", cooldown=12 * 3600):
        dc = book.get("day_change") or 0
        hs = sorted(_holdings(book), key=lambda x: x["dc"])
        top = hs[-1] if hs else None
        bot = hs[0] if hs else None
        extra = ""
        if top and bot:
            extra = f" · top {top['sym']} {top['pct']:+.1f}% · worst {bot['sym']} {bot['pct']:+.1f}%"
        await _push("Market closed — EOD",
                    f"Net worth {_inr(nw)}, day {_inr(dc)} ({(book.get('day_change_pct') or 0)*100:+.2f}%){extra}")


def start(get_book) -> None:
    """Launch the monitor as a background task. `get_book` is the async consolidated-book fn."""
    if os.environ.get("CFO_PROACTIVE_ENABLED", "1").strip() == "0":
        log.info("proactive agent disabled (CFO_PROACTIVE_ENABLED=0)")
        return

    async def _loop():
        from . import notify
        # wait a moment for startup, then confirm arming (once) if a channel exists
        await asyncio.sleep(20)
        if not notify.configured():
            log.info("proactive agent idle — no notification channel configured")
            return
        await _push("Shares CFO", "Proactive agent armed — alerts on during market hours.")
        while True:
            delay = 300
            try:
                now = _now()
                book = await get_book()
                await _daily(book, now)
                if _market_open(now):
                    await _alert_movers(book)
                    await _alert_regime()
                    delay = 300      # 5 min while the market is open
                else:
                    delay = 1200     # 20 min when closed
            except Exception as exc:
                log.warning("proactive cycle error: %s", exc)
            await asyncio.sleep(delay)

    try:
        asyncio.get_event_loop().create_task(_loop())
    except RuntimeError:
        asyncio.ensure_future(_loop())
    log.info("proactive agent scheduled")
