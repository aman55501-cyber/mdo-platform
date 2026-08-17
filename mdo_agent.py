#!/usr/bin/env python3
"""MDO Agent Runner — the autonomous checks, running ON the VPS.

Why here and not in a cloud session: this process already has the Anthropic
key, the database, and network access to the backend. Cloud-scheduled agents
kept firing and delivering nothing, with no visible failure.

Usage (inside the backend container):
    python mdo_agent.py premarket   # 08:30 IST market roundup — the day's first report
    python mdo_agent.py hourly
    python mdo_agent.py daily

Cadences differ in posture: `premarket` ALWAYS reports (it is a briefing, and uses
live web search for crude/currency/global closes, which MDO has no feed for);
`hourly` reports only on a threshold breach; `daily` always reports.

Cron on the host (see DEPLOY_HOSTINGER.md §8) — times are UTC, IST = UTC+5:30:
    0  3 * * 1-5 cd /docker/sharecfo/mdo-platform && docker compose exec -T backend python mdo_agent.py premarket >> /var/log/mdo-agent.log 2>&1
    24 * * * *   cd /docker/sharecfo/mdo-platform && docker compose exec -T backend python mdo_agent.py hourly    >> /var/log/mdo-agent.log 2>&1
    27 1 * * *   cd /docker/sharecfo/mdo-platform && docker compose exec -T backend python mdo_agent.py daily     >> /var/log/mdo-agent.log 2>&1
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
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


# Anthropic's server-side web search. MDO has no source at all for crude, DXY,
# USDINR or the overnight global closes, so the 08:30 roundup cannot be written
# from the database alone. Server-side means the API runs the searches and returns
# finished text — no client-side tool loop needed. The identifier is versioned and
# may change; WEB_SEARCH_TOOL overrides it, and ask_claude degrades to no-search
# rather than failing the whole report.
WEB_SEARCH_TOOL = os.environ.get("WEB_SEARCH_TOOL", "web_search_20250305")
WEB_SEARCH_MAX_USES = int(os.environ.get("WEB_SEARCH_MAX_USES", "8"))


def _post_messages(payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode(),
        headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ask_claude(prompt: str, max_tokens: int = 8000, web_search: bool = False) -> str:
    """Call Claude and return its text. Logs why the text is empty rather than
    leaving a silent blank (an empty answer used to look like a parse failure).

    With web_search=True the model may search the live web. If the API rejects the
    tool (wrong version, not enabled on the account), we retry WITHOUT it and say
    so in the log — a roundup missing its global section beats no roundup, and the
    prompt already requires the model to mark unverifiable figures rather than
    invent them."""
    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if web_search:
        payload["tools"] = [{"type": WEB_SEARCH_TOOL, "name": "web_search",
                             "max_uses": WEB_SEARCH_MAX_USES}]
    try:
        resp = _post_messages(payload)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:300]
        except Exception:
            pass
        if web_search and e.code in (400, 403, 404):
            log(f"web search unavailable ({e.code}: {body}) — retrying without it. "
                "Global/commodity figures will be missing from this report.")
            payload.pop("tools", None)
            resp = _post_messages(payload)
        else:
            raise
    searches = sum(1 for b in resp.get("content", [])
                   if b.get("type") in ("web_search_tool_result", "server_tool_use"))
    if web_search:
        log(f"web search blocks in response: {searches}")
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

    if cadence == "premarket":
        # A market roundup does not need site chatter; it needs prices and news.
        grab("indices", "/api/market/indices")
        grab("watchlist", "/api/market/watchlist")
        grab("news", "/api/news/portfolio?limit=40")
        grab("capital", "/api/capital/networth/live")
        grab("singhvi", "/api/singhvi/today")
        return d

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

PREMARKET_RULES = """You are the MDO Market Roundup for Aman Agrawal, delivered at
08:30 IST — the FIRST thing he reads each day, before the 09:15 open and before the
Zee Business/Singhvi window.

This is a BRIEFING, NOT an exception alert. Unlike the hourly watcher, you ALWAYS
report. Silence here is a failure, not health.

Cover what has ALREADY happened. Do not forecast, do not recommend trades:
1. INDIA — previous session's close: NIFTY, SENSEX, BANKNIFTY with levels and %;
   advance/decline and market breadth; best and worst sectors; anything that moved
   his 15-name watchlist, especially the CG industrial cluster (COALINDIA, NTPC,
   JSPL, SAIL, NALCO, VEDL), power (ADANIPOWER, JSWENERGY) and holdings (HAL,
   TATAMOTORS, MSTC, IRCON, RITES).
2. GLOBAL OVERNIGHT — US closes (S&P, Nasdaq, Dow), Asia this morning (Nikkei,
   Hang Seng, Shanghai), and Europe's previous close. Say what drove them.
3. COMMODITIES — Brent and WTI crude with the move and why; gold; and where it is
   relevant, coal/coking coal and steel, because they hit VWLR and the buyers.
4. CURRENCY & RATES — USDINR, DXY, US 10-year. Note any RBI or Fed signal.
5. FLOWS — FII and DII activity if a figure is genuinely available. If not, write
   "FII/DII: no reliable source wired" — never estimate it.
6. NEWS THAT MATTERS TO HIM — results, regulatory news, sector policy, coal or
   railway announcements, and anything touching a watchlist thesis or a holding.
7. WHAT TO WATCH TODAY — factual only: results due, expiry, data releases,
   ex-dates. Not predictions.

Rules specific to this report:
- Every number must come from the live data or a search result. Attribute anything
  from search. If a figure cannot be verified, say so on its own line.
- Lead with what changed most, not with a fixed running order.
- Indian amounts in lakh/crore; index levels as points plus %.
- The summary field is the phone notification: 3-5 lines, the most consequential
  facts only. Put the full roundup in body as markdown with clear headings.
- Findings are for items needing action or carrying real risk — a routine index
  move is body content, not a finding."""

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
        (PREMARKET_RULES if cadence == "premarket"
         else HOURLY_RULES if cadence == "hourly" else DAILY_RULES)
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

    want_search = cadence == "premarket"

    def attempt(p: str, max_tokens: int):
        raw = ask_claude(p, max_tokens=max_tokens, web_search=want_search)
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
    return 0


if __name__ == "__main__":
    cad = (sys.argv[1] if len(sys.argv) > 1 else "daily").lower()
    if cad not in ("premarket", "hourly", "daily", "weekly", "monthly",
                   "quarterly", "annual"):
        print(__doc__)
        sys.exit(1)
    sys.exit(run(cad))
