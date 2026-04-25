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
from fastapi import FastAPI, HTTPException
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
""")
    await db.commit()
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

def vedanta_conn() -> sqlite3.Connection:
    if not os.path.exists(VEDANTA_DB):
        raise FileNotFoundError(f"Vedanta DB not found: {VEDANTA_DB}")
    conn = sqlite3.connect(VEDANTA_DB)
    conn.row_factory = sqlite3.Row
    return conn

# _"__"_ app _"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"__"_
@asynccontextmanager
async def lifespan(app: FastAPI):
    await vdb()  # connect on startup
    print(f"\n___ MDO Server running at http://localhost:{PORT}")
    print(f"   VEGA DB:    {VEGA_DB}")
    print(f"   Vedanta DB: {VEDANTA_DB}\n")
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
async def briefing_today():
    """Return today's briefing from DB if it exists."""
    db = await vdb()
    from datetime import date
    today = date.today().isoformat()
    rows = await db.execute_fetchall(
        "SELECT * FROM morning_briefing WHERE date=? ORDER BY id DESC LIMIT 1", (today,)
    )
    if rows:
        return {"briefing": dict(rows[0]), "fresh": True}
    return {"briefing": None, "fresh": False}

@app.post("/api/briefing/generate")
async def briefing_generate():
    """Generate today morning briefing using Grok API."""
    from datetime import date, datetime

    # Read Grok key from env or .env file
    grok_key = os.environ.get("GROK_API_KEY", "")
    if not grok_key:
        env_path = BASE / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("GROK_API_KEY="):
                    grok_key = line.split("=", 1)[1].strip()
                    break

    today = date.today().isoformat()

    # Pull live context from DB
    db = await vdb()
    pending_tenders = await db.execute_fetchall(
        "SELECT buyer AS title, category AS issuer, due_date FROM vwlr_tender_pipeline WHERE status='active' ORDER BY due_date LIMIT 5"
    )
    urgent_intel = await db.execute_fetchall(
        "SELECT title FROM intel_items WHERE status='open' AND urgency IN ('CRITICAL','HIGH') LIMIT 5"
    )
    signals = await db.execute_fetchall(
        "SELECT ticker, action, confidence FROM trading_signals WHERE status='pending' ORDER BY confidence DESC LIMIT 5"
    )

    tender_lines = [str(r["title"]) + " -- deadline " + str(r["due_date"] or "TBD") for r in pending_tenders]
    intel_lines  = [str(r["title"]) for r in urgent_intel]
    signal_lines = [str(r["ticker"]) + " " + str(r["action"]) + " (" + str(r["confidence"]) + "% conf)" for r in signals]

    tenders_ctx = "\n".join("- " + t for t in tender_lines) if tender_lines else "None tracked"
    intel_ctx   = "\n".join("- " + t for t in intel_lines)  if intel_lines  else "None"
    signals_ctx = "\n".join("- " + t for t in signal_lines) if signal_lines else "No pending signals"

    prompt = (
        "You are Aman's personal morning intelligence officer. Aman runs:\n"
        "- Vedanta Washery & Logistic Solutions (VWLR) -- 6-platform railway siding at Raigarh CG, coal loading/unloading/RCR/washing\n"
        "- Hotel Ans International -- 70 rooms, Raigarh\n"
        "- Active equity and options trader on NSE via HDFC Securities\n"
        "- 26 group companies across logistics, trading, steel\n\n"
        "Current context:\n"
        "Pending coal tenders:\n" + tenders_ctx + "\n\n"
        "Urgent intel items:\n" + intel_ctx + "\n\n"
        "Capital algo pending trade signals:\n" + signals_ctx + "\n\n"
        "Date: " + today + "\n\n"
        "Write exactly 5 bullet points. Max 2 lines each. No jargon. No preamble. No 'Good morning'.\n"
        "Start with most important. Be specific with numbers where possible.\n"
        "Format each line starting with: * CATEGORY: text\n"
        "Categories to use: MARKETS, COAL, TENDERS, CAPITAL, ACTION"
    )

    content = ""
    error_msg = ""

    if grok_key:
        try:
            payload = _json.dumps({
                "model": "grok-3-mini",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.x.ai/v1/chat/completions",
                data=payload,
                headers={"Authorization": "Bearer " + grok_key, "Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                resp = _json.loads(r.read().decode("utf-8"))
            content = resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
            error_msg = str(e)
            content = (
                "* MARKETS: API error -- " + error_msg[:80] + "\n"
                "* COAL: No update available.\n"
                "* TENDERS: " + (tender_lines[0] if tender_lines else "No active tenders tracked.") + "\n"
                "* CAPITAL: " + (signal_lines[0] if signal_lines else "No signals pending.") + "\n"
                "* ACTION: Check GROK_API_KEY in .env and retry."
            )
    else:
        content = (
            "* MARKETS: Add GROK_API_KEY to .env for live briefings.\n"
            "* COAL: No live data -- key missing.\n"
            "* TENDERS: " + (tender_lines[0] if tender_lines else "No active tenders tracked.") + "\n"
            "* CAPITAL: " + (signal_lines[0] if signal_lines else "No signals pending.") + "\n"
            "* ACTION: Add GROK_API_KEY to .env file to enable AI morning briefings."
        )

    await db.execute(
        "INSERT OR REPLACE INTO morning_briefing (date, content, generated_at) VALUES (?,?,datetime('now'))",
        (today, content)
    )
    await db.commit()
    return {"briefing": {"date": today, "content": content, "error": error_msg or None}}

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

@app.post("/api/singhvi/extract")
async def singhvi_extract():
    """Trigger YouTube audio extraction from Zee Business live stream.
    Runs yt-dlp + faster-whisper + Grok in background thread.
    Returns immediately; calls appear in /api/singhvi/today as they are parsed."""
    import threading
    def _run():
        try:
            _extract_singhvi_calls()
        except Exception as ex:
            print("Singhvi extract error:", ex)
    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "message": "Extraction started. Calls will appear in 2-3 minutes."}

def _extract_singhvi_calls():
    """Pull Zee Business live audio, transcribe, parse with Grok, insert calls."""
    import subprocess, tempfile, os, json as _j, sqlite3, datetime as _dt
    grok_key = os.environ.get("GROK_API_KEY", "")

    # Step 1: Download ~10 min of Zee Business live audio via yt-dlp
    ZEE_URL = "https://www.youtube.com/@ZeeBusiness/streams"
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
        audio_path = tf.name

    try:
        subprocess.run([
            "yt-dlp", "--no-playlist", "-x", "--audio-format", "mp3",
            "--audio-quality", "0", "--match-filter", "is_live",
            "-o", audio_path, "--max-filesize", "20M",
            "--no-warnings", "--quiet",
            ZEE_URL,
        ], timeout=120, check=False)

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:
            print("Singhvi: no audio downloaded")
            return

        # Step 2: Transcribe with faster-whisper
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("small", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(audio_path, language="hi", beam_size=1)
            transcript = " ".join(seg.text for seg in segments)
        except ImportError:
            transcript = "[faster-whisper not installed — install on server]"

        if not transcript or len(transcript) < 50:
            print("Singhvi: transcript too short")
            return

        # Step 3: Send to Grok to extract stock calls
        if not grok_key:
            print("Singhvi: no GROK_API_KEY")
            return

        prompt = (
            "Extract every stock/futures/options call from this Zee Business / Anil Singhvi transcript.\n"
            "Return a JSON array. Each object must have:\n"
            "  ticker (NSE symbol, uppercase), direction (BUY/SELL/AVOID),\n"
            "  entry_price (number or 0), stop_loss (number or 0), target_price (number or 0),\n"
            "  instrument (EQ/FUT/OPT-CE/OPT-PE), timeframe (Intraday/Swing/Positional),\n"
            "  confidence (0-100), raw_quote (exact words from transcript).\n"
            "If no calls found, return [].\n"
            "Transcript:\n" + transcript[:3000]
        )

        payload = _j.dumps({
            "model": "grok-3-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.x.ai/v1/chat/completions", data=payload,
            headers={"Authorization": "Bearer " + grok_key, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = _j.loads(r.read())
        text = resp["choices"][0]["message"]["content"].strip()

        # Parse JSON from Grok response
        start = text.find("[")
        end   = text.rfind("]") + 1
        if start < 0 or end <= start:
            print("Singhvi: Grok returned no JSON array")
            return
        calls = _j.loads(text[start:end])

        # Step 4: Insert into DB
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
                    str(c.get("ticker","")).upper(),
                    "NSE",
                    str(c.get("instrument","EQ")),
                    str(c.get("direction","BUY")),
                    float(c.get("entry_price",0) or 0),
                    float(c.get("stop_loss",0) or 0),
                    float(c.get("target_price",0) or 0),
                    str(c.get("timeframe","Intraday")),
                    "Confidence: " + str(c.get("confidence","—")) + "%",
                    "youtube",
                    str(c.get("raw_quote",""))[:500],
                    "pending",
                )
            )
        conn.commit()
        conn.close()
        print("Singhvi: inserted", len(calls), "calls")
    finally:
        try: os.unlink(audio_path)
        except: pass

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

HDFC_CLIENT_ID     = "45889297"
HDFC_API_KEY_VAL   = os.environ.get("HDFC_API_KEY", "f0ff26190ea94acb87593ce2ad556d02")
HDFC_API_SECRET    = os.environ.get("HDFC_API_SECRET", "815f56e54ea84c58923fd7c187ef7c29")
HDFC_REDIRECT_URL  = os.environ.get("HDFC_REDIRECT_URL", "https://localhost/callback")
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
    import urllib.parse as _up
    params = _up.urlencode({
        "apiKey": HDFC_API_KEY_VAL,
        "redirect_uri": HDFC_REDIRECT_URL,
        "response_type": "code",
    })
    login_url = HDFC_AUTH_BASE + "/oauth2/auth?" + params
    return {"login_url": login_url, "client_id": HDFC_CLIENT_ID}

@app.post("/api/hdfc/auth/callback")
async def hdfc_auth_callback(body: dict):
    """Exchange auth code for access token and store in DB."""
    code = body.get("code", "")
    if not code:
        raise HTTPException(400, "Missing code")

    payload = _json.dumps({
        "apiKey": HDFC_API_KEY_VAL,
        "apiSecret": HDFC_API_SECRET,
        "code": code,
    }).encode("utf-8")
    req = urllib.request.Request(
        HDFC_AUTH_BASE + "/oauth2/token",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = _json.loads(r.read())
        token = resp.get("access_token", "")
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
    except Exception as e:
        raise HTTPException(500, str(e))

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

# ── run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

