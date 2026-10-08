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


def _deeplink(tab: str = "") -> str:
    base = os.environ.get("CFO_APP_URL", "").strip().rstrip("/")
    if not base:
        return ""
    return f"\nOpen: {base}/#{tab}" if tab else f"\nOpen: {base}/"


async def _push(title: str, body: str) -> None:
    from . import notify
    try:
        await asyncio.to_thread(notify.send, title, body)
        log.info("proactive push: %s", title)
    except Exception as exc:  # never let a push crash the loop
        log.warning("proactive push failed: %s", exc)


async def _alert(level: str, entity: str, what: str, why: str, action: str, tab: str = "") -> None:
    """Standard briefing format: 🔴/🟡/🟢 [ENTITY] What / WHY / ACTION (+ deep link)."""
    title = f"{level} {entity} — {what}"
    body = f"WHY: {why}\nACTION: {action}{_deeplink(tab)}"
    await _push(title, body)


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
        bucket = int(abs(h["pct"]) // 2)  # re-alert only on a bigger move, not every tick
        key = f"move:{h['sym']}:{'up' if h['pct']>=0 else 'dn'}:{bucket}"
        if _fresh(key, cooldown=3 * 3600):
            up = h["pct"] >= 0
            await _alert("🟡", h["sym"], f"{'▲' if up else '▼'} {h['pct']:+.1f}% today",
                         f"{h['holder']} holds {_inr(h['mv'])}; day move {_inr(h['dc'])}.",
                         "Review the position; check levels/OI before adding or trimming.",
                         tab="portfolio")


async def _alert_sessions(book: dict) -> None:
    """A broker session dropped — the book is partial until re-login."""
    deg = (book.get("book_health") or {}).get("degraded_accounts") or []
    for a in deg:
        key = f"session:{a.get('creds_key')}"
        if _fresh(key, cooldown=2 * 3600):
            await _alert("🔴", a.get("creds_key", "account"), "session logged out",
                         "Net worth + positions are partial until this account re-authenticates.",
                         "Open Login and re-auth (2FA on that holder's phone).", tab="login")


async def _alert_drawdown() -> None:
    """Any live F&O leg losing more than the cap — a risk event to act on."""
    cap = float(os.environ.get("CFO_ALERT_DRAWDOWN", "50000") or 50000)
    try:
        from .server import _live_positions
        data = await _live_positions()
    except Exception:
        return
    for p in data.get("positions", []):
        pnl = p.get("pnl") or 0
        if pnl >= -cap:
            continue
        bucket = int(abs(pnl) // cap)  # re-alert as the loss deepens by another cap
        key = f"dd:{p.get('label')}:{bucket}"
        if _fresh(key, cooldown=2 * 3600):
            await _alert("🔴", p.get("label", "position"), f"drawdown {_inr(pnl)}",
                         f"{p.get('holder')} · qty {p.get('quantity')} @ {p.get('average_price')}, "
                         f"LTP {p.get('last_price')}. Loss past ₹{int(cap):,}.",
                         "Decide: cut, hedge, or hold with a hard stop. Agent never auto-exits.",
                         tab="positions")


async def _alert_fno_moves() -> None:
    """Live F&O watch during market hours: a sharp price move or an OI build-up/unwind on
    any open leg is worth a nudge even before it hits the drawdown cap."""
    move_thr = float(os.environ.get("CFO_FNO_MOVE_PCT", "8") or 8)
    try:
        from .server import _live_positions
        data = await _live_positions()
    except Exception:
        return
    for p in data.get("positions", []):
        if p.get("kind") not in ("option", "future"):
            continue
        chg = p.get("change_pct")
        danger = p.get("risk") == "danger"
        big_move = chg is not None and abs(chg) >= move_thr
        if not (danger or big_move):
            continue
        oi = p.get("oi")
        oi_txt = f" · OI {oi:,}" if isinstance(oi, (int, float)) else ""
        bu = p.get("buildup")
        bu_txt = f" · {bu}" if bu else ""
        body = (f"{p.get('holder')} · qty {p.get('quantity')} @ {p.get('average_price')}, "
                f"LTP {p.get('last_price')}{oi_txt}{bu_txt}. MTM {_inr(p.get('pnl'))}.")
        if danger:  # loss likely to deepen — fire once per ~90 min while it persists
            key = f"fnorisk:{p.get('label')}"
            if _fresh(key, cooldown=90 * 60):
                await _alert("🔴", p.get("label", "F&O"), "risk building against you",
                             body + f" {p.get('risk_why', '')}",
                             "Losing with OI/price against the leg — cut, hedge, or hard-stop it.",
                             tab="positions")
        elif big_move:
            bucket = int(abs(chg) // move_thr)  # re-alert only on a bigger move
            key = f"fno:{p.get('label')}:{'up' if chg >= 0 else 'dn'}:{bucket}"
            if _fresh(key, cooldown=2 * 3600):
                await _alert("🟡", p.get("label", "F&O"), f"{'▲' if chg >= 0 else '▼'} {chg:+.1f}% intraday",
                             body, "Live leg moving — check the chain/OI and your stop.", tab="positions")


async def _alert_conflicts() -> None:
    """~Every 40 min in market hours: flag any F&O position where the deep analysis
    (fundamental + technical + news + macro) conflicts with how you're positioned."""
    if not _fresh("deepconflictscan", 40 * 60):  # heavy report — throttle hard
        return
    try:
        from .server import _deep_report
        rep = await _deep_report()  # plain (no LLM) — cached ~20 min
    except Exception:
        return
    day = _now().strftime("%Y-%m-%d")
    for r in rep.get("reports", []):
        if r.get("alignment") != "conflicts":
            continue
        sym = r.get("symbol", "position")
        if _fresh(f"conflict:{day}:{sym}", 20 * 3600):
            bear = "; ".join((r.get("bear") or [])[:2]) or "the evidence leans the other way"
            await _alert("🔴", sym, f"analysis conflicts with your {r.get('position_bias', '')} position",
                         f"Deep read is {r.get('stance', 'neutral')}. {bear}.",
                         "Re-check the thesis — tighten the stop, hedge, or cut.", tab="positions")


_ORDER_SEEN: dict = {}  # orderid -> last status, to fire once on each transition


async def _alert_order_status() -> None:
    """Push a fill / rejection the moment an order's broker status changes."""
    try:
        from .brokers import angel_scrip
        orders = await asyncio.to_thread(angel_scrip.order_book)
    except Exception:
        return
    for o in orders or []:
        oid, st = o.get("orderid"), (o.get("status") or "").lower()
        if not oid or not st:
            continue
        prev = _ORDER_SEEN.get(oid)
        _ORDER_SEEN[oid] = st
        if prev is None or st == prev:  # first sighting this session, or unchanged
            continue
        sym = o.get("symbol", "order")
        line = f"{o.get('side', '')} {o.get('qty', '')} {o.get('type', '')}".strip()
        if "complete" in st or "filled" in st:
            await _alert("🟢", sym, "order FILLED", f"{line}.", "Position updated.", tab="positions")
        elif "reject" in st:
            await _alert("🔴", sym, "order REJECTED", f"{line}: {(o.get('reason') or '')[:80]}",
                         "Re-check the order and re-place.", tab="positions")


async def _alert_health() -> None:
    """Self-watch: if a core module that should auto-report goes dark in market hours,
    say so — the terminal must never rot silently. Only the headless modules are checked
    (the ones the agents/feeds keep warm without you opening a tab)."""
    from . import health
    from datetime import datetime
    snap = health.snapshot()
    core = {"holdings": "book / net worth", "positions": "live F&O feed",
            "sector_map": "holdings map"}
    stale = []
    for mid, label in core.items():
        last = (snap["modules"].get(mid) or {}).get("last")
        if not last:
            continue  # never seen this session — don't alarm on a cold start
        try:
            age_min = (_now() - datetime.fromisoformat(last)).total_seconds() / 60
        except ValueError:
            continue
        if age_min > 25:
            stale.append(f"{label} ({int(age_min)}m)")
    if stale and _fresh("selfhealth", 2 * 3600):
        await _alert("🔴", "CONSOLE", "a data module went dark",
                     "Not refreshing during market hours: " + "; ".join(stale) + ".",
                     "Check the feed / broker login — open /status for the full board.", tab="")


async def _alert_ideas() -> None:
    """A fresh high-conviction setup appeared."""
    try:
        from .server import _high_conviction
        data = await asyncio.to_thread(_high_conviction)
    except Exception:
        return
    day = _now().strftime("%Y-%m-%d")
    for i in (data.get("ideas") or [])[:5]:
        key = f"idea:{day}:{i.get('symbol')}"
        if _fresh(key, cooldown=8 * 3600):
            await _alert("🟢", i.get("symbol", "idea"),
                         f"high-conviction {int(i.get('conviction',0))} · {i.get('horizon','')}",
                         f"{i.get('pattern','setup')} · {i.get('hit_rate','?')}% hit · F{i.get('fundamental_score')}/T{i.get('technical_score')}.",
                         f"Entry {i.get('entry')} · SL {i.get('stop_loss')} · TGT {i.get('target')} · R:R {i.get('reward_risk')}. Verify, then size.",
                         tab="ideas")


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
            lvl = "🔴" if label == "stressed" else "🟢" if label == "calm" else "🟡"
            await _alert(lvl, "MARKET", f"regime {prev} → {label}",
                         f"India VIX + trend shifted. {r.get('tilt','')}",
                         f"Size new risk to {r.get('risk_budget_pct')}% budget; keep hedges ready.",
                         tab="chart")


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
        cycle = 0
        while True:
            delay = 300
            try:
                from . import health
                health.beat("agent")
                now = _now()
                book = await get_book()
                await _daily(book, now)
                await _alert_sessions(book)          # a dropped session matters anytime
                if _market_open(now):
                    await _alert_movers(book)
                    await _alert_regime()
                    await _alert_drawdown()          # live F&O leg losses (tightened cadence)
                    await _alert_fno_moves()         # live F&O OI/price shifts on open legs
                    await _alert_conflicts()         # position vs deep-analysis conflicts (~40 min)
                    await _alert_order_status()      # fills / rejections the moment they change
                    await _alert_health()            # self-watch: warn if a core module goes dark
                    if cycle % 10 == 0:              # heavy scan ~every 30 min
                        await _alert_ideas()
                    delay = 180                      # 3 min while the market is open (was 5)
                else:
                    delay = 1200                     # 20 min when closed
            except Exception as exc:
                log.warning("proactive cycle error: %s", exc)
            cycle += 1
            await asyncio.sleep(delay)

    try:
        asyncio.get_event_loop().create_task(_loop())
    except RuntimeError:
        asyncio.ensure_future(_loop())
    log.info("proactive agent scheduled")
