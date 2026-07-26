"""Seed vega_data.db with ANS Group master data.
Run once: python seed_mdo_db.py
"""
import sqlite3, os, sys

# In Docker the backend sets VEGA_DB_PATH=/data/vega_data.db (persistent volume)
DB = os.environ.get("VEGA_DB_PATH") or os.path.join(
    os.path.dirname(__file__), "vega", "data", "vega_data.db"
)
os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# ── ensure tables exist (subset needed here) ─────────────────────────────────
c.executescript("""
CREATE TABLE IF NOT EXISTS ans_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE, short_name TEXT, entity_type TEXT NOT NULL DEFAULT 'company',
    cin TEXT, gstin TEXT, pan TEXT, business TEXT DEFAULT '', location TEXT DEFAULT 'Raigarh, CG',
    status TEXT NOT NULL DEFAULT 'active', directors TEXT DEFAULT '',
    annual_turnover TEXT DEFAULT '', notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS compliance_filings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL, entity_type TEXT NOT NULL DEFAULT 'company',
    filing_type TEXT NOT NULL, description TEXT DEFAULT '', due_date TEXT,
    period TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT DEFAULT '', assigned_to TEXT DEFAULT 'CA Vimal Agrawal',
    filed_on TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS aditi_pools (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pool_code TEXT NOT NULL UNIQUE,
    pool_name TEXT NOT NULL, description TEXT DEFAULT '',
    target_allocation REAL DEFAULT 0, current_value REAL DEFAULT 0,
    instruments TEXT DEFAULT '', notes TEXT DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS ops_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    description TEXT DEFAULT '', entity TEXT DEFAULT '',
    assigned_to TEXT DEFAULT '', priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open', category TEXT NOT NULL DEFAULT 'general',
    due_date TEXT, completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS intel_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL DEFAULT 'market',
    source TEXT NOT NULL DEFAULT 'system', urgency TEXT NOT NULL DEFAULT 'MEDIUM',
    entity TEXT, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
    due_date TEXT, status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS vwlr_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER,
    company TEXT NOT NULL, contact TEXT DEFAULT '',
    type TEXT NOT NULL DEFAULT 'call', notes TEXT DEFAULT '',
    outcome TEXT DEFAULT '', follow_up_date TEXT,
    created_by TEXT DEFAULT 'Aman',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
""")
conn.commit()

# ── 26 ANS Group entities ─────────────────────────────────────────────────────
ENTITIES = [
    # name, short_name, type, business, location, directors, turnover, notes
    ("ANS Coal Washery Pvt Ltd",       "ANS Coal",     "company", "Coal washery / VWLR",          "Kharsia, Raigarh CG", "Aman Agrawal",          "₹18-22 Cr",  "Core washery ops"),
    ("Aditi Investments",              "Aditi Inv",    "company", "Equity / derivatives trading",  "Raigarh CG",          "Aman Agrawal",          "₹16-20 Cr AUM", "Liquid portfolio entity"),
    ("Hotel ANS International Ltd",    "Hotel ANS",    "company", "Hospitality / hotel",           "Raigarh CG",          "Aman Agrawal",          "₹2-3 Cr",    "Hotel operations"),
    ("Ozone Steel & Power Ltd",        "Ozone Steel",  "company", "Steel / iron",                  "Raigarh CG",          "Aman Agrawal",          "",           "§454 CRITICAL — strike-off notice"),
    ("Rashi Steel Ltd",                "Rashi Steel",  "company", "Steel manufacturing",           "Raigarh CG",          "Aman Agrawal",          "",           "Court case 3616/2026"),
    ("ANS Transport Pvt Ltd",          "ANS Trans",    "company", "Coal/goods transport",          "Raigarh CG",          "Aman Agrawal",          "₹1-2 Cr",    "Fleet: trucks/tippers"),
    ("ANS Minerals Pvt Ltd",           "ANS Min",      "company", "Mineral trading",               "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Infrastructure Pvt Ltd",     "ANS Infra",    "company", "Infrastructure/construction",   "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Energy Pvt Ltd",             "ANS Energy",   "company", "Power / energy",                "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Logistics Pvt Ltd",          "ANS Logi",     "company", "Logistics",                     "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Agro Pvt Ltd",               "ANS Agro",     "company", "Agri / farming",                "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Realty Pvt Ltd",             "ANS Realty",   "company", "Real estate",                   "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Trading Co",                 "ANS Trade",    "firm",    "Trading firm",                  "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("Aman Agrawal (Individual)",      "Aman",         "individual","Director / proprietor",       "Raigarh CG",          "—",                     "",           "PAN, ITR, DIN compliance"),
    ("ANS Group HUF",                  "ANS HUF",      "huf",     "HUF entity",                    "Raigarh CG",          "Aman Agrawal (Karta)",  "",           ""),
    ("ANS Cement Pvt Ltd",             "ANS Cement",   "company", "Cement / construction",         "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Power Pvt Ltd",              "ANS Power",    "company", "Power generation",              "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Mining Pvt Ltd",             "ANS Mining",   "company", "Coal mining services",          "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Coals Pvt Ltd",              "ANS Coals",    "company", "Coal procurement",              "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Construction Pvt Ltd",       "ANS Const",    "company", "Civil construction",            "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Enterprises",                "ANS Ent",      "firm",    "General trading",               "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Projects Pvt Ltd",           "ANS Proj",     "company", "Project management",            "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Fuels Pvt Ltd",              "ANS Fuels",    "company", "Fuel distribution",             "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Metals Pvt Ltd",             "ANS Metals",   "company", "Metal trading",                 "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Ventures Pvt Ltd",           "ANS Ventures", "company", "Business development",          "Raigarh CG",          "Aman Agrawal",          "",           ""),
    ("ANS Holdings Pvt Ltd",           "ANS Holdings", "company", "Group holding company",         "Raigarh CG",          "Aman Agrawal",          "",           "Parent entity"),
]

for row in ENTITIES:
    c.execute("""INSERT OR IGNORE INTO ans_entities
        (name,short_name,entity_type,business,location,directors,annual_turnover,notes)
        VALUES (?,?,?,?,?,?,?,?)""", row)

conn.commit()
print(f"✓ {len(ENTITIES)} entities seeded")

# ── Aditi Investment Pools ────────────────────────────────────────────────────
POOLS = [
    ("A", "Operating Capital",    "Day-to-day business liquidity, working capital, payroll buffer",             2_00_00_000,  1_80_00_000, "Current account, liquid FDs, OD limit",  "Keep 6-month opex coverage"),
    ("B", "Liquid Growth",        "Active equity + derivatives trading via HDFC SKY. Aman manages directly",   16_00_00_000, 16_00_00_000,"NSE equity, F&O, MFs",                    "₹16-20 Cr target. VEGA algo trading"),
    ("C", "Strategic Illiquid",   "Long-term strategic stakes: real estate, unlisted equity, private deals",    5_00_00_000,  4_50_00_000, "Unlisted shares, land, NPA auctions",     "3-5 year horizon. NPA/NCLT opportunities"),
    ("D", "Freedom Capital",      "Wealth preservation. Low-risk instruments. Safety net",                      3_00_00_000,  3_10_00_000, "Debt MF, bonds, SGBs, NPS",              "Capital preservation priority"),
]
for row in POOLS:
    c.execute("""INSERT OR IGNORE INTO aditi_pools
        (pool_code,pool_name,description,target_allocation,current_value,instruments,notes)
        VALUES (?,?,?,?,?,?,?)""", row)
conn.commit()
print("✓ 4 Aditi pools seeded")

# ── Compliance Filings ────────────────────────────────────────────────────────
FILINGS = [
    # entity_name, type, description, due_date, period, status, notes
    ("Ozone Steel Pvt Ltd",       "MCA ROC",    "Annual return + financial statements",     "2024-12-31", "FY2024",   "overdue",  "§454 CRITICAL — file immediately"),
    ("Ozone Steel Pvt Ltd",       "MCA ROC",    "DIR-3 KYC for all directors",             "2024-09-30", "FY2024",   "overdue",  "DIN deactivation risk"),
    ("Rashi Steel Ltd",           "Legal",      "Court case 3616/2026 — next hearing",     "2026-05-15", "2026",     "pending",  "CA + advocate coordination needed"),
    ("Aditi Investments",         "ITR",        "Individual ITR filing",                    "2026-07-31", "FY2026",   "pending",  "Capital gains from F&O"),
    ("Aditi Investments",         "GST",        "GST quarterly return",                     "2026-04-30", "Q4 FY26",  "pending",  ""),
    ("ANS Coal Washery Pvt Ltd",  "GST",        "GSTR-1 monthly",                           "2026-04-11", "Mar 2026", "pending",  ""),
    ("ANS Coal Washery Pvt Ltd",  "GST",        "GSTR-3B monthly",                          "2026-04-20", "Mar 2026", "pending",  ""),
    ("ANS Coal Washery Pvt Ltd",  "TDS",        "TDS Q4 return",                            "2026-05-31", "Q4 FY26",  "pending",  ""),
    ("ANS Coal Washery Pvt Ltd",  "MCA ROC",    "Annual return",                            "2026-09-30", "FY2026",   "pending",  ""),
    ("Hotel ANS",                 "GST",        "GSTR-1 monthly",                           "2026-04-11", "Mar 2026", "pending",  ""),
    ("Hotel ANS",                 "ITR",        "Company ITR",                              "2026-10-31", "FY2026",   "pending",  ""),
    ("ANS Transport Pvt Ltd",     "GST",        "GSTR-1 monthly",                           "2026-04-11", "Mar 2026", "pending",  ""),
    ("ANS Transport Pvt Ltd",     "MCA ROC",    "Annual return",                            "2026-09-30", "FY2026",   "pending",  ""),
    ("Aman Agrawal (Individual)", "ITR",        "Personal ITR + capital gains",             "2026-07-31", "FY2026",   "pending",  "F&O + salary + dividend income"),
    ("Aman Agrawal (Individual)", "MCA DIR",    "DIR-3 KYC renewal",                        "2026-09-30", "FY2026",   "pending",  "All directorships"),
    ("ANS Group HUF",             "ITR",        "HUF ITR",                                  "2026-07-31", "FY2026",   "pending",  ""),
    ("ANS Holdings Pvt Ltd",      "MCA ROC",    "Annual return",                            "2026-09-30", "FY2026",   "pending",  ""),
    ("ANS Holdings Pvt Ltd",      "Board",      "Board meeting + minutes",                  "2026-06-30", "FY2026",   "pending",  "All subsidiaries"),
]
if c.execute("SELECT COUNT(*) FROM compliance_filings").fetchone()[0] == 0:
    for row in FILINGS:
        c.execute("""INSERT INTO compliance_filings
            (entity_name,filing_type,description,due_date,period,status,notes)
            VALUES (?,?,?,?,?,?,?)""", row)
    conn.commit()
    print(f"✓ {len(FILINGS)} compliance filings seeded")
else:
    print("· compliance filings already present — skipped")

# ── Intel Items ───────────────────────────────────────────────────────────────
INTEL = [
    ("compliance", "system",  "CRITICAL", "Ozone Steel",    "§454 Strike-off Notice — File immediately",        "Ozone Steel not filing annual returns. NCLT strike-off proceedings underway. Contact CA Vimal Agrawal (9755220259) TODAY.", "2026-04-30", "open"),
    ("compliance", "system",  "HIGH",     "Rashi Steel",    "Court Case 3616/2026 — Next hearing May 15",        "Civil dispute in progress. CA + advocate coordination needed. Get case status update.", "2026-05-15", "open"),
    ("trading",    "system",  "HIGH",     "Aditi",          "F&O expiry week — review open positions",           "April series expiry approaching. Review all open F&O positions and decide roll/close.", "2026-04-24", "open"),
    ("vwlr",       "system",  "HIGH",     "Vedanta",        "Tender VED/WC/2026/004 closes May 5",               "Coal washery tender 10,000 MT. Eligibility 92%. Prepare bid with gate price ₹4,200. Volume discount applicable.", "2026-05-05", "open"),
    ("compliance", "system",  "MEDIUM",   "All Entities",   "GST filings due Apr 20 — 6 companies",             "GSTR-3B for March 2026 due April 20. Companies: ANS Coal, Hotel ANS, ANS Transport, ANS Mining, ANS Minerals, ANS Coals.", "2026-04-20", "open"),
    ("market",     "system",  "MEDIUM",   "NIFTY",          "Nifty at key resistance 23,500 — monitor",          "Technical resistance zone. Multiple Singhvi calls cautious above 23,400. Review positions if breakout fails.", None, "open"),
    ("vwlr",       "system",  "MEDIUM",   "SECL",           "SECL tender MCL/2026/048 — due Apr 28",            "10,500 MT coal supply tender from SECL. Eligibility 85%. Prepare documentation.", "2026-04-28", "open"),
    ("wealth",     "system",  "LOW",      "Pool D",         "SGB tranche open — consider allocation",           "Sovereign Gold Bond new tranche. Pool D allocation opportunity for capital preservation.", None, "open"),
]
# guard on source='system' so Brain/agent-filed intel doesn't block seeding
if c.execute("SELECT COUNT(*) FROM intel_items WHERE source='system'").fetchone()[0] == 0:
    for row in INTEL:
        c.execute("""INSERT INTO intel_items
            (category,source,urgency,entity,title,body,due_date,status)
            VALUES (?,?,?,?,?,?,?,?)""", row)
    conn.commit()
    print(f"✓ {len(INTEL)} intel items seeded")
else:
    print("· system intel items already present — skipped")

# ── Ops Tasks ─────────────────────────────────────────────────────────────────
TASKS = [
    ("File Ozone Steel annual returns",          "Contact CA Vimal, get financials ready, file MCA ROC",                "Ozone Steel",    "CA Vimal Agrawal", "critical", "open",   "compliance", "2026-04-30"),
    ("Prepare Vedanta tender bid VED/WC/2026/004","Use bid calculator, prepare documents, submit on Tender247",          "ANS Coal Washery","Aman",            "high",     "open",   "sales",      "2026-05-03"),
    ("File April GSTR-1 for all companies",      "6 companies: ANS Coal, Hotel, Transport, Mining, Minerals, Coals",    "All Entities",   "CA Vimal Agrawal", "high",     "open",   "compliance", "2026-04-11"),
    ("Review Q4 TDS returns",                    "Coordinate with CA for Q4 TDS filing across all entities",             "All Entities",   "CA Vimal Agrawal", "medium",   "open",   "compliance", "2026-05-31"),
    ("Call Rajesh Kumar re follow-up",           "High priority lead — potential 8,000 MT/month volume",                 "ANS Coal Washery","Aman",            "high",     "open",   "sales",      "2026-04-25"),
    ("Hotel ANS occupancy report April",         "Get room occupancy, revenue, and opex for April from hotel manager",   "Hotel ANS",      "Aman",             "medium",   "open",   "operations", "2026-04-30"),
    ("Pool B rebalancing review",                "Review Aditi equity portfolio. Assess underperformers for exit.",       "Aditi Inv",      "Aman",             "medium",   "open",   "trading",    "2026-04-26"),
    ("SECL tender MCL/2026/048 bid prep",        "Prepare eligibility docs and pricing for SECL tender",                 "ANS Coal Washery","Aman",            "high",     "open",   "sales",      "2026-04-27"),
    ("DIR-3 KYC for all directorships",          "Aman Agrawal DIN renewal across all companies",                        "All Entities",   "CA Vimal Agrawal", "medium",   "open",   "compliance", "2026-09-30"),
    ("Board meeting — ANS Holdings",             "Schedule Q1 FY27 board meeting, prepare minutes template",             "ANS Holdings",   "Aman",             "low",      "open",   "operations", "2026-06-30"),
]
# exclude roadmap tasks from the guard — the server seeds those itself
if c.execute("SELECT COUNT(*) FROM ops_tasks WHERE category != 'roadmap'").fetchone()[0] == 0:
    for row in TASKS:
        c.execute("""INSERT INTO ops_tasks
            (title,description,entity,assigned_to,priority,status,category,due_date)
            VALUES (?,?,?,?,?,?,?,?)""", row)
    conn.commit()
    print(f"✓ {len(TASKS)} ops tasks seeded")
else:
    print("· ops tasks already present — skipped")

# ── Entity enrichment — verified facts from MDO_VISION.md / MDO_INTEL.md ─────
# Idempotent: re-asserts doc-sourced fields on every run. Placeholder rows are
# only flagged while still in untouched seed state (empty notes) so manual
# edits in the app are never overwritten.

# Legal-name corrections — migrate rows created by older seed runs, then drop
# any stale old-name duplicate the UNIQUE constraint kept around.
c.execute("UPDATE OR IGNORE ans_entities SET name='Hotel ANS International Ltd' WHERE name='Hotel ANS'")
c.execute("UPDATE OR IGNORE ans_entities SET name='Ozone Steel & Power Ltd' WHERE name='Ozone Steel Pvt Ltd'")
c.execute("DELETE FROM ans_entities WHERE name IN ('Hotel ANS','Ozone Steel Pvt Ltd')")
c.execute("UPDATE compliance_filings SET entity_name='Hotel ANS International Ltd' WHERE entity_name='Hotel ANS'")
c.execute("UPDATE ops_tasks SET entity='Hotel ANS International Ltd' WHERE entity='Hotel ANS'")
c.execute("UPDATE compliance_filings SET entity_name='Ozone Steel & Power Ltd' WHERE entity_name='Ozone Steel Pvt Ltd'")

ENRICH = {
    "ANS Coal Washery Pvt Ltd": {
        "pan": "AAECV8176B",
        "business": "Coal washery — VWLR (RCR, loading/unloading, rake handling)",
        "location": "Kharsia, Raigarh CG",
        "notes": "C1. COMMISSIONING ~50% capacity (Apr 2026). Active pipeline ₹34.55 Cr: "
                 "WCL ₹22.2 Cr, SCCL ₹7.8 Cr, SECL ₹51.32 L, Indonesian ₹4 Cr. "
                 "Tender platform: Tender247. Exact legal name unconfirmed (MDO_INTEL §2) — "
                 "verify against ANS_Group_Data_Capture.",
    },
    "Hotel ANS International Ltd": {
        "business": "Hospitality — 88 rooms",
        "location": "Regd. Kolkata · ops Raigarh CG",
        "notes": "C2, Public Ltd. Occupancy ~23% (Apr 2026) — focus area. Staah inventory, "
                 "Swiggy/Zomato delivery. 🔴 AOC-4 + MGT-7 filing currency unknown — confirm with CA Vimal.",
    },
    "Aditi Investments": {
        "entity_type": "firm",
        "pan": "ACFFA4349B",
        "directors": "Partners: Aman Agrawal, Ashok, Sudha",
        "annual_turnover": "₹85.78 L liquid (19 Apr 2026) · target ₹100 Cr in 2 yrs",
        "notes": "F1 partnership firm. HDFC Securities a/c #4016900. Pool B vehicle: 200+ NSE "
                 "equities, F&O (NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY), US equity via IndMoney, "
                 "crypto on SunCrypto + Binance.",
    },
    "Ozone Steel & Power Ltd": {
        "pan": "AAACA1111A",
        "business": "Steel & power — Public Ltd",
        "notes": "C10. 🔴 §454(8) strike-off risk — no ITR PDF filed. NCLT/ROC exposure. "
                 "Escalate via CA Vimal Agrawal (9755220259).",
    },
    "Rashi Steel Ltd": {
        "entity_type": "external",
        "directors": "",
        "notes": "X1 — EXTERNAL entity, not ANS-controlled. 🔴 §454(8) CJM Bilaspur case "
                 "3616/2026, next hearing was 15 May 2026; advocate not yet engaged.",
    },
    "Aman Agrawal (Individual)": {
        "notes": "I1. Age 31, first-generation industrialist. Father: Narendra Agrawal (founder), "
                 "sister: Aditi Agrawal. PAN/ITR/DIN compliance; DIR-3 KYC due 30 Sep 2026.",
    },
    "ANS Group HUF": {
        "notes": "H1. Karta: Aman Agrawal. HUF ITR due 31 Jul 2026.",
    },
}
for name, fields in ENRICH.items():
    sets = ", ".join(f"{k}=?" for k in fields)
    c.execute(f"UPDATE ans_entities SET {sets} WHERE name=?", [*fields.values(), name])
conn.commit()
print(f"✓ {len(ENRICH)} entities enriched from MDO_VISION/MDO_INTEL")

# Rows that appear in NO source document — likely placeholders from an earlier
# session. MDO_VISION §2D says the real register is 6 persons + 1 HUF + 5 firms
# + 14 companies + 1 external; the authoritative list lives in the
# ANS_Group_Data_Capture files on Aman's laptop.
UNVERIFIED = [
    "ANS Energy Pvt Ltd", "ANS Logistics Pvt Ltd", "ANS Agro Pvt Ltd",
    "ANS Realty Pvt Ltd", "ANS Cement Pvt Ltd", "ANS Power Pvt Ltd",
    "ANS Construction Pvt Ltd", "ANS Projects Pvt Ltd", "ANS Fuels Pvt Ltd",
    "ANS Metals Pvt Ltd", "ANS Ventures Pvt Ltd", "ANS Enterprises",
]
flagged = 0
for name in UNVERIFIED:
    flagged += c.execute(
        "UPDATE ans_entities SET status='unverified', "
        "notes='UNVERIFIED — name not found in any source document. Real 26-unit register "
        "(6 persons, 1 HUF, 5 firms, 14 companies, 1 external) is in ANS_Group_Data_Capture "
        "on laptop. Confirm, correct, or delete.' "
        "WHERE name=? AND status='active' AND notes=''",
        (name,),
    ).rowcount
conn.commit()
if flagged:
    print(f"✓ {flagged} placeholder entities flagged unverified")

AUDIT_TITLE = "Entity register needs verification — seed list vs documented 26-unit structure"
if not c.execute("SELECT 1 FROM intel_items WHERE title=?", (AUDIT_TITLE,)).fetchone():
    c.execute(
        """INSERT INTO intel_items (category,source,urgency,entity,title,body,due_date,status)
           VALUES ('compliance','audit','MEDIUM','All Entities',?,?,NULL,'open')""",
        (AUDIT_TITLE,
         "MDO_VISION §2D documents 26 taxable units as 6 persons (I1-I6) + 1 HUF + 5 firms "
         "(F1-F5) + 14 companies (C1-C14) + 1 external (X1 Rashi Steel). The seeded register "
         "has 1 person, 1 HUF, 2 firms, 22 companies — 12 company names have no source and "
         "are flagged 'unverified'. Action: pull the ANS_Group_Data_Capture files from "
         "Desktop/MASTER and replace placeholders with the real register."),
    )
    conn.commit()
    print("✓ audit intel item filed")

# Roadmap step 1 is factually complete — the system is running on the VPS.
c.execute(
    "UPDATE ops_tasks SET status='done', completed_at=datetime('now'), updated_at=datetime('now') "
    "WHERE category='roadmap' AND title='Deploy MDO to Hostinger VPS' AND status='open'"
)
conn.commit()

conn.close()
print("\n✅ MDO database seeded successfully!")
print(f"   DB: {DB}")

# ── Stopgap Vedanta CRM DB (tenders / leads) ─────────────────────────────────
# Created ONLY if /data/vedanta_crm.db is absent, so it can never clobber the
# real CRM database once that is uploaded from the laptop. Contents come from
# MDO_INTEL §3 (11 seed leads) and MDO_VISION §2A (pipeline breakdown).
VDB = os.environ.get("VEDANTA_DB_PATH") or os.path.join(
    os.path.dirname(__file__), "vega", "data", "vedanta_crm.db"
)
if os.path.exists(VDB):
    print(f"· Vedanta CRM DB present — untouched: {VDB}")
else:
    v = sqlite3.connect(VDB)
    v.executescript("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL, contact_person TEXT DEFAULT '', phone TEXT DEFAULT '',
        location TEXT DEFAULT '', distance_km REAL DEFAULT 0,
        potential_volume TEXT DEFAULT '', status TEXT DEFAULT 'prospect',
        priority TEXT DEFAULT 'Medium', tender_score REAL DEFAULT 0,
        next_followup TEXT, notes TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS tender_tracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        buyer TEXT NOT NULL, title TEXT DEFAULT '', volume REAL, unit TEXT DEFAULT 'MT',
        category TEXT DEFAULT '', due_date TEXT, status TEXT DEFAULT 'active',
        eligibility_score REAL, url TEXT DEFAULT '', notes TEXT DEFAULT ''
    );
    """)
    LEADS = [
        # company, distance_km, potential_volume, priority  (MDO_INTEL §3)
        ("NTPC Sipat",        85, "50,000 MT/mo", "High"),
        ("JSPL Raigarh",      12, "30,000 MT/mo", "High"),
        ("SAIL Bhilai",      140, "45,000 MT/mo", "High"),
        ("Monnet Ispat",      35, "20,000 MT/mo", "High"),
        ("Chettinad Cement",  95, "15,000 MT/mo", "Medium"),
        ("OCL India",        110, "12,000 MT/mo", "Medium"),
        ("Godawari Power",    45, "25,000 MT/mo", "High"),
        ("Shakti Pumps",     180, "8,000 MT/mo",  "Low"),
        ("KSK Energy",        65, "18,000 MT/mo", "Medium"),
        ("SECL",              20, "100,000 MT/mo","High"),
        ("ACC Cement",       125, "10,000 MT/mo", "Low"),
    ]
    v.executemany(
        "INSERT INTO leads (company,distance_km,potential_volume,priority,status,notes) "
        "VALUES (?,?,?,?,'prospect','Seeded from MDO_INTEL §3 (Apr 2026) — stopgap until real CRM DB is uploaded')",
        LEADS,
    )
    PIPELINE = [
        ("WCL",        "Service pipeline — RCR / handling", "₹22.2 Cr pipeline value (MDO_VISION §2A, Apr 2026)"),
        ("SCCL",       "Service pipeline — RCR / handling", "₹7.8 Cr pipeline value. 🔴 18 Apr 2026 tender deadline — confirm submitted/missed (MDO_VISION §4)"),
        ("SECL",       "Service pipeline — RCR / handling", "₹51.32 L pipeline value (MDO_VISION §2A, Apr 2026)"),
        ("Indonesian", "Service pipeline — import-linked",  "₹4 Cr pipeline value (MDO_VISION §2A, Apr 2026)"),
    ]
    v.executemany(
        "INSERT INTO tender_tracking (buyer,title,category,status,notes) VALUES (?,?, 'Pipeline','pipeline',?)",
        PIPELINE,
    )
    v.commit()
    v.close()
    print(f"✓ Stopgap Vedanta CRM DB created: 11 leads + 4 pipeline entries → {VDB}")
    print("  (upload the real vedanta_crm.db from the laptop to replace it)")
