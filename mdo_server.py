"""Standalone MDO FastAPI server "" runs without any API keys.

Reads directly from vega_data.db and vedanta_crm.db.
No HDFC, Grok, or Telegram keys needed to start.

Usage:
    pip install fastapi uvicorn aiosqlite
    python mdo_server.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import urllib.request
import urllib.parse
import json as _json
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env for local dev — Railway injects env vars directly, this is a no-op there
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import aiosqlite
import uvicorn

import mdo_feed
import mdo_sites
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# ── paths ────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
VEGA_DB    = os.environ.get("VEGA_DB_PATH",    str(BASE / "vega" / "data" / "vega_data.db"))
VEDANTA_DB = os.environ.get("VEDANTA_DB_PATH", str(BASE / "vega" / "data" / "vedanta_crm.db"))
# Railway injects PORT; fall back to MDO_PORT (local) then 8501
PORT       = int(os.environ.get("PORT", os.environ.get("MDO_PORT", 8501)))

# Aman's watchlist "" business-context stocks
WATCHLIST = [
    # Core business "" CG industrial cluster
    {"symbol": "COALINDIA.NS", "ticker": "COALINDIA", "name": "Coal India", "context": "Sector anchor "" supply chain visibility"},
    {"symbol": "NTPC.NS",      "ticker": "NTPC",      "name": "NTPC",       "context": "CG plants at Sipat/Korba "" capex = rake contracts"},
    {"symbol": "JSPL.NS",      "ticker": "JSPL",      "name": "JSPL",       "context": "Jindal Steel Raigarh "" major coal consumer"},
    {"symbol": "SAIL.NS",      "ticker": "SAIL",      "name": "SAIL",       "context": "Bhilai Steel Plant "" coal logistics corridor"},
    {"symbol": "NALCO.NS",     "ticker": "NALCO",     "name": "NALCO",      "context": "Damanjodi relationship "" capex = RCR opportunity"},
    {"symbol": "VEDL.NS",      "ticker": "VEDL",      "name": "Vedanta",    "context": "BALCO Korba coal buyer "" backyard client"},
    # Power sector
    {"symbol": "ADANIPOWER.NS","ticker": "ADANIPOWER","name": "Adani Power","context": "Raipur/Korba plants "" active coal buyer"},
    {"symbol": "JSWENERGY.NS", "ticker": "JSWENERGY", "name": "JSW Energy", "context": "CG presence growing"},
    # Portfolio holdings
    {"symbol": "HAL.NS",       "ticker": "HAL",       "name": "HAL",        "context": "Strong performer "" track for exit/add"},
    {"symbol": "TATAMOTORs.NS","ticker": "TATAMOTORS","name": "Tata Motors","context": "Watch for fundamental changes"},
    {"symbol": "MSTC.NS",      "ticker": "MSTC",      "name": "MSTC",       "context": "CRITICAL "" runs CIL e-auctions AND bank auctions"},
    {"symbol": "IRCON.NS",     "ticker": "IRCON",     "name": "IRCON",      "context": "Railway infra "" siding-adjacent"},
    {"symbol": "RITES.NS",     "ticker": "RITES",     "name": "RITES",      "context": "Railway consulting "" siding expansion tenders"},
    # Trading watchlist
    {"symbol": "RELIANCE.NS",  "ticker": "RELIANCE",  "name": "Reliance",   "context": "Options trading"},
    {"symbol": "HDFCBANK.NS",  "ticker": "HDFCBANK",  "name": "HDFC Bank",  "context": "Options trading"},
]

# _"__"_ DB helpers _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
_vdb: aiosqlite.Connection | None = None

async def vdb() -> aiosqlite.Connection:
    global _vdb
    if _vdb is None:
        _vdb = await aiosqlite.connect(VEGA_DB)
        _vdb.row_factory = aiosqlite.Row
        await _ensure_schema()
    return _vdb

async def _ensure_schema():
    """Create tables if they don't exist yet."""
    db = _vdb
    await db.executescript("""
CREATE TABLE IF NOT EXISTS intel_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT DEFAULT 'market',
    source TEXT DEFAULT 'system', urgency TEXT DEFAULT 'MEDIUM',
    entity TEXT, title TEXT NOT NULL, body TEXT DEFAULT '',
    due_date TEXT, status TEXT DEFAULT 'open',
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ops_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    description TEXT DEFAULT '', entity TEXT DEFAULT '',
    assigned_to TEXT DEFAULT '', priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open', category TEXT DEFAULT 'general',
    due_date TEXT, completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS compliance_filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, entity_name TEXT NOT NULL,
    entity_type TEXT DEFAULT 'company', filing_type TEXT NOT NULL,
    description TEXT DEFAULT '', due_date TEXT, period TEXT DEFAULT '',
    status TEXT DEFAULT 'pending', notes TEXT DEFAULT '',
    assigned_to TEXT DEFAULT 'CA Vimal Agrawal', filed_on TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ans_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
    short_name TEXT, entity_type TEXT DEFAULT 'company',
    cin TEXT, gstin TEXT, pan TEXT, business TEXT DEFAULT '',
    location TEXT DEFAULT 'Raigarh, CG', status TEXT DEFAULT 'active',
    directors TEXT DEFAULT '', annual_turnover TEXT DEFAULT '',
    notes TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS aditi_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pool_code TEXT NOT NULL UNIQUE,
    pool_name TEXT NOT NULL, description TEXT DEFAULT '',
    target_allocation REAL DEFAULT 0, current_value REAL DEFAULT 0,
    instruments TEXT DEFAULT '', notes TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS vwlr_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER,
    company TEXT NOT NULL, contact TEXT DEFAULT '',
    type TEXT DEFAULT 'call', notes TEXT DEFAULT '',
    outcome TEXT DEFAULT '', follow_up_date TEXT,
    created_by TEXT DEFAULT 'Aman', created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS vwlr_tender_pipeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer TEXT NOT NULL, volume_mt REAL DEFAULT 0,
    category TEXT DEFAULT 'Other', due_date TEXT,
    status TEXT DEFAULT 'active', url TEXT DEFAULT '',
    notes TEXT DEFAULT '', eligibility_score REAL DEFAULT 0.8,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS hotel_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    total_rooms INTEGER DEFAULT 30,
    occupied INTEGER DEFAULT 0,
    rate REAL DEFAULT 0,
    fnb_revenue REAL DEFAULT 0,
    occupancy_pct REAL DEFAULT 0,
    room_revenue REAL DEFAULT 0,
    total_revenue REAL DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS trading_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    instrument_type TEXT DEFAULT 'equity',
    entry_price REAL NOT NULL,
    target_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    quantity INTEGER DEFAULT 1,
    confidence INTEGER DEFAULT 60,
    strategy TEXT DEFAULT '',
    rationale TEXT DEFAULT '',
    plain_english TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    pool TEXT DEFAULT 'B',
    order_id TEXT DEFAULT '',
    executed_price REAL DEFAULT 0,
    pnl REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    executed_at TEXT,
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS morning_briefing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    generated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS singhvi_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    exchange TEXT DEFAULT 'NSE',
    instrument TEXT DEFAULT 'EQ',
    direction TEXT NOT NULL,
    entry_price REAL DEFAULT 0,
    stop_loss REAL DEFAULT 0,
    target_price REAL DEFAULT 0,
    quantity INTEGER DEFAULT 1,
    timeframe TEXT DEFAULT 'Intraday',
    notes TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    raw_text TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    order_id TEXT DEFAULT '',
    executed_price REAL DEFAULT 0,
    pnl REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    executed_at TEXT
);
CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_name TEXT NOT NULL,
    sender TEXT DEFAULT '',
    text TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    jid TEXT DEFAULT '',
    flagged INTEGER DEFAULT 0,
    category TEXT DEFAULT 'ops',
    created_at TEXT DEFAULT (datetime('now'))
);
-- Checks registry: the standing questions the agents answer on a cadence.
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    cadence TEXT NOT NULL,                  -- hourly|daily|weekly|monthly|quarterly|annual
    domain TEXT DEFAULT 'general',          -- market|capital|vwlr|hotel|compliance|projects|banking
    sources TEXT DEFAULT '',                -- where the data comes from
    threshold TEXT DEFAULT '',              -- what makes it red vs amber
    owner TEXT DEFAULT 'Aman',
    run_window TEXT DEFAULT '',             -- e.g. "09:00-15:30 IST Mon-Fri"; blank = any time
    status TEXT NOT NULL DEFAULT 'active',  -- active|blocked|paused
    blocker TEXT DEFAULT '',                -- why it cannot run yet
    last_run TEXT,
    last_result TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
-- Agent output lands here (not only a git branch) so it reaches the app/phone.
CREATE TABLE IF NOT EXISTS agent_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cadence TEXT NOT NULL DEFAULT 'daily',
    agent TEXT DEFAULT '',
    title TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    body TEXT DEFAULT '',
    findings_json TEXT DEFAULT '[]',
    n_critical INTEGER DEFAULT 0,
    n_important INTEGER DEFAULT 0,
    n_info INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
-- What the photos actually said (weighbridge slips, tallies, registers).
CREATE TABLE IF NOT EXISTS media_extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    group_name TEXT DEFAULT '',
    sender TEXT DEFAULT '',
    doc_type TEXT DEFAULT 'other',
    summary TEXT DEFAULT '',
    extracted_text TEXT DEFAULT '',
    fields_json TEXT DEFAULT '{}',
    timestamp TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS hdfc_session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    access_token TEXT DEFAULT '',
    token_expiry TEXT DEFAULT '',
    available_margin REAL DEFAULT 0,
    client_id TEXT DEFAULT '45889297',
    connected INTEGER DEFAULT 0,
    last_updated TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS vwlr_competitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    location TEXT DEFAULT 'CG',
    type TEXT DEFAULT 'coal-handler',
    tenders_won INTEGER DEFAULT 0,
    tenders_tracked INTEGER DEFAULT 0,
    last_seen TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS intelligence_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    what_changed TEXT DEFAULT '',
    why_matters TEXT DEFAULT '',
    recommended_action TEXT DEFAULT '',
    source TEXT DEFAULT '',
    source_id INTEGER DEFAULT 0,
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS portfolio_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT DEFAULT '',
    url TEXT DEFAULT '',
    source TEXT DEFAULT '',
    sentiment TEXT DEFAULT 'neutral',
    impact TEXT DEFAULT 'medium',
    fetched_at TEXT DEFAULT (datetime('now')),
    read INTEGER DEFAULT 0,
    UNIQUE(ticker, headline)
);
CREATE TABLE IF NOT EXISTS life_map_nodes (
    id TEXT PRIMARY KEY,
    layer TEXT NOT NULL,
    label TEXT NOT NULL,
    detail TEXT DEFAULT '',
    status TEXT DEFAULT 'planned',
    kind TEXT DEFAULT '',
    icon TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    sort INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS life_map_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    label TEXT DEFAULT '',
    UNIQUE(from_node, to_node)
);
""")
    await db.commit()
    # Decision Feed tables (feed_items, feed_audit) — owned by mdo_feed.
    await mdo_feed.ensure_schema(db)
    # Seed competitors if table is empty
    async with db.execute("SELECT COUNT(*) as n FROM vwlr_competitors") as cur:
        row = await cur.fetchone()
    if row["n"] == 0:
        competitors = [
            ("Godavari Commodities",), ("Ind Synergy",), ("Hind Group",),
            ("Harijika Logistics",), ("Vimla Infrastructure",), ("Sendoz Minerals",),
            ("Kunal Transport",), ("Mohit Minerals",), ("RKTC",),
            ("Anoop Road Carriers",), ("Indramani",), ("Advika Logistics",),
            ("Omax Minerals",), ("KTC",), ("Tiwarta Coal",),
        ]
        await db.executemany(
            "INSERT OR IGNORE INTO vwlr_competitors (name) VALUES (?)", competitors
        )
        await db.commit()
    # Seed Life LLM Map if empty
    async with db.execute("SELECT COUNT(*) as n FROM life_map_nodes") as cur:
        row = await cur.fetchone()
    if row["n"] == 0:
        await _seed_life_map(db)
    # Seed the checks registry (Aman's standing cadence list) if empty
    async with db.execute("SELECT COUNT(*) as n FROM checks") as cur:
        row = await cur.fetchone()
    if row["n"] == 0:
        await db.executemany(
            """INSERT OR IGNORE INTO checks
               (code,title,cadence,domain,sources,threshold,owner,run_window,status,blocker)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            CHECKS_SEED,
        )
        await db.commit()
    # Seed build roadmap (shown as "Remaining Steps" on /lifemap + sidebar) if empty
    async with db.execute("SELECT COUNT(*) as n FROM ops_tasks WHERE category='roadmap'") as cur:
        row = await cur.fetchone()
    if row["n"] == 0:
        roadmap = [
            # (title, description, entity=phase, priority)
            ("Deploy MDO to Hostinger VPS",
             "Follow DEPLOY_HOSTINGER.md — docker compose up; replaces Railway, fixes DB persistence", "Phase 2 — Connectors", "critical"),
            ("HDFC OAuth: register VPS callback + OTP test",
             "Unlocks live trade execution from Morning Setup", "Phase 2 — Connectors", "critical"),
            ("Fetch Staah API token",
             "Hotel occupancy becomes a live feed instead of manual entry", "Phase 2 — Connectors", "high"),
            ("Scan WhatsApp QR after VPS launch",
             "Baileys bridge is integrated — open VWLR Ops Feed page, scan once; session persists", "Phase 2 — Connectors", "high"),
            ("Singhvi extractor live test",
             "VPS has the RAM — run yt-dlp → Whisper → Grok end-to-end; manual entry stays fallback", "Phase 2 — Connectors", "medium"),
            ("Review first nightly agent report",
             "Branch claude/agent-reports, runs 01:30 IST — tune the Routine prompt after reading", "Phase 3 — Agents", "high"),
            ("Attach MCP connectors to Routines",
             "Gmail/Notion via claude.ai Routines UI — gives agents inbox/docs reach", "Phase 3 — Agents", "medium"),
            ("Write Tier 1 skill: escalation-routing",
             "First of 10 playbooks in skills/ — the COO-handoff unlock", "Phase 4 — Skills", "high"),
            ("Build 13-week cash flow rollup",
             "Build priority #10 from MDO_VISION §15", "Phase 4 — Skills", "medium"),
            ("Wire 🔴 alerts to phone push",
             "WhatsApp/push for critical items — agents reach you unprompted", "Phase 5 — Surfaces", "medium"),
            ("Monday Master Brief page in app",
             "Render the weekly agent synthesis as an app module", "Phase 5 — Surfaces", "medium"),
        ]
        await db.executemany(
            "INSERT INTO ops_tasks (title, description, entity, priority, category, assigned_to) "
            "VALUES (?,?,?,?, 'roadmap', 'Aman')",
            roadmap,
        )
        await db.commit()


# ── Life LLM Map seed ───────────────────────────────────────────────────────
# Layer order drives the left→right column layout on /lifemap.
LIFE_MAP_LAYERS = [
    {"key": "principal",  "label": "Principal",            "hint": "The person all of this serves"},
    {"key": "domains",    "label": "Life & Business",      "hint": "Domains the system manages"},
    {"key": "sources",    "label": "Data Sources",         "hint": "Raw signals from the real world"},
    {"key": "connectors", "label": "APIs · MCP · Bridges", "hint": "How signals enter the system"},
    {"key": "core",       "label": "LLM Core & Agents",    "hint": "Engines that think 24/7"},
    {"key": "skills",     "label": "Skill Library",        "hint": "Codified playbooks (Tier 1–5)"},
    {"key": "surfaces",   "label": "Surfaces & Outputs",   "hint": "Where decisions reach Aman"},
]

# Reconstructed from MDO_VISION.md / MDO_INTEL.md — NOT absolute data.
# Refine freely from the /lifemap UI; this seed only runs on an empty table.
LIFE_MAP_SEED_NODES = [
    # (id, layer, label, detail, status, kind, icon, notes, sort)
    ("principal", "principal", "Aman Agrawal", "Operator → Architect · 10x ANS in 3 years", "live", "person", "👑",
     "First-gen industrialist, Raigarh CG. Bottleneck today; COO transition unlocked by Tier 1 skills.", 0),

    # ── Domains ──
    ("dom_vwlr", "domains", "VWLR — Coal Washery", "₹34.55 Cr tender pipeline · 50% commissioning", "live", "domain", "🏭",
     "RCR, loading/unloading, rake handling. Tender247 + 15 competitors tracked.", 0),
    ("dom_aditi", "domains", "Aditi Investments", "₹85.78L liquid → ₹100 Cr in 2 yrs", "live", "domain", "📈",
     "HDFC Securities. Equities + F&O + US + crypto. Singhvi signal flow.", 1),
    ("dom_hotel", "domains", "Hotel ANS", "88 rooms · 23% occupancy (focus area)", "live", "domain", "🏨",
     "Staah inventory, Swiggy/Zomato. AOC-4/MGT-7 currency unknown.", 2),
    ("dom_compliance", "domains", "Compliance & Legal", "26 entities · 2 critical §454(8) flags", "live", "domain", "⚖️",
     "Ozone Steel (no ITR PDF) + Rashi Steel (CJM Bilaspur 3616/2026).", 3),
    ("dom_wealth", "domains", "ANS Wealth OS", "Pools A–D: operating / liquid / illiquid / freedom", "planned", "domain", "💎",
     "Pool sizes for C and D still TBD.", 4),
    ("dom_legacy", "domains", "Family & Legacy", "Newborn corpus · HUF/trust · global citizen", "planned", "domain", "👨‍👩‍👦",
     "Tier 4 skills: newborn-legacy-structure, family-financial-review.", 5),
    ("dom_health", "domains", "Health & Personal OS", "Health protocol + personal discipline", "planned", "domain", "🫀",
     "Tier 4: health-protocol.", 6),

    # ── Data sources ──
    ("src_tender247", "sources", "Tender247", "Tender listings — RCR / loading / rakes", "live", "source", "📋",
     "Manual login each session. Watch WCL, SCCL, SECL categories.", 0),
    ("src_whatsapp", "sources", "WhatsApp Ops Groups", "6 VWLR site groups on +91 7000512030", "building", "source", "💬",
     "Baileys bridge ships in docker-compose — scan QR once on the Ops Feed page.", 1),
    ("src_zee", "sources", "Zee Business — Anil Singhvi", "Live 8:00–9:15 AM IST · ~70% claimed accuracy", "building", "source", "📺",
     "yt-dlp → Whisper → Grok extraction. Manual entry is the reliable fallback.", 2),
    ("src_hdfc", "sources", "HDFC Securities", "Positions, funds, orders via InvestRight", "building", "source", "🏦",
     "OAuth + daily OTP. Callback URL still pointing at localhost.", 3),
    ("src_yahoo", "sources", "Yahoo Finance RSS", "News for all 15 watchlist stocks", "live", "source", "📰", "", 4),
    ("src_staah", "sources", "Staah · Swiggy · Zomato", "Room inventory + food delivery data", "planned", "source", "🍽️",
     "Staah API token pending from dashboard.", 5),
    ("src_mca", "sources", "MCA · GST · IT portals", "Filing status, due dates, notices", "planned", "source", "🏛️",
     "Manual today. Candidate for scraping or CA-assisted feed.", 6),
    ("src_nse", "sources", "NSE Block Deals · FII/DII", "Institutional flow signals", "parked", "source", "📊",
     "Needs session-cookie handling or a paid data provider.", 7),
    ("src_gsuite", "sources", "Gmail · Calendar · Drive", "Mail, meetings, documents", "planned", "source", "📧",
     "Best reached via MCP connectors — no scraping needed.", 8),

    # ── Connectors ──
    ("con_backend", "connectors", "MDO Backend (FastAPI)", "Hostinger VPS 24/7 · Docker · proxy for all feeds", "live", "api", "⚙️",
     "Everything proxies through here to avoid CORS.", 0),
    ("con_grok", "connectors", "Grok API (xAI)", "grok-4 · x_search + web_search live tools", "live", "api", "🤖", "", 1),
    ("con_hdfc_api", "connectors", "HDFC InvestRight API", "OAuth2 + OTP · order placement", "building", "api", "🔑",
     "Auth wired, untested. Register the VPS callback URL (stable now).", 2),
    ("con_claude", "connectors", "Claude API / Claude Code", "Agent runtime — skills, routines, repo access", "building", "api", "✨",
     "Runs in the cloud; this map itself was built by a Claude session.", 3),
    ("con_mcp", "connectors", "MCP Servers", "Gmail · Calendar · Drive · Notion · Supabase · GitHub", "planned", "mcp", "🔌",
     "Standard protocol — lets any LLM agent use your accounts as tools.", 4),
    ("con_ytdlp", "connectors", "yt-dlp + Whisper", "Zee Business audio → transcript", "building", "bridge", "🎙️",
     "Unblocked by Hostinger VPS RAM — ready for live test.", 5),
    ("con_wa_bridge", "connectors", "WhatsApp Bridge", "Baileys — no Chromium needed", "building", "bridge", "🌉",
     "Rewritten on Baileys (WebSocket) — runs as a compose service on the VPS.", 6),

    # ── LLM core & agents ──
    ("core_brain", "core", "MDO Brain", "LLM with 18 live tools over the whole backend", "live", "engine", "🧠",
     "Claude (claude-opus-5) with Grok fallback. Chat in-app; same tools exposed via MCP to the Claude phone app.", 0),
    ("core_briefing", "core", "Daily Briefing Engine", "🔴🟡🟢 classified scan across all domains", "live", "engine", "🧠",
     "What changed → Why it matters → Action. Runs on demand today; make it scheduled.", 0),
    ("core_grok_qa", "core", "Grok Q&A + Sentiment", "Ask-anything + live X sentiment", "live", "engine", "💬", "", 1),
    ("core_singhvi", "core", "Singhvi Extractor", "Transcript → structured trade calls", "building", "engine", "📡",
     "Built — VPS has the RAM to test it now.", 2),
    ("agent_biz", "core", "Agent — Business Optimizer", "24/7: tenders, competitors, occupancy, bottlenecks", "live", "agent", "🕵️",
     "LIVE — Claude Routine, nightly 01:30 IST, reports to branch claude/agent-reports + push/email notification.", 3),
    ("agent_capital", "core", "Agent — Capital Optimizer", "24/7: portfolio drift, screens, position sizing", "live", "agent", "💹",
     "LIVE — covered by nightly Routine (capital track). Screens, drift checks, watchlist thesis review.", 4),
    ("agent_compliance", "core", "Agent — Compliance Sentinel", "24/7: filing calendar, notices, court dates", "live", "agent", "🛡️",
     "LIVE — nightly Routine restates unresolved critical flags with days-elapsed pressure.", 5),

    # ── Skills ──
    ("skill_t1", "skills", "Tier 1 — Operator → Architect", "10 skills · unlocks COO hire", "building", "skill", "1️⃣",
     "vendor-evaluation, tender-go-no-go, escalation-routing (NEXT), weekly-operating-review…", 0),
    ("skill_t2", "skills", "Tier 2 — 10x Growth Engine", "BD pitches, acquisition screens, capex framework", "planned", "skill", "2️⃣",
     "bd-pitch-generator (JSW first), tender-document-parser, cash-flow-13-week.", 1),
    ("skill_t3", "skills", "Tier 3 — Capital Discipline", "Screens, sizing, drift, backtesting", "planned", "skill", "3️⃣",
     "qglp-graham-screen, fo-position-sizer, singhvi-backtester.", 2),
    ("skill_t4", "skills", "Tier 4 — Legacy & Personal", "Newborn structure, health, legal tracker", "planned", "skill", "4️⃣", "", 3),
    ("skill_t5", "skills", "Tier 5 — Meta", "monday-master-brief, decision-log, skill iteration", "planned", "skill", "5️⃣", "", 4),

    # ── Surfaces ──
    ("surf_app", "surfaces", "MDO Web App", "14 live modules · Railway · mobile-first", "live", "surface", "📱", "", 0),
    ("surf_briefing", "surfaces", "Daily Briefing", "Morning scan — critical items first", "live", "surface", "🗞️", "", 1),
    ("surf_morning", "surfaces", "Morning Setup → Execute", "Approve calls · execute 9:15 AM via HDFC", "live", "surface", "🌅",
     "Live execution blocked on HDFC OTP test.", 2),
    ("surf_push", "surfaces", "WhatsApp / Push Alerts", "Critical alerts reach the phone unprompted", "planned", "surface", "🔔",
     "Meta WhatsApp Business API or push notifications.", 3),
    ("surf_weekly", "surfaces", "Monday Master Brief", "Weekly synthesis of all agents' findings", "building", "surface", "📅",
     "Routine live: Mondays 07:00 IST — synthesis of the week's agent reports.", 4),
]

LIFE_MAP_SEED_EDGES = [
    # principal → domains
    ("principal", "dom_vwlr", ""), ("principal", "dom_aditi", ""), ("principal", "dom_hotel", ""),
    ("principal", "dom_compliance", ""), ("principal", "dom_wealth", ""), ("principal", "dom_legacy", ""),
    ("principal", "dom_health", ""),
    # domains → sources they emit/need
    ("dom_vwlr", "src_tender247", "tenders"), ("dom_vwlr", "src_whatsapp", "site ops"),
    ("dom_aditi", "src_zee", "signals"), ("dom_aditi", "src_hdfc", "broker"),
    ("dom_aditi", "src_yahoo", "news"), ("dom_aditi", "src_nse", "flows"),
    ("dom_hotel", "src_staah", "occupancy"),
    ("dom_compliance", "src_mca", "filings"),
    ("dom_legacy", "src_gsuite", "docs"), ("dom_wealth", "src_hdfc", "portfolio"),
    # sources → connectors
    ("src_tender247", "con_backend", ""), ("src_yahoo", "con_backend", ""),
    ("src_staah", "con_backend", ""), ("src_mca", "con_backend", ""), ("src_nse", "con_backend", ""),
    ("src_whatsapp", "con_wa_bridge", ""), ("src_zee", "con_ytdlp", ""),
    ("src_hdfc", "con_hdfc_api", ""), ("src_gsuite", "con_mcp", ""),
    # connectors → core
    ("con_backend", "core_briefing", ""), ("con_grok", "core_grok_qa", ""),
    ("con_grok", "core_singhvi", ""), ("con_ytdlp", "core_singhvi", ""),
    ("con_wa_bridge", "core_briefing", ""),
    ("con_claude", "agent_biz", ""), ("con_claude", "agent_capital", ""), ("con_claude", "agent_compliance", ""),
    ("con_mcp", "agent_biz", ""), ("con_mcp", "agent_compliance", ""),
    ("con_backend", "agent_biz", ""), ("con_backend", "agent_capital", ""),
    ("con_hdfc_api", "agent_capital", ""),
    # brain wiring
    ("con_backend", "core_brain", ""), ("con_claude", "core_brain", ""),
    ("con_grok", "core_brain", ""), ("con_wa_bridge", "core_brain", "ops feed"),
    ("core_brain", "surf_app", "chat"), ("core_brain", "skill_t1", ""),
    # core → skills
    ("agent_biz", "skill_t1", ""), ("agent_biz", "skill_t2", ""),
    ("agent_capital", "skill_t3", ""), ("agent_compliance", "skill_t1", ""),
    ("core_briefing", "skill_t5", ""), ("core_singhvi", "skill_t3", ""),
    ("agent_biz", "skill_t4", ""),
    # core/skills → surfaces
    ("core_briefing", "surf_briefing", ""), ("core_singhvi", "surf_morning", ""),
    ("core_grok_qa", "surf_app", ""),
    ("skill_t1", "surf_app", ""), ("skill_t2", "surf_app", ""),
    ("skill_t3", "surf_morning", ""), ("skill_t5", "surf_weekly", ""),
    ("agent_compliance", "surf_push", ""), ("agent_biz", "surf_weekly", ""),
    ("agent_capital", "surf_weekly", ""),
]


async def _seed_life_map(db):
    await db.executemany(
        """INSERT OR IGNORE INTO life_map_nodes
           (id, layer, label, detail, status, kind, icon, notes, sort)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        LIFE_MAP_SEED_NODES,
    )
    await db.executemany(
        "INSERT OR IGNORE INTO life_map_edges (from_node, to_node, label) VALUES (?,?,?)",
        LIFE_MAP_SEED_EDGES,
    )
    await db.commit()

# ── Checks registry seed ─────────────────────────────────────────────────────
# Aman's standing cadence list. status='blocked' means the data source does not
# exist yet — the agent reports the gap instead of inventing an answer.
# (code, title, cadence, domain, sources, threshold, owner, run_window, status, blocker)
MARKET_WINDOW = "09:00-15:30 IST Mon-Fri"
CHECKS_SEED = [
    # ── hourly ──────────────────────────────────────────────────────────────
    ("mkt_pulse", "Share market update — indices + watchlist", "hourly", "market",
     "/api/market/indices, /api/market/watchlist (15 business-context names)",
     "🔴 watchlist name moves >4% or index >1.5%; 🟡 >2% / >0.8%", "Aman",
     MARKET_WINDOW, "active", ""),
    ("acct_positions", "Portfolio — all 4 accounts (Aman, Sudha, Ashok, Aditi)", "hourly", "capital",
     "sharecfo bridge /api/capital/summary — HDFC1/2/3 + Angel, live sessions",
     "🔴 book moves >3% in a day or a position down >5%; 🟡 >2% day move, unrealised <-5%, sector >25%", "Aman",
     MARKET_WINDOW, "active", ""),
    ("fo_update", "F&O book — expiry, exposure, hedge", "hourly", "capital",
     "sharecfo bridge /api/capital/summary (positions/live + exposure)",
     "🔴 expiry within 2 days, or position down >5%; 🟡 net exposure tilt vs hedge suggestion", "Aman",
     MARKET_WINDOW, "active", ""),
    ("dispatch_rakes", "Dispatch vs incoming rakes — Vedanta", "hourly", "vwlr",
     "WhatsApp: Vedanta Daily Report, VWLR RAKE PLACEMENT, VWLR - RKM GROUP, LOADER REPORT VWLR",
     "🔴 rake placed with no dispatch movement >6h, or dispatch <70% of placed volume", "Aman",
     "", "active", ""),
    ("tender_watch", "New relevant tenders — coal/RCR/handling", "hourly", "vwlr",
     "Public portals (SECL/WCL/CIL/GeM/CPPP) + web search; Tender247 is manual login",
     "🔴 eligible tender closing <72h; 🟡 new eligible tender in target categories", "Aman",
     "", "active", "Tender247 has no API — public sources only"),
    # ── daily ───────────────────────────────────────────────────────────────
    ("dispatch_trend", "Dispatch report — day vs week vs month", "daily", "vwlr",
     "whatsapp_messages history (rake/dispatch groups)",
     "🔴 day <70% of trailing weekly average; 🟡 weekly trend down 2 weeks running", "Aman",
     "", "active", ""),
    ("market_close", "Market change — close + portfolio impact", "daily", "market",
     "/api/market/indices, watchlist, portfolio news",
     "🔴 any watchlist thesis broken by news; 🟡 sector move >3%", "Aman",
     "", "active", ""),
    ("compliance_due", "Compliance & deadlines — all entities", "daily", "compliance",
     "compliance_filings, ops_tasks(category=compliance), intel_items",
     "🔴 overdue or due <3 days; 🟡 due 4-14 days", "CA Vimal Agrawal",
     "", "active", "Seeded filing dates are from Apr 2026 — need a refresh pass with CA"),
    ("hotel_daily", "Hotel ANS — sales + occupancy", "daily", "hotel",
     "WhatsApp group 'Daily Sales Report' (auto-parsed into hotel_daily); Staah API as future backup",
     "🔴 occupancy <20% or no report received; 🟡 below trailing 7-day average", "Aman",
     "", "active", ""),
    ("projects_update", "Ongoing projects — hotel renovation, washery, siding/civil", "daily", "projects",
     "WhatsApp: Ans Hotel civil, Vedanta washery- Civil Works, ROAD BRIDGE WORK VEDANTA KUNKUNI, VWLR Machine Update",
     "🔴 no update >48h on an active project, or a blocker/stoppage reported", "Aman",
     "", "active", ""),
    ("bank_balances", "Bank balances — personal + all firms", "daily", "banking",
     "None connected yet (options: emailed statements via Gmail, bank API, manual entry)",
     "🔴 any account below its working-capital floor; 🟡 large unexplained debit", "Aman",
     "", "blocked", "No bank feed exists — decide channel: emailed statements, API, or manual"),
]

def vedanta_conn() -> sqlite3.Connection:
    if not os.path.exists(VEDANTA_DB):
        raise FileNotFoundError(f"Vedanta DB not found: {VEDANTA_DB}")
    conn = sqlite3.connect(VEDANTA_DB)
    conn.row_factory = sqlite3.Row
    return conn

# _"__"_ app _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
# MDO Brain: MCP server is mounted at /mcp/<MDO_MCP_SECRET>/ when the secret is
# set — that URL is what the Claude app connects to as a custom connector.
MCP_SECRET = os.environ.get("MDO_MCP_SECRET", "").strip()
_mcp_manager = None  # assigned at the bottom of this file once tools exist

@asynccontextmanager
async def lifespan(app: FastAPI):
    await vdb()  # connect on startup
    print(f"\n___ MDO Server running at http://localhost:{PORT}")
    print(f"   VEGA DB:    {VEGA_DB}")
    print(f"   Vedanta DB: {VEDANTA_DB}\n")
    if _mcp_manager is not None:
        print(f"   MCP server mounted at /mcp/{MCP_SECRET}/mcp\n")
        async with _mcp_manager.run():
            yield
    else:
        yield
    if _vdb:
        await _vdb.close()

app = FastAPI(title="ANS MDO Server", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── access control ──────────────────────────────────────────────────────────
# Set MDO_AUTH_TOKEN in .env to require a key on every API call. The frontend
# asks for it once (lock screen) and sends it as X-MDO-Key; the SSE stream and
# any manual use can pass ?key=. The /mcp/<secret> mount keeps its own secret.
MDO_AUTH_TOKEN = os.environ.get("MDO_AUTH_TOKEN", "").strip()
_CORS_401 = {"Access-Control-Allow-Origin": "*"}

@app.middleware("http")
async def _require_key(request, call_next):
    # /api/hdfc/callback is exempt: HDFC's OAuth redirect arrives from the
    # user's browser without our key. It carries only a one-time auth code.
    if (not MDO_AUTH_TOKEN or request.method == "OPTIONS"
            or request.url.path.startswith("/mcp/")
            or request.url.path == "/api/hdfc/callback"):
        return await call_next(request)
    supplied = (
        request.headers.get("x-mdo-key")
        or request.query_params.get("key")
        or (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    )
    if supplied != MDO_AUTH_TOKEN:
        from starlette.responses import JSONResponse
        return JSONResponse({"detail": "unauthorized — send X-MDO-Key"}, status_code=401, headers=_CORS_401)
    return await call_next(request)

# _"__"_ status _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/status")
async def status():
    from datetime import datetime
    now = datetime.now()
    hour = now.hour
    is_open = (9 <= hour < 15) or (hour == 15 and now.minute < 30)
    market = "OPEN" if is_open else ("PRE-MARKET" if hour == 9 and now.minute < 15 else "CLOSED")
    return {
        "time": now.strftime("%H:%M IST"),
        "market": market,
        "broker_authenticated": False,
        "active_positions": 0,
        "watchlist": ["RELIANCE", "INFY", "NIFTY", "BANKNIFTY", "TATAMOTORS"],
    }

@app.get("/api/positions")
async def positions():
    return {"positions": []}

@app.get("/api/holdings")
async def holdings():
    return {"holdings": []}

@app.get("/api/funds")
async def funds():
    return {"available": 0, "used_margin": 0, "total": 0}

@app.get("/api/pnl")
async def pnl():
    return {"total_pnl": 0, "realized_pnl": 0, "unrealized_pnl": 0, "trades_today": 0, "win_rate": 0}

@app.get("/api/watchlist")
async def watchlist():
    tickers = ["RELIANCE", "INFY", "NIFTY", "BANKNIFTY", "TATAMOTORS"]
    return {"watchlist": [{"ticker": t, "ltp": None, "sentiment_score": None, "sentiment_confidence": None} for t in tickers]}

@app.get("/api/health")
async def health():
    return {"db": True, "broker": False, "grok": False}

# SSE stub (keeps frontend happy)
@app.get("/api/stream")
async def stream():
    from fastapi.responses import StreamingResponse
    async def gen():
        while True:
            yield "event: ping\ndata: {}\n\n"
            await asyncio.sleep(25)
    return StreamingResponse(gen(), media_type="text/event-stream")

# _"__"_ Intel _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/intel")
async def intel(urgency: str | None = None, category: str | None = None, status: str | None = None):
    db = await vdb()
    q = "SELECT * FROM intel_items WHERE 1=1"
    params: list = []
    if urgency:   q += " AND urgency=?";  params.append(urgency.upper())
    if category:  q += " AND category=?"; params.append(category.lower())
    if status:    q += " AND status=?";   params.append(status.lower())
    q += " ORDER BY CASE urgency WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, created_at DESC LIMIT 100"
    rows = await db.execute_fetchall(q, params)
    return {"items": [dict(r) for r in rows]}

@app.post("/api/intel")
async def intel_add(body: dict):
    db = await vdb()
    await db.execute(
        "INSERT INTO intel_items (category,source,urgency,entity,title,body,due_date,status) VALUES (?,?,?,?,?,?,?,?)",
        (body.get("category","market"), body.get("source","manual"), body.get("urgency","MEDIUM"),
         body.get("entity",""), body.get("title",""), body.get("body",""),
         body.get("due_date"), "open")
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM intel_items ORDER BY id DESC LIMIT 1")
    return dict(rows[0]) if rows else {}

@app.post("/api/intel/{item_id}/resolve")
async def intel_resolve(item_id: int):
    db = await vdb()
    await db.execute("UPDATE intel_items SET status='resolved', updated_at=datetime('now') WHERE id=?", (item_id,))
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM intel_items WHERE id=?", (item_id,))
    return dict(rows[0]) if rows else {}

@app.post("/api/intel/{item_id}/acknowledge")
async def intel_ack(item_id: int):
    db = await vdb()
    await db.execute("UPDATE intel_items SET status='acknowledged', updated_at=datetime('now') WHERE id=?", (item_id,))
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM intel_items WHERE id=?", (item_id,))
    return dict(rows[0]) if rows else {}

@app.post("/api/intel/{item_id}/snooze")
async def intel_snooze(item_id: int):
    db = await vdb()
    await db.execute("UPDATE intel_items SET status='snoozed', updated_at=datetime('now') WHERE id=?", (item_id,))
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM intel_items WHERE id=?", (item_id,))
    return dict(rows[0]) if rows else {}

# _"__"_ Operations Tasks _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/ops/tasks")
async def ops_tasks(status: str | None = None, category: str | None = None):
    db = await vdb()
    q = "SELECT * FROM ops_tasks WHERE status != 'deleted'"
    params: list = []
    if status:   q += " AND status=?";   params.append(status)
    if category: q += " AND category=?"; params.append(category)
    q += " ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, due_date ASC NULLS LAST"
    rows = await db.execute_fetchall(q, params)
    return {"tasks": [dict(r) for r in rows]}

@app.post("/api/ops/tasks")
async def ops_task_add(body: dict):
    db = await vdb()
    await db.execute(
        "INSERT INTO ops_tasks (title,description,entity,assigned_to,priority,status,category,due_date) VALUES (?,?,?,?,?,?,?,?)",
        (body.get("title",""), body.get("description",""), body.get("entity",""),
         body.get("assigned_to","Aman"), body.get("priority","medium"),
         "open", body.get("category","general"), body.get("due_date") or None)
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM ops_tasks ORDER BY id DESC LIMIT 1")
    return dict(rows[0]) if rows else {}

@app.put("/api/ops/tasks/{task_id}")
async def ops_task_update(task_id: int, body: dict):
    db = await vdb()
    sets, params = [], []
    for k in ("title","description","entity","assigned_to","priority","status","category","due_date"):
        if k in body:
            sets.append(f"{k}=?"); params.append(body[k])
    if body.get("status") in ("done","completed"):
        sets.append("completed_at=datetime('now')")
    if sets:
        sets.append("updated_at=datetime('now')")
        params.append(task_id)
        await db.execute(f"UPDATE ops_tasks SET {','.join(sets)} WHERE id=?", params)
        await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM ops_tasks WHERE id=?", (task_id,))
    return dict(rows[0]) if rows else {}

# ── Capital bridge (sharecfo) ───────────────────────────────────────────────
# sharecfo already holds authenticated sessions for all four broker accounts
# (Aman/Sudha/Ashok on HDFC, Aditi on Angel). MDO reads through it rather than
# building a second broker auth path.
CFO_URL = os.environ.get("CFO_API_URL", "").strip().rstrip("/")
CFO_TOKEN = os.environ.get("CFO_API_TOKEN", "").strip()

def _cfo_get(path: str, timeout: int = 25) -> dict:
    if not CFO_URL or not CFO_TOKEN:
        return {"error": "CFO_API_URL / CFO_API_TOKEN not configured"}
    try:
        url = f"{CFO_URL}{path}?token={urllib.parse.quote(CFO_TOKEN)}"
        with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
            return _json.loads(r.read() or b"{}")
    except Exception as e:
        return {"error": str(e)[:200]}

def _stale_hours(as_of: str | None) -> float | None:
    if not as_of:
        return None
    try:
        from datetime import datetime, timezone
        t = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - t).total_seconds() / 3600, 1)
    except Exception:
        return None

@app.get("/api/capital/summary")
async def capital_summary():
    """Portfolio, exposure and F&O positions across all broker accounts, with
    threshold flags computed. Staleness is reported, never hidden."""
    pf = _cfo_get("/portfolio")
    ex = _cfo_get("/exposure")
    pos = _cfo_get("/positions/live")
    if pf.get("error"):
        return {"connected": False, "error": pf["error"]}

    positions = pos.get("positions") or []
    as_of = pf.get("as_of")
    stale = _stale_hours(as_of)

    flags: list[dict] = []
    if stale is not None and stale > 24:
        flags.append({"level": "important",
                      "text": f"Broker data is {stale}h old (as_of {as_of}) — sharecfo may not be refreshing"})
    dpct = pf.get("day_change_pct")
    if isinstance(dpct, (int, float)) and abs(dpct) >= 0.02:
        flags.append({"level": "critical" if abs(dpct) >= 0.03 else "important",
                      "text": f"Book moved {dpct*100:.2f}% today ({pf.get('day_change')})"})
    upct = pf.get("unrealised_pnl_pct")
    if isinstance(upct, (int, float)) and upct <= -0.05:
        flags.append({"level": "important",
                      "text": f"Unrealised P&L {upct*100:.1f}% vs invested"})
    # F&O: expiry pressure and per-position drawdown
    from datetime import date, datetime as _dtc
    for p in positions:
        if p.get("kind") in ("future", "option") or p.get("opt"):
            pnl_pct = p.get("pnl_pct")
            if isinstance(pnl_pct, (int, float)) and pnl_pct <= -5:
                flags.append({"level": "critical",
                              "text": f"{p.get('holder')} {p.get('label')}: {pnl_pct}% ({p.get('pnl')})"})
            exp = str(p.get("expiry") or "")
            if exp:
                try:
                    d = _dtc.strptime(exp, "%d-%b-%y").date()
                    days = (d - date.today()).days
                    if 0 <= days <= 2:
                        flags.append({"level": "critical",
                                      "text": f"{p.get('holder')} {p.get('label')} expires in {days}d — decide roll/close"})
                    elif days < 0:
                        flags.append({"level": "important",
                                      "text": f"{p.get('holder')} {p.get('label')} shows expiry {exp} (past) — stale position data"})
                except Exception:
                    pass
    # concentration
    for s in (pf.get("sector_concentration") or [])[:3]:
        if isinstance(s.get("pct"), (int, float)) and s["pct"] >= 0.25:
            flags.append({"level": "important",
                          "text": f"Sector concentration: {s.get('sector')} {s['pct']*100:.0f}% of book"})

    return {
        "connected": True,
        "as_of": as_of,
        "stale_hours": stale,
        "net_worth": pf.get("net_worth"),
        "holdings_value": pf.get("holdings_value"),
        "invested_value": pf.get("invested_value"),
        "cash": pf.get("cash"),
        "unrealised_pnl": pf.get("unrealised_pnl"),
        "unrealised_pnl_pct": pf.get("unrealised_pnl_pct"),
        "day_change": pf.get("day_change"),
        "day_change_pct": pf.get("day_change_pct"),
        "sector_concentration": (pf.get("sector_concentration") or [])[:6],
        "exposure": ex.get("net_exposure") if not ex.get("error") else {"error": ex.get("error")},
        "tilt": (ex.get("net_exposure") or {}).get("tilt") if not ex.get("error") else None,
        "hedge_suggestions": ex.get("hedge_suggestions") if not ex.get("error") else None,
        "fno_positions": [p for p in positions if p.get("kind") in ("future", "option") or p.get("opt")],
        "position_count": len(positions),
        "flags": flags,
    }

@app.get("/api/capital/accounts")
async def capital_accounts():
    return _cfo_get("/accounts")

# ── Checks registry ─────────────────────────────────────────────────────────
@app.get("/api/checks")
async def checks_list(cadence: str | None = None, status: str | None = None,
                      domain: str | None = None):
    """The standing cadence list. Agents call this to know what to produce."""
    db = await vdb()
    q = "SELECT * FROM checks WHERE 1=1"
    params: list = []
    if cadence: q += " AND cadence=?"; params.append(cadence.lower())
    if status:  q += " AND status=?";  params.append(status.lower())
    if domain:  q += " AND domain=?";  params.append(domain.lower())
    q += (" ORDER BY CASE cadence WHEN 'hourly' THEN 0 WHEN 'daily' THEN 1 "
          "WHEN 'weekly' THEN 2 WHEN 'monthly' THEN 3 WHEN 'quarterly' THEN 4 "
          "ELSE 5 END, domain, code")
    rows = await db.execute_fetchall(q, params)
    out = [dict(r) for r in rows]
    return {"checks": out, "count": len(out),
            "blocked": [c["code"] for c in out if c["status"] == "blocked"]}

@app.post("/api/checks")
async def checks_add(body: dict):
    db = await vdb()
    await db.execute(
        """INSERT OR REPLACE INTO checks
           (code,title,cadence,domain,sources,threshold,owner,run_window,status,blocker)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (str(body.get("code", "")).strip(), body.get("title", ""),
         str(body.get("cadence", "daily")).lower(), str(body.get("domain", "general")).lower(),
         body.get("sources", ""), body.get("threshold", ""), body.get("owner", "Aman"),
         body.get("run_window", ""), str(body.get("status", "active")).lower(),
         body.get("blocker", "")),
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM checks WHERE code=?", (body.get("code", ""),))
    return dict(rows[0]) if rows else {}

@app.put("/api/checks/{check_id}")
async def checks_update(check_id: int, body: dict):
    db = await vdb()
    sets, params = [], []
    for k in ("title", "cadence", "domain", "sources", "threshold", "owner",
              "run_window", "status", "blocker", "last_result"):
        if k in body:
            sets.append(f"{k}=?"); params.append(body[k])
    if sets:
        sets.append("updated_at=datetime('now')")
        params.append(check_id)
        await db.execute(f"UPDATE checks SET {','.join(sets)} WHERE id=?", params)
        await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM checks WHERE id=?", (check_id,))
    return dict(rows[0]) if rows else {}

# ── Agent reports ───────────────────────────────────────────────────────────
_LEVEL_URGENCY = {"critical": "CRITICAL", "red": "CRITICAL", "🔴": "CRITICAL",
                  "important": "HIGH", "amber": "HIGH", "🟡": "HIGH",
                  "info": "LOW", "green": "LOW", "🟢": "LOW"}

# 🔴 alerts reach Aman's phone through the WhatsApp bridge (self-message), so
# agents can interrupt him when it matters instead of waiting to be opened.
ALERT_TO = os.environ.get("ALERT_WHATSAPP_TO", "").strip()

def _send_whatsapp(text: str) -> dict:
    wa_url = os.environ.get("WA_BRIDGE_URL", "")
    if not wa_url or not ALERT_TO:
        return {"sent": False, "reason": "WA_BRIDGE_URL or ALERT_WHATSAPP_TO not set"}
    try:
        req = urllib.request.Request(
            wa_url.rstrip("/") + "/api/whatsapp/send",
            data=_json.dumps({"to": ALERT_TO, "text": text}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"sent": True, **_json.loads(r.read() or b"{}")}
    except Exception as e:
        return {"sent": False, "reason": str(e)[:200]}

@app.post("/api/alerts/test")
async def alerts_test(body: dict | None = None):
    """Prove the alert path end to end without waiting for a real 🔴."""
    msg = (body or {}).get("text") or "🔴 MDO test alert — if you can read this, critical findings will reach your phone."
    return _send_whatsapp(msg)


# ── One notifier ───────────────────────────────────────────────────────────
# Both halves grew their own push path: WhatsApp here, ntfy/Telegram in
# shares_cfo/notify.py. The Decision Feed sends through all of them best-effort so a
# finding is not lost because one channel is unconfigured. [A1]

MDO_APP_URL = os.environ.get("MDO_APP_URL", "").strip().rstrip("/")


def _deep_link(item_id: int) -> str:
    """Where the tap lands. Approval happens in the app, not in the notification."""
    return f"{MDO_APP_URL}/feed/{item_id}" if MDO_APP_URL else ""


def _send_ntfy(title: str, text: str, link: str = "") -> dict:
    topic = os.environ.get("CFO_NTFY_TOPIC", "").strip()
    if not topic:
        return {"sent": False, "reason": "CFO_NTFY_TOPIC not set"}
    try:
        headers = {"Title": title[:200].encode("ascii", "ignore").decode() or "MDO"}
        if link:
            headers["Click"] = link
        req = urllib.request.Request(
            f"https://ntfy.sh/{urllib.parse.quote(topic)}",
            data=text.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            return {"sent": True}
    except Exception as e:
        return {"sent": False, "reason": str(e)[:200]}


def _send_telegram(text: str) -> dict:
    token = os.environ.get("CFO_TELEGRAM_BOT_TOKEN", "").strip() or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("CFO_TELEGRAM_CHAT_ID", "").strip() or os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return {"sent": False, "reason": "telegram token/chat not set"}
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=_json.dumps({"chat_id": chat, "text": text[:4000],
                              "disable_web_page_preview": True}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10):
            return {"sent": True}
    except Exception as e:
        return {"sent": False, "reason": str(e)[:200]}


def _notify_all(item: dict) -> dict:
    """Push one feed item to every configured channel. Never raises."""
    icon = {"critical": "🔴", "important": "🟡"}.get(item["severity"], "🟢")
    link = _deep_link(item["id"])
    lines = [f"{icon} {item['title']}"]
    if item.get("body"):
        lines.append(item["body"][:600])
    if item.get("action_type"):
        lines.append(f"→ proposed: {item['action_type']} (approve in the app)")
    if link:
        lines.append(link)
    else:
        # [A5] fallback — without a public app URL the push still carries the substance.
        lines.append("(set MDO_APP_URL to get a one-tap link)")
    text = "\n".join(lines)
    results = {"whatsapp": _send_whatsapp(text), "ntfy": _send_ntfy(item["title"], text, link),
               "telegram": _send_telegram(text)}
    results["any_sent"] = any(r.get("sent") for r in results.values() if isinstance(r, dict))
    return results


# ── Decision Feed actions ──────────────────────────────────────────────────
# Registered once at import. The *kind* is what the approval path enforces:
# internal changes only our data, outward reaches a real person, money is refused.

async def _act_add_task(payload: dict) -> dict:
    db = await vdb()
    cur = await db.execute(
        "INSERT INTO ops_tasks (title, description, entity, priority, category, due_date)"
        " VALUES (?,?,?,?,?,?)",
        (payload.get("title", "Untitled"), payload.get("description", ""),
         payload.get("entity", ""), payload.get("priority", "medium"),
         payload.get("category", "general"), payload.get("due_date")))
    await db.commit()
    return {"task_id": cur.lastrowid, "title": payload.get("title")}


async def _act_file_intel(payload: dict) -> dict:
    db = await vdb()
    cur = await db.execute(
        "INSERT INTO intel_items (category, source, urgency, entity, title, body, due_date)"
        " VALUES (?,?,?,?,?,?,?)",
        (payload.get("category", "general"), payload.get("source", "decision-feed"),
         payload.get("urgency", "MEDIUM"), payload.get("entity", ""),
         payload.get("title", "Untitled"), payload.get("body", ""), payload.get("due_date")))
    await db.commit()
    return {"intel_id": cur.lastrowid}


async def _act_whatsapp_message(payload: dict) -> dict:
    """Reaches a real person — hence kind 'outward'. The full text is shown on the
    confirm screen before approval, and every send is audited by the feed."""
    to = payload.get("to") or ALERT_TO
    text = payload.get("text", "")
    if not text:
        raise ValueError("refusing to send an empty message")
    wa_url = os.environ.get("WA_BRIDGE_URL", "")
    if not wa_url or not to:
        raise RuntimeError("WA_BRIDGE_URL or recipient not configured")
    req = urllib.request.Request(
        wa_url.rstrip("/") + "/api/whatsapp/send",
        data=_json.dumps({"to": to, "text": text}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return {"sent": True, "to": to, **_json.loads(r.read() or b"{}")}


def register_feed_actions() -> dict:
    """Bind the action handlers to the feed. Idempotent and callable again — the
    registry is process-global, so anything that resets it (a test, a reload) can
    restore the real handlers by calling this rather than leaving approvals to fail
    with 'no handler registered'."""
    mdo_feed.register_action("add_task", "internal", _act_add_task)
    mdo_feed.register_action("file_intel", "internal", _act_file_intel)
    mdo_feed.register_action("whatsapp_message", "outward", _act_whatsapp_message)
    return mdo_feed.registered_actions()


register_feed_actions()


# ── Decision Feed routes ───────────────────────────────────────────────────

@app.get("/api/feed")
async def feed_list(status: str = None, severity: str = None, domain: str = None,
                    pending: bool = True, limit: int = 100):
    """The one feed. Critical first, then newest."""
    db = await vdb()
    await mdo_feed.expire_stale(db)
    items = await mdo_feed.list_items(db, status=status, severity=severity,
                                      domain=domain, pending_only=pending and not status,
                                      limit=limit)
    return {"items": items, "counts": await mdo_feed.counts(db),
            "actions": mdo_feed.registered_actions(),
            "money_actions_enabled": mdo_feed.money_actions_enabled()}


@app.get("/api/feed/digest")
async def feed_digest():
    """What is waiting, grouped — the batched view for 'important' items."""
    db = await vdb()
    items = await mdo_feed.list_items(db, pending_only=True, limit=200)
    by_domain: dict = {}
    for it in items:
        by_domain.setdefault(it["domain"], []).append(
            {"id": it["id"], "severity": it["severity"], "title": it["title"],
             "action_type": it["action_type"]})
    return {"counts": await mdo_feed.counts(db), "by_domain": by_domain}


@app.get("/api/feed/{item_id}")
async def feed_get(item_id: int):
    db = await vdb()
    item = await mdo_feed.get_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="no such feed item")
    return {**item, "audit": await mdo_feed.audit_trail(db, item_id)}


@app.post("/api/feed/publish")
async def feed_publish(body: dict):
    """Producers file findings here. Dedup, cooldown and severity routing are applied
    inside publish() so no producer can bypass them."""
    db = await vdb()
    try:
        item = await mdo_feed.publish(
            db,
            key=body["key"], title=body["title"],
            severity=body.get("severity", "info"),
            source=body.get("source", ""), domain=body.get("domain", "general"),
            body=body.get("body", ""), evidence=body.get("evidence"),
            action_type=body.get("action_type", ""),
            action_payload=body.get("action_payload"))
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    if item is None:
        return {"published": False, "reason": "suppressed by cooldown"}
    if item["notify_policy"] == "push":
        result = _notify_all(item)
        await mdo_feed.mark_notified(db, item["id"], _json.dumps(result)[:400])
        item = await mdo_feed.get_item(db, item["id"])
    return {"published": True, "item": item}


@app.post("/api/feed/{item_id}/approve")
async def feed_approve(item_id: int, body: dict | None = None):
    """One tap. Money actions are refused here by policy, not by omission."""
    db = await vdb()
    return await mdo_feed.decide(db, item_id, "approve",
                                 actor=(body or {}).get("actor", "aman"))


@app.post("/api/feed/{item_id}/reject")
async def feed_reject(item_id: int, body: dict | None = None):
    db = await vdb()
    return await mdo_feed.decide(db, item_id, "reject",
                                 actor=(body or {}).get("actor", "aman"))


@app.post("/api/feed/notify-pending")
async def feed_notify_pending():
    """Push anything critical that has not been notified yet (e.g. published while a
    channel was down). Safe to call repeatedly — already-notified items are skipped."""
    db = await vdb()
    items = await mdo_feed.list_items(db, status="new", severity="critical", limit=20)
    sent = []
    for it in items:
        result = _notify_all(it)
        await mdo_feed.mark_notified(db, it["id"], _json.dumps(result)[:400])
        sent.append({"id": it["id"], "title": it["title"], "result": result})
    return {"notified": len(sent), "items": sent}


@app.post("/api/feed/check-sessions")
async def feed_check_sessions():
    """Broker logins expire daily, and a logged-out account fails silently: the app
    still renders, it just has no capital in it. That is the worst kind of failure —
    it looks like calm. So the absence is published as a finding in its own right.

    Runs on the agent's cadence. `add_task` is drafted rather than executed, because
    re-authenticating needs a browser and a phone, not a server."""
    db = await vdb()
    published, checked = [], []

    acc = await asyncio.to_thread(_cfo_get, "/accounts")
    if acc.get("error"):
        item = await mdo_feed.publish(
            db, key="capital.bridge.down",
            title="Capital bridge unreachable — no broker data at all",
            severity="critical", source="session-check", domain="capital",
            body=("The Shares CFO service is not answering, so every capital number in "
                  "the feed and the briefing is missing rather than stale. "
                  f"Detail: {acc['error']}"),
            evidence=[{"endpoint": "/accounts", "error": acc["error"]}])
        if item:
            published.append(item)
    else:
        accounts = acc.get("accounts", [])
        out = [a for a in accounts if not a.get("logged_in")]
        checked = [{"key": a.get("key"), "label": a.get("label"),
                    "logged_in": bool(a.get("logged_in"))} for a in accounts]
        if out:
            names = ", ".join(f"{a.get('label') or a.get('key')}" for a in out)
            item = await mdo_feed.publish(
                db, key="capital.session.stale",
                title=f"Broker login expired — {len(out)} of {len(accounts)} accounts logged out",
                severity="important", source="session-check", domain="capital",
                body=(f"Logged out: {names}. Until these are re-authenticated the capital "
                      f"side of the feed is blind — it will look empty rather than broken. "
                      f"HDFC needs browser 2FA (scripts/hdfc_login.py); it expires daily."),
                evidence=[checked],
                action_type="add_task",
                action_payload={
                    "title": f"Re-run broker login ({names})",
                    "description": "HDFC needs daily browser 2FA via scripts/hdfc_login.py.",
                    "priority": "high", "category": "capital"})
            if item:
                published.append(item)

    # Separately: the bridge can be up and authenticated while the snapshot rots.
    summary = await capital_summary()
    stale = summary.get("stale_hours") if isinstance(summary, dict) else None
    if isinstance(stale, (int, float)) and stale > 24:
        item = await mdo_feed.publish(
            db, key="capital.snapshot.stale",
            title=f"Broker snapshot is {stale}h old",
            severity="important", source="session-check", domain="capital",
            body="Logins look fine but the data behind them is not refreshing.",
            evidence=[{"stale_hours": stale}])
        if item:
            published.append(item)

    for item in published:
        if item["notify_policy"] == "push":
            result = _notify_all(item)
            await mdo_feed.mark_notified(db, item["id"], _json.dumps(result)[:400])

    return {"accounts": checked, "published": len(published), "items": published}


# ── Site access over the VPN sidecars ──────────────────────────────────────

@app.get("/api/sites")
async def sites_overview():
    """Both site links and what is configured to be read through them."""
    return {"tunnels": mdo_sites.all_tunnels(),
            "sources": mdo_sites.load_sources(),
            "read_only": True}


@app.get("/api/sites/{site}")
async def site_read(site: str):
    """Live readings from one site, each carrying where it came from and when."""
    if site not in mdo_sites.SITES:
        raise HTTPException(status_code=404, detail=f"unknown site {site!r}")
    return {"tunnel": mdo_sites.tunnel_status(site), **mdo_sites.read_site(site)}


@app.post("/api/sites/check")
async def sites_check():
    """Probe both tunnels; publish a critical finding for any that is down while
    something is configured to be read through it."""
    db = await vdb()
    published = await mdo_sites.publish_tunnel_alerts(db, mdo_feed)
    for item in published:
        result = _notify_all(item)
        await mdo_feed.mark_notified(db, item["id"], _json.dumps(result)[:400])
    return {"tunnels": mdo_sites.all_tunnels(), "published": len(published),
            "items": published}

@app.post("/api/agent/report")
async def agent_report(body: dict):
    """Agents POST their run here — this is the delivery path that reaches the
    app and the phone. 🔴/🟡 findings also become intel items automatically."""
    db = await vdb()
    findings = body.get("findings") or []
    if not isinstance(findings, list):
        findings = []
    counts = {"CRITICAL": 0, "HIGH": 0, "LOW": 0}
    for f in findings:
        counts[_LEVEL_URGENCY.get(str(f.get("level", "info")).lower().strip(), "LOW")] += 1

    await db.execute(
        """INSERT INTO agent_reports
           (cadence,agent,title,summary,body,findings_json,n_critical,n_important,n_info)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (str(body.get("cadence", "daily")).lower(), str(body.get("agent", ""))[:80],
         str(body.get("title", ""))[:200], str(body.get("summary", ""))[:2000],
         str(body.get("body", ""))[:60000], _json.dumps(findings)[:60000],
         counts["CRITICAL"], counts["HIGH"], counts["LOW"]),
    )
    # Surface actionable findings in the Intel Centre / briefing
    filed = 0
    newly_filed: set[str] = set()
    for f in findings:
        urgency = _LEVEL_URGENCY.get(str(f.get("level", "info")).lower().strip(), "LOW")
        if urgency == "LOW":
            continue
        title = str(f.get("title", ""))[:200]
        if not title:
            continue
        # don't refile an identical open item from an earlier run
        dup = await db.execute_fetchall(
            "SELECT id FROM intel_items WHERE title=? AND status='open' LIMIT 1", (title,))
        if dup:
            continue
        detail = str(f.get("detail", ""))
        action = str(f.get("action", ""))
        await db.execute(
            """INSERT INTO intel_items (category,source,urgency,entity,title,body,due_date,status)
               VALUES (?,?,?,?,?,?,?,'open')""",
            (str(f.get("domain", "agent")).lower()[:40], "agent", urgency,
             str(f.get("entity", ""))[:100], title,
             (detail + ("\n\nAction: " + action if action else ""))[:4000],
             f.get("due_date") or None),
        )
        filed += 1
        newly_filed.add(title)

    # Stamp the checks this run covered
    for code in (body.get("checks_run") or []):
        await db.execute(
            "UPDATE checks SET last_run=datetime('now'), last_result=?, updated_at=datetime('now') WHERE code=?",
            (str(body.get("summary", ""))[:300], str(code)),
        )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM agent_reports ORDER BY id DESC LIMIT 1")

    # Push 🔴 findings to WhatsApp — only the newly filed ones, so a recurring
    # problem doesn't re-alert every hour.
    alert = {"sent": False, "reason": "no new critical findings"}
    new_crit = [f for f in findings
                if _LEVEL_URGENCY.get(str(f.get("level", "")).lower().strip()) == "CRITICAL"
                and str(f.get("title", ""))[:200] in newly_filed]
    if new_crit:
        lines = [f"🔴 MDO ALERT — {body.get('cadence', 'agent')} run"]
        for f in new_crit[:5]:
            lines.append("")
            lines.append("• " + str(f.get("title", ""))[:150])
            if f.get("detail"):
                lines.append("  " + str(f["detail"])[:300])
            if f.get("action"):
                lines.append("  → " + str(f["action"])[:200] +
                             (f" ({f['owner']})" if f.get("owner") else ""))
        lines.append("")
        lines.append("Full report: https://amanagrawal.cloud/reports")
        alert = _send_whatsapp("\n".join(lines))
        print("alert push:", alert)

    return {"stored": True, "report_id": (dict(rows[0])["id"] if rows else None),
            "intel_filed": filed, "counts": counts, "alert": alert}

@app.get("/api/agent/reports")
async def agent_reports_list(cadence: str | None = None, limit: int = 20):
    db = await vdb()
    q = "SELECT * FROM agent_reports WHERE 1=1"
    params: list = []
    if cadence: q += " AND cadence=?"; params.append(cadence.lower())
    q += " ORDER BY id DESC LIMIT ?"; params.append(min(int(limit), 100))
    rows = await db.execute_fetchall(q, params)
    return {"reports": [dict(r) for r in rows]}

@app.get("/api/agent/reports/{report_id}")
async def agent_report_get(report_id: int):
    db = await vdb()
    rows = await db.execute_fetchall("SELECT * FROM agent_reports WHERE id=?", (report_id,))
    return dict(rows[0]) if rows else {}

# _"__"_ Entities _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/entities")
async def entities(type: str | None = None):
    db = await vdb()
    q = "SELECT * FROM ans_entities WHERE 1=1"
    params: list = []
    if type: q += " AND entity_type=?"; params.append(type)
    q += " ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, name"
    rows = await db.execute_fetchall(q, params)
    return {"entities": [dict(r) for r in rows]}

@app.put("/api/entities/{entity_id}")
async def entity_update(entity_id: int, body: dict):
    db = await vdb()
    sets, params = [], []
    for k in ("business","location","directors","annual_turnover","status","notes","cin","gstin","pan"):
        if k in body:
            sets.append(f"{k}=?"); params.append(body[k])
    if sets:
        params.append(entity_id)
        await db.execute(f"UPDATE ans_entities SET {','.join(sets)} WHERE id=?", params)
        await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM ans_entities WHERE id=?", (entity_id,))
    return dict(rows[0]) if rows else {}

# _"__"_ Compliance _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/compliance/filings")
async def compliance_filings(entity: str | None = None, status: str | None = None):
    db = await vdb()
    q = "SELECT * FROM compliance_filings WHERE 1=1"
    params: list = []
    if entity: q += " AND entity_name=?"; params.append(entity)
    if status: q += " AND status=?";      params.append(status)
    q += " ORDER BY CASE status WHEN 'overdue' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, due_date ASC NULLS LAST"
    rows = await db.execute_fetchall(q, params)
    return {"filings": [dict(r) for r in rows]}

@app.put("/api/compliance/filings/{filing_id}")
async def compliance_filing_update(filing_id: int, body: dict):
    db = await vdb()
    sets, params = [], []
    for k in ("status","notes","filed_on","assigned_to","due_date"):
        if k in body:
            sets.append(f"{k}=?"); params.append(body[k])
    if body.get("status") == "filed":
        sets.append("filed_on=date('now')")
    if sets:
        sets.append("updated_at=datetime('now')")
        params.append(filing_id)
        await db.execute(f"UPDATE compliance_filings SET {','.join(sets)} WHERE id=?", params)
        await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM compliance_filings WHERE id=?", (filing_id,))
    return dict(rows[0]) if rows else {}

# _"__"_ Aditi Pools _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/aditi/pools")
async def aditi_pools():
    db = await vdb()
    rows = await db.execute_fetchall("SELECT * FROM aditi_pools ORDER BY pool_code")
    return {"pools": [dict(r) for r in rows]}

@app.put("/api/aditi/pools/{pool_code}")
async def aditi_pool_update(pool_code: str, body: dict):
    db = await vdb()
    sets, params = [], []
    for k in ("current_value","target_allocation","instruments","notes"):
        if k in body:
            sets.append(f"{k}=?"); params.append(body[k])
    if sets:
        sets.append("updated_at=datetime('now')")
        params.append(pool_code)
        await db.execute(f"UPDATE aditi_pools SET {','.join(sets)} WHERE pool_code=?", params)
        await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM aditi_pools WHERE pool_code=?", (pool_code,))
    return dict(rows[0]) if rows else {}

# _"__"_ VWLR (Vedanta CRM) _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/vwlr/tenders")
async def vwlr_tenders(buyer: str | None = None, hot: bool = False):
    try:
        conn = vedanta_conn()
        rows = conn.execute("SELECT * FROM tender_tracking ORDER BY due_date ASC").fetchall()
        tenders = [dict(r) for r in rows]
        if buyer: tenders = [t for t in tenders if buyer.lower() in str(t.get("buyer","")).lower()]
        if hot:   tenders = [t for t in tenders if float(t.get("eligibility_score",0) or 0) > 0.7]
        return {"tenders": tenders}
    except Exception as e:
        return {"tenders": [], "error": str(e)}

def _map_lead(r) -> dict:
    d = dict(r)
    # Normalise field name for frontend
    if "distance_from_vwlr" in d and "distance_km" not in d:
        d["distance_km"] = d.pop("distance_from_vwlr")
    return d

@app.get("/api/vwlr/leads")
async def vwlr_leads(priority: str | None = None):
    try:
        conn = vedanta_conn()
        q = "SELECT * FROM leads"
        params: list = []
        if priority: q += " WHERE priority=?"; params.append(priority)
        q += " ORDER BY CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, tender_score DESC"
        rows = conn.execute(q, params).fetchall()
        return {"leads": [_map_lead(r) for r in rows]}
    except Exception as e:
        return {"leads": [], "error": str(e)}

@app.get("/api/vwlr/followups")
async def vwlr_followups():
    try:
        conn = vedanta_conn()
        rows = conn.execute(
            "SELECT * FROM leads WHERE next_followup <= date('now', '+3 days') ORDER BY next_followup ASC LIMIT 20"
        ).fetchall()
        return {"leads": [_map_lead(r) for r in rows]}
    except Exception as e:
        return {"leads": [], "error": str(e)}

@app.get("/api/vwlr/bid")
async def vwlr_bid(buyer: str, volume: float, route: str, gate_price: float):
    FOIS = {"RAIGARH": 450, "BILASPUR": 520, "RAIPUR": 580, "NAGPUR": 680, "MUMBAI": 920}
    freight = FOIS.get(route.upper(), 600)
    discount = 0.02 if volume >= 10000 else (0.01 if volume >= 5000 else 0)
    landed = gate_price + freight
    bid = round(landed * (1 - 0.04), 2)
    margin = round((bid - landed) / bid * 100, 2)
    return {
        "buyer": buyer, "volume_mt": volume, "route": route, "gate_price": gate_price,
        "fois_freight": freight, "landed_cost": landed, "volume_discount_pct": discount * 100,
        "suggested_bid": bid, "margin_pct": margin,
        "total_revenue": round(bid * volume, 2), "total_margin": round((bid - landed) * volume, 2),
    }

@app.put("/api/vwlr/leads/{lead_id}")
async def vwlr_lead_update(lead_id: int, body: dict):
    try:
        conn = vedanta_conn()
        sets, params = [], []
        for k in ("status","priority","next_followup","notes","potential_volume"):
            if k in body: sets.append(f"{k}=?"); params.append(body[k])
        if sets:
            params.append(lead_id)
            conn.execute(f"UPDATE leads SET {','.join(sets)} WHERE id=?", params)
            conn.commit()
        row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        return dict(row) if row else {}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/vwlr/leads")
async def vwlr_lead_add(body: dict):
    try:
        conn = vedanta_conn()
        conn.execute(
            "INSERT INTO leads (company,contact_person,phone,location,distance_km,potential_volume,status,priority,next_followup,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (body.get("company",""), body.get("contact_person",""), body.get("phone",""),
             body.get("location",""), body.get("distance_km",0), body.get("potential_volume",""),
             body.get("status","prospect"), body.get("priority","Medium"),
             body.get("next_followup"), body.get("notes",""))
        )
        conn.commit()
        row = conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else {}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/vwlr/interactions")
async def vwlr_interactions(lead_id: int | None = None):
    db = await vdb()
    q = "SELECT * FROM vwlr_interactions WHERE 1=1"
    params: list = []
    if lead_id: q += " AND lead_id=?"; params.append(lead_id)
    q += " ORDER BY created_at DESC LIMIT 50"
    rows = await db.execute_fetchall(q, params)
    return {"interactions": [dict(r) for r in rows]}

@app.post("/api/vwlr/interactions")
async def vwlr_interaction_add(body: dict):
    db = await vdb()
    await db.execute(
        "INSERT INTO vwlr_interactions (lead_id,company,contact,type,notes,outcome,follow_up_date,created_by) VALUES (?,?,?,?,?,?,?,?)",
        (body.get("lead_id"), body.get("company",""), body.get("contact",""),
         body.get("type","call"), body.get("notes",""), body.get("outcome",""),
         body.get("follow_up_date"), body.get("created_by","Aman"))
    )
    await db.commit()
    return {"ok": True}

# _"__"_ VWLR tender pipeline (internal tracking) _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/vwlr/pipeline")
async def vwlr_pipeline(status: str | None = None):
    db = await vdb()
    q = "SELECT * FROM vwlr_tender_pipeline WHERE 1=1"
    params: list = []
    if status: q += " AND status=?"; params.append(status)
    q += " ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'evaluating' THEN 1 ELSE 2 END, due_date ASC NULLS LAST"
    rows = await db.execute_fetchall(q, params)
    return {"tenders": [dict(r) for r in rows]}

@app.post("/api/vwlr/tenders/add")
async def vwlr_pipeline_add(body: dict):
    db = await vdb()
    await db.execute(
        "INSERT INTO vwlr_tender_pipeline (buyer,volume_mt,category,due_date,status,url,notes,eligibility_score) VALUES (?,?,?,?,?,?,?,?)",
        (body.get("buyer",""), body.get("volume_mt",0), body.get("category","Other"),
         body.get("due_date"), body.get("status","active"),
         body.get("url",""), body.get("notes",""), body.get("eligibility_score",0.8))
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM vwlr_tender_pipeline ORDER BY id DESC LIMIT 1")
    return dict(rows[0]) if rows else {}

@app.put("/api/vwlr/pipeline/{tender_id}")
async def vwlr_pipeline_update(tender_id: int, body: dict):
    db = await vdb()
    sets, params = [], []
    for k in ("buyer","volume_mt","category","due_date","status","url","notes","eligibility_score"):
        if k in body: sets.append(f"{k}=?"); params.append(body[k])
    if sets:
        sets.append("updated_at=datetime('now')")
        params.append(tender_id)
        await db.execute(f"UPDATE vwlr_tender_pipeline SET {','.join(sets)} WHERE id=?", params)
        await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM vwlr_tender_pipeline WHERE id=?", (tender_id,))
    return dict(rows[0]) if rows else {}

# _"__"_ VWLR Competitors (legacy Vedanta CRM read — superseded by vwlr_competitors table below) _"__"__"__"__"__"__"__"__"_
# NOTE: endpoint kept for reference but route is overridden by the vwlr_competitors function further below.

# _"__"_ Hotel ANS _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/hotel/daily")
async def hotel_daily(days: int = 7):
    db = await vdb()
    rows = await db.execute_fetchall(
        "SELECT * FROM hotel_daily ORDER BY date DESC LIMIT ?", (days,)
    )
    records = [dict(r) for r in rows]
    records.reverse()  # chronological order
    return {"records": records}

@app.post("/api/hotel/daily")
async def hotel_daily_add(body: dict):
    db = await vdb()
    from datetime import date as dt
    date_str = body.get("date", dt.today().isoformat())
    occupied = int(body.get("occupied", 0))
    total_rooms = int(body.get("total_rooms", 30))
    rate = float(body.get("rate", 0))
    fnb = float(body.get("fnb_revenue", 0))
    occ_pct = round(occupied / total_rooms * 100, 1) if total_rooms > 0 else 0
    room_rev = occupied * rate
    total_rev = room_rev + fnb
    await db.execute("""
        INSERT INTO hotel_daily (date,total_rooms,occupied,rate,fnb_revenue,occupancy_pct,room_revenue,total_revenue,notes)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(date) DO UPDATE SET
          occupied=excluded.occupied, rate=excluded.rate,
          fnb_revenue=excluded.fnb_revenue, occupancy_pct=excluded.occupancy_pct,
          room_revenue=excluded.room_revenue, total_revenue=excluded.total_revenue,
          notes=excluded.notes
    """, (date_str, total_rooms, occupied, rate, fnb, occ_pct, room_rev, total_rev, body.get("notes","")))
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM hotel_daily WHERE date=?", (date_str,))
    return dict(rows[0]) if rows else {}

# _"__"_ Trading Signals (live in-app confirm/reject) _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/trading/signals")
async def trading_signals(status: str | None = None, limit: int = 20):
    db = await vdb()
    q = "SELECT * FROM trading_signals WHERE 1=1"
    params: list = []
    if status:
        q += " AND status=?"; params.append(status)
    else:
        q += " AND status IN ('pending','confirmed','executed')"
    q += " ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'confirmed' THEN 1 ELSE 2 END, created_at DESC LIMIT ?"
    params.append(limit)
    rows = await db.execute_fetchall(q, params)
    return {"signals": [dict(r) for r in rows]}

@app.post("/api/trading/signals")
async def trading_signal_add(body: dict):
    """Capital engine posts new signals here."""
    db = await vdb()
    from datetime import datetime, timedelta
    expires = (datetime.now() + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        """INSERT INTO trading_signals
           (ticker,action,instrument_type,entry_price,target_price,stop_loss,quantity,
            confidence,strategy,rationale,plain_english,status,pool,expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (body.get("ticker",""), body.get("action","BUY"),
         body.get("instrument_type","equity"),
         body.get("entry_price",0), body.get("target_price",0), body.get("stop_loss",0),
         body.get("quantity",1), body.get("confidence",60),
         body.get("strategy",""), body.get("rationale",""), body.get("plain_english",""),
         "pending", body.get("pool","B"), expires)
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM trading_signals ORDER BY id DESC LIMIT 1")
    return dict(rows[0]) if rows else {}

@app.post("/api/trading/signals/{sig_id}/confirm")
async def trading_confirm(sig_id: int):
    """User confirms trade from MDO app "" Capital engine executes."""
    db = await vdb()
    await db.execute(
        "UPDATE trading_signals SET status='confirmed', updated_at=datetime('now') WHERE id=? AND status='pending'",
        (sig_id,)
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM trading_signals WHERE id=?", (sig_id,))
    sig = dict(rows[0]) if rows else {}
    # Write to a trigger file that Capital engine polls
    try:
        trigger_path = BASE / "vega" / "data" / "pending_order.json"
        import json as _json
        with open(trigger_path, "w") as f:
            _json.dump(sig, f)
    except Exception:
        pass
    return sig

@app.post("/api/trading/signals/{sig_id}/reject")
async def trading_reject(sig_id: int):
    db = await vdb()
    await db.execute(
        "UPDATE trading_signals SET status='rejected', updated_at=datetime('now') WHERE id=?",
        (sig_id,)
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM trading_signals WHERE id=?", (sig_id,))
    return dict(rows[0]) if rows else {}

@app.post("/api/trading/signals/{sig_id}/execute")
async def trading_execute(sig_id: int, body: dict):
    """Called by Capital engine when order is placed. Updates status + execution price."""
    db = await vdb()
    executed_price = body.get("executed_price", 0)
    order_id = body.get("order_id", "")
    await db.execute(
        """UPDATE trading_signals SET status='executed', executed_price=?, order_id=?,
           executed_at=datetime('now'), updated_at=datetime('now') WHERE id=?""",
        (executed_price, order_id, sig_id)
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM trading_signals WHERE id=?", (sig_id,))
    return dict(rows[0]) if rows else {}

@app.put("/api/trading/signals/{sig_id}")
async def trading_signal_update(sig_id: int, body: dict):
    db = await vdb()
    sets, params = [], []
    for k in ("status","pnl","executed_price","order_id","plain_english","rationale"):
        if k in body: sets.append(f"{k}=?"); params.append(body[k])
    if sets:
        sets.append("updated_at=datetime('now')")
        params.append(sig_id)
        await db.execute(f"UPDATE trading_signals SET {','.join(sets)} WHERE id=?", params)
        await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM trading_signals WHERE id=?", (sig_id,))
    return dict(rows[0]) if rows else {}

# _"__"_ Feeds (stub "" needs Grok) _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/feeds/all")
async def feeds_all():
    return {"items": [], "count": 0, "sources": {"tender247": 0, "gem": 0, "npa": 0, "singhvi": 0}, "note": "Add GROK_API_KEY to .env for live feeds"}

@app.get("/api/feeds/tenders")
async def feeds_tenders():
    return {"items": [], "count": 0}

@app.get("/api/feeds/gem")
async def feeds_gem():
    return {"items": [], "count": 0}

@app.get("/api/feeds/npa")
async def feeds_npa():
    return {"items": [], "count": 0}

@app.get("/api/singhvi")
async def singhvi():
    return {"calls": [], "count": 0}

@app.post("/api/singhvi/refresh")
async def singhvi_refresh():
    return {"calls": [], "count": 0, "refreshed": False, "note": "Add GROK_API_KEY to .env for Singhvi live feed"}

@app.post("/api/grok/ask")
async def grok_ask(body: dict):
    return {"answer": "Grok AI requires a valid GROK_API_KEY in .env"}

# _"__"_ Market data "" Yahoo Finance _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/market/quote/{symbol}")
async def market_quote(symbol: str):
    """Fetch real-time quote from Yahoo Finance. symbol = e.g. COALINDIA.NS"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?interval=1d&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read())
        meta = data["chart"]["result"][0]["meta"]
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or meta.get("regularMarketPreviousClose", 0)
        cmp = meta.get("regularMarketPrice", 0)
        change = cmp - prev_close if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0
        fifty_two_week_low  = meta.get("fiftyTwoWeekLow", 0)
        fifty_two_week_high = meta.get("fiftyTwoWeekHigh", 0)
        return {
            "symbol": symbol,
            "cmp": round(cmp, 2),
            "prev_close": round(prev_close, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "52w_low": round(fifty_two_week_low, 2),
            "52w_high": round(fifty_two_week_high, 2),
            "market_cap": meta.get("marketCap", 0),
            "volume": meta.get("regularMarketVolume", 0),
            "updated": meta.get("regularMarketTime", 0),
        }
    except Exception as e:
        return {"symbol": symbol, "cmp": 0, "change": 0, "change_pct": 0, "error": str(e)}

@app.get("/api/market/watchlist")
async def market_watchlist():
    """Fetch all watchlist quotes. Returns list with business context."""
    import asyncio

    async def fetch_one(item: dict):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(item['symbol'])}?interval=1d&range=1d"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            loop = asyncio.get_event_loop()
            def _fetch():
                with urllib.request.urlopen(req, timeout=8) as r:
                    return _json.loads(r.read())
            data = await loop.run_in_executor(None, _fetch)
            meta = data["chart"]["result"][0]["meta"]
            prev = meta.get("chartPreviousClose") or meta.get("previousClose") or meta.get("regularMarketPreviousClose", 0)
            cmp  = meta.get("regularMarketPrice", 0)
            chg  = cmp - prev if prev else 0
            pct  = (chg / prev * 100) if prev else 0
            return {**item,
                "cmp": round(cmp, 2), "prev_close": round(prev, 2),
                "change": round(chg, 2), "change_pct": round(pct, 2),
                "52w_low": round(meta.get("fiftyTwoWeekLow", 0), 2),
                "52w_high": round(meta.get("fiftyTwoWeekHigh", 0), 2),
                "volume": meta.get("regularMarketVolume", 0),
            }
        except Exception as e:
            return {**item, "cmp": 0, "change": 0, "change_pct": 0, "error": str(e)}

    import asyncio
    tasks = [fetch_one(item) for item in WATCHLIST]
    results = await asyncio.gather(*tasks)
    return {"watchlist": list(results)}

@app.get("/api/market/indices")
async def market_indices():
    """Nifty 50, BankNifty, SGX Nifty, USD/INR from Yahoo Finance."""
    import asyncio
    symbols = [
        ("^NSEI",    "NIFTY 50"),
        ("^NSEBANK", "BANKNIFTY"),
        ("USDINR=X", "USD/INR"),
        ("^IXIC",    "NASDAQ"),
        ("^DJI",     "DOW JONES"),
    ]
    async def fetch_index(sym, label):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1d&range=1d"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            loop = asyncio.get_event_loop()
            def _f():
                with urllib.request.urlopen(req, timeout=8) as r:
                    return _json.loads(r.read())
            data = await loop.run_in_executor(None, _f)
            meta = data["chart"]["result"][0]["meta"]
            prev = meta.get("chartPreviousClose") or meta.get("previousClose") or meta.get("regularMarketPreviousClose", 0)
            cmp  = meta.get("regularMarketPrice", 0)
            chg  = cmp - prev if prev else 0
            pct  = (chg / prev * 100) if prev else 0
            return {"symbol": sym, "label": label, "value": round(cmp, 2),
                    "change": round(chg, 2), "change_pct": round(pct, 2)}
        except Exception as e:
            return {"symbol": sym, "label": label, "value": 0, "change": 0, "change_pct": 0, "error": str(e)}

    tasks = [fetch_index(s, l) for s, l in symbols]
    results = await asyncio.gather(*tasks)
    return {"indices": list(results)}

# _"__"_ Morning Briefing (Grok AI) _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@app.get("/api/briefing/today")
async def briefing_today(auto: int = 1):
    """Today's briefing. Generates it on first view of the day (auto=1) so the
    homepage is never empty — no button press required."""
    from datetime import date
    db = await vdb()
    today = date.today().isoformat()
    rows = await db.execute_fetchall(
        "SELECT * FROM morning_briefing WHERE date=? ORDER BY id DESC LIMIT 1", (today,))
    if rows:
        return {"briefing": dict(rows[0]), "fresh": True}
    if auto:
        try:
            gen = await briefing_generate()
            if gen.get("briefing"):
                return {"briefing": gen["briefing"], "fresh": True, "auto_generated": True}
        except Exception as e:
            print("auto-briefing failed:", e)
    return {"briefing": None, "fresh": False}

@app.get("/api/briefing/today/raw")
async def briefing_today_raw():
    """Return today's briefing from DB only — never generates."""
    db = await vdb()
    from datetime import date
    today = date.today().isoformat()
    rows = await db.execute_fetchall(
        "SELECT * FROM morning_briefing WHERE date=? ORDER BY id DESC LIMIT 1", (today,)
    )
    if rows:
        return {"briefing": dict(rows[0]), "fresh": True}
    return {"briefing": None, "fresh": False}

async def _briefing_context(db) -> dict:
    """Everything today's briefing should be built from — live, never invented."""
    from datetime import date
    today = date.today().isoformat()
    ctx: dict = {"date": today}

    ctx["overdue_filings"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT entity_name, filing_type, description, due_date, status FROM compliance_filings "
        "WHERE status IN ('overdue','pending') AND due_date IS NOT NULL AND due_date <= date('now','+14 days') "
        "ORDER BY due_date LIMIT 12")]
    ctx["open_tasks"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT title, entity, assigned_to, priority, due_date FROM ops_tasks "
        "WHERE status='open' AND category!='roadmap' "
        "ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, "
        "due_date ASC NULLS LAST LIMIT 12")]
    ctx["intel"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT urgency, entity, title FROM intel_items WHERE status='open' "
        "AND urgency IN ('CRITICAL','HIGH') ORDER BY CASE urgency WHEN 'CRITICAL' THEN 0 ELSE 1 END, "
        "created_at DESC LIMIT 10")]
    ctx["tenders"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT buyer, category, due_date, status, notes FROM vwlr_tender_pipeline "
        "ORDER BY due_date ASC NULLS LAST LIMIT 8")]
    ctx["wa_recent"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT group_name, sender, substr(text,1,180) AS text, timestamp FROM whatsapp_messages "
        "WHERE text != '[media]' AND created_at >= datetime('now','-1 day') "
        "ORDER BY id DESC LIMIT 40")]
    ctx["wa_activity"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT group_name, COUNT(*) AS n FROM whatsapp_messages "
        "WHERE created_at >= datetime('now','-1 day') GROUP BY group_name ORDER BY n DESC LIMIT 10")]
    ctx["agent_reports"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT cadence, title, summary, n_critical, n_important, created_at FROM agent_reports "
        "ORDER BY id DESC LIMIT 5")]
    ctx["blocked_checks"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT code, title, blocker FROM checks WHERE status='blocked'")]
    ctx["hotel"] = [dict(r) for r in await db.execute_fetchall(
        "SELECT date, occupied, total_rooms, occupancy_pct FROM hotel_daily ORDER BY date DESC LIMIT 3")]
    return ctx

def _briefing_fallback(ctx: dict) -> str:
    """Deterministic briefing from real records only — used when no LLM key is
    configured or the call fails. States gaps instead of inventing content."""
    lines = []
    crit = [i for i in ctx["intel"] if i["urgency"] == "CRITICAL"]
    if crit:
        lines.append("* CRITICAL: " + "; ".join(i["title"] for i in crit[:2]))
    od = [f for f in ctx["overdue_filings"] if f["status"] == "overdue"]
    if od:
        lines.append("* COMPLIANCE: " + str(len(od)) + " overdue filing(s) — " +
                     ", ".join(f"{f['entity_name']} {f['filing_type']} (due {f['due_date']})" for f in od[:2]))
    elif ctx["overdue_filings"]:
        lines.append("* COMPLIANCE: " + str(len(ctx["overdue_filings"])) + " filing(s) due within 14 days")
    if ctx["wa_activity"]:
        top = ctx["wa_activity"][0]
        lines.append("* SITE OPS: " + str(sum(g["n"] for g in ctx["wa_activity"])) +
                     " messages in last 24h; busiest " + top["group_name"] + " (" + str(top["n"]) + ")")
    else:
        lines.append("* SITE OPS: no WhatsApp messages in the last 24h — check the bridge is connected")
    if ctx["open_tasks"]:
        t = ctx["open_tasks"][0]
        lines.append("* TASKS: " + str(len(ctx["open_tasks"])) + " open — top: " + t["title"] +
                     (" (due " + str(t["due_date"]) + ")" if t.get("due_date") else ""))
    if ctx["blocked_checks"]:
        lines.append("* GAPS: no data source yet for " +
                     ", ".join(c["code"] for c in ctx["blocked_checks"][:4]))
    lines.append("* ACTION: add ANTHROPIC_API_KEY on the VPS for a written briefing — this is the raw-data fallback")
    return "\n".join(lines[:6])

def _briefing_llm(prompt: str) -> str:
    """Claude first, Grok fallback. Returns '' if neither is configured/works."""
    ant = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    grok = os.environ.get("GROK_API_KEY", "").strip()
    try:
        if ant:
            payload = _json.dumps({"model": "claude-sonnet-5", "max_tokens": 1200,
                                   "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=payload,
                headers={"x-api-key": ant, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=45) as r:
                resp = _json.loads(r.read())
            return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text").strip()
        if grok:
            payload = _json.dumps({"model": "grok-3-mini", "max_tokens": 1200,
                                   "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
            req = urllib.request.Request(
                "https://api.x.ai/v1/chat/completions", data=payload,
                headers={"Authorization": "Bearer " + grok, "Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=45) as r:
                resp = _json.loads(r.read())
            return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("briefing LLM failed:", str(e)[:200])
    return ""

@app.post("/api/briefing/generate")
async def briefing_generate():
    """Build today's briefing from live business data (Claude → Grok → facts)."""
    from datetime import date
    db = await vdb()
    today = date.today().isoformat()
    ctx = await _briefing_context(db)

    def block(title, rows, fmt):
        if not rows:
            return title + ": none\n"
        return title + ":\n" + "\n".join("- " + fmt(r) for r in rows) + "\n"

    prompt = (
        "You are Aman Agrawal's morning intelligence officer. He is a first-generation "
        "industrialist in Raigarh, Chhattisgarh running: VWLR coal washery (Kharsia, ~50% "
        "commissioning capacity, ₹34.55 Cr service pipeline), Hotel ANS International "
        "(88 rooms, ~23% occupancy), Aditi Investments (NSE cash + F&O), and ~26 group entities.\n\n"
        "TODAY IS " + today + ". Live data follows — this is everything the system knows.\n\n"
        + block("OPEN CRITICAL/HIGH INTEL", ctx["intel"], lambda r: f"[{r['urgency']}] {r['entity'] or '-'}: {r['title']}")
        + block("FILINGS DUE OR OVERDUE (next 14 days)", ctx["overdue_filings"],
                lambda r: f"{r['entity_name']} — {r['filing_type']} {r['description'] or ''} due {r['due_date']} ({r['status']})")
        + block("OPEN TASKS", ctx["open_tasks"],
                lambda r: f"[{r['priority']}] {r['title']} — {r['entity'] or '-'}, owner {r['assigned_to'] or '-'}, due {r['due_date'] or 'none'}")
        + block("TENDER PIPELINE", ctx["tenders"],
                lambda r: f"{r['buyer']} — {r['category'] or ''} due {r['due_date'] or 'TBD'} ({r['status']}) {r['notes'] or ''}")
        + block("WHATSAPP ACTIVITY (24h, by group)", ctx["wa_activity"], lambda r: f"{r['group_name']}: {r['n']} messages")
        + block("RECENT SITE MESSAGES", ctx["wa_recent"][:25], lambda r: f"[{r['group_name']}] {r['sender']}: {r['text']}")
        + block("HOTEL OCCUPANCY (latest records)", ctx["hotel"],
                lambda r: f"{r['date']}: {r['occupied']}/{r['total_rooms']} rooms ({r['occupancy_pct']}%)")
        + block("RECENT AGENT REPORTS", ctx["agent_reports"],
                lambda r: f"{r['cadence']} {r['created_at']}: {r['title']} — {r['summary'][:160]}")
        + block("CHECKS WITH NO DATA SOURCE YET", ctx["blocked_checks"], lambda r: f"{r['code']}: {r['blocker']}")
        + "\nWrite Aman's morning briefing as 5-7 bullet lines, each starting '* CATEGORY: '.\n"
        "Categories: CRITICAL, COMPLIANCE, SITE OPS, TENDERS, HOTEL, CAPITAL, ACTION.\n"
        "Rules — these are absolute:\n"
        "- NEVER invent a number or a fact. Only use what appears above. If a domain has no data, "
        "say so plainly (e.g. 'HOTEL: no occupancy data — source not connected') rather than guessing.\n"
        "- Lead with whatever genuinely matters most today, not a fixed order.\n"
        "- Be specific: name entities, amounts (lakh/crore), dates, group names.\n"
        "- Note where a date looks stale (data seeded April 2026) rather than treating it as current.\n"
        "- Last line is always '* ACTION: ' with the single most valuable thing he should do today.\n"
        "- No preamble, no greeting, no closing remark. Just the bullets."
    )

    content = _briefing_llm(prompt).strip()
    if not content or "* " not in content:
        content = _briefing_fallback(ctx)

    await db.execute(
        "INSERT OR REPLACE INTO morning_briefing (date, content, generated_at) VALUES (?,?,datetime('now'))",
        (today, content)
    )
    await db.commit()
    rows = await db.execute_fetchall(
        "SELECT * FROM morning_briefing WHERE date=? ORDER BY id DESC LIMIT 1", (today,))
    return {"briefing": dict(rows[0]) if rows else {"date": today, "content": content}}

# ── WhatsApp Bridge ──────────────────────────────────────────────────────────

HOTEL_TOTAL_ROOMS = 88  # Hotel ANS International (MDO_VISION §2B)

# ── Vision: read the photos, not just the text ──────────────────────────────
# ~27% of WhatsApp traffic is images — weighbridge slips, dispatch tallies,
# hotel sales registers, machine faults. Without this the agents are blind to
# the numbers that matter most. Vision runs only on groups likely to carry
# reports (every image would be costly and mostly noise); set VISION_GROUPS=*
# to process everything.
VISION_ENABLED = os.environ.get("VISION_ENABLED", "1").strip() not in ("0", "false", "")
VISION_GROUPS = [g.strip().lower() for g in os.environ.get(
    "VISION_GROUPS",
    "daily sales report,night report,dsr,rake,dispatch,weighbridge,w/b,loading,"
    "loader,machine,civil,washery,report,accounts,payment,purchase,store"
).split(",") if g.strip()]
VISION_MODEL = os.environ.get("VISION_MODEL", "claude-sonnet-5")

def _vision_group_match(group: str) -> bool:
    if not VISION_ENABLED:
        return False
    if "*" in VISION_GROUPS:
        return True
    g = re.sub(r"[^a-z0-9]+", " ", group.lower())
    return any(k in g for k in VISION_GROUPS)

def _vision_extract(image_b64: str, mime: str, group: str, caption: str) -> dict:
    """Ask Claude what the image says. Returns {} on any failure — a missed
    extraction must never become an invented one."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return {}
    prompt = (
        "This image was posted in the WhatsApp group \"" + group + "\" of an Indian "
        "industrial group (coal washery + railway siding at Raigarh CG, and an 88-room hotel).\n"
        + (f"Caption: {caption}\n" if caption and caption != "[media]" else "")
        + "It is likely one of: a weighbridge slip, a rake/dispatch tally, a daily sales or "
        "occupancy register, a machine/fault log, an invoice or payment advice, a purchase "
        "order, or a site photograph.\n\n"
        "Return ONLY a JSON object:\n"
        '{"doc_type":"weighbridge_slip|dispatch_report|sales_report|occupancy_report|'
        'machine_log|invoice|payment|purchase_order|site_photo|other",\n'
        ' "summary":"one line a busy owner would want",\n'
        ' "text":"all legible text, preserving numbers and labels",\n'
        ' "fields":{"any labelled values you can read, e.g. vehicle_no, gross_wt, tare_wt, '
        'net_wt, rake_no, qty_mt, rooms_sold, occupancy_pct, revenue, amount, date, party"}}\n'
        "Transcribe only what is actually legible. Never guess a digit — if a value is "
        "unclear or cut off, omit the field entirely. If the image is a photo with no "
        "readable data, set doc_type to site_photo and describe it in summary."
    )
    try:
        payload = _json.dumps({
            "model": VISION_MODEL, "max_tokens": 1500,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": image_b64}},
                {"type": "text", "text": prompt},
            ]}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=payload,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = _json.loads(r.read())
        txt = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
        s, e = txt.find("{"), txt.rfind("}") + 1
        return _json.loads(txt[s:e]) if s >= 0 and e > s else {}
    except Exception as ex:
        print("vision failed:", str(ex)[:200])
        return {}

async def _process_image(msg_id: int, group: str, sender: str, timestamp: str,
                         image_b64: str, mime: str, caption: str):
    """Background: extract, store, and let the hotel parser see the result."""
    import asyncio as _aio
    out = await _aio.to_thread(_vision_extract, image_b64, mime, group, caption)
    if not out:
        return
    db = await vdb()
    text = (out.get("text") or "").strip()
    summary = (out.get("summary") or "").strip()
    await db.execute(
        """INSERT INTO media_extractions
           (message_id, group_name, sender, doc_type, summary, extracted_text, fields_json, timestamp)
           VALUES (?,?,?,?,?,?,?,?)""",
        (msg_id, group[:200], sender[:100], str(out.get("doc_type", "other"))[:40],
         summary[:1000], text[:8000], _json.dumps(out.get("fields") or {})[:4000], timestamp[:50]))
    # Replace the useless "[media]" placeholder so every downstream reader —
    # agents, briefing, Brain, ops feed — sees the content.
    if msg_id:
        await db.execute(
            "UPDATE whatsapp_messages SET text=? WHERE id=? AND text='[media]'",
            (("[image] " + (summary or text))[:2000], msg_id))
    await db.commit()

    combined = " ".join(filter(None, [caption if caption != "[media]" else "", summary, text]))
    if any(k in re.sub(r"[^a-z0-9]+", " ", group.lower()) for k in HOTEL_REPORT_GROUPS):
        parsed = _parse_night_report(combined)
        if parsed:
            date_str = _night_report_date(timestamp)
            note = f"auto: WhatsApp image ({sender[:40]})"
            cur = await db.execute(
                "UPDATE hotel_daily SET occupied=?, total_rooms=?, occupancy_pct=?, notes=? WHERE date=?",
                (parsed["occupied"], parsed["total"], parsed["pct"], note, date_str))
            if cur.rowcount == 0:
                await db.execute(
                    "INSERT INTO hotel_daily (date,total_rooms,occupied,occupancy_pct,notes) VALUES (?,?,?,?,?)",
                    (date_str, parsed["total"], parsed["occupied"], parsed["pct"], note))
            await db.commit()
            print(f"vision → hotel_daily {date_str}: {parsed}")
# WhatsApp groups whose messages carry the hotel's daily figures. Matched on a
# punctuation-insensitive substring, so "Daily Sales Report" also catches
# "DAILY SALES REPORT - HOTEL". Confirmed by Aman 31-Jul-2026.
HOTEL_REPORT_GROUPS = ("daily sales report", "night report", "dsr")

def _parse_night_report(text: str) -> dict | None:
    """Extract occupancy from a hotel night-report WhatsApp message.

    Conservative: returns None unless an explicit occupied-count or
    occupancy-% is present. Handles '34/88', 'rooms sold: 34',
    'occupied rooms - 34', 'occupancy 38.6%'.
    """
    t = text.lower()
    occupied = total = pct = None
    m = re.search(r"\b(\d{1,3})\s*/\s*(\d{2,3})\b", t)
    if m and 40 <= int(m.group(2)) <= 150 and int(m.group(1)) <= int(m.group(2)):
        occupied, total = int(m.group(1)), int(m.group(2))
    if occupied is None:
        m = re.search(r"(?:rooms?\s*(?:sold|occupied|occ)\w*|(?:occupied|occ\w*|sold)\s*rooms?)\s*[:\-–=]?\s*(\d{1,3})\b", t)
        if m:
            occupied = int(m.group(1))
    m = re.search(r"occupanc\w*\s*[:\-–=]?\s*(\d{1,3}(?:\.\d+)?)\s*%", t)
    if m:
        pct = float(m.group(1))
    if occupied is None and pct is None:
        return None
    total = total or HOTEL_TOTAL_ROOMS
    if occupied is not None and occupied > total:
        return None
    if pct is None:
        pct = round(occupied * 100.0 / total, 1)
    if occupied is None:
        occupied = round(pct * total / 100)
    if not (0 <= pct <= 100):
        return None
    return {"occupied": occupied, "total": total, "pct": pct}

def _night_report_date(timestamp: str) -> str:
    """A night report sent before 6 AM IST covers the previous hotel day."""
    from datetime import datetime, timedelta, timezone
    try:
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        ts = datetime.now(timezone.utc)
    ist = ts.astimezone(timezone(timedelta(hours=5, minutes=30)))
    day = ist.date() - timedelta(days=1) if ist.hour < 6 else ist.date()
    return day.isoformat()

@app.post("/api/whatsapp/message")
async def whatsapp_message(body: dict):
    """Receives messages forwarded from the WhatsApp bridge."""
    db = await vdb()
    group = str(body.get("group", ""))[:200]
    text = str(body.get("text", ""))[:2000]
    timestamp = str(body.get("timestamp", ""))[:50]
    sender = str(body.get("sender", ""))[:100]
    await db.execute(
        "INSERT INTO whatsapp_messages (group_name, sender, text, timestamp, jid) VALUES (?,?,?,?,?)",
        (group, sender, text, timestamp, str(body.get("jid", ""))[:100])
    )
    await db.commit()
    msg_id = None
    rows = await db.execute_fetchall("SELECT last_insert_rowid() AS id")
    if rows:
        msg_id = dict(rows[0])["id"]

    # Image → vision extraction, in the background so the bridge isn't blocked
    img = body.get("image_b64")
    if img and _vision_group_match(group):
        asyncio.create_task(_process_image(
            msg_id, group, sender, timestamp, img,
            str(body.get("image_mime") or "image/jpeg"), text))

    # Hotel daily/night report → parse occupancy straight into hotel_daily
    _g = re.sub(r"[^a-z0-9]+", " ", group.lower())
    if any(k in _g for k in HOTEL_REPORT_GROUPS):
        parsed = _parse_night_report(text)
        if parsed:
            date_str = _night_report_date(timestamp)
            note = f"auto: WhatsApp night report ({str(body.get('sender',''))[:40]})"
            cur = await db.execute(
                "UPDATE hotel_daily SET occupied=?, total_rooms=?, occupancy_pct=?, notes=? WHERE date=?",
                (parsed["occupied"], parsed["total"], parsed["pct"], note, date_str),
            )
            if cur.rowcount == 0:
                await db.execute(
                    "INSERT INTO hotel_daily (date,total_rooms,occupied,occupancy_pct,notes) VALUES (?,?,?,?,?)",
                    (date_str, parsed["total"], parsed["occupied"], parsed["pct"], note),
                )
            await db.commit()
            return {"received": True, "hotel_daily": date_str, **parsed}

    return {"received": True}

@app.post("/api/whatsapp/status")
async def whatsapp_status_update(body: dict):
    return {"ok": True}

@app.get("/api/whatsapp/qr")
async def whatsapp_qr(account: str = "1"):
    """Proxy QR code from a WhatsApp bridge (account 1 or 2) to avoid CORS issues."""
    env_key = "WA_BRIDGE2_URL" if account == "2" else "WA_BRIDGE_URL"
    wa_url = os.environ.get(env_key, "")
    if not wa_url:
        return {"connected": False, "qr": None, "message": f"{env_key} not set"}
    try:
        req = urllib.request.Request(wa_url.rstrip("/") + "/api/whatsapp/qr")
        with urllib.request.urlopen(req, timeout=8) as r:
            return _json.loads(r.read())
    except Exception as e:
        return {"connected": False, "qr": None, "message": str(e)}

@app.get("/api/whatsapp/extractions")
async def whatsapp_extractions(group: str = "", doc_type: str = "", limit: int = 50):
    """What the images said — weighbridge slips, tallies, registers, invoices."""
    db = await vdb()
    q = "SELECT * FROM media_extractions WHERE 1=1"
    params: list = []
    if group:    q += " AND group_name LIKE ?"; params.append(f"%{group}%")
    if doc_type: q += " AND doc_type=?";        params.append(doc_type)
    q += " ORDER BY id DESC LIMIT ?"; params.append(min(int(limit), 200))
    rows = await db.execute_fetchall(q, params)
    out = [dict(r) for r in rows]
    for r in out:
        try:
            r["fields"] = _json.loads(r.pop("fields_json") or "{}")
        except Exception:
            r["fields"] = {}
    return {"extractions": out, "count": len(out)}

@app.get("/api/whatsapp/messages")
async def whatsapp_messages(group: str = "", limit: int = 100):
    db = await vdb()
    if group:
        async with db.execute(
            "SELECT * FROM whatsapp_messages WHERE group_name LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{group}%", limit)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute(
            "SELECT * FROM whatsapp_messages ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return {"messages": rows, "count": len(rows)}

@app.get("/api/whatsapp/groups")
async def whatsapp_groups():
    db = await vdb()
    async with db.execute(
        "SELECT group_name, COUNT(*) as msg_count, MAX(timestamp) as last_msg FROM whatsapp_messages GROUP BY group_name ORDER BY last_msg DESC"
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    return {"groups": rows}

# ── VWLR Competitors ─────────────────────────────────────────────────────────

@app.get("/api/vwlr/competitors")
async def vwlr_competitors():
    db = await vdb()
    async with db.execute("SELECT * FROM vwlr_competitors ORDER BY name") as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    return {"competitors": rows}

@app.put("/api/vwlr/competitors/{comp_id}")
async def vwlr_competitor_update(comp_id: int, body: dict):
    db = await vdb()
    fields = {k: v for k, v in body.items() if k in ("tenders_won","tenders_tracked","last_seen","notes","location","type")}
    if not fields:
        raise HTTPException(400, "No valid fields")
    sets = ", ".join(k + "=?" for k in fields)
    await db.execute(f"UPDATE vwlr_competitors SET {sets} WHERE id=?", (*fields.values(), comp_id))
    await db.commit()
    return {"id": comp_id, "updated": True}

# ── Singhvi Calls ────────────────────────────────────────────────────────────

@app.get("/api/singhvi/today")
async def singhvi_today():
    db = await vdb()
    today = __import__("datetime").date.today().isoformat()
    async with db.execute(
        "SELECT * FROM singhvi_calls WHERE date=? ORDER BY created_at DESC", (today,)
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    return {"calls": rows, "date": today}

@app.post("/api/singhvi/calls")
async def singhvi_add_call(body: dict):
    db = await vdb()
    today = __import__("datetime").date.today().isoformat()
    await db.execute(
        """INSERT INTO singhvi_calls
           (date, ticker, exchange, instrument, direction, entry_price, stop_loss,
            target_price, quantity, timeframe, notes, source, raw_text, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            today,
            str(body.get("ticker", "")).upper(),
            str(body.get("exchange", "NSE")),
            str(body.get("instrument", "EQ")),
            str(body.get("direction", "BUY")),
            float(body.get("entry_price", 0) or 0),
            float(body.get("stop_loss", 0) or 0),
            float(body.get("target_price", 0) or 0),
            int(body.get("quantity", 1) or 1),
            str(body.get("timeframe", "Intraday")),
            str(body.get("notes", "")),
            str(body.get("source", "manual")),
            str(body.get("raw_text", "")),
            str(body.get("status", "pending")),
        )
    )
    await db.commit()
    async with db.execute("SELECT last_insert_rowid() as id") as cur:
        row = await cur.fetchone()
    return {"id": row["id"], "status": "created"}

@app.post("/api/singhvi/calls/{call_id}/approve")
async def singhvi_approve(call_id: int):
    db = await vdb()
    await db.execute("UPDATE singhvi_calls SET status='approved' WHERE id=?", (call_id,))
    await db.commit()
    return {"id": call_id, "status": "approved"}

@app.post("/api/singhvi/calls/{call_id}/reject")
async def singhvi_reject(call_id: int):
    db = await vdb()
    await db.execute("UPDATE singhvi_calls SET status='rejected' WHERE id=?", (call_id,))
    await db.commit()
    return {"id": call_id, "status": "rejected"}

@app.delete("/api/singhvi/calls/{call_id}")
async def singhvi_delete(call_id: int):
    db = await vdb()
    await db.execute("DELETE FROM singhvi_calls WHERE id=?", (call_id,))
    await db.commit()
    return {"id": call_id, "deleted": True}

# Progress is tracked so the app (and you, via curl) can watch the pipeline.
_singhvi_status = {"state": "idle", "detail": "", "updated": ""}

def _sstat(state: str, detail: str = ""):
    import datetime as _dt
    _singhvi_status.update({
        "state": state, "detail": detail,
        "updated": _dt.datetime.now().isoformat(timespec="seconds"),
    })
    print(f"Singhvi[{state}] {detail}")

@app.post("/api/singhvi/extract")
async def singhvi_extract(body: dict | None = None):
    """Trigger the yt-dlp → faster-whisper → LLM pipeline in a background thread.

    Default: capture the Zee Business LIVE stream (use during 8:00–9:15 AM IST).
    Test mode: pass {"url": "<any past YouTube video>"} to run the identical
    pipeline on recorded video — verifies everything end-to-end off-hours.
    Optional {"seconds": N} sets capture length (default 600)."""
    body = body or {}
    url = str(body.get("url", "") or "")
    seconds = min(int(body.get("seconds", 600) or 600), 1800)
    if _singhvi_status["state"] in ("downloading", "transcribing", "extracting"):
        return {"started": False, "message": "Extraction already running", "status": _singhvi_status}
    import threading
    threading.Thread(target=_extract_singhvi_calls, args=(url, seconds), daemon=True).start()
    return {"started": True, "message": "Extraction started — poll /api/singhvi/extract/status"}

@app.get("/api/singhvi/extract/status")
async def singhvi_extract_status():
    return _singhvi_status

def _singhvi_llm_extract(transcript: str):
    """Transcript → list of structured calls. Claude first, Grok fallback."""
    import json as _j
    prompt = (
        "Extract every stock/futures/options call from this Zee Business / Anil Singhvi "
        "transcript (Hindi/Hinglish). Return ONLY a JSON array. Each object:\n"
        "  ticker (NSE symbol, uppercase), direction (BUY/SELL/AVOID),\n"
        "  entry_price (number or 0), stop_loss (number or 0), target_price (number or 0),\n"
        "  instrument (EQ/FUT/OPT-CE/OPT-PE), timeframe (Intraday/Swing/Positional),\n"
        "  confidence (0-100), raw_quote (the exact transcript words backing the call).\n"
        "Do NOT invent prices — 0 when not stated. If no calls, return [].\n"
        "Transcript:\n" + transcript[:12000]
    )
    ant_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    grok_key = os.environ.get("GROK_API_KEY", "").strip()
    try:
        if ant_key:
            payload = _j.dumps({
                "model": "claude-sonnet-5", "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=payload,
                headers={"x-api-key": ant_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=90) as r:
                resp = _j.loads(r.read())
            text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
        elif grok_key:
            payload = _j.dumps({
                "model": "grok-3-mini", "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.x.ai/v1/chat/completions", data=payload,
                headers={"Authorization": "Bearer " + grok_key,
                         "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=90) as r:
                resp = _j.loads(r.read())
            text = resp["choices"][0]["message"]["content"].strip()
        else:
            _sstat("error", "no ANTHROPIC_API_KEY or GROK_API_KEY configured")
            return None
        start = text.find("[")
        end = text.rfind("]") + 1
        if start < 0 or end <= start:
            _sstat("error", "LLM returned no JSON array: " + text[:150])
            return None
        return _j.loads(text[start:end])
    except Exception as e:
        _sstat("error", "LLM extraction failed: " + str(e)[:250])
        return None

def _extract_singhvi_calls(src_url: str = "", capture_seconds: int = 600):
    """Audio (live capture or test URL) → Hindi transcript → structured calls → DB."""
    import subprocess, tempfile, os as _os, json as _j, sqlite3, datetime as _dt
    audio_path = tempfile.mktemp(suffix=".mp3")
    try:
        live = not src_url
        target = src_url or "https://www.youtube.com/@ZeeBusiness/live"
        _sstat("downloading", f"live capture {capture_seconds}s" if live else target)
        r = None
        if live:
            # Resolve the live stream manifest, then record N seconds with ffmpeg.
            # (yt-dlp downloading a live stream directly never terminates.)
            g = subprocess.run(["yt-dlp", "-g", "-f", "bestaudio/best", "--no-warnings", target],
                               capture_output=True, text=True, timeout=90)
            stream = (g.stdout or "").strip().splitlines()
            if not stream:
                _sstat("error", "no live stream right now: " + (g.stderr or "")[-200:])
                return
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", stream[0], "-t", str(capture_seconds),
                 "-vn", "-acodec", "libmp3lame", "-ar", "16000", "-ac", "1", audio_path],
                capture_output=True, timeout=capture_seconds + 180)
        else:
            section = "*00:00-" + str(_dt.timedelta(seconds=capture_seconds))
            r = subprocess.run(
                ["yt-dlp", "--no-playlist", "-x", "--audio-format", "mp3",
                 "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
                 "--download-sections", section,
                 "-o", audio_path, "--force-overwrites", "--no-warnings", target],
                capture_output=True, timeout=1200)
        if not _os.path.exists(audio_path) or _os.path.getsize(audio_path) < 10_000:
            err = ""
            if r is not None and r.stderr:
                err = (r.stderr.decode() if isinstance(r.stderr, bytes) else str(r.stderr))[-300:]
            _sstat("error", "no audio produced. " + err)
            return
        _sstat("transcribing", f"{_os.path.getsize(audio_path)//1024} KB audio (first run downloads the Whisper model, ~1 min extra)")
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(audio_path, language="hi", beam_size=1, vad_filter=True)
        transcript = " ".join(seg.text for seg in segments).strip()
        if len(transcript) < 50:
            _sstat("error", f"transcript too short ({len(transcript)} chars) — silent audio?")
            return
        _sstat("extracting", f"{len(transcript)} chars of transcript → LLM")
        calls = _singhvi_llm_extract(transcript)
        if calls is None:
            return  # error state already set
        today = _dt.date.today().isoformat()
        conn = sqlite3.connect(VEGA_DB)
        for c in calls:
            conn.execute(
                """INSERT INTO singhvi_calls
                   (date,ticker,exchange,instrument,direction,entry_price,stop_loss,
                    target_price,timeframe,notes,source,raw_text,status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    today,
                    str(c.get("ticker", "")).upper(),
                    "NSE",
                    str(c.get("instrument", "EQ")),
                    str(c.get("direction", "BUY")),
                    float(c.get("entry_price", 0) or 0),
                    float(c.get("stop_loss", 0) or 0),
                    float(c.get("target_price", 0) or 0),
                    str(c.get("timeframe", "Intraday")),
                    "Confidence: " + str(c.get("confidence", "—")) + "%",
                    "youtube" if live else "youtube-test",
                    str(c.get("raw_quote", ""))[:500],
                    "pending",
                )
            )
        conn.commit()
        conn.close()
        _sstat("done", f"inserted {len(calls)} calls — review in Morning Setup")
    except subprocess.TimeoutExpired:
        _sstat("error", "audio download timed out")
    except Exception as ex:
        _sstat("error", str(ex)[:300])
    finally:
        try:
            _os.unlink(audio_path)
        except Exception:
            pass

@app.post("/api/singhvi/execute")
async def singhvi_execute():
    """Move all approved singhvi_calls to trading_signals for HDFC execution."""
    db = await vdb()
    today = __import__("datetime").date.today().isoformat()
    async with db.execute(
        "SELECT * FROM singhvi_calls WHERE date=? AND status='approved'", (today,)
    ) as cur:
        approved = [dict(r) for r in await cur.fetchall()]

    inserted = []
    for c in approved:
        await db.execute(
            """INSERT INTO trading_signals
               (ticker, action, instrument_type, entry_price, target_price, stop_loss,
                quantity, strategy, rationale, status)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                c["ticker"], c["direction"], c["instrument"],
                c["entry_price"], c["target_price"], c["stop_loss"],
                c["quantity"], "singhvi",
                "Singhvi call: " + (c["notes"] or c["raw_text"] or "")[:200],
                "pending",
            )
        )
        await db.execute(
            "UPDATE singhvi_calls SET status='executed' WHERE id=?", (c["id"],)
        )
        inserted.append(c["ticker"])
    await db.commit()
    return {"executed": len(inserted), "tickers": inserted}

# ── HDFC Auth ────────────────────────────────────────────────────────────────

# Credentials live ONLY in .env — never hardcode them here (they end up in git).
HDFC_CLIENT_ID     = os.environ.get("HDFC_CLIENT_ID", "45889297")
HDFC_API_KEY_VAL   = os.environ.get("HDFC_API_KEY", "")
HDFC_API_SECRET    = os.environ.get("HDFC_API_SECRET", "")
HDFC_REDIRECT_URL  = os.environ.get("HDFC_REDIRECT_URL", "https://api.amanagrawal.cloud/api/hdfc/callback")
HDFC_AUTH_BASE     = "https://developer.hdfcsec.com"

@app.get("/api/hdfc/status")
async def hdfc_status():
    db = await vdb()
    async with db.execute("SELECT * FROM hdfc_session ORDER BY id DESC LIMIT 1") as cur:
        row = await cur.fetchone()
    if not row or not row["connected"]:
        return {"connected": False}
    return {
        "connected": bool(row["connected"]),
        "client_id": row["client_id"],
        "available_margin": row["available_margin"],
        "token_expiry": row["token_expiry"],
    }

@app.post("/api/hdfc/auth/init")
async def hdfc_auth_init():
    """Return the HDFC OAuth login URL for the user to complete in browser."""
    if not HDFC_API_KEY_VAL or not HDFC_API_SECRET:
        raise HTTPException(400, "HDFC_API_KEY / HDFC_API_SECRET not set in .env on the VPS")
    import urllib.parse as _up
    # InvestRight Individual API lives under /oapi/v1/ (confirmed base path);
    # the login page takes the key as api_key and redirects back to the URL
    # registered in the developer portal.
    login_url = HDFC_AUTH_BASE + "/oapi/v1/login?" + _up.urlencode({"api_key": HDFC_API_KEY_VAL})
    return {"login_url": login_url, "client_id": HDFC_CLIENT_ID}

def _hdfc_try_exchange(code: str) -> dict:
    """Try the token exchange against the endpoint/payload shapes InvestRight
    is known to use, in order. Returns the parsed JSON of the first success;
    raises with ALL failure details otherwise (they show on the callback page
    so the exact mismatch is visible)."""
    import urllib.parse as _up
    attempts = [
        (HDFC_AUTH_BASE + "/oapi/v1/access-token?" + _up.urlencode({"api_key": HDFC_API_KEY_VAL}),
         {"apiSecret": HDFC_API_SECRET, "requestToken": code}),
        (HDFC_AUTH_BASE + "/oapi/v1/access-token",
         {"api_key": HDFC_API_KEY_VAL, "api_secret": HDFC_API_SECRET, "request_token": code}),
        (HDFC_AUTH_BASE + "/oapi/v1/access-token?" + _up.urlencode({"api_key": HDFC_API_KEY_VAL}),
         {"apiSecret": HDFC_API_SECRET, "tokenId": code}),
        (HDFC_AUTH_BASE + "/oauth2/token",
         {"apiKey": HDFC_API_KEY_VAL, "apiSecret": HDFC_API_SECRET, "code": code}),
    ]
    errors = []
    for url, body in attempts:
        try:
            req = urllib.request.Request(
                url, data=_json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = _json.loads(r.read())
            token = (resp.get("access_token") or resp.get("accessToken")
                     or resp.get("token") or (resp.get("data") or {}).get("access_token", ""))
            if token:
                resp["_token"] = token
                return resp
            errors.append(f"{url} → 200 but no token field: {str(resp)[:200]}")
        except Exception as e:
            errors.append(f"{url} → {str(e)[:200]}")
    raise RuntimeError("all exchange attempts failed:\n" + "\n".join(errors))

async def _hdfc_store_token(code: str) -> dict:
    """Exchange an auth code/request token for an access token and persist it."""
    resp = _hdfc_try_exchange(code)
    token = resp["_token"]
    expiry = resp.get("expires_in", 86400)
    import datetime as _dtt
    expiry_str = (_dtt.datetime.now() + _dtt.timedelta(seconds=expiry)).isoformat()

    db = await vdb()
    await db.execute("DELETE FROM hdfc_session")
    await db.execute(
        "INSERT INTO hdfc_session (access_token,token_expiry,connected,client_id) VALUES (?,?,1,?)",
        (token, expiry_str, HDFC_CLIENT_ID)
    )
    await db.commit()
    return {"connected": True, "expiry": expiry_str}

@app.post("/api/hdfc/auth/callback")
async def hdfc_auth_callback(body: dict):
    """Exchange auth code for access token and store in DB (app-initiated)."""
    code = body.get("code", "")
    if not code:
        raise HTTPException(400, "Missing code")
    try:
        return await _hdfc_store_token(code)
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/hdfc/callback")
async def hdfc_oauth_redirect(request: Request, code: str = "", request_token: str = "",
                              requestToken: str = "", tokenid: str = "", tokenId: str = ""):
    """Browser lands here after HDFC login + OTP. Exempt from the access key.

    Since the merge there are two callback handlers, and they arm different things:
    this one writes MDO's own `hdfc_session` table (used by /api/hdfc/funds), while
    Shares CFO's /hdfc/callback arms `token_store` — the store that makes /accounts
    report logged_in and every capital number flow.

    Registering the wrong one fails silently in the nastiest way: this page paints a
    green tick while the broker sessions stay logged out. So when a public Shares CFO
    URL is configured we hand the request token straight over rather than spending it
    here — the token is single-use, so it must be exchanged exactly once, by the
    service that actually needs the session.
    """
    from starlette.responses import HTMLResponse, RedirectResponse
    print("HDFC callback query:", str(request.query_params))  # shows the real param name in logs

    cfo_public = os.environ.get("CFO_PUBLIC_URL", "").strip().rstrip("/")
    if cfo_public:
        qs = str(request.url.query)
        return RedirectResponse(
            f"{cfo_public}/hdfc/callback" + (f"?{qs}" if qs else ""), status_code=307)

    tok = code or request_token or requestToken or tokenid or tokenId
    if not tok and len(request.query_params) == 1:
        tok = next(iter(request.query_params.values()))  # single unknown param — take it
    page = (
        "<html><body style=\"font-family:system-ui,sans-serif;background:#07080d;"
        "color:#e7ebf4;display:flex;align-items:center;justify-content:center;"
        "height:100vh;margin:0\"><div style=\"text-align:center\">{inner}</div></body></html>"
    )
    if not tok:
        return HTMLResponse(page.format(inner="<h2 style='color:#f87171'>HDFC callback: no auth code received</h2><p>Check the redirect URL registered in the HDFC developer portal.</p>"), status_code=400)
    try:
        res = await _hdfc_store_token(tok)
        return HTMLResponse(page.format(inner=(
            "<h2 style='color:#34d399'>✓ HDFC connected</h2>"
            f"<p>Token valid until {res.get('expiry','')}</p>"
            "<p>Return to the MDO app → Morning Setup.</p>"
            "<p style='color:#fbbf24;max-width:460px;font-size:14px'>Note: this armed "
            "MDO's own session only. The consolidated book, positions and exposure read "
            "from Shares CFO, which was not armed by this callback. Set "
            "<code>CFO_PUBLIC_URL</code> so this redirect hands over to it, or register "
            "<code>&lt;shares-cfo-host&gt;/hdfc/callback</code> in the HDFC portal instead.</p>"
        )))
    except Exception as e:
        return HTMLResponse(page.format(inner=(
            "<h2 style='color:#f87171'>HDFC token exchange failed</h2>"
            f"<pre style='color:#8b93ab;white-space:pre-wrap;max-width:480px'>{str(e)[:400]}</pre>"
            "<p>Send this error to Claude — likely an endpoint-shape mismatch we can fix in minutes.</p>"
        )), status_code=502)

@app.get("/api/hdfc/funds")
async def hdfc_funds():
    db = await vdb()
    async with db.execute("SELECT access_token FROM hdfc_session WHERE connected=1 LIMIT 1") as cur:
        row = await cur.fetchone()
    if not row or not row["access_token"]:
        raise HTTPException(401, "Not authenticated — use /api/hdfc/auth/init first")
    token = row["access_token"]
    req = urllib.request.Request(
        HDFC_AUTH_BASE + "/v2.0/funds",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return _json.loads(r.read())
    except Exception as e:
        raise HTTPException(502, str(e))

# ── Portfolio News ───────────────────────────────────────────────────────────

import xml.etree.ElementTree as _ET

_NEWS_DEFAULT_TICKERS = [
    "RELIANCE", "HDFCBANK", "COALINDIA", "NTPC", "JSPL", "SAIL",
    "HAL", "TATAMOTORS", "MSTC", "NALCO", "VEDL", "ADANIPOWER",
    "JSWENERGY", "IRCON", "RITES",
]

def _fetch_rss_news(ticker: str) -> list[dict]:
    """Fetch Yahoo Finance RSS for one ticker. Returns list of item dicts."""
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}.NS&region=IN&lang=en-IN"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
        root = _ET.fromstring(raw)
        ns = {"media": "http://search.yahoo.com/mrss/"}
        items = []
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            pub_el   = item.find("pubDate")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link  = link_el.text.strip()  if link_el  is not None and link_el.text  else ""
            pub   = pub_el.text.strip()   if pub_el   is not None and pub_el.text   else ""
            if title:
                items.append({"ticker": ticker, "headline": title, "url": link,
                              "source": "Yahoo Finance", "pub_date": pub})
        return items
    except Exception as e:
        return []

async def _store_news_items(db, items: list[dict]) -> int:
    """Insert items into portfolio_news, skip duplicates. Returns count of new rows."""
    new_count = 0
    for it in items:
        try:
            await db.execute(
                """INSERT OR IGNORE INTO portfolio_news
                   (ticker, headline, url, source)
                   VALUES (?, ?, ?, ?)""",
                (it["ticker"], it["headline"], it["url"], it["source"]),
            )
            if db.total_changes > 0:
                new_count += 1
        except Exception:
            pass
    await db.commit()
    return new_count

@app.get("/api/news/portfolio")
async def portfolio_news_get(tickers: str | None = None):
    """Return last 50 portfolio news items. Optional ?tickers=RELIANCE,HDFCBANK"""
    db = await vdb()
    ticker_list = [t.strip().upper() for t in tickers.split(",")] if tickers else _NEWS_DEFAULT_TICKERS

    # Fetch fresh in background — non-blocking best-effort
    loop = asyncio.get_event_loop()
    def _fetch_all():
        results = []
        for t in ticker_list:
            results.extend(_fetch_rss_news(t))
        return results

    try:
        items = await loop.run_in_executor(None, _fetch_all)
        await _store_news_items(db, items)
    except Exception:
        pass

    # Build WHERE clause
    placeholders = ",".join("?" * len(ticker_list))
    rows = await db.execute_fetchall(
        f"SELECT * FROM portfolio_news WHERE ticker IN ({placeholders}) ORDER BY fetched_at DESC LIMIT 50",
        ticker_list,
    )
    return {"news": [dict(r) for r in rows], "tickers": ticker_list}

@app.post("/api/news/portfolio/refresh")
async def portfolio_news_refresh(tickers: str | None = None):
    """Force-fetch Yahoo Finance RSS for all tickers concurrently. Returns new item count."""
    db = await vdb()
    ticker_list = [t.strip().upper() for t in tickers.split(",")] if tickers else _NEWS_DEFAULT_TICKERS

    loop = asyncio.get_event_loop()

    async def fetch_one(ticker: str):
        return await loop.run_in_executor(None, _fetch_rss_news, ticker)

    results = await asyncio.gather(*[fetch_one(t) for t in ticker_list])
    all_items: list[dict] = []
    for batch in results:
        all_items.extend(batch)

    new_count = await _store_news_items(db, all_items)
    return {"new_items": new_count, "total_fetched": len(all_items), "tickers": ticker_list}

@app.post("/api/news/{news_id}/read")
async def portfolio_news_mark_read(news_id: int):
    """Mark a news item as read."""
    db = await vdb()
    await db.execute("UPDATE portfolio_news SET read=1 WHERE id=?", (news_id,))
    await db.commit()
    return {"id": news_id, "read": True}

# ── Intelligence Engine ─────────────────────────────────────────────────────

@app.get("/api/intelligence/alerts")
async def intelligence_alerts(level: str = None, domain: str = None):
    """Get all unacknowledged alerts, optionally filtered."""
    db = await vdb()
    q = "SELECT * FROM intelligence_alerts WHERE acknowledged=0"
    params = []
    if level:
        q += " AND level=?"; params.append(level)
    if domain:
        q += " AND domain=?"; params.append(domain)
    q += " ORDER BY CASE level WHEN 'critical' THEN 1 WHEN 'important' THEN 2 ELSE 3 END, created_at DESC"
    async with db.execute(q, params) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    return {"alerts": rows}

@app.post("/api/intelligence/alerts/{alert_id}/ack")
async def intelligence_ack(alert_id: int):
    db = await vdb()
    await db.execute("UPDATE intelligence_alerts SET acknowledged=1 WHERE id=?", (alert_id,))
    await db.commit()
    return {"id": alert_id, "acknowledged": True}

@app.post("/api/intelligence/scan")
async def intelligence_scan():
    """Run classification engine — pulls from all data sources, classifies via rules + Grok,
    stores in intelligence_alerts. Returns count by level."""
    db = await vdb()
    import datetime as _dt
    today = _dt.date.today()
    today_str = today.isoformat()

    # Clear today's auto-generated alerts to refresh
    await db.execute("DELETE FROM intelligence_alerts WHERE source='auto_scan' AND date(created_at)=date('now')")

    counts = {"critical": 0, "important": 0, "info": 0}

    def add(level, domain, title, changed, matters, action, src_id=0):
        counts[level] = counts.get(level, 0) + 1
        return (level, domain, title, changed, matters, action, "auto_scan", src_id)

    rows_to_insert = []

    # 1. COMPLIANCE — deadlines
    async with db.execute(
        "SELECT id, entity_name, filing_type, due_date, status FROM compliance_filings WHERE status='pending' AND due_date IS NOT NULL"
    ) as cur:
        filings = await cur.fetchall()
    for f in filings:
        try:
            due = _dt.date.fromisoformat(f["due_date"][:10])
            days = (due - today).days
        except Exception:
            continue
        if days < 0:
            rows_to_insert.append(add("critical", "Compliance",
                f"{f['filing_type']} OVERDUE — {f['entity_name']}",
                f"Filing was due {abs(days)} days ago ({f['due_date'][:10]})",
                "Risk of penalty, ROC notice, or §454(8) escalation",
                f"Call CA Vimal Agrawal (9755220259) today; file immediately",
                f["id"]))
        elif days <= 3:
            rows_to_insert.append(add("critical", "Compliance",
                f"{f['filing_type']} due in {days}d — {f['entity_name']}",
                f"Deadline {f['due_date'][:10]} is {days} days away",
                "Late filing = penalty + compliance flag",
                "File this week; confirm with CA Vimal",
                f["id"]))
        elif days <= 14:
            rows_to_insert.append(add("important", "Compliance",
                f"{f['filing_type']} due in {days}d — {f['entity_name']}",
                f"Deadline approaching: {f['due_date'][:10]}",
                "Plan filing window; gather documents",
                "Sync with CA this week",
                f["id"]))

    # 2. SALES — VWLR tenders
    async with db.execute(
        "SELECT id, buyer, volume_mt, category, due_date FROM vwlr_tender_pipeline WHERE status='active' AND due_date IS NOT NULL"
    ) as cur:
        tenders = await cur.fetchall()
    for t in tenders:
        try:
            due = _dt.date.fromisoformat(t["due_date"][:10])
            days = (due - today).days
        except Exception:
            continue
        if days < 0:
            continue
        if days <= 3:
            rows_to_insert.append(add("critical", "Sales",
                f"Tender closing in {days}d — {t['buyer']}",
                f"{t['category']} tender, {int(t['volume_mt'] or 0)} MT, deadline {t['due_date'][:10]}",
                "Pipeline value at risk; bid window closing",
                "Submit bid today / confirm decision to skip",
                t["id"]))
        elif days <= 7:
            rows_to_insert.append(add("important", "Sales",
                f"Tender in {days}d — {t['buyer']}",
                f"{t['category']}, {int(t['volume_mt'] or 0)} MT — deadline {t['due_date'][:10]}",
                "Bid prep window opening",
                "Run bid calculator; check eligibility",
                t["id"]))

    # 3. INVESTMENTS — pending Singhvi calls
    async with db.execute(
        "SELECT id, ticker, direction, entry_price, target_price, stop_loss, status FROM singhvi_calls WHERE date=? AND status='pending'", (today_str,)
    ) as cur:
        pending_calls = await cur.fetchall()
    if pending_calls:
        rows_to_insert.append(add("important", "Investments",
            f"{len(pending_calls)} Singhvi call(s) pending review",
            f"Calls extracted from Zee Business not yet approved/skipped",
            "Market opens at 9:15 AM — late approvals miss the entry",
            "Open Morning Setup → review and approve",
            0))

    # 4. INTEL — high urgency items
    async with db.execute(
        "SELECT id, title, urgency, entity FROM intel_items WHERE urgency IN ('HIGH','CRITICAL') AND status='open'"
    ) as cur:
        intel = await cur.fetchall()
    for i in intel:
        rows_to_insert.append(add(
            "critical" if i["urgency"] == "CRITICAL" else "important",
            "Strategic",
            i["title"],
            "Open intel item, urgency: " + i["urgency"],
            "Flagged as time-sensitive — risk of escalation if ignored",
            f"Review on Intel Centre; resolve or escalate to {i['entity'] or 'CA/Legal'}",
            i["id"]))

    # 5. STRATEGIC — competitor activity
    async with db.execute(
        "SELECT id, name, tenders_won, tenders_tracked FROM vwlr_competitors WHERE tenders_won >= 3 ORDER BY tenders_won DESC LIMIT 3"
    ) as cur:
        threats = await cur.fetchall()
    for c in threats:
        rows_to_insert.append(add("important", "Strategic",
            f"{c['name']} winning aggressively",
            f"{c['tenders_won']} tenders won across {c['tenders_tracked']} tracked",
            "Top competitor in your tender categories — eroding margin pool",
            f"Pull Tender247 competitor report; identify their pricing pattern",
            c["id"]))

    # Insert all alerts
    for r in rows_to_insert:
        await db.execute(
            """INSERT INTO intelligence_alerts
               (level, domain, title, what_changed, why_matters, recommended_action, source, source_id)
               VALUES (?,?,?,?,?,?,?,?)""",
            r
        )
    await db.commit()

    return {
        "scanned_at": _dt.datetime.now().isoformat(),
        "counts": counts,
        "total": sum(counts.values()),
    }

@app.get("/api/intelligence/briefing")
async def intelligence_briefing():
    """Return today's structured briefing, grouped by level."""
    db = await vdb()
    async with db.execute(
        "SELECT * FROM intelligence_alerts WHERE acknowledged=0 ORDER BY CASE level WHEN 'critical' THEN 1 WHEN 'important' THEN 2 ELSE 3 END, domain"
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    grouped = {"critical": [], "important": [], "info": []}
    for r in rows:
        grouped[r["level"]].append(r)

    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "critical": grouped["critical"],
        "important": grouped["important"],
        "info": grouped["info"],
        "summary": {
            "critical_count": len(grouped["critical"]),
            "important_count": len(grouped["important"]),
            "info_count": len(grouped["info"]),
        }
    }

# ── Life LLM Map ────────────────────────────────────────────────────────────
@app.get("/api/lifemap")
async def lifemap():
    """Full map: layer definitions + nodes + edges."""
    db = await vdb()
    async with db.execute("SELECT * FROM life_map_nodes ORDER BY sort, label") as cur:
        nodes = [dict(r) for r in await cur.fetchall()]
    async with db.execute("SELECT * FROM life_map_edges") as cur:
        edges = [dict(r) for r in await cur.fetchall()]
    return {"layers": LIFE_MAP_LAYERS, "nodes": nodes, "edges": edges}

@app.post("/api/lifemap/nodes")
async def lifemap_add_node(body: dict):
    db = await vdb()
    label = (body.get("label") or "").strip()
    layer = (body.get("layer") or "").strip()
    if not label or layer not in {l["key"] for l in LIFE_MAP_LAYERS}:
        raise HTTPException(400, "label and a valid layer are required")
    node_id = body.get("id") or "n_" + "".join(
        c if c.isalnum() else "_" for c in label.lower()
    )[:40]
    await db.execute(
        """INSERT INTO life_map_nodes (id, layer, label, detail, status, kind, icon, notes, sort)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO NOTHING""",
        (node_id, layer, label, body.get("detail", ""), body.get("status", "planned"),
         body.get("kind", ""), body.get("icon", ""), body.get("notes", ""), body.get("sort", 99)),
    )
    await db.commit()
    async with db.execute("SELECT * FROM life_map_nodes WHERE id=?", (node_id,)) as cur:
        return dict(await cur.fetchone())

@app.put("/api/lifemap/nodes/{node_id}")
async def lifemap_update_node(node_id: str, body: dict):
    db = await vdb()
    fields = {k: v for k, v in body.items()
              if k in ("layer", "label", "detail", "status", "kind", "icon", "notes", "sort")}
    if not fields:
        raise HTTPException(400, "no editable fields provided")
    sets = ", ".join(f"{k}=?" for k in fields)
    await db.execute(
        f"UPDATE life_map_nodes SET {sets}, updated_at=datetime('now') WHERE id=?",
        (*fields.values(), node_id),
    )
    await db.commit()
    async with db.execute("SELECT * FROM life_map_nodes WHERE id=?", (node_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "node not found")
    return dict(row)

@app.delete("/api/lifemap/nodes/{node_id}")
async def lifemap_delete_node(node_id: str):
    db = await vdb()
    await db.execute("DELETE FROM life_map_edges WHERE from_node=? OR to_node=?", (node_id, node_id))
    await db.execute("DELETE FROM life_map_nodes WHERE id=?", (node_id,))
    await db.commit()
    return {"deleted": node_id}

@app.post("/api/lifemap/edges")
async def lifemap_add_edge(body: dict):
    db = await vdb()
    frm, to = body.get("from_node"), body.get("to_node")
    if not frm or not to or frm == to:
        raise HTTPException(400, "from_node and to_node (distinct) are required")
    await db.execute(
        "INSERT OR IGNORE INTO life_map_edges (from_node, to_node, label) VALUES (?,?,?)",
        (frm, to, body.get("label", "")),
    )
    await db.commit()
    async with db.execute(
        "SELECT * FROM life_map_edges WHERE from_node=? AND to_node=?", (frm, to)
    ) as cur:
        return dict(await cur.fetchone())

@app.delete("/api/lifemap/edges/{edge_id}")
async def lifemap_delete_edge(edge_id: int):
    db = await vdb()
    await db.execute("DELETE FROM life_map_edges WHERE id=?", (edge_id,))
    await db.commit()
    return {"deleted": edge_id}

@app.post("/api/lifemap/reset")
async def lifemap_reset():
    """Wipe the map and restore the seed. Destructive — UI asks for confirmation."""
    db = await vdb()
    await db.execute("DELETE FROM life_map_edges")
    await db.execute("DELETE FROM life_map_nodes")
    await db.commit()
    await _seed_life_map(db)
    return {"reset": True}

# ── MDO Brain — the LLM layer around this whole backend ────────────────────
import mdo_brain

mdo_brain.configure({
    "tenders":     vwlr_tenders,
    "leads":       vwlr_leads,
    "followups":   vwlr_followups,
    "competitors": vwlr_competitors,
    "bid":         vwlr_bid,
    "filings":     compliance_filings,
    "entities":    entities,
    "pools":       aditi_pools,
    "hotel":       hotel_daily,
    "watchlist":   market_watchlist,
    "briefing":    intelligence_briefing,
    "tasks":       ops_tasks,
    "task_add":    ops_task_add,
    "intel_add":   intel_add,
    "lifemap":     lifemap,
    "wa_messages": whatsapp_messages,
    "wa_groups":   whatsapp_groups,
    "capital":     capital_summary,
    "extractions": whatsapp_extractions,
    "checks":      checks_list,
    "reports":     agent_reports_list,
    "file_report": agent_report,
    # Capital depth: the brain used to see all of this through get_portfolio alone.
    "cfo":         lambda path: asyncio.to_thread(_cfo_get, path),
    # Site networks over the VPN sidecars, and the Decision Feed.
    "site_read":   lambda site: asyncio.to_thread(
                       lambda: {"tunnel": mdo_sites.tunnel_status(site), **mdo_sites.read_site(site)}),
    "site_links":  lambda: asyncio.to_thread(mdo_sites.all_tunnels),
    "feed":        feed_list,
})

@app.post("/api/brain/ask")
async def brain_ask_endpoint(body: dict):
    """Ask the MDO Brain — an LLM with live tool access to the whole business."""
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question required")
    try:
        return await mdo_brain.brain_ask(question, body.get("history") or [])
    except Exception as e:
        return {"answer": f"Brain error: {type(e).__name__}: {e}", "tools_used": [],
                "provider": None, "model": None}

@app.get("/api/brain/status")
async def brain_status():
    st = mdo_brain.provider_status()
    st["mcp_mounted"] = _mcp_manager is not None
    return st

if MCP_SECRET:
    _mcp_manager = mdo_brain.build_mcp_manager()
    if _mcp_manager is not None:
        async def _mcp_asgi(scope, receive, send):
            await _mcp_manager.handle_request(scope, receive, send)
        app.mount(f"/mcp/{MCP_SECRET}", _mcp_asgi)

# ── run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

