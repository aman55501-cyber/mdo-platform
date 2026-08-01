"""
Business OS — ops agents + morning MIS.

Separate watchers scan the imported datasets and fire phone alerts so nothing
slips. Each watcher uses ``_alert`` (which wraps ``_fresh`` + ``notify``) so the
same condition doesn't spam every cycle. Every numeric threshold passes through
the normaliser first (hard rule).

Watchers:
  - watch_tasks        : tasks past due / still pending
  - watch_projects     : project milestones due soon or overdue
  - watch_receivables  : receivables aged 60+ days
  - watch_compliance   : statutory filings due soon
And a once-a-morning digest:
  - morning_mis        : net worth-ish brief (tenders, receivables, tasks)

``run_all()`` runs every watcher; ``morning_mis()`` is meant to be scheduled
once before the day starts (cron / systemd timer / APScheduler — left to the
deployment, not wired here).
"""

from __future__ import annotations

import logging
import os
from datetime import date

from . import business
from .business import _parse_date, _map_columns
from .helpers import _alert, normalise, notify

log = logging.getLogger("business_os")


def _threshold(env_name: str, default: float) -> float:
    """Read a threshold from env and normalise it (hard rule: every threshold
    field passes the normaliser first)."""
    val = normalise(os.getenv(env_name), default)
    return val if val is not None else default


def _fmt_inr(x: float | None) -> str:
    if x is None:
        return "-"
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


# ---------------------------------------------------------------------------
# Watchers
# ---------------------------------------------------------------------------

def watch_tasks() -> int:
    """Alert on tasks that are overdue or still pending. Returns # alerts sent."""
    rows = business.load_dataset("tasks")
    if not rows:
        return 0
    cols = _map_columns("tasks", rows)
    today = date.today()
    sent = 0
    overdue: list[str] = []
    for r in rows:
        status = str(r.get(cols.get("status") or "", "")).lower()
        if any(w in status for w in ("done", "complete", "closed", "yes")):
            continue
        due = _parse_date(r.get(cols.get("due_date") or ""))
        title = str(r.get(cols.get("title") or "", "")) or "(untitled task)"
        if due and due < today:
            overdue.append(f"• {title} — due {due.isoformat()} ({(today - due).days}d late)")
    if overdue:
        msg = "Overdue tasks:\n" + "\n".join(overdue[:15])
        if _alert("tasks:overdue", msg, title="⏰ Tasks overdue", tags="alarm_clock"):
            sent += 1
    return sent


def watch_projects() -> int:
    """Alert on project milestones due within the window or overdue."""
    rows = business.load_dataset("projects")
    if not rows:
        return 0
    cols = _map_columns("projects", rows)
    today = date.today()
    horizon = int(_threshold("PROJECT_HORIZON_DAYS", 7))
    sent = 0
    hits: list[str] = []
    for r in rows:
        status = str(r.get(cols.get("status") or "", "")).lower()
        if any(w in status for w in ("done", "complete", "closed")):
            continue
        due = _parse_date(r.get(cols.get("due_date") or ""))
        if not due:
            continue
        days = (due - today).days
        if days <= horizon:
            name = str(r.get(cols.get("name") or "", "")) or "(project)"
            ms = str(r.get(cols.get("milestone") or "", ""))
            label = f"{name} — {ms}" if ms else name
            when = "OVERDUE" if days < 0 else f"in {days}d"
            hits.append(f"• {label} ({when})")
    if hits:
        msg = "Milestones needing attention:\n" + "\n".join(hits[:15])
        if _alert("projects:milestones", msg, title="📌 Project milestones",
                  tags="pushpin"):
            sent += 1
    return sent


def watch_receivables() -> int:
    """Alert when receivables aged past the threshold (default 60 days) exist."""
    rows = business.load_dataset("receivables")
    if not rows:
        return 0
    cols = _map_columns("receivables", rows)
    today = date.today()
    min_age = int(_threshold("RECEIVABLE_AGE_DAYS", 60))
    sent = 0
    aged_total = 0.0
    lines: list[str] = []
    for r in rows:
        amt = normalise(r.get(cols.get("amount")), 0.0) or 0.0
        age = normalise(r.get(cols.get("age")))
        if age is None:
            ref = _parse_date(r.get(cols.get("due_date") or "")) or \
                _parse_date(r.get(cols.get("date") or ""))
            age = (today - ref).days if ref else None
        if age is not None and age >= min_age and amt > 0:
            aged_total += amt
            party = str(r.get(cols.get("party") or "", "")) or "(party)"
            lines.append(f"• {party}: {_fmt_inr(amt)} ({int(age)}d)")
    if lines:
        msg = (f"Receivables {min_age}+ days: {_fmt_inr(aged_total)}\n"
               + "\n".join(lines[:15]))
        if _alert("receivables:aged", msg, title="💰 Aged receivables",
                  priority="high", tags="money_with_wings"):
            sent += 1
    return sent


def watch_compliance() -> int:
    """Alert on statutory filings due within the window or overdue."""
    rows = business.load_dataset("compliance")
    if not rows:
        return 0
    cols = _map_columns("compliance", rows)
    today = date.today()
    horizon = int(_threshold("COMPLIANCE_HORIZON_DAYS", 10))
    sent = 0
    hits: list[str] = []
    for r in rows:
        status = str(r.get(cols.get("status") or "", "")).lower()
        if any(w in status for w in ("filed", "done", "complete", "submitted")):
            continue
        due = _parse_date(r.get(cols.get("due_date") or ""))
        if not due:
            continue
        days = (due - today).days
        if days <= horizon:
            name = str(r.get(cols.get("name") or "", "")) or "(filing)"
            when = "OVERDUE" if days < 0 else f"in {days}d"
            hits.append(f"• {name} ({when} — {due.isoformat()})")
    if hits:
        msg = "Statutory filings:\n" + "\n".join(hits[:15])
        if _alert("compliance:due", msg, title="📋 Compliance due",
                  priority="high", tags="clipboard"):
            sent += 1
    return sent


def run_all() -> dict[str, int]:
    """Run every watcher once. Returns per-watcher alert counts."""
    return {
        "tasks": watch_tasks(),
        "projects": watch_projects(),
        "receivables": watch_receivables(),
        "compliance": watch_compliance(),
    }


# ---------------------------------------------------------------------------
# Morning MIS  (once-a-morning digest)
# ---------------------------------------------------------------------------

def morning_mis(send: bool = True) -> str:
    """Build (and optionally push) the once-a-morning digest.

    Pulls the KPI brief and formats the headline numbers: tenders in the
    pipeline, receivables outstanding + 60+ aged, and open tasks.
    """
    brief = business.summary()
    kpis = brief.get("kpis", {})
    lines = [f"☀️ Morning MIS — {date.today().isoformat()}"]

    rec = kpis.get("receivables", {})
    if rec.get("kind") == "receivables":
        lines.append(f"Receivables: {_fmt_inr(rec.get('total_outstanding'))} "
                     f"(60+: {_fmt_inr(rec.get('overdue_60_plus'))})")

    ten = kpis.get("tenders", {})
    if ten.get("kind") == "tenders":
        lines.append(f"Tenders: {ten.get('pipeline_count', 0)} in pipeline, "
                     f"{ten.get('closing_this_week', 0)} closing this week "
                     f"({_fmt_inr(ten.get('total_value'))})")

    hotel = kpis.get("hotel", {})
    if hotel.get("kind") == "hotel" and hotel.get("revpar") is not None:
        lines.append(f"Hotel: RevPAR {_fmt_inr(hotel.get('revpar'))}, "
                     f"MTD {_fmt_inr(hotel.get('mtd_revenue'))}, "
                     f"Occ {hotel.get('occupancy_pct')}%")

    tasks = business.load_dataset("tasks")
    if tasks:
        cols = _map_columns("tasks", tasks)
        open_n = sum(
            1 for r in tasks
            if not any(w in str(r.get(cols.get("status") or "", "")).lower()
                       for w in ("done", "complete", "closed", "yes"))
        )
        lines.append(f"Open tasks: {open_n}")

    digest = "\n".join(lines)
    if send:
        # Digest is a daily send, so a 20h TTL avoids a double-push on a re-run.
        _alert("mis:morning", digest, ttl=20 * 3600, title="Morning MIS",
               tags="sunny")
    return digest
