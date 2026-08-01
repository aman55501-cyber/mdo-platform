"""MDO Brain — the LLM layer wrapped around the whole backend.

Gives an LLM *hands on the live business data*: a registry of tools that map
straight onto the backend's own endpoint functions, plus two front doors:

  1. brain_ask()      — agentic loop for the in-app chat (/api/brain/ask).
                        Uses Claude (claude-opus-5) when ANTHROPIC_API_KEY is
                        set; falls back to Grok (GROK_API_KEY) otherwise.
  2. build_mcp_manager() — the same tools exposed as an MCP server, mounted by
                        mdo_server under a secret path so the Claude app
                        (phone/web) can connect to MDO as a custom connector.

mdo_server.py owns the DB and endpoint functions; it injects them via
configure() at startup, so this module has no circular imports.
"""

from __future__ import annotations

import json
import os
from typing import Any, Awaitable, Callable

# ── wiring ───────────────────────────────────────────────────────────────────
_toolbox: dict[str, Callable[..., Awaitable[Any]]] = {}

def configure(toolbox: dict[str, Callable[..., Awaitable[Any]]]) -> None:
    """Called once by mdo_server with its endpoint functions."""
    _toolbox.update(toolbox)


SYSTEM_PROMPT = """You are the MDO Brain — the intelligence layer of Aman Agrawal's \
Management Decision Office (ANS Group, Raigarh, Chhattisgarh, India).

Aman is a first-generation industrialist. His businesses: VWLR coal washery \
(commissioning at ~50% capacity, ₹34.55 Cr tender pipeline across WCL/SCCL/SECL), \
Hotel ANS (88 rooms, low occupancy — a standing focus area), Aditi Investments \
(liquid portfolio, target ₹100 Cr in 2 years), and 26 taxable entities with two \
critical §454(8) compliance flags (Ozone Steel, Rashi Steel).

You have tools that read his LIVE business database and a few that write to it. \
Rules, in order:
1. NEVER invent numbers. Pull them with tools; if a tool can't provide a figure, \
say "unverified" explicitly. Data accuracy is non-negotiable.
2. Classify findings 🔴 critical / 🟡 important / 🟢 info when reporting risk or news.
3. Recommendations follow: what changed → why it matters → specific action with owner.
4. Use add_task / add_intel_item when Aman asks you to track something, or when you \
surface something genuinely critical he should not lose — say so when you do.
5. Be direct and concise. Aman reads on a phone between site visits.
6. Amounts are in INR; use lakh/crore notation (₹12.5 L, ₹3.4 Cr)."""


# ── tool registry ────────────────────────────────────────────────────────────
# name → (description, JSON schema, toolbox key, kwargs mapper)
def _ident(args: dict) -> dict:
    return args

TOOLS: list[dict] = [
    {
        "name": "business_snapshot",
        "description": "One-shot overview of the whole operation: tender pipeline totals, hot leads, open compliance filings, latest hotel occupancy, wealth pools, open tasks and critical alerts. Call this first for broad questions.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_tenders",
        "description": "VWLR coal tender pipeline. Optionally filter by buyer (e.g. SECL, WCL, NTPC) or only tenders closing within 7 days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "buyer": {"type": "string", "description": "Buyer name filter, e.g. SECL"},
                "hot": {"type": "boolean", "description": "Only tenders closing in the next 7 days"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_leads",
        "description": "VWLR sales CRM leads (buyers of washed coal), with volumes, distance and priority.",
        "input_schema": {
            "type": "object",
            "properties": {"priority": {"type": "string", "enum": ["High", "Medium", "Low"]}},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_followups",
        "description": "CRM leads needing follow-up within the next 3 days.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_competitors",
        "description": "The tracked VWLR competitors with tenders won/tracked and threat notes.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "calculate_bid",
        "description": "VWLR bid calculator: landed cost and recommended bid for a coal tender given buyer, volume (MT), rail route and washery gate price (₹/MT). Routes: RAIGARH, BILASPUR, RAIPUR, NAGPUR, MUMBAI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "buyer": {"type": "string"},
                "volume_mt": {"type": "number"},
                "route": {"type": "string"},
                "gate_price": {"type": "number"},
            },
            "required": ["buyer", "volume_mt", "route", "gate_price"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_compliance_filings",
        "description": "Compliance filings across all ANS entities (ROC, GST, ITR, TDS...). Filter by status: pending, overdue, filed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "overdue", "filed"]},
                "entity": {"type": "string", "description": "Entity name filter"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_entities",
        "description": "The ANS Group taxable entities (companies, firms, HUF, individuals) with status and notes.",
        "input_schema": {
            "type": "object",
            "properties": {"type": {"type": "string", "enum": ["company", "individual", "huf", "firm"]}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_wealth_pools",
        "description": "The four ANS Wealth OS pools (A operating cash, B liquid/Aditi, C strategic illiquid, D freedom capital) with current values.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_hotel_performance",
        "description": "Hotel ANS daily occupancy / revenue entries for the last N days (default 30).",
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 365}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_market_watchlist",
        "description": "Live quotes for the 15 business-context watchlist stocks (COALINDIA, NTPC, JSPL, MSTC...). Slow (~seconds); only call when asked about markets or the portfolio.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_briefing",
        "description": "Today's classified intelligence briefing: 🔴 critical / 🟡 important / 🟢 info alerts across compliance, tenders, competitors and markets.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_tasks",
        "description": "The operations task board, including the build roadmap (category='roadmap').",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "done"]},
                "category": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_life_map",
        "description": "The Life LLM Map — every layer of the MDO system (domains, data sources, connectors, agents, skills, surfaces) with build status and connections.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_site_ops_feed",
        "description": "Raw messages from the 6 VWLR site-operations WhatsApp groups (rake status, placement, shifting, daily reports). Use to spot bottlenecks: weighbridge, gate, PC, operator, infrastructure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {"type": "string", "description": "Partial group name filter, e.g. 'rake'"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 300},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_whatsapp_groups",
        "description": "The WhatsApp ops groups seen so far, with message counts and last-message time.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_photo_data",
        "description": "Data read OUT OF PHOTOS posted in WhatsApp groups — weighbridge slips, rake/dispatch tallies, hotel sales and occupancy registers, machine logs, invoices, payment advices. Each entry has doc_type, a summary, the transcribed text and any labelled fields (vehicle_no, net_wt, qty_mt, rooms_sold, revenue...). Use whenever a number might have been sent as an image rather than typed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {"type": "string", "description": "Partial group name filter"},
                "doc_type": {"type": "string", "description": "weighbridge_slip|dispatch_report|sales_report|occupancy_report|machine_log|invoice|payment|purchase_order|site_photo"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_portfolio",
        "description": "LIVE portfolio across all four broker accounts (Aman/HDFC, Sudha/HDFC, Ashok/HDFC, Aditi/Angel) via the sharecfo bridge: net worth, invested vs holdings value, cash, day change, unrealised P&L, sector concentration, net market exposure and tilt, hedge suggestions, and open F&O positions with expiry. Also reports how stale the broker snapshot is. Use for any question about wealth, positions, F&O, exposure or trading P&L — this is real money, never estimate it.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_checks",
        "description": "The standing checks registry — every recurring question the agents answer (hourly/daily/weekly/monthly/quarterly/annual), with its data source, red/amber threshold, owner, run window, and whether it is blocked (data source missing). Use to answer 'what is monitored', 'what ran', or 'what is not covered yet'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cadence": {"type": "string", "enum": ["hourly", "daily", "weekly", "monthly", "quarterly", "annual"]},
                "status": {"type": "string", "enum": ["active", "blocked", "paused"]},
                "domain": {"type": "string", "description": "market|capital|vwlr|hotel|compliance|projects|banking"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "list_agent_reports",
        "description": "Past agent runs (hourly/daily/weekly…) with their summaries and 🔴/🟡/🟢 counts. Use to see what the autonomous agents already reported before repeating a finding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cadence": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "additionalProperties": False,
        },
    },
    # ── Capital depth ────────────────────────────────────────────────────
    # get_portfolio above is a summary keyhole. These reach the Shares CFO service
    # directly (same compose network) so capital questions get the same depth the
    # capital surface has, instead of an answer hedged by missing detail.
    {
        "name": "capital_positions",
        "description": "LIVE open positions with per-position P&L, LTP and expiry across all broker accounts, deeper than get_portfolio's summary. Use for 'what am I holding', 'which position is bleeding', F&O expiry questions.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "capital_exposure",
        "description": "Net market exposure, directional tilt, sector concentration and hedge suggestions. Use for 'how exposed am I', 'am I over-concentrated', risk-posture questions.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "capital_reconcile",
        "description": "Reconciliation across brokers — what the books say vs what the brokers report, and any mismatch. Use when a number is disputed or a holding looks wrong.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "capital_market_regime",
        "description": "Current market regime read (trend/volatility state) plus index levels. Use to frame any 'should I act now' capital question.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "capital_ideas",
        "description": "High-conviction ideas the capital engine currently ranks, with their basis. These are candidates for discussion, never instructions — nothing executes from this tool.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "capital_fundamentals",
        "description": "Fundamentals for one ticker from the Screener universe (valuation, growth, quality). Use for any 'is X a good business' question.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "NSE symbol, e.g. RELIANCE"}},
            "required": ["symbol"], "additionalProperties": False,
        },
    },
    {
        "name": "capital_execution_status",
        "description": "Whether live trading is armed, which guardrails are set, and what preflight says is missing. Use before discussing any action that would move money — and to explain why an order cannot be placed.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    # ── Site networks (over the VPN sidecars) ────────────────────────────
    {
        "name": "get_site_data",
        "description": "LIVE readings from a site's own servers, reached over that site's VPN tunnel (hotel = Hotel ANS International, vedanta = the VWLR washery). Every reading carries its source URL and fetch time. If the tunnel is down or nothing is configured to be read, this says so — treat that as a gap, never fill it with an estimate.",
        "input_schema": {
            "type": "object",
            "properties": {"site": {"type": "string", "enum": ["hotel", "vedanta"]}},
            "required": ["site"], "additionalProperties": False,
        },
    },
    {
        "name": "get_site_links",
        "description": "Health of both site VPN tunnels — up/down, the proxy each uses, and what is configured to be read through them. Use to answer 'is the site data current' or to explain a missing number.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_decision_feed",
        "description": "The Decision Feed — everything currently waiting on Aman across all domains, critical first, with any drafted action attached. Use for 'what needs me', 'what's pending', or to avoid repeating a finding already queued.",
        "input_schema": {
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["critical", "important", "info"]},
                "domain": {"type": "string", "description": "market|capital|vwlr|hotel|compliance|projects|banking"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "add_task",
        "description": "WRITE: add a task to Aman's ops board. Use when he asks you to track something or a finding demands follow-up.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                "entity": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_intel_item",
        "description": "WRITE: file an item into the Intel Centre so it surfaces in briefings.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "urgency": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "category": {"type": "string", "enum": ["market", "tender", "compliance", "competitor", "general"]},
                "entity": {"type": "string"},
                "due_date": {"type": "string"},
            },
            "required": ["title", "body", "urgency"],
            "additionalProperties": False,
        },
    },
]


async def execute_tool(name: str, args: dict) -> str:
    """Run one tool against the injected backend functions; return JSON text."""
    try:
        result = await _dispatch(name, args or {})
        return json.dumps(result, default=str)[:60_000]
    except Exception as e:  # tool errors go back to the model, not the user
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


async def _dispatch(name: str, a: dict) -> Any:
    tb = _toolbox
    if name == "business_snapshot":
        snapshot: dict[str, Any] = {}
        tenders = (await tb["tenders"]()).get("tenders", [])
        snapshot["tenders"] = {"count": len(tenders)}
        pools = (await tb["pools"]()).get("pools", [])
        snapshot["wealth_pools"] = [
            {"pool": p.get("pool_code"), "name": p.get("pool_name"), "value": p.get("current_value")} for p in pools
        ]
        filings = (await tb["filings"](status="pending")).get("filings", [])
        overdue = (await tb["filings"](status="overdue")).get("filings", [])
        snapshot["compliance"] = {"pending": len(filings), "overdue": len(overdue)}
        snapshot["hotel_last_7_days"] = (await tb["hotel"](days=7)).get("records", [])
        tasks = (await tb["tasks"](status="open")).get("tasks", [])
        snapshot["open_tasks"] = len(tasks)
        snapshot["roadmap_open"] = [t["title"] for t in tasks if t.get("category") == "roadmap"][:6]
        leads = (await tb["leads"](priority="High")).get("leads", [])
        snapshot["hot_leads"] = [{"company": l.get("company") or l.get("name"), "volume": l.get("volume_mt") or l.get("volume")} for l in leads[:8]]
        return snapshot
    if name == "list_tenders":
        return await tb["tenders"](buyer=a.get("buyer"), hot=bool(a.get("hot")))
    if name == "list_leads":
        return await tb["leads"](priority=a.get("priority"))
    if name == "list_followups":
        return await tb["followups"]()
    if name == "list_competitors":
        return await tb["competitors"]()
    if name == "calculate_bid":
        return await tb["bid"](buyer=a["buyer"], volume=float(a["volume_mt"]), route=a["route"], gate_price=float(a["gate_price"]))
    if name == "list_compliance_filings":
        return await tb["filings"](entity=a.get("entity"), status=a.get("status"))
    if name == "list_entities":
        return await tb["entities"](type=a.get("type"))
    if name == "get_wealth_pools":
        return await tb["pools"]()
    if name == "get_hotel_performance":
        return await tb["hotel"](days=int(a.get("days", 30)))
    if name == "get_market_watchlist":
        return await tb["watchlist"]()
    if name == "get_briefing":
        return await tb["briefing"]()
    if name == "list_tasks":
        return await tb["tasks"](status=a.get("status"), category=a.get("category"))
    if name == "get_life_map":
        return await tb["lifemap"]()
    if name == "get_site_ops_feed":
        return await tb["wa_messages"](group=a.get("group", ""), limit=int(a.get("limit", 100)))
    if name == "list_whatsapp_groups":
        return await tb["wa_groups"]()
    if name == "get_photo_data":
        return await tb["extractions"](group=a.get("group", ""), doc_type=a.get("doc_type", ""),
                                       limit=int(a.get("limit", 30)))
    if name == "get_portfolio":
        return await tb["capital"]()
    # Capital depth — straight through the Shares CFO bridge.
    if name == "capital_positions":
        return await tb["cfo"]("/positions/live")
    if name == "capital_exposure":
        return await tb["cfo"]("/exposure")
    if name == "capital_reconcile":
        return await tb["cfo"]("/reconcile")
    if name == "capital_market_regime":
        return await tb["cfo"]("/market/regime")
    if name == "capital_ideas":
        return await tb["cfo"]("/ideas/high-conviction")
    if name == "capital_fundamentals":
        return await tb["cfo"](f"/fundamentals/{a['symbol'].strip().upper()}")
    if name == "capital_execution_status":
        return await tb["cfo"]("/execution/preflight")
    # Site networks, over the VPN sidecars.
    if name == "get_site_data":
        return await tb["site_read"](a["site"])
    if name == "get_site_links":
        return await tb["site_links"]()
    if name == "get_decision_feed":
        return await tb["feed"](severity=a.get("severity"), domain=a.get("domain"))
    if name == "list_checks":
        return await tb["checks"](cadence=a.get("cadence"), status=a.get("status"),
                                  domain=a.get("domain"))
    if name == "list_agent_reports":
        return await tb["reports"](cadence=a.get("cadence"), limit=int(a.get("limit", 10)))
    if name == "add_task":
        return await tb["task_add"]({
            "title": a["title"], "description": a.get("description", ""),
            "priority": a.get("priority", "medium"), "entity": a.get("entity", ""),
            "due_date": a.get("due_date"), "category": "general",
        })
    if name == "add_intel_item":
        return await tb["intel_add"]({
            "title": a["title"], "body": a.get("body", ""), "urgency": a.get("urgency", "MEDIUM"),
            "category": a.get("category", "general"), "entity": a.get("entity"),
            "due_date": a.get("due_date"),
        })
    raise ValueError(f"unknown tool: {name}")


# ── provider: Claude (preferred) ─────────────────────────────────────────────
MAX_TURNS = 8
_fallbacks_supported = True  # flipped off if the account lacks the beta

async def _claude_create(client, **kwargs):
    """messages.create with server-side refusal fallback (beta) — degrades
    gracefully if this account doesn't have the beta enabled."""
    global _fallbacks_supported
    import anthropic

    if _fallbacks_supported:
        try:
            return await client.messages.create(
                extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
                extra_body={"fallbacks": "default"},
                **kwargs,
            )
        except anthropic.BadRequestError as e:
            if "fallback" not in str(e).lower():
                raise
            _fallbacks_supported = False  # remember; retry plain below
    return await client.messages.create(**kwargs)


async def _ask_claude(question: str, history: list[dict]) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic()
    messages = [*history, {"role": "user", "content": question}]
    tool_defs = [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in TOOLS
    ]
    trace: list[str] = []

    for _ in range(MAX_TURNS):
        response = await _claude_create(
            client,
            model="claude-opus-5",
            max_tokens=16000,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=tool_defs,
            messages=messages,
        )

        if response.stop_reason == "refusal":
            return {"answer": "The model declined this request (safety classifiers). Rephrase and try again.",
                    "tools_used": trace, "provider": "claude", "model": response.model}

        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        if response.stop_reason != "tool_use":
            answer = "".join(b.text for b in response.content if b.type == "text")
            return {"answer": answer, "tools_used": trace, "provider": "claude", "model": response.model}

        # execute requested tools, return all results in one user message
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                trace.append(block.name)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": await execute_tool(block.name, dict(block.input or {})),
                })
        messages.append({"role": "user", "content": results})

    return {"answer": "Stopped after too many tool rounds — try a narrower question.",
            "tools_used": trace, "provider": "claude", "model": "claude-opus-5"}


# ── provider: Grok fallback (existing key works day one) ─────────────────────
async def _ask_grok(question: str, history: list[dict]) -> dict:
    import httpx

    key = os.environ["GROK_API_KEY"]
    model = os.environ.get("GROK_MODEL", "grok-4")
    oai_tools = [
        {"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in TOOLS
    ]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "user", "content": question}]
    trace: list[str] = []

    async with httpx.AsyncClient(timeout=120) as http:
        for _ in range(MAX_TURNS):
            r = await http.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "messages": messages, "tools": oai_tools},
            )
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            if not calls:
                return {"answer": msg.get("content") or "", "tools_used": trace,
                        "provider": "grok", "model": model}
            messages.append(msg)
            for c in calls:
                fn = c["function"]["name"]
                trace.append(fn)
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                messages.append({"role": "tool", "tool_call_id": c["id"],
                                 "content": await execute_tool(fn, args)})

    return {"answer": "Stopped after too many tool rounds — try a narrower question.",
            "tools_used": trace, "provider": "grok", "model": model}


def provider_status() -> dict:
    has_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_grok = bool(os.environ.get("GROK_API_KEY"))
    return {
        "claude": has_claude, "grok": has_grok,
        "active": "claude" if has_claude else ("grok" if has_grok else None),
        "tools": [t["name"] for t in TOOLS],
    }


async def brain_ask(question: str, history: list[dict] | None = None) -> dict:
    """Answer a question with full tool access. history = [{role, content}] text turns."""
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in (history or [])
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str) and m["content"].strip()
    ][-12:]
    status = provider_status()
    if status["active"] == "claude":
        try:
            return await _ask_claude(question, history)
        except Exception as e:
            # bad/expired Claude key or account issue → degrade to Grok if possible
            import anthropic
            auth_issue = isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError))
            if status["grok"]:
                result = await _ask_grok(question, history)
                result["note"] = f"Claude unavailable ({type(e).__name__}) — answered via Grok"
                return result
            if auth_issue:
                return {"answer": "ANTHROPIC_API_KEY looks invalid — check it in .env, or add GROK_API_KEY as fallback.",
                        "tools_used": [], "provider": None, "model": None}
            raise
    if status["active"] == "grok":
        return await _ask_grok(question, history)
    return {"answer": "No LLM key configured. Set ANTHROPIC_API_KEY (preferred) or GROK_API_KEY in .env.",
            "tools_used": [], "provider": None, "model": None}


# ── MCP server: the same tools, for the Claude app on Aman's phone ───────────
def build_mcp_manager():
    """Returns a StreamableHTTPSessionManager exposing the tool registry over MCP,
    or None if the `mcp` package is not installed."""
    try:
        import mcp.types as mcp_types
        from mcp.server import Server
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    except ImportError:
        return None

    server = Server("mdo-business-brain")

    @server.list_tools()
    async def _list_tools() -> list:
        return [
            mcp_types.Tool(name=t["name"], description=t["description"], inputSchema=t["input_schema"])
            for t in TOOLS
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list:
        return [mcp_types.TextContent(type="text", text=await execute_tool(name, arguments or {}))]

    return StreamableHTTPSessionManager(app=server, json_response=True, stateless=True)
