"""Chief of Staff — shared, dependency-free helpers.

Used by mdo_server.py (endpoints), mdo_agent.py (bot runner) and
mdo_housekeeping.py. Nothing here touches the network or the database, so
it is unit-testable on any machine (tests/test_cos.py).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

# ── model pricing (USD per 1M tokens) — Anthropic first-party rates ──────────
# Source: Anthropic pricing page, cached 2026-09-25. Cache reads ≈ 10% of input.
MODEL_PRICES_USD: dict[str, tuple[float, float]] = {
    "claude-fable-5-1":  (10.0, 50.0),
    "claude-opus-5-5":   (4.0, 20.0),
    "claude-opus-5":     (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5":   (2.0, 10.0),
    "claude-haiku-4-5":  (1.0, 5.0),
}
ECONOMY_MODEL = "claude-haiku-4-5"


def _grok_prices() -> tuple[float, float]:
    """xAI list price per 1M tokens, approximate; override with GROK_PRICE_IN_USD / GROK_PRICE_OUT_USD."""
    try:
        return float(os.environ.get("GROK_PRICE_IN_USD", "3")), float(os.environ.get("GROK_PRICE_OUT_USD", "15"))
    except ValueError:
        return 3.0, 15.0


def usd_inr() -> float:
    try:
        return float(os.environ.get("USD_INR", "84"))
    except ValueError:
        return 84.0


def cost_inr(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0) -> float:
    """Rupee cost of one call. Unknown models are priced at Opus rates so an
    unpriced bot can never look free."""
    if model.startswith("grok"):
        p_in, p_out = _grok_prices()
    else:
        p_in, p_out = MODEL_PRICES_USD.get(model, MODEL_PRICES_USD["claude-opus-5-5"])
    usd = (max(input_tokens - cache_read_tokens, 0) * p_in
           + cache_read_tokens * p_in * 0.1
           + output_tokens * p_out) / 1_000_000
    return round(usd * usd_inr(), 4)


def spend_cap_inr() -> float | None:
    raw = os.environ.get("SPEND_CAP_INR_MONTH", "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def budget_mode(month_to_date_inr: float, cap_inr: float | None) -> str:
    """normal | economy (≥90% of cap → Haiku) | paused (≥100% → stop, report)."""
    if not cap_inr:
        return "normal"
    if month_to_date_inr >= cap_inr:
        return "paused"
    if month_to_date_inr >= 0.9 * cap_inr:
        return "economy"
    return "normal"


# ── reply routing — what Aman types back on WhatsApp ─────────────────────────
_ACK = re.compile(r"^\s*(ok|okay|yes|y|go|approve|approved|buy)\s*#?\s*(\d+)\s*$", re.I)
_NACK = re.compile(r"^\s*(no|n|skip|reject|cancel|kill)\s*#?\s*(\d+)\s*$", re.I)
_CHOICE = re.compile(r"^\s*#?(\d+)\s*$")
_CHOICE_FOR = re.compile(r"^\s*#?(\d+)\s*[:\-]\s*(\d+)\s*$")  # "14:2" → job 14, option 2


def parse_reply(text: str) -> dict | None:
    """Return {"kind": "ack"|"nack"|"choice", "job": int|None, "option": int|None}
    or None when the text is a free question for the brain.

    A bare number ("2") is a choice whose job is resolved by the caller (the
    single job currently awaiting a choice); "14:2" names both."""
    if not text:
        return None
    m = _ACK.match(text)
    if m:
        return {"kind": "ack", "job": int(m.group(2)), "option": None}
    m = _NACK.match(text)
    if m:
        return {"kind": "nack", "job": int(m.group(2)), "option": None}
    m = _CHOICE_FOR.match(text)
    if m:
        return {"kind": "choice", "job": int(m.group(1)), "option": int(m.group(2))}
    m = _CHOICE.match(text)
    if m:
        return {"kind": "choice", "job": None, "option": int(m.group(1))}
    return None


# ── cadence → next due ───────────────────────────────────────────────────────
_HHMM = re.compile(r"(\d{1,2}):(\d{2})")
_DOW = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def next_due(cadence: str, last_run: datetime | None, now: datetime) -> datetime | None:
    """When a bot with this cadence string should next report.

    Understands: "hourly", "hourly 09:00-15:30 IST Mon-Fri", "daily 06:57 IST",
    "weekly Sun 03:00 IST", "daily". Returns None for cadences it cannot
    parse (e.g. "on demand"), which the caller treats as never-late."""
    c = (cadence or "").strip().lower().split("+")[0].strip()  # "daily 06:30 IST + on demand" → daily part
    if not c or c.startswith("on demand"):
        return None
    if c.startswith("hourly"):
        base = last_run or now - timedelta(hours=1)
        due = base + timedelta(hours=1)
        if "mon-fri" in c:
            span = re.search(r"(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", c)
            if span:
                sh, sm = (int(x) for x in span.group(1).split(":"))
                eh, em = (int(x) for x in span.group(2).split(":"))
                while True:
                    local = due.astimezone(IST)
                    minutes = local.hour * 60 + local.minute
                    if local.weekday() <= 4 and sh * 60 + sm <= minutes <= eh * 60 + em:
                        break
                    if local.weekday() > 4 or minutes > eh * 60 + em:
                        nxt = (local + timedelta(days=1)).replace(hour=sh, minute=sm, second=0, microsecond=0)
                    else:
                        nxt = local.replace(hour=sh, minute=sm, second=0, microsecond=0)
                    due = nxt.astimezone(timezone.utc)
        return due
    m = _HHMM.search(c)
    hh, mm = (int(m.group(1)), int(m.group(2))) if m else (6, 30)
    local_now = now.astimezone(IST)
    if c.startswith("daily"):
        candidate = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if last_run is not None and last_run.astimezone(IST) >= candidate - timedelta(hours=1):
            candidate += timedelta(days=1)
        elif candidate <= local_now - timedelta(minutes=1) and last_run is None:
            pass
        return candidate.astimezone(timezone.utc)
    if c.startswith("weekly"):
        dow = next((v for k, v in _DOW.items() if k in c), 6)
        candidate = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        days_ahead = (dow - candidate.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if last_run is not None and last_run.astimezone(IST) >= candidate - timedelta(days=1):
            candidate += timedelta(days=7)
        return candidate.astimezone(timezone.utc)
    return None


def is_missed(cadence: str, last_run: datetime | None, now: datetime, grace_minutes: int = 20) -> bool:
    due = next_due(cadence, last_run, now)
    if due is None:
        return False
    return now > due + timedelta(minutes=grace_minutes)


# ── event lines (CHIEF_OF_STAFF.md §4) ───────────────────────────────────────
def job_line(job: dict) -> str:
    """One WhatsApp line for a job, with the reply that resolves it."""
    jid = job.get("id")
    title = str(job.get("title", ""))[:140]
    kind = job.get("kind", "info")
    eta = f" · ETA {job['eta']}" if job.get("eta") else ""
    if kind == "needs_click":
        return f'🖐 #{jid} {title}{eta} — reply "ok {jid}" / "no {jid}"'
    if kind == "needs_choice":
        opts = job.get("options") or []
        listed = " ".join(f"({i + 1}) {str(o)[:60]}" for i, o in enumerate(opts))
        return f"❓ #{jid} {title} {listed}{eta} — reply {jid}:1 … {jid}:{len(opts) or 1}"
    if kind == "done":
        return f"✅ #{jid} {title}"
    if kind == "proposal":
        return f'💡 #{jid} {title}{eta} — reply "buy {jid}" / "skip {jid}"'
    if kind == "stuck":
        return f"⛔ #{jid} {title}{eta}"
    return f"• #{jid} {title}{eta}"


def rollup_line(now: datetime, live: int, moved: int, blocked: int, ran: int, total: int,
                findings: int, needs_you: list[int], spend_inr: float, cap_inr: float | None,
                dead: list[str]) -> str:
    d = now.astimezone(IST)
    parts = [f"CoS · {d:%a %d %b} · {d:%H:%M} IST",
             f"Objectives: {live} live · {moved} moved · {blocked} blocked",
             f"Fleet: {ran}/{total} reported · " + (", ".join(dead) + " dead" if dead else "all alive"),
             f"Findings: {findings}" + (" · needs you: " + ", ".join(f"#{j}" for j in needs_you) if needs_you else " · nothing needs you"),
             f"Spend: ₹{spend_inr:,.0f} of " + (f"₹{cap_inr:,.0f}" if cap_inr else "no cap set")]
    return "\n".join(parts)
