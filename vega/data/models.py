"""Database table schemas for SQLite persistence."""

from __future__ import annotations

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trade_signals (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    product_type TEXT NOT NULL DEFAULT 'MIS',
    entry_price REAL NOT NULL,
    target_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    quantity INTEGER NOT NULL,
    technical_score REAL,
    sentiment_score REAL,
    combined_score REAL,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT NOT NULL,
    order_id TEXT,
    side TEXT NOT NULL,
    fill_price REAL,
    fill_qty INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    executed_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (signal_id) REFERENCES trade_signals(id)
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    date TEXT PRIMARY KEY,
    realized_pnl REAL NOT NULL DEFAULT 0,
    unrealized_pnl REAL NOT NULL DEFAULT 0,
    total_trades INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sentiment_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    summary TEXT,
    themes TEXT,
    post_count INTEGER,
    queried_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS price_levels (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    direction TEXT NOT NULL,
    price REAL NOT NULL,
    sl REAL NOT NULL,
    target REAL NOT NULL,
    expiry TEXT,
    source TEXT NOT NULL DEFAULT 'telegram',
    status TEXT NOT NULL DEFAULT 'active',
    proximity_alerted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    triggered_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_ticker ON trade_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_signals_status ON trade_signals(status);
CREATE INDEX IF NOT EXISTS idx_sentiment_ticker ON sentiment_log(ticker);
CREATE INDEX IF NOT EXISTS idx_sentiment_time ON sentiment_log(queried_at);
CREATE INDEX IF NOT EXISTS idx_levels_ticker ON price_levels(ticker);
CREATE INDEX IF NOT EXISTS idx_levels_status ON price_levels(status);

-- ── Intel Centre ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intel_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT 'market',
    source TEXT NOT NULL DEFAULT 'system',
    urgency TEXT NOT NULL DEFAULT 'MEDIUM',
    entity TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_intel_urgency ON intel_items(urgency);
CREATE INDEX IF NOT EXISTS idx_intel_status ON intel_items(status);

-- ── Operations Task Board ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ops_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    entity TEXT DEFAULT '',
    assigned_to TEXT DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    category TEXT NOT NULL DEFAULT 'general',
    due_date TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON ops_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON ops_tasks(due_date);

-- ── Compliance Filings ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compliance_filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'company',
    filing_type TEXT NOT NULL,
    description TEXT DEFAULT '',
    due_date TEXT,
    period TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT DEFAULT '',
    assigned_to TEXT DEFAULT 'CA Vimal Agrawal',
    filed_on TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_filing_entity ON compliance_filings(entity_name);
CREATE INDEX IF NOT EXISTS idx_filing_status ON compliance_filings(status);
CREATE INDEX IF NOT EXISTS idx_filing_due ON compliance_filings(due_date);

-- ── ANS Group Entities ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ans_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    short_name TEXT,
    entity_type TEXT NOT NULL DEFAULT 'company',
    cin TEXT,
    gstin TEXT,
    pan TEXT,
    business TEXT DEFAULT '',
    location TEXT DEFAULT 'Raigarh, CG',
    status TEXT NOT NULL DEFAULT 'active',
    directors TEXT DEFAULT '',
    annual_turnover TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Aditi Investment Pools ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aditi_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool_code TEXT NOT NULL UNIQUE,
    pool_name TEXT NOT NULL,
    description TEXT DEFAULT '',
    target_allocation REAL DEFAULT 0,
    current_value REAL DEFAULT 0,
    instruments TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── VWLR Interactions (CRM log) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vwlr_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    company TEXT NOT NULL,
    contact TEXT DEFAULT '',
    type TEXT NOT NULL DEFAULT 'call',
    notes TEXT DEFAULT '',
    outcome TEXT DEFAULT '',
    follow_up_date TEXT,
    created_by TEXT DEFAULT 'Aman',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_interact_lead ON vwlr_interactions(lead_id);
"""
