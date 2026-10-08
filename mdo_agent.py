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
from datetime import datetime, timedelta

import mdo_wa_intel as wai
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
    if wants & {"dispatch_rakes", "dispatch_trend", "projects_update", "hotel_daily"}:
        # Site servers over the VPN sidecars. A down tunnel arrives as an explicit
        # error here, so the bot reports a gap instead of reasoning over silence.
        grab("sites", "/api/sites")
        grab("site_hotel", "/api/sites/hotel")
        grab("site_vedanta", "/api/sites/vedanta")
    # What is already queued for Aman — so the bot doesn't re-raise a live item.
    grab("decision_feed", "/api/feed?limit=40")
    if not hourly:
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
    cadence_key = ("hourly" if cadence.startswith(("hourly", "every")) else
                   ("weekly" if cadence.startswith("weekly") else "daily"))

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
    wa_runner = WA_BOTS.get(bot_id)
    if wa_runner is not None:
        # WhatsApp Intelligence bots have no checks registry; they drive /api/wa/*.
        try:
            return wa_runner(bot, model, cadence_key)
        except urllib.error.HTTPError as e:
            heartbeat(bot_id, cadence_key, "error", f"backend call failed: HTTP {e.code} {e.reason} ({e.url})")
            return 3
        except Exception as e:
            heartbeat(bot_id, cadence_key, "error", f"{type(e).__name__}: {str(e)[:200]}")
            return 3
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
        if wanted & {"acct_positions", "fo_update"}:
            check_broker_sessions()
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

    publish_to_feed(actionable, bot_id)
    if wanted & {"acct_positions", "fo_update"}:
        check_broker_sessions()
    return 0


# ── WhatsApp Intelligence bots (fleet.yaml: wa-classifier, wa-intel, business-pulse) ──
# The pipeline lives in mdo_wa_intel.py (pure helpers + /api/wa/*). These three
# functions only orchestrate: read via the API, ask the model, write via the API,
# heartbeat. Every run heartbeats, including an empty one (CHIEF_OF_STAFF.md §1.5).
MAX_CLASSIFY_PER_RUN = 40          # chats per classifier run (Haiku, ~1 call each)
MAX_INTEL_MSGS_PER_RUN = 2000      # messages per wa-intel run; the watermark carries the rest
INTEL_BATCH = 80                   # messages per extraction call


def _bot_memory_get(bot_id: str, key: str) -> str | None:
    try:
        for r in api("/api/cos/memory").get("bot_memory", []):
            if r.get("bot") == bot_id and r.get("key") == key and r.get("status") == "active":
                return r.get("value")
    except Exception as e:
        log(f"bot_memory read failed: {str(e)[:120]}")
    return None


def _bot_memory_set(bot_id: str, key: str, value: str, source: str) -> None:
    # A watermark is operational state, not a fact about the business, so it is
    # stored active (not proposed) — Aman never needs to approve it.
    try:
        api("/api/cos/memory", "POST", {"bot": bot_id, "key": key, "value": value, "source": source, "status": "active"})
    except Exception as e:
        log(f"bot_memory write failed: {str(e)[:120]}")


def run_wa_classifier(bot: dict, model: str, cadence_key: str) -> int:
    """Unclear chats → business/personal. Confident → applied (decided_by auto);
    otherwise one needs_choice job for Aman, asked once. Also applies the
    answers Aman already gave."""
    bot_id = "wa-classifier"
    errors: list[str] = []
    try:
        applied = api("/api/wa/verdicts/apply", "POST", {})
        n_applied = int(applied.get("applied") or 0)
        if n_applied:
            log(f"applied {n_applied} verdict(s) from Aman: {applied.get('details')}")
    except Exception as e:
        n_applied = 0
        errors.append(f"verdicts: {str(e)[:80]}")
    chats = api("/api/wa/chats?classification=unclear&with_samples=1&limit=400").get("chats", [])
    candidates = [c for c in chats if not c.get("asked_job_id")
                  and (int(c.get("msg_count") or 0) >= 3 or c.get("kind") == "group")]
    auto = asked = 0
    for chat in candidates[:MAX_CLASSIFY_PER_RUN]:
        name, account = str(chat.get("name") or chat.get("jid")), str(chat.get("account") or "1")
        try:
            raw = ask_claude(wai.classify_prompt(chat, chat.get("samples") or []), model, bot_id, max_tokens=400)
        except Exception as e:
            errors.append(f"{name[:30]}: {type(e).__name__}")
            continue
        v = wai.parse_classification(raw)
        if v and v["classification"] in ("business", "personal") and v["confidence"] >= wai.AUTO_CONFIDENCE:
            try:
                api("/api/wa/chats/classify", "POST", {
                    "jid": chat["jid"], "classification": v["classification"], "entity": v["entity"],
                    "decided_by": "auto", "confidence": v["confidence"], "reason": v["reason"]})
                auto += 1
                log(f"auto: {name[:40]} ({account}) → {v['classification']} {v['entity']} ({v['confidence']:.2f})")
                continue
            except Exception as e:
                errors.append(f"{name[:30]}: classify {str(e)[:60]}")
                continue
        guess = (v or {}).get("entity") or ""
        options = ([f"business: {guess}", "personal", "business: other entity"] if guess
                   else ["business", "personal"])
        try:
            job = api("/api/cos/jobs", "POST", {
                "title": f'chat "{name[:60]}" ({account}) — business or personal?', "kind": "needs_choice",
                "bot": bot_id, "options": options, "eta": "",
                "payload": {"action": "wa_classify", "jid": chat["jid"], "guess_entity": guess,
                            "model_reason": (v or {}).get("reason", "")[:200],
                            "model_confidence": (v or {}).get("confidence")}})
            api("/api/wa/chats/asked", "POST", {"jid": chat["jid"], "job_id": job.get("id")})
            asked += 1
            log(f"asked Aman: job #{job.get('id')} for {name[:40]} ({account})")
        except Exception as e:
            errors.append(f"{name[:30]}: job {str(e)[:60]}")
    pending = len(chats) - auto                   # still unclear after this run (asked ones included)
    line = f"wa-classifier: {auto} classified auto, {asked} asked, {pending} pending"
    if n_applied:
        line += f" · {n_applied} verdict(s) from Aman applied"
    if errors:
        line += f" · {len(errors)} error(s): " + "; ".join(errors[:3])
    heartbeat(bot_id, cadence_key, "warning" if errors else "clean", line)
    return 0


def run_wa_intel(bot: dict, model: str, cadence_key: str) -> int:
    """Business chats → biz_signals, from the watermark forward, ≤80 messages a
    call, every signal with evidence ids. Fingerprint dedup and the 🔴 push
    happen server-side on insert."""
    bot_id = "wa-intel"
    watermark = int(_bot_memory_get(bot_id, "watermark_msg_id") or 0)
    res = api(f"/api/wa/messages?classification=business&since_id={watermark}&limit={MAX_INTEL_MSGS_PER_RUN}")
    msgs = res.get("messages", [])
    open_total = (api("/api/wa/stats").get("signals") or {}).get("open_total", "?")
    if not msgs:
        heartbeat(bot_id, cadence_key, "clean",
                  f"wa-intel: scanned 0 msgs in 0 chats → 0 new signals (open total {open_total}) · watermark {watermark}")
        return 0
    by_chat: dict[str, list[dict]] = {}
    for m in msgs:
        by_chat.setdefault(str(m.get("chat_jid") or ""), []).append(m)
    now = datetime.now(IST)
    new_total = dup_total = alerts = 0
    errors: list[str] = []
    for jid, rows in by_chat.items():
        chat = {"jid": jid, "name": rows[0].get("chat_name"), "entity": rows[0].get("entity"),
                "account": rows[0].get("account"), "kind": rows[0].get("chat_kind")}
        for i in range(0, len(rows), INTEL_BATCH):
            batch = rows[i:i + INTEL_BATCH]
            try:
                raw = ask_claude(wai.extract_prompt(chat, batch, now=now), model, bot_id, max_tokens=4000)
            except Exception as e:
                errors.append(f"{str(chat['name'])[:30]}: {type(e).__name__}")
                continue
            sigs = wai.parse_signals(raw, allowed_ids={m["id"] for m in batch})
            for s in sigs:
                s["entity"] = s["entity"] or chat["entity"] or ""
                s["chat_jid"], s["chat_name"] = jid, chat["name"]
            if not sigs:
                continue
            try:
                out = api("/api/wa/signals", "POST", {"signals": sigs, "bot_id": bot_id}, timeout=60)
            except Exception as e:
                errors.append(f"{str(chat['name'])[:30]}: insert {str(e)[:60]}")
                continue
            new_total += int(out.get("inserted") or 0)
            dup_total += int(out.get("duplicates") or 0)
            alerts += len(out.get("alerts") or [])
    max_id = max(int(m["id"]) for m in msgs)
    _bot_memory_set(bot_id, "watermark_msg_id", str(max_id), f"wa-intel run {now:%Y-%m-%d %H:%M} IST")
    try:
        open_total = (api("/api/wa/stats").get("signals") or {}).get("open_total", "?")
    except Exception:
        pass
    line = (f"wa-intel: scanned {len(msgs)} msgs in {len(by_chat)} chats → {new_total} new signals "
            f"(open total {open_total})")
    if dup_total:
        line += f" · {dup_total} duplicate(s) skipped"
    if alerts:
        line += f" · {alerts} 🔴 pushed"
    if res.get("count", 0) >= MAX_INTEL_MSGS_PER_RUN:
        line += " · backlog remains, next run continues"
    if errors:
        line += f" · {len(errors)} error(s): " + "; ".join(errors[:3])
    heartbeat(bot_id, cadence_key, "warning" if errors else "clean", line)
    return 0


def run_business_pulse(bot: dict, model: str, cadence_key: str) -> int:
    """Weekly: open signals (90d) + response metrics (14d) + register →
    pulse_compute → the model narrates with ≤5 next steps. Any number the model
    writes that is not in its input is rejected (one retry, then the
    deterministic summary stands alone)."""
    bot_id = "business-pulse"
    inp = api("/api/wa/pulse/input?days=90&metric_days=14", timeout=60)
    signals, metrics, register = inp.get("signals", []), inp.get("metrics", []), inp.get("register", [])
    now = datetime.now(IST)
    computed = wai.pulse_compute(signals, metrics, now=now)
    known_ids = {s.get("id") for s in signals}
    prompt = wai.pulse_prompt(computed, signals, register, now)
    allowed = {"computed": computed, "signals": signals, "register": register, "now": now.strftime("%Y-%m-%d")}
    narrative: dict | None = None
    rejected: list[str] = []
    for attempt in range(2):
        p = prompt if not rejected else prompt + (
            "\n\nYOUR PREVIOUS ANSWER WAS REJECTED. These figures are not in the input: "
            + ", ".join(rejected[:20]) + ". Remove them or replace them with figures that are, citing #id.")
        raw = ask_claude(p, model, bot_id, max_tokens=6000)
        out = wai.parse_pulse(raw)
        if not out:
            rejected = ["(no JSON object returned)"]
            continue
        text = out["narrative"] + " " + out["headline"] + " " + " ".join(
            f"{st['step']} {st['eta']}" for st in out["next_steps"])
        bad = wai.verify_numbers(text, allowed)
        bad_ids = [f"#{i}" for st in out["next_steps"] for i in st["signal_ids"] if i not in known_ids]
        missing = [st["step"][:40] for st in out["next_steps"] if not (st["owner"] and st["eta"])]
        if not bad and not bad_ids and not missing:
            narrative = out
            break
        rejected = bad + bad_ids + [f"step without owner/ETA: {m}" for m in missing]
        log(f"pulse attempt {attempt + 1} rejected: {rejected[:10]}")
    n_open, n_gap = computed["totals"]["open"], len(computed["sales_gap"])
    n_bot, n_dec = len(computed["bottlenecks"]), len(computed["decisions_needed"])
    period_end, period_start = now.date(), now.date() - timedelta(days=7)
    if narrative is None:
        headline = (f"Business pulse {period_end:%d %b}: {n_open} open signals · {n_gap} sales gaps · "
                    f"{n_bot} recurring bottlenecks · {n_dec} decisions waiting — narrative withheld (uncited figures)")
        steps: list = []
        body_text = ""
    else:
        headline = narrative["headline"] or f"Business pulse {period_end:%d %b}"
        steps, body_text = narrative["next_steps"], narrative["narrative"]
    summary = headline + "\n" + "\n".join(
        f"{i + 1}. {st['step']} — {st['owner']} · ETA {st['eta']} · " + ", ".join(f"#{x}" for x in st["signal_ids"])
        for i, st in enumerate(steps))
    report = {"computed": computed, "narrative": body_text, "next_steps": steps, "headline": headline,
              "rejected": rejected if narrative is None else [], "model": model,
              "signals": [{"id": s.get("id"), "kind": s.get("kind")} for s in signals],
              "messages_scanned": inp.get("messages_scanned")}
    res = api("/api/wa/pulse", "POST", {
        "period_start": period_start.isoformat(), "period_end": period_end.isoformat(), "entity": "group",
        "report_json": report, "summary": summary, "headline": headline}, timeout=60)
    status = "clean" if narrative is not None else "warning"
    heartbeat(bot_id, cadence_key, status,
              f"business-pulse: {n_open} open signals · {n_gap} sales gaps · {n_bot} recurring bottlenecks · "
              f"{n_dec} decisions · {len(steps)} next steps → pulse #{res.get('id')}"
              + (" · narrative withheld: " + "; ".join(rejected[:5]) if narrative is None else ""))
    return 0


WA_BOTS = {"wa-classifier": run_wa_classifier, "wa-intel": run_wa_intel, "business-pulse": run_business_pulse}


def check_broker_sessions() -> None:
    """Broker logins expire daily and fail silently — the capital side just goes empty.
    Checked every cycle so the gap announces itself instead of being discovered."""
    try:
        res = api("/api/feed/check-sessions", "POST", {})
        n = res.get("published", 0)
        if n:
            log(f"broker sessions: {n} finding(s) published to the feed")
        else:
            accounts = res.get("accounts", [])
            log(f"broker sessions: all {len(accounts)} logged in" if accounts
                else "broker sessions: nothing to report")
    except Exception as e:
        log(f"broker session check failed: {str(e)[:150]}")


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
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if not arg:
        print(__doc__)
        sys.exit(1)
    sys.exit(run(arg))
