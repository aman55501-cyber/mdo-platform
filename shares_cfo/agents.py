"""Multiple proactive agents over the Business/Life OS data.

Separate, independent agents so pending tasks, ongoing projects, receivables,
compliance and the daily MIS each get their own watcher — nothing slips. They read
the imported datasets (local files, no network), classify what's due/overdue/at
risk, and push phone alerts in the same 🔴🟡🟢 [ENTITY] / WHY / ACTION format as the
trading agent. De-duplicated with cooldowns; the MIS digest fires once a morning.

Activates the moment you import data (tasks, projects, receivables, compliance,
hotel, tenders); silent until then. Gated on a notification channel +
CFO_AGENTS_ENABLED != "0".
"""

from __future__ import annotations

import asyncio
import logging
import os

from . import business
from .proactive import IST, _alert, _fresh, _inr, _now

log = logging.getLogger("shares_cfo.agents")


def _days_until(d) -> int | None:
    return (d - _now().date()).days if d else None


def _open(status: str) -> bool:
    s = (status or "").lower()
    return not any(x in s for x in ("done", "closed", "complete", "resolved", "paid", "filed"))


async def _tasks_agent() -> None:
    d = business.load("tasks")
    rows, cols = d["rows"], d["columns"]
    if not rows:
        return
    name_c = business._find(cols, "task", "title", "name", "description", "activity", "item")
    due_c = business._find(cols, "due", "deadline", "target", "date")
    stat_c = business._find(cols, "status", "stage", "state")
    owner_c = business._find(cols, "owner", "assigned", "responsible", "by")
    today = _now().strftime("%Y-%m-%d")
    for r in rows:
        if stat_c and not _open(str(r.get(stat_c))):
            continue
        days = _days_until(business._to_date(r.get(due_c))) if due_c else None
        if days is None or days > 2:
            continue
        nm = str(r.get(name_c) or "task")[:44]
        if _fresh(f"task:{today}:{nm}", 12 * 3600):
            lvl = "🔴" if days < 0 else "🟡"
            when = f"overdue {-days}d" if days < 0 else (f"due in {days}d" if days else "due TODAY")
            who = f" · {r.get(owner_c)}" if owner_c and r.get(owner_c) else ""
            await _alert(lvl, nm, when, f"Pending task{who} at its deadline.",
                         "Close it, delegate, or reschedule.", tab="")


async def _projects_agent() -> None:
    d = business.load("projects")
    rows, cols = d["rows"], d["columns"]
    if not rows:
        return
    name_c = business._find(cols, "project", "name", "title")
    due_c = business._find(cols, "milestone", "deadline", "due", "target date", "end")
    stat_c = business._find(cols, "status", "stage", "health")
    today = _now().strftime("%Y-%m-%d")
    for r in rows:
        if stat_c and not _open(str(r.get(stat_c))):
            continue
        days = _days_until(business._to_date(r.get(due_c))) if due_c else None
        st = str(r.get(stat_c) or "").lower() if stat_c else ""
        at_risk = any(x in st for x in ("risk", "delay", "block", "hold", "red"))
        if days is not None and days <= 5:
            nm = str(r.get(name_c) or "project")[:44]
            if _fresh(f"proj:{today}:{nm}", 12 * 3600):
                lvl = "🔴" if (days < 0 or at_risk) else "🟡"
                when = f"milestone overdue {-days}d" if days < 0 else f"milestone in {days}d"
                await _alert(lvl, nm, when, f"Ongoing project {st or 'active'}.",
                             "Check progress; unblock or re-plan.", tab="")
        elif at_risk and _fresh(f"projrisk:{today}:{r.get(name_c)}", 12 * 3600):
            await _alert("🔴", str(r.get(name_c) or "project")[:44], "flagged at risk",
                         "Project status marks risk/delay/blocked.", "Review and unblock.", tab="")


async def _receivables_agent() -> None:
    k = business.receivables_aging()
    if not k.get("count"):
        return
    overdue = k.get("overdue_60_plus") or 0
    if overdue > 0 and _fresh(f"recv:{_now().strftime('%Y-%m-%d')}", 20 * 3600):
        worst = k.get("worst") or []
        top = worst[0] if worst else None
        detail = f"Worst: {top['party']} {_inr(top['amount'])} ({top['age_days']}d)." if top else ""
        await _alert("🔴", "RECEIVABLES", f"{_inr(overdue)} over 60 days",
                     f"Cash stuck in aged debtors. {detail}",
                     "Chase collections on the 60+ bucket today.", tab="")


async def _compliance_agent() -> None:
    d = business.load("compliance")
    rows, cols = d["rows"], d["columns"]
    if not rows:
        return
    name_c = business._find(cols, "filing", "compliance", "name", "type", "description", "return")
    due_c = business._find(cols, "due", "deadline", "date")
    stat_c = business._find(cols, "status", "state")
    today = _now().strftime("%Y-%m-%d")
    for r in rows:
        if stat_c and not _open(str(r.get(stat_c))):
            continue
        days = _days_until(business._to_date(r.get(due_c))) if due_c else None
        if days is None or days > 7:
            continue
        nm = str(r.get(name_c) or "filing")[:44]
        if _fresh(f"comp:{today}:{nm}", 20 * 3600):
            lvl = "🔴" if days < 0 else "🟡"
            when = f"overdue {-days}d" if days < 0 else f"due in {days}d"
            await _alert(lvl, nm, f"compliance {when}",
                         "Statutory filing at its deadline — penalty risk.",
                         "File now or confirm it's done.", tab="")


async def _life_agent() -> None:
    """Nudge on Life OS items (shared household + personal) that are due soon or overdue."""
    from . import life
    data = life.list_items("full")
    today = _now().strftime("%Y-%m-%d")
    for it in data["items"]:
        if it.get("done") or not it.get("due"):
            continue
        days = _days_until(business._to_date(it["due"]))
        if days is None or days > 1:
            continue
        nm = str(it.get("title") or "item")[:44]
        who = " · shared" if it.get("shared") else ""
        if _fresh(f"life:{today}:{it['id']}", 12 * 3600):
            lvl = "🔴" if days < 0 else "🟡"
            when = f"overdue {-days}d" if days < 0 else ("due TODAY" if days == 0 else f"due in {days}d")
            await _alert(lvl, nm, f"life {when}{who}",
                         f"{it.get('kind', 'task').title()} on the household board at its deadline.",
                         "Do it, delegate, or move the date.", tab="")


async def _mis_agent(get_book) -> None:
    """Once-a-morning MIS digest (~08:15–08:45 IST): trading + business at a glance."""
    now = _now()
    mins = now.hour * 60 + now.minute
    if now.weekday() > 5 or not (495 <= mins <= 525):  # 08:15–08:45
        return
    if not _fresh(f"mis:{now.strftime('%Y-%m-%d')}", 20 * 3600):
        return
    nw = None
    try:
        book = await get_book()
        nw = book.get("net_worth")
    except Exception:
        pass
    s = business.summary()
    t, r = s.get("tenders", {}), s.get("receivables", {})
    tasks = business.load("tasks")
    open_tasks = sum(1 for x in tasks["rows"]
                     if not (business._find(tasks["columns"], "status") and
                             not _open(str(x.get(business._find(tasks["columns"], "status"))))))
    lines = []
    if nw is not None:
        lines.append(f"Net worth {_inr(nw)}")
    if t.get("count"):
        lines.append(f"Tenders {_inr(t.get('pipeline_value'))} ({t.get('count')})")
    if r.get("count"):
        lines.append(f"Receivables {_inr(r.get('total_outstanding'))}, 60+ {_inr(r.get('overdue_60_plus'))}")
    if tasks["rows"]:
        lines.append(f"Open tasks {open_tasks}")
    try:
        from . import life
        lst = life.stats()
        if lst.get("open"):
            over = f", {lst['overdue']} overdue" if lst.get("overdue") else ""
            lines.append(f"Life {lst['open']} open{over}")
    except Exception:
        pass
    body = " · ".join(lines) if lines else "Import business data to populate the MIS."
    await _alert("🟢", "DAILY MIS", now.strftime("%d %b"), body,
                 "Scan the day's priorities in the app.", tab="")


def start(get_book) -> None:
    """Launch the business/life agents as a background task."""
    if os.environ.get("CFO_AGENTS_ENABLED", "1").strip() == "0":
        log.info("business agents disabled (CFO_AGENTS_ENABLED=0)")
        return

    async def _loop():
        from . import notify
        await asyncio.sleep(30)
        if not notify.configured():
            log.info("business agents idle — no notification channel")
            return
        while True:
            try:
                await _mis_agent(get_book)
                await _tasks_agent()
                await _projects_agent()
                await _receivables_agent()
                await _compliance_agent()
                await _life_agent()
            except Exception as exc:
                log.warning("agents cycle error: %s", exc)
            await asyncio.sleep(900)  # every 15 min; daily items self-gate by time

    try:
        asyncio.get_event_loop().create_task(_loop())
    except RuntimeError:
        asyncio.ensure_future(_loop())
    log.info("business agents scheduled")
