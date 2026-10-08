#!/usr/bin/env python3
"""MDO bot runner — every specialist bot in fleet.yaml runs through this, ON the VPS.

Why here and not in a cloud session: this process already has the Anthropic
key, the database, and network access to the backend. Cloud-scheduled agents
kept firing and delivering nothing, with no visible failure.

Usage (inside the backend container):
    python mdo_agent.py ops-hourly          # any bot id from fleet.yaml
    python mdo_agent.py daily-brief
    python mdo_agent.py hourly              # legacy alias → ops-hourly
    python mdo_agent.py daily               # legacy alias → daily-brief

Guarantees (CHIEF_OF_STAFF.md §1):
  - EVERY run files a report, including a clean one (a heartbeat). A missing
    heartbeat is how the Chief of Staff knows a bot is dead.
  - The run checks the spend ledger first: ≥90% of cap → Haiku; ≥100% → the
    bot files "paused: budget" and exits. Paused is reported, never silent.
  - Numbers come only from the backend. Failures degrade to a note, never to
    a guess.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime

from mdo_cos import ECONOMY_MODEL, IST

BASE = os.environ.get("MDO_SELF_URL", "http://localhost:8501")
KEY = os.environ.get("MDO_AUTH_TOKEN", "").strip()
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
DEFAULT_MODEL = os.environ.get("MDO_AGENT_MODEL", "claude-sonnet-5-5")
FLEET_PATH = os.environ.get("FLEET_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fleet.yaml"))
LEGACY = {"hourly": "ops-hourly", "daily": "daily-brief"}


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


def load_fleet() -> dict:
    import yaml
    with open(FLEET_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def find_bot(fleet: dict, bot_id: str) -> dict | None:
    for b in fleet.get("bots") or []:
        if b.get("id") == bot_id:
            return b
    return None


def heartbeat(bot_id: str, cadence: str, status: str, summary: str, checks_run: list[str] | None = None) -> None:
    """The one call every run must make. Never raises: a heartbeat that
    cannot be filed is logged loudly so the cron log shows it."""
    try:
        api("/api/agent/report", "POST", {
            "bot": bot_id, "cadence": cadence, "heartbeat": True, "status": status,
            "agent": f"{bot_id} (vps)", "title": f"{bot_id}: {status}", "summary": summary,
            "body": "", "findings": [], "checks_run": checks_run or [],
        }, timeout=30)
        log(f"heartbeat filed: {status} — {summary[:120]}")
    except Exception as e:
        log(f"FATAL: heartbeat could not be filed ({e}) — the CoS will see a missed slot")


def ask_claude(prompt: str, model: str, bot_id: str, max_tokens: int = 16000) -> str:
    """Call Claude, record the spend, return the text. Logs why the text is
    empty rather than leaving a silent blank."""
    payload = json.dumps({
        "model": model,
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
    usage = resp.get("usage") or {}
    try:
        api("/api/spend/record", "POST", {
            "bot": bot_id, "model": resp.get("model") or model,
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
        }, timeout=15)
    except Exception as e:
        log(f"spend not recorded: {e}")
    if resp.get("stop_reason") == "refusal":
        log(f"model declined (refusal, {resp.get('stop_details')}) — treating as no output")
        return ""
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    if not text.strip():
        log("model returned no text — stop_reason=%s blocks=%s usage=%s" % (
            resp.get("stop_reason"), [b.get("type") for b in resp.get("content", [])], usage))
    return text


GROK_KEY = os.environ.get("GROK_API_KEY", "").strip()


def ask_grok(prompt: str, model: str, bot_id: str, handles: list[str] | None = None) -> str:
    """Call xAI's Responses API with live X search + web search, record the
    spend, return the text. Used by bots with provider: grok (x-watch)."""
    from datetime import date
    today = date.today().isoformat()
    x_tool: dict = {"type": "x_search", "from_date": today, "to_date": today}
    if handles:
        x_tool["allowed_x_handles"] = handles[:50]
    payload = json.dumps({
        "model": model,
        "instructions": "You are a real-time intelligence scout. Use x_search and web_search. "
                        "Report only what the tools returned, with the post/article link as source. "
                        "Never invent. Return ONLY the JSON object requested.",
        "input": [{"role": "user", "content": prompt}],
        "tools": [x_tool, {"type": "web_search"}],
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        "https://api.x.ai/v1/responses", data=payload,
        headers={"Authorization": f"Bearer {GROK_KEY}", "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        resp = json.loads(r.read())
    usage = resp.get("usage") or {}
    try:
        api("/api/spend/record", "POST", {
            "bot": bot_id, "model": resp.get("model") or model,
            "input_tokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        }, timeout=15)
    except Exception as e:
        log(f"spend not recorded: {e}")
    for item in reversed(resp.get("output", [])):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    return part.get("text", "")
    text = resp.get("output_text") or resp.get("text") or ""
    if not text:
        log(f"grok returned no text — keys={list(resp.keys())}")
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


def gather(bot: dict) -> dict:
    """Pull the live data the bot reasons over. Failures degrade to a note,
    never to a fabricated value."""
    d: dict = {}

    def grab(key, path, transform=lambda x: x):
        try:
            d[key] = transform(api(path))
        except Exception as e:
            d[key] = {"error": str(e)[:200]}

    wants = set(bot.get("checks") or [])
    hourly = "hourly" in str(bot.get("cadence", ""))
    grab("agenda", "/api/cos/agenda")
    grab("reports", "/api/agent/reports?limit=5")
    grab("intel", "/api/intel?urgency=CRITICAL")
    grab("intel_high", "/api/intel?urgency=HIGH")
    if wants & {"dispatch_rakes", "dispatch_trend", "projects_update", "hotel_daily"}:
        grab("wa_activity", "/api/whatsapp/groups")
        grab("wa_recent", "/api/whatsapp/messages?limit=" + ("120" if hourly else "300"))
    if wants & {"tender_watch"}:
        grab("tenders", "/api/vwlr/pipeline")
    if wants & {"compliance_due"}:
        grab("filings", "/api/compliance/filings")
        grab("tasks", "/api/ops/tasks?status=open")
        grab("entities", "/api/entities")
    if wants & {"hotel_daily"}:
        grab("hotel", "/api/hotel/daily?days=7")
    if wants & {"mkt_pulse", "acct_positions", "fo_update", "market_close"}:
        grab("capital", "/api/capital/summary")
        grab("watchlist", "/api/market/watchlist")
    if wants & {"market_close", "projects_update", "dispatch_trend"}:
        grab("tasks", "/api/ops/tasks?status=open")
        grab("pools", "/api/aditi/pools")
    return d


BOT_RULES = {
    "ops-hourly": """You are the MDO Ops Hourly Watcher for Aman Agrawal (ANS Group, Raigarh CG):
VWLR coal washery (Kharsia, commissioning), Hotel ANS International, group entities.

YOUR DEFAULT ANSWER IS "NOTHING". Most hours nothing has crossed a line. Reporting
routine noise trains him to ignore you. Only escalate genuine threshold breaches:
site stoppages, equipment faults, rakes idle with no dispatch movement, safety issues,
payment failures, a tender deadline inside 72 hours, or a compliance item turning overdue.
Ignore chit-chat, greetings, photos with no context, and anything already reported in
the recent agent reports below.""",
    "daily-brief": """You are the MDO Daily Brief for Aman Agrawal (ANS Group, Raigarh CG):
VWLR coal washery (Kharsia, commissioning), Hotel ANS International (88 rooms),
Aditi Investments (NSE cash + F&O), the group entities. This reaches his phone first
thing in the morning.

Cover: yesterday's site operations and dispatch/rake movement, equipment faults and
project progress (hotel renovation, washery development, siding/civil works),
compliance items due or overdue, and anything needing a decision today.""",
    "tender-go-no-go": """You are the VWLR Tender bot. Target categories: RCR of coal, loading/unloading
of coal, handling of rakes (ROM coal). For every tender in the pipeline or feed: eligible
or not against the criteria in the agenda, closing date, decision deadline, and a one-line
go / no-go with the reason. A tender closing inside 72 hours with no decision is 🔴.""",
    "compliance-sentinel": """You are the Compliance Sentinel across the ANS Group entities. Overdue or due
inside 3 days is 🔴; 4 to 14 days is 🟡. Owner is CA Vimal Agrawal unless the filing needs
Aman's signature, which is Aman's click. Seeded dates may be stale: flag staleness.""",
    "capital-watcher": """You are the Capital Watcher for the 4 broker accounts (Aman, Sudha, Ashok,
Aditi Investments). Thresholds: 🔴 book moves >3% in a day, a position down >5%, F&O
expiry within 2 days unhedged; 🟡 >2% day move, unrealised <-5%, sector >25%. You never
trade. You report.""",
    "x-watch": """You are the X / web real-time scout for Aman Agrawal (ANS Group, Raigarh CG). Search X and
the web NOW for: new NITs / tenders from CIL, SECL, WCL, MCL, NTPC, NALCO, GeM, CPPP in coal RCR,
coal loading/unloading, rake handling; news at client sites (Vedanta/BALCO Korba, JSPL Raigarh,
SAIL Bhilai, NTPC Sipat) — stoppages, strikes, accidents, rake/wagon shortages; posts by the tracked
competitors; coal policy and rail freight changes (Ministry of Coal, Railways, CEA); Anil Singhvi's
market calls. Every finding carries the post or article URL as its source. If the tools return
nothing relevant, say so — an empty result is a valid result.""",
    "hotel-daily": """You are the Hotel ANS daily bot. Occupancy below 20% or no night report received
is 🔴; below the trailing 7-day average is 🟡. Rate parity and OTA issues are 🟡.""",
}
GENERIC_RULES = """You are a specialist bot in Aman Agrawal's MDO fleet (ANS Group, Raigarh CG).
Run only the checks listed. Escalate only threshold breaches."""

COMMON_RULES = """
ABSOLUTE RULES (CHIEF_OF_STAFF.md §1):
- Only Aman sets objectives. Work only toward the confirmed objectives in the AGENDA
  block, and the checks listed. Propose, never start, anything else.
- NEVER invent a number, date, or fact. Use only the data given below. If something
  cannot be verified, write "unverified" and say why. A wrong number is worse than none.
- A check marked blocked has no data source — report the gap, never fill it with a guess.
- Every finding: What changed -> Why it matters -> Recommended action, with an owner,
  and an ETA for the action when one can be estimated.
- Indian amounts in lakh/crore.
- Seeded compliance dates are from April 2026 and may be stale; flag staleness rather
  than treating them as current truth.

Return ONLY a JSON object, no prose around it:
{"title": "...", "summary": "2-4 lines, most important first (this is the phone notification)",
 "body": "markdown detail, or empty string if nothing to report",
 "findings": [{"level":"critical|important|info","title":"...","detail":"what changed and why it matters",
               "action":"specific next step","owner":"Aman|CA Vimal Agrawal|...","entity":"...",
               "eta":"e.g. today 17:00 / 2 days / unknown",
               "domain":"vwlr|market|capital|hotel|compliance|projects|banking"}]}
If genuinely nothing is worth reporting, return {"findings": [], "summary": "", "title": "", "body": ""}.
"""


def run(bot_id: str) -> int:
    bot_id = LEGACY.get(bot_id, bot_id)
    if not KEY:
        log("FATAL: MDO_AUTH_TOKEN not set in this container's environment")
        return 2
    if not wait_for_backend():
        log("FATAL: backend not answering on " + BASE)
        return 2

    try:
        fleet = load_fleet()
    except Exception as e:
        log(f"FATAL: cannot read fleet.yaml at {FLEET_PATH}: {e}")
        return 2
    bot = find_bot(fleet, bot_id)
    if bot is None:
        log(f"FATAL: no bot '{bot_id}' in fleet.yaml")
        return 2
    cadence = str(bot.get("cadence", "daily"))
    cadence_key = "hourly" if cadence.startswith("hourly") else ("weekly" if cadence.startswith("weekly") else "daily")

    if not bot.get("enabled", True):
        heartbeat(bot_id, cadence_key, "disabled", "bot disabled in fleet.yaml — nothing run")
        return 0
    provider = str(bot.get("provider") or "anthropic").lower()
    if provider == "grok" and not GROK_KEY:
        heartbeat(bot_id, cadence_key, "error", "GROK_API_KEY not set — add it to .env on the VPS")
        return 2
    if provider != "grok" and not ANTHROPIC_KEY:
        heartbeat(bot_id, cadence_key, "error", "ANTHROPIC_API_KEY not set — add it to .env on the VPS")
        return 2

    # Budget first (Directive §6).
    model = str(bot.get("model") or DEFAULT_MODEL)
    try:
        spend = api("/api/spend")
        mode = spend.get("mode", "normal")
    except Exception as e:
        mode, spend = "normal", {"error": str(e)[:100]}
    if mode == "paused":
        heartbeat(bot_id, cadence_key, "paused",
                  f"paused: budget — ₹{spend.get('month_to_date_inr', 0):,.0f} of ₹{spend.get('cap_inr', 0):,.0f} spent this month")
        return 0
    if mode == "economy" and provider != "grok" and model != ECONOMY_MODEL:
        log(f"economy mode: {model} → {ECONOMY_MODEL}")
        model = ECONOMY_MODEL

    now_ist = datetime.now(IST)
    try:
        registry = api("/api/checks").get("checks", [])
    except Exception as e:
        heartbeat(bot_id, cadence_key, "error", f"cannot read checks registry: {e}")
        return 2
    wanted = set(bot.get("checks") or [])
    checks = [c for c in registry if c["code"] in wanted] if wanted else [c for c in registry if c["cadence"] == cadence_key]

    active, skipped, blocked = [], [], []
    for c in checks:
        if c["status"] == "blocked":
            blocked.append(c)
        elif not in_window(c.get("run_window", ""), now_ist):
            skipped.append(c)
        else:
            active.append(c)
    log(f"{bot_id}: {len(active)} active, {len(skipped)} out-of-window, {len(blocked)} blocked, model {model}")
    if not active:
        heartbeat(bot_id, cadence_key, "clean",
                  f"nothing in window — {len(skipped)} checks out of window, {len(blocked)} blocked",
                  [c["code"] for c in checks])
        return 0

    data = gather(bot)
    agenda = data.pop("agenda", {}) or {}
    charter = bot.get("charter") or {}
    prompt = (
        BOT_RULES.get(bot_id, GENERIC_RULES)
        + ("\n\nYOUR CHARTER (fleet.yaml — Aman's standing orders for this bot):\n"
           + "\n".join(f"- {k}: {v if not isinstance(v, list) else '; '.join(map(str, v))}" for k, v in charter.items())
           if charter else "")
        + "\n\nNOW: " + now_ist.strftime("%A %d %B %Y, %H:%M IST")
        + "\n\nAGENDA (Aman's confirmed objectives — the only things you work toward):\n"
        + json.dumps(agenda.get("objectives") or [], default=str)[:6000]
        + "\n\nCHECKS YOU MUST RUN (each carries its own red/amber threshold):\n"
        + json.dumps([{k: c[k] for k in ("code", "title", "sources", "threshold", "owner")}
                      for c in active], indent=1)
        + ("\n\nCHECKS WITH NO DATA SOURCE (report the gap, do not guess):\n"
           + json.dumps([{"code": c["code"], "blocker": c["blocker"]} for c in blocked])
           if blocked else "")
        # 60k chars keeps the full picture while guaranteeing an output budget.
        + "\n\nLIVE DATA:\n" + json.dumps(data, default=str)[:60000]
        + COMMON_RULES
    )

    def attempt(p: str, max_tokens: int):
        if provider == "grok":
            raw = ask_grok(p, model, bot_id, handles=bot.get("x_handles") or None)
        else:
            raw = ask_claude(p, model, bot_id, max_tokens=max_tokens)
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s < 0 or e <= s:
            return None, raw
        try:
            return json.loads(raw[s:e]), raw
        except json.JSONDecodeError as err:
            log(f"JSON decode failed: {err}")
            return None, raw

    try:
        out, raw = attempt(prompt, 16000)
        if out is None:
            log(f"retrying with a tighter payload (first attempt returned {len(raw)} chars)")
            short = prompt[:45000] + (
                "\n\n[data truncated for retry]\n"
                "Reply with the JSON object ONLY — no preamble, no explanation, "
                "no code fence. Start your reply with { and end it with }."
            )
            out, raw = attempt(short, 24000)
    except urllib.error.HTTPError as e:
        heartbeat(bot_id, cadence_key, "error", f"Claude call failed: HTTP {e.code} {e.reason}")
        return 3
    except Exception as e:
        heartbeat(bot_id, cadence_key, "error", f"Claude call failed: {type(e).__name__}: {e}")
        return 3

    if out is None:
        heartbeat(bot_id, cadence_key, "error", f"no usable JSON after retry: {raw[:200] or '(empty)'}")
        return 3

    findings = out.get("findings") or []
    actionable = [f for f in findings if str(f.get("level", "")).lower() in ("critical", "important")]
    codes = [c["code"] for c in active]

    # Hourly bots stay quiet on the phone when clean, but ALWAYS file a heartbeat.
    if cadence_key == "hourly" and not actionable:
        heartbeat(bot_id, cadence_key, "clean", f"clean — {len(active)} checks ran, nothing crossed a threshold", codes)
        return 0

    try:
        res = api("/api/agent/report", "POST", {
            "bot": bot_id,
            "cadence": cadence_key,
            "status": "reported",
            "agent": f"{bot_id} (vps)",
            "model": model,
            "title": out.get("title") or f"{bot_id} report",
            "summary": out.get("summary", ""),
            "body": out.get("body", ""),
            "findings": findings,
            "checks_run": codes,
        }, timeout=60)
        log(f"filed report {res.get('report_id')} — {res.get('counts')} — intel items: {res.get('intel_filed')}")
        if out.get("summary"):
            log("SUMMARY: " + out["summary"].replace("\n", " ")[:400])
    except Exception as e:
        log(f"FATAL: could not file report: {e}")
        heartbeat(bot_id, cadence_key, "error", f"report produced but could not be filed: {e}", codes)
        return 4
    return 0


if __name__ == "__main__":
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if not arg:
        print(__doc__)
        sys.exit(1)
    sys.exit(run(arg))
