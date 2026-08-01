#!/usr/bin/env python3
"""MDO Agent Runner — the autonomous checks, running ON the VPS.

Why here and not in a cloud session: this process already has the Anthropic
key, the database, and network access to the backend. Cloud-scheduled agents
kept firing and delivering nothing, with no visible failure.

Usage (inside the backend container):
    python mdo_agent.py hourly
    python mdo_agent.py daily

Cron on the host (see DEPLOY_HOSTINGER.md §8):
    24 * * * * cd /docker/sharecfo/mdo-platform && docker compose exec -T backend python mdo_agent.py hourly  >> /var/log/mdo-agent.log 2>&1
    27 1 * * * cd /docker/sharecfo/mdo-platform && docker compose exec -T backend python mdo_agent.py daily   >> /var/log/mdo-agent.log 2>&1
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.environ.get("MDO_SELF_URL", "http://localhost:8501")
KEY = os.environ.get("MDO_AUTH_TOKEN", "").strip()
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = os.environ.get("MDO_AGENT_MODEL", "claude-sonnet-5")
IST = timezone(timedelta(hours=5, minutes=30))


def log(msg: str) -> None:
    print(f"[{datetime.now(IST):%Y-%m-%d %H:%M:%S} IST] {msg}", flush=True)


def api(path: str, method: str = "GET", body: dict | None = None, timeout: int = 30):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-MDO-Key": KEY, "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def wait_for_backend(attempts: int = 12, delay: float = 5.0) -> bool:
    """The backend may still be booting (container restart, VPS reboot) when
    cron fires. Wait rather than failing the run."""
    import time
    for i in range(1, attempts + 1):
        try:
            api("/api/status", timeout=5)
            if i > 1:
                log(f"backend ready after {i} attempts")
            return True
        except Exception as e:
            if i == attempts:
                log(f"backend unreachable after {attempts} attempts: {e}")
                return False
            time.sleep(delay)
    return False


def ask_claude(prompt: str, max_tokens: int = 8000) -> str:
    """Call Claude and return its text. Logs why the text is empty rather than
    leaving a silent blank (an empty answer used to look like a parse failure)."""
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    if not text.strip():
        log("model returned no text — stop_reason=%s blocks=%s usage=%s" % (
            resp.get("stop_reason"),
            [b.get("type") for b in resp.get("content", [])],
            resp.get("usage"),
        ))
    return text


def in_window(window: str, now_ist: datetime) -> bool:
    """Respect a check's run_window, e.g. '09:00-15:30 IST Mon-Fri'."""
    if not window:
        return True
    w = window.lower()
    if "mon-fri" in w and now_ist.weekday() > 4:
        return False
    try:
        span = w.split(" ")[0]
        start_s, end_s = span.split("-")
        sh, sm = (int(x) for x in start_s.split(":"))
        eh, em = (int(x) for x in end_s.split(":"))
        minutes = now_ist.hour * 60 + now_ist.minute
        return sh * 60 + sm <= minutes <= eh * 60 + em
    except Exception:
        return True


def gather(cadence: str) -> dict:
    """Pull the live data the agent reasons over. Failures degrade to a note,
    never to a fabricated value."""
    d: dict = {}

    def grab(key, path, transform=lambda x: x):
        try:
            d[key] = transform(api(path))
        except Exception as e:
            d[key] = {"error": str(e)[:200]}

    grab("wa_activity", "/api/whatsapp/groups")
    grab("wa_recent", "/api/whatsapp/messages?limit=" + ("120" if cadence == "hourly" else "300"))
    grab("intel", "/api/intel?urgency=CRITICAL")
    grab("intel_high", "/api/intel?urgency=HIGH")
    grab("tasks", "/api/ops/tasks?status=open")
    grab("filings", "/api/compliance/filings")
    grab("tenders", "/api/vwlr/pipeline")
    grab("hotel", "/api/hotel/daily?days=7")
    grab("reports", "/api/agent/reports?limit=5")
    grab("capital", "/api/capital/summary")
    # Site servers, read over the VPN sidecars. A down tunnel arrives as an explicit
    # error here, so the agent reports a gap instead of reasoning over silence.
    grab("sites", "/api/sites")
    grab("site_hotel", "/api/sites/hotel")
    grab("site_vedanta", "/api/sites/vedanta")
    # What is already queued for him — so the agent doesn't re-raise a live item.
    grab("decision_feed", "/api/feed?limit=40")
    if cadence != "hourly":
        grab("entities", "/api/entities")
        grab("pools", "/api/aditi/pools")
    return d


HOURLY_RULES = """You are the MDO Hourly Watcher for Aman Agrawal (ANS Group, Raigarh CG):
VWLR coal washery (Kharsia, ~50% commissioning), Hotel ANS International (88 rooms),
Aditi Investments (NSE cash + F&O), ~26 group entities.

YOUR DEFAULT ANSWER IS "NOTHING". Most hours nothing has crossed a line. Reporting
routine noise trains him to ignore you. Only escalate genuine threshold breaches:
site stoppages, equipment faults, rakes idle with no dispatch movement, safety issues,
payment failures, a tender deadline inside 72 hours, or a compliance item turning overdue.
Ignore chit-chat, greetings, photos with no context, and anything already reported in
the recent agent reports below."""

DAILY_RULES = """You are the MDO Daily Brief for Aman Agrawal (ANS Group, Raigarh CG):
VWLR coal washery (Kharsia, ~50% commissioning, Rs 34.55 Cr service pipeline),
Hotel ANS International (88 rooms, ~23% occupancy), Aditi Investments (NSE cash + F&O),
~26 group entities. This reaches his phone first thing in the morning.

Cover: yesterday's site operations and dispatch/rake movement, equipment faults and
project progress (hotel renovation, washery development, siding/civil works),
compliance items due or overdue, and anything needing a decision today."""

COMMON_RULES = """
ABSOLUTE RULES (MDO_VISION section 13/19):
- NEVER invent a number, date, or fact. Use only the data given below. If something
  cannot be verified, write "unverified" and say why. A wrong number is worse than none.
- A check marked blocked has no data source — report the gap, never fill it with a guess.
- Every finding: What changed -> Why it matters -> Recommended action, with an owner.
- Indian amounts in lakh/crore.
- Seeded compliance dates are from April 2026 and may be stale; flag staleness rather
  than treating them as current truth.

Return ONLY a JSON object, no prose around it:
{"title": "...", "summary": "2-4 lines, most important first (this is the phone notification)",
 "body": "markdown detail, or empty string if nothing to report",
 "findings": [{"level":"critical|important|info","title":"...","detail":"what changed and why it matters",
               "action":"specific next step","owner":"Aman|CA Vimal Agrawal|...","entity":"...",
               "domain":"vwlr|market|capital|hotel|compliance|projects|banking"}]}
If genuinely nothing is worth reporting, return {"findings": [], "summary": "", "title": "", "body": ""}.
"""


def run(cadence: str) -> int:
    if not KEY:
        log("FATAL: MDO_AUTH_TOKEN not set in this container's environment")
        return 2
    if not ANTHROPIC_KEY:
        log("FATAL: ANTHROPIC_API_KEY not set — add it to .env on the VPS")
        return 2

    if not wait_for_backend():
        log("FATAL: backend not answering on " + BASE)
        return 2

    now_ist = datetime.now(IST)
    try:
        checks = api(f"/api/checks?cadence={cadence}").get("checks", [])
    except Exception as e:
        log(f"FATAL: cannot read checks registry: {e}")
        return 2

    active, skipped, blocked = [], [], []
    for c in checks:
        if c["status"] == "blocked":
            blocked.append(c)
        elif not in_window(c.get("run_window", ""), now_ist):
            skipped.append(c)
        else:
            active.append(c)
    log(f"{cadence}: {len(active)} active, {len(skipped)} out-of-window, {len(blocked)} blocked")
    if not active:
        log("nothing to run in this window")
        return 0

    data = gather(cadence)
    prompt = (
        (HOURLY_RULES if cadence == "hourly" else DAILY_RULES)
        + "\n\nNOW: " + now_ist.strftime("%A %d %B %Y, %H:%M IST")
        + "\n\nCHECKS YOU MUST RUN (each carries its own red/amber threshold):\n"
        + json.dumps([{k: c[k] for k in ("code", "title", "sources", "threshold", "owner")}
                      for c in active], indent=1)
        + ("\n\nCHECKS WITH NO DATA SOURCE (report the gap, do not guess):\n"
           + json.dumps([{"code": c["code"], "blocker": c["blocker"]} for c in blocked])
           if blocked else "")
        # 120k chars of JSON was ~35k input tokens and left the model no room to
        # answer; 60k keeps the full picture while guaranteeing an output budget.
        + "\n\nLIVE DATA:\n" + json.dumps(data, default=str)[:60000]
        + COMMON_RULES
    )

    def attempt(p: str, max_tokens: int):
        raw = ask_claude(p, max_tokens=max_tokens)
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s < 0 or e <= s:
            return None, raw
        try:
            return json.loads(raw[s:e]), raw
        except json.JSONDecodeError as err:
            log(f"JSON decode failed: {err}")
            return None, raw

    try:
        out, raw = attempt(prompt, 8000)
        if out is None:
            # Usually the budget went on reasoning before any text was emitted.
            # Retry once: less data, more room, and an explicit shape reminder.
            log(f"retrying with a tighter payload (first attempt returned {len(raw)} chars)")
            short = prompt[:45000] + (
                "\n\n[data truncated for retry]\n"
                "Reply with the JSON object ONLY — no preamble, no explanation, "
                "no code fence. Start your reply with { and end it with }."
            )
            out, raw = attempt(short, 16000)
    except Exception as e:
        log(f"FATAL: Claude call failed: {e}")
        return 3

    if out is None:
        log(f"FATAL: no usable JSON after retry. Model output was: {raw[:400] or '(empty)'}")
        return 3

    findings = out.get("findings") or []
    actionable = [f for f in findings if str(f.get("level", "")).lower() in ("critical", "important")]

    # Hourly stays silent unless something crossed a line; daily always reports.
    if cadence == "hourly" and not actionable:
        log("clean — nothing crossed a threshold, no report filed")
        for c in active:  # still record that the check ran
            try:
                api(f"/api/checks/{c['id']}", "PUT", {"last_result": "clean"})
            except Exception:
                pass
        return 0

    try:
        res = api("/api/agent/report", "POST", {
            "cadence": cadence,
            "agent": f"{cadence}-agent (vps)",
            "title": out.get("title") or f"{cadence.title()} report",
            "summary": out.get("summary", ""),
            "body": out.get("body", ""),
            "findings": findings,
            "checks_run": [c["code"] for c in active],
        }, timeout=60)
        log(f"filed report {res.get('report_id')} — {res.get('counts')} — intel items: {res.get('intel_filed')}")
        if out.get("summary"):
            log("SUMMARY: " + out["summary"].replace("\n", " ")[:400])
    except Exception as e:
        log(f"FATAL: could not file report: {e}")
        return 4

    publish_to_feed(actionable, cadence)
    return 0


# Severity mapping [A4] — matches the n_critical/n_important/n_info counters the
# reports table already uses, so one vocabulary runs end to end.
_LEVEL_TO_SEVERITY = {"critical": "critical", "important": "important"}


def publish_to_feed(findings: list, cadence: str) -> int:
    """Route the agent's actionable findings into the Decision Feed.

    The report stays where it was — this is additive. Dedup, cooldown and severity
    routing all happen inside the feed's publish(), so a finding repeated hour after
    hour interrupts once, not every hour. A finding that proposes a follow-up arrives
    with the task already drafted for one-tap approval.
    """
    published = 0
    for f in findings:
        level = str(f.get("level", "")).lower()
        severity = _LEVEL_TO_SEVERITY.get(level)
        if not severity:
            continue
        title = str(f.get("title") or "").strip()
        if not title:
            continue
        # Stable dedup identity: same check + same headline = the same finding.
        code = str(f.get("code") or f.get("check") or "").strip()
        key = f"agent.{code or title.lower()[:60]}"
        payload = {
            "key": key, "title": title[:200], "severity": severity,
            "source": f"{cadence}-agent", "domain": str(f.get("domain") or "general"),
            "body": str(f.get("detail") or ""),
            "evidence": [{"cadence": cadence, "level": level,
                          "owner": f.get("owner"), "entity": f.get("entity")}],
        }
        # The agent names an action -> draft it as a task he can approve with one tap.
        if f.get("action"):
            payload["action_type"] = "add_task"
            payload["action_payload"] = {
                "title": str(f["action"])[:200],
                "description": str(f.get("detail") or ""),
                "priority": "critical" if severity == "critical" else "high",
                "entity": f.get("entity") or "",
            }
        try:
            res = api("/api/feed/publish", "POST", payload)
            if res.get("published"):
                published += 1
        except Exception as e:
            # Never let feed publication break a report that already filed.
            log(f"feed publish failed for {key}: {str(e)[:150]}")
    log(f"decision feed: {published} of {len(findings)} findings published "
        f"({len(findings) - published} suppressed as duplicates or unmapped)")
    return published


if __name__ == "__main__":
    cad = (sys.argv[1] if len(sys.argv) > 1 else "daily").lower()
    if cad not in ("hourly", "daily", "weekly", "monthly", "quarterly", "annual"):
        print(__doc__)
        sys.exit(1)
    sys.exit(run(cad))
