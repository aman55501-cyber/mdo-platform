"""Share Master — one workbook Aman opens, current every trading day with no clicks.

Aman, chat 2026-10-09: a master share sheet with tabs that auto-update daily — Portfolio
(from the broker holdings), Mausaji Calls (from "Bantu Mausaji"'s WhatsApp chat), Levels
(his buy/sell list), plus a Summary. He is not technical; the output is a file.

Two tables, mounted onto the FastAPI app by mdo_server.py via register():
  portfolio_snapshot  one row per (snap_date, account, ticker) — what the broker said that day
  mausaji_calls       one row per (message_id, ticker, action) — Mausaji's own words, never inferred

Where the data comes from (be precise, never invent):
  Portfolio  Shares CFO `/portfolio` (the `sharescfo` service in this compose stack; env
             SHARESCFO_URL, falling back to CFO_API_URL, default http://sharescfo:8000;
             token CFO_API_TOKEN). It holds the HDFC1/2/3 OAuth sessions (Aman's daily login)
             and ANGEL1 (TOTP). An account that is not logged in comes back `ok: false` with a
             reason; that account keeps its LAST snapshot and the Portfolio tab says so.
             /api/holdings on the MDO backend is a stub ([]) and is not used.
  Prices     mdo_levels.fetch_ltp (Yahoo Finance, LEVELS_PRICE_SOURCE override), falling back
             to the broker's last_price when Yahoo has no answer. No price → blank, never a guess.
  Mausaji    whatsapp_messages rows whose chat display name (group_name) contains MAUSAJI_CHAT
             (default "Bantu Mausaji"), from_me=0, id > the bot_memory watermark. The bot
             (share-master-daily in mdo_agent.py) sends ≤60 messages per claude-haiku-4-5 call
             and inserts what parse_mausaji_calls() returns; UNIQUE dedups repeats.
  Outcomes   prices only: BUY hit_target when ltp ≥ target, hit_stop when ltp ≤ stop; SELL
             mirrored; any open call expires after CALL_EXPIRY_DAYS.
  Levels     share_levels (mdo_levels) — seeded from Aman's list; POST /api/levels/import
             takes rows parsed from his CSV/XLSX files (parse_levels_table guesses headers).

Pure helpers (no I/O, unit-tested): parse_mausaji_prompt, parse_mausaji_calls, call_outcome,
apply_outcomes, holdings_from_book, portfolio_rows, parse_levels_table, summarise, build_workbook.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import math
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request

import mdo_levels as lv
import mdo_wa_intel as wai
from mdo_cos import IST, VAULT_MAX_BYTES, safe_vault_path

BOT_ID = "share-master-daily"
WATERMARK_KEY = "mausaji_watermark_msg_id"
ACCOUNTS_KEY = "account_status"       # bot_memory: what the last refresh saw per broker account
VAULT_FILE = "finance/Share_Master.xlsx"
MAUSAJI_CHAT_DEFAULT = "Bantu Mausaji"
MAUSAJI_BATCH = 60                    # messages per Claude call
MAUSAJI_MAX_PER_RUN = 600             # backlog cap per run; the next run continues
QUOTE_MAX = 300
CALL_EXPIRY_DAYS = 60
CSV_STALE_DAYS = 3                    # an HDFC CSV older than this is reported stale, still shown
CAP_WEIGHT_PCT = 12.0                 # CAP: one share > 12% of the book (share-master rule)
L15_PCT = -15.0                       # L15: unrealised loss ≥ 15% vs avg cost
L30_PCT = -30.0                       # L30: unrealised loss ≥ 30% vs avg cost
ACTIONS = ("BUY", "SELL", "HOLD", "AVOID")
STATUSES = ("open", "hit_target", "hit_stop", "expired")
TOP_N = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS mausaji_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_date TEXT NOT NULL,                     -- YYYY-MM-DD of the message
    ticker TEXT NOT NULL,                        -- as Mausaji named it, upper
    action TEXT NOT NULL CHECK (action IN ('BUY','SELL','HOLD','AVOID')),
    entry REAL, target REAL, stop REAL,
    timeframe TEXT DEFAULT '',
    quote TEXT DEFAULT '',                       -- his words, ≤300 chars
    message_id INTEGER,                          -- whatsapp_messages.id
    chat_name TEXT DEFAULT '',
    extracted_at TEXT DEFAULT (datetime('now')),
    ltp_at_call REAL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','hit_target','hit_stop','expired')),
    last_ltp REAL, last_checked TEXT,
    UNIQUE(message_id, ticker, action)
);
CREATE TABLE IF NOT EXISTS portfolio_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snap_date TEXT NOT NULL, account TEXT NOT NULL, ticker TEXT NOT NULL,
    qty REAL, avg_price REAL, ltp REAL, invested REAL, value REAL, pnl REAL, pnl_pct REAL, weight_pct REAL,
    flag TEXT DEFAULT '', source TEXT DEFAULT '', company TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(snap_date, account, ticker)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_snap ON portfolio_snapshot(account, snap_date);
CREATE TABLE IF NOT EXISTS share_master_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    holder TEXT NOT NULL,                        -- who uploaded / whose account (e.g. Aditi)
    ticker TEXT NOT NULL,                        -- NSE symbol (mapped) or the stripped HDFC code
    hdfc_code TEXT DEFAULT '', company TEXT DEFAULT '',
    qty REAL, avg_price REAL, cmp REAL, invested REAL, value REAL, pnl REAL, pnl_pct REAL,
    ticker_verified INTEGER NOT NULL DEFAULT 1,  -- 0 = code not in HDFC_CODE_MAP / NSE list ("unverified ticker")
    source TEXT DEFAULT 'hdfc-csv', uploaded_at TEXT DEFAULT (datetime('now')),  -- hdfc-csv | hdfc-json | angel-dp | angel-json
    isin TEXT DEFAULT '', broker TEXT DEFAULT '',                               -- Angel DP rows carry the ISIN
    bse_code TEXT DEFAULT '',                    -- BSE scrip code for a BSE-only holding (priced as <code>.BO)
    UNIQUE(holder, ticker)
);
CREATE TABLE IF NOT EXISTS share_master_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL, instrument TEXT NOT NULL, side TEXT NOT NULL,   -- BUY|SELL
    qty REAL, avg REAL, ltp REAL, pl REAL, product TEXT DEFAULT '',      -- OVERNIGHT|MTF|COLL-SELL|...
    as_of TEXT DEFAULT '', source TEXT DEFAULT 'manual',                 -- manual (CoS-transcribed) | hdfc-api later
    imported_at TEXT DEFAULT (datetime('now')),
    UNIQUE(account, instrument, side, product)
);
CREATE INDEX IF NOT EXISTS idx_mausaji_status ON mausaji_calls(status, call_date);
CREATE TABLE IF NOT EXISTS vault_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL, path TEXT NOT NULL, bytes INTEGER DEFAULT 0,
    actor TEXT DEFAULT '', ok INTEGER DEFAULT 1, note TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS bot_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, source TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(bot, key)
);
"""

_num = lv._num
norm_ticker = lv.norm_ticker
_SERIES_SUFFIX = re.compile(r"-(EQ|BE|BZ|BL|SM|ST|IQ)$")


def mausaji_chat() -> str:
    return (os.environ.get("MAUSAJI_CHAT") or MAUSAJI_CHAT_DEFAULT).strip() or MAUSAJI_CHAT_DEFAULT


def sharescfo_url() -> str:
    return (os.environ.get("SHARESCFO_URL") or os.environ.get("CFO_API_URL") or "http://sharescfo:8000").strip().rstrip("/")


def clean_symbol(t: Any) -> str:
    """Broker symbol → plain NSE symbol: 'TCS-EQ' → 'TCS', 'infy.ns' → 'INFY'."""
    return norm_ticker(_SERIES_SUFFIX.sub("", str(t or "").strip().upper()))


def _pct(part: float | None, whole: float | None) -> float | None:
    if part is None or whole in (None, 0):
        return None
    return round(part / whole * 100, 2)


# ── Mausaji: prompt + parse ───────────────────────────────────────────────────
def parse_mausaji_prompt(messages: list[dict], chat_name: str = "", now: datetime | None = None) -> str:
    """The extraction prompt. Only explicit calls; the quote is his own words; never infer."""
    now = now or datetime.now(IST)
    lines = []
    for m in messages:
        ts = str(m.get("timestamp") or "")[:16]
        who = str(m.get("sender") or "?")[:40]
        text = str(m.get("text") or "").replace("\n", " ⏎ ")[:1200]
        lines.append(f"[id {m.get('id')}] {ts} {who}: {text}")
    body = "\n".join(lines) or "(no messages)"
    return (
        f"These are WhatsApp messages from the chat \"{chat_name or mausaji_chat()}\" (read on "
        f"{now:%A %d %B %Y} IST). The sender is Aman's uncle, who sometimes gives stock calls.\n"
        "Extract ONLY explicit stock calls: a message must name a stock (ticker or company) AND state "
        "an action — buy, sell, hold or avoid. Prices (entry, target, stop) and the timeframe are "
        "taken only when the message states them; a number that is not in the message is null. "
        "Never infer a call from a question, a news forward, a greeting, or a general market comment. "
        "One message may carry several calls (one object each). The quote is his own words for that "
        "call, verbatim, at most 300 characters.\n"
        "Return ONLY a JSON list, no prose:\n"
        '[{"message_id": <the id in brackets>, "ticker": "NSE symbol or company name as written", '
        '"action": "BUY|SELL|HOLD|AVOID", "entry": number or null, "target": number or null, '
        '"stop": number or null, "timeframe": "as stated or empty", "quote": "his words"}]\n'
        "No calls → []\n\nMESSAGES:\n" + body
    )


_ACTION_ALIASES = {
    "buy": "BUY", "accumulate": "BUY", "add": "BUY", "long": "BUY", "enter": "BUY",
    "sell": "SELL", "exit": "SELL", "book": "SELL", "short": "SELL", "reduce": "SELL",
    "hold": "HOLD", "keep": "HOLD", "stay": "HOLD",
    "avoid": "AVOID", "skip": "AVOID", "stay away": "AVOID", "do not buy": "AVOID", "dont buy": "AVOID",
}


def _action(v: Any) -> str:
    s = str(v or "").strip().lower()
    if not s:
        return ""
    if s.upper() in ACTIONS:
        return s.upper()
    for k, a in _ACTION_ALIASES.items():
        if s == k or s.startswith(k + " "):
            return a
    return ""


def _int(v: Any) -> int | None:
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return int(f) if math.isfinite(f) and f == int(f) else None


def parse_mausaji_calls(text: Any, allowed_ids: set[int] | dict[int, Any] | None = None,
                        chat_name: str = "") -> list[dict]:
    """Model text → normalised call dicts. Tolerates fences, prose, a dict wrapper, a truncated
    tail, missing fields, strings for numbers. Drops rows without a ticker, an action, or a
    message_id; drops a message_id outside allowed_ids (a hallucinated id) when given; dedups on
    (message_id, ticker, action) — the table's UNIQUE. Never raises.

    allowed_ids may be a dict {message_id: message} — then call_date comes from the message's
    timestamp instead of today."""
    data = wai.extract_json(text)
    if isinstance(data, dict):
        inner = data.get("calls")
        data = inner if isinstance(inner, list) else [data]
    if not isinstance(data, list):
        return []
    by_id = allowed_ids if isinstance(allowed_ids, dict) else None
    allowed = set(allowed_ids) if allowed_ids is not None else None
    out, seen = [], set()
    for it in data:
        if not isinstance(it, dict):
            continue
        mid = _int(it.get("message_id") if it.get("message_id") is not None else it.get("id"))
        ticker = clean_symbol(it.get("ticker") or it.get("symbol") or it.get("stock") or it.get("company"))[:40]
        action = _action(it.get("action") or it.get("call") or it.get("direction"))
        if mid is None or not ticker or not action:
            continue
        if allowed is not None and mid not in allowed:
            continue
        key = (mid, ticker, action)
        if key in seen:
            continue
        seen.add(key)
        msg = by_id.get(mid) if by_id else None
        call_date = None
        if msg:
            ts = wai.parse_ts(str(msg.get("timestamp") or ""))
            if ts:
                call_date = ts.astimezone(IST).date().isoformat()
        out.append({
            "message_id": mid, "ticker": ticker, "action": action,
            "entry": _num(it.get("entry") if it.get("entry") is not None else it.get("entry_price")),
            "target": _num(it.get("target") if it.get("target") is not None else it.get("target_price")),
            "stop": _num(it.get("stop") if it.get("stop") is not None else it.get("stop_loss")),
            "timeframe": str(it.get("timeframe") or "").strip()[:40],
            "quote": str(it.get("quote") or it.get("text") or "").strip()[:QUOTE_MAX],
            "call_date": call_date or date.today().isoformat(),
            "chat_name": chat_name or (str(msg.get("group_name") or msg.get("chat_name") or "") if msg else "")[:200],
        })
    return out


# ── outcomes: prices only ─────────────────────────────────────────────────────
def call_outcome(call: dict, ltp: float | None, now: datetime | date | None = None) -> str | None:
    """New status for an OPEN call, or None when nothing changed.
    BUY: ltp ≥ target → hit_target; ltp ≤ stop → hit_stop. SELL: mirrored (ltp ≤ target hits,
    ltp ≥ stop stops). HOLD/AVOID carry no price rule. Any open call older than
    CALL_EXPIRY_DAYS expires. A missing ltp never changes a status (expiry excepted)."""
    if str(call.get("status") or "open") != "open":
        return None
    today = now.date() if isinstance(now, datetime) else (now or datetime.now(IST).date())
    action = str(call.get("action") or "").upper()
    ltp, target, stop = _num(ltp), _num(call.get("target")), _num(call.get("stop"))
    if ltp is not None and ltp > 0 and action in ("BUY", "SELL"):
        if action == "BUY":
            if target is not None and ltp >= target:
                return "hit_target"
            if stop is not None and ltp <= stop:
                return "hit_stop"
        else:
            if target is not None and ltp <= target:
                return "hit_target"
            if stop is not None and ltp >= stop:
                return "hit_stop"
    try:
        called = date.fromisoformat(str(call.get("call_date"))[:10])
    except ValueError:
        return None
    if (today - called).days > CALL_EXPIRY_DAYS:
        return "expired"
    return None


def apply_outcomes(calls: list[dict], ltps: dict[str, float | None], now: datetime | None = None) -> list[dict]:
    """[{id, status, last_ltp}] for every call: the new status where one applies, else the old."""
    out = []
    for c in calls:
        ltp = _num((ltps or {}).get(clean_symbol(c.get("ticker"))))
        if ltp is None:
            ltp = _num(c.get("last_ltp"))
        new = call_outcome(c, ltp, now)
        out.append({"id": c.get("id"), "status": new or str(c.get("status") or "open"),
                    "last_ltp": ltp, "changed": new is not None})
    return out


# ── portfolio ─────────────────────────────────────────────────────────────────
def holdings_from_book(book: dict | None) -> tuple[list[dict], list[dict]]:
    """Shares CFO /portfolio → (holdings rows, account statuses). A degraded account yields no
    rows and a status with its reason; an unreachable bridge yields nothing but the error."""
    holdings, accounts = [], []
    if not isinstance(book, dict) or book.get("error"):
        err = (book or {}).get("error") if isinstance(book, dict) else "no book"
        return [], [{"account": "*", "ok": False, "reason": f"Shares CFO unreachable: {err}", "fetched_at": None, "n": 0}]
    for acc in book.get("accounts") or []:
        key = str(acc.get("label") or acc.get("creds_key") or "?")
        ok = bool(acc.get("ok", True)) and str(acc.get("status") or "ok") == "ok"
        rows = acc.get("holdings") or [] if ok else []
        n = 0
        for h in rows:
            t = clean_symbol(h.get("ticker"))
            qty = _num(h.get("quantity") if h.get("quantity") is not None else h.get("qty"))
            if not t or not qty:
                continue
            holdings.append({"account": key, "ticker": t, "qty": qty,
                             "avg_price": _num(h.get("average_price") if h.get("average_price") is not None else h.get("avg_price")),
                             "ltp": _num(h.get("last_price") if h.get("last_price") is not None else h.get("ltp")),
                             "source": f"sharescfo:{acc.get('creds_key') or key}"})
            n += 1
        accounts.append({"account": key, "ok": ok, "reason": str(acc.get("reason") or "")[:200],
                         "fetched_at": acc.get("fetched_at") or book.get("as_of"), "n": n})
    return holdings, accounts


# ── HDFC Securities portfolio export (CSV) ───────────────────────────────────
# "Stock Name" in the export is HDFC's own code (ZOMATOEQ, VSNLTDEQ), not the NSE symbol.
# Strip the series suffix, then map. A code outside this table keeps the stripped code and is
# flagged "unverified ticker" — never guessed. Seed list: Aditi's export, 2026-10-09.
HDFC_CODE_MAP = {
    "AZAD": "AZAD", "BANMAH": "MAHABANK", "BORGLW": "BORORENEW", "MAPMYINDIA": "MAPMYINDIA", "DIXON": "DIXON",
    "DLFLTD": "DLF", "DYNTEC": "DYNAMATECH", "ZOMATO": "ETERNAL", "FEDFINA": "FEDFINA", "FILIND": "FILATEX",
    "FCL": "FCL", "HAPPYFORGE": "HAPPYFORGE", "HAL": "HAL", "HINCOP": "HINDCOPPER", "HINZIN": "HINDZINC",
    "IDFCBANK": "IDFCFIRSTB", "IPCLAB": "IPCALAB", "JIOFIN": "JIOFIN", "MCX": "MCX", "NETFIN": "NETWORK18",
    "NORTHARC": "NORTHARC", "NUVAMA": "NUVAMA", "HOUPEA": "PGIL", "POWFIN": "PFC", "PROTEAN": "PROTEAN",
    "RELINF": "RIIL", "ROLEXRINGS": "ROLEXRINGS", "SANSERA": "SANSERA", "JARITEX": "SGMART", "SHYAMMETL": "SHYAMMETL",
    "SONACOMS": "SONACOMS", "STEOPT": "STLTECH", "VSNLTD": "TATACOMM", "TATELX": "TATAELXSI", "TATPOW": "TATAPOWER",
    "HUGTEL": "TTML", "WOCLTD": "WOCKPHARMA", "ZAGGLE": "ZAGGLE",
    # 2026-10-09 refresh left eight codes unresolved by name. These three are in NSE EQUITY_L (matched on
    # the VPS list by ISIN and by NSE-spelled name); the HDFC export spells the name differently
    # ("A V T NATURAL PRODUCTS", "PCBL CHEMICALS", "SARDA ENERGY & MINERRALS"), so the normaliser missed.
    # Not in EQUITY_L. Verified by the 2026-10-09 worker (BSE scrip codes / the ETF's NSE symbol) and seeded
    # here as structured entries: {"bse": code} = BSE-only, priced from Yahoo as <code>.BO (the ticker stays the
    # HDFC code); {"nse": symbol} = listed on NSE under another symbol. JAIASS (Jaiprakash Associates) is NOT
    # mapped: see UNPRICED below — it stays unpriced with the reason until Aman says otherwise.
    "AVTNAT": "AVTNPL", "PHICAR": "PCBL", "RAIALL": "SARDAEN",
    "DIATEA": {"bse": "530959", "name": "Diana Tea"},
    "DUROFLX": {"bse": "512229", "name": "Veritas (India)"},
    "JSGLEASING": {"bse": "542866", "name": "Colab Platforms"},
    "HDFCMFGETF": {"nse": "HDFCGOLD", "name": "HDFC Gold ETF"},
}
# Tickers with no price by Aman's standing: the flag text is the reason, shown on every row (Directive 17),
# never a blank. Keyed by the ticker the holding is stored under.
UNPRICED = {
    "JAIASS": "withdrawn from trading 18 Jun 2026 — awaiting Aman's instruction",
}
HDFC_CSV_COLUMNS = ("Stock Name", "Company Name", "CMP", "Invested Value", "Average Cost Value",
                    "Unrealized Profit/Loss", "Current Value", "Qty")
_HDFC_SERIES = re.compile(r"(EQ|IQ|BE|BZ|SM|ST)$")


def _strip_code(code: Any) -> str:
    raw = re.sub(r"[^A-Z0-9&-]", "", str(code or "").strip().upper())
    return (_HDFC_SERIES.sub("", raw) or raw) if raw else ""


def map_entry(code: Any) -> dict | None:
    """The HDFC_CODE_MAP entry for a code, normalised: {"ticker", "bse", "nse", "name"} or None. A plain string
    entry is an NSE symbol; a dict entry carries {"bse": scrip code} and/or {"nse": symbol}."""
    stripped = _strip_code(code)
    if not stripped or stripped not in HDFC_CODE_MAP:
        return None
    ent = HDFC_CODE_MAP[stripped]
    if isinstance(ent, str):
        return {"ticker": ent, "nse": ent, "bse": "", "name": ""}
    nse = str(ent.get("nse") or "").strip().upper()
    bse = str(ent.get("bse") or "").strip()
    return {"ticker": nse or stripped, "nse": nse, "bse": bse, "name": str(ent.get("name") or "")}


def hdfc_code_to_ticker(code: Any) -> tuple[str, bool]:
    """'ZOMATOEQ' → ('ETERNAL', True); 'DIATEAEQ' → ('DIATEA', True) (BSE-only, see map_entry);
    'DECGOLEQ' → ('DECGOL', False)."""
    stripped = _strip_code(code)
    if not stripped:
        return "", False
    ent = map_entry(stripped)
    if ent:
        return ent["ticker"], True
    return stripped, False


def hdfc_code_bse(code: Any) -> str:
    """The BSE scrip code the map carries for an HDFC code ('DIATEAEQ' → '530959'), else ''."""
    ent = map_entry(code)
    return ent["bse"] if ent else ""


def bse_code_for(ticker: Any, hdfc_code: Any = "", stored: Any = "") -> str:
    """The BSE scrip code to price a holding with: the stored column first, then the map by HDFC code, then
    the map by the ticker itself (a BSE-only holding keeps the HDFC code as its ticker)."""
    for cand in (stored, hdfc_code_bse(hdfc_code), hdfc_code_bse(ticker)):
        c = str(cand or "").strip()
        if c.isdigit():
            return c
    return ""


def unpriced_note(ticker: Any) -> str:
    return UNPRICED.get(clean_symbol(ticker), "")


# ── NSE equity list: resolve an HDFC code by company name ───────────────────
# The seed map covers ~40 codes; the four family exports carry ~260. NSE's official list
# (SYMBOL, NAME OF COMPANY) is downloaded on the VPS, cached in the data dir for 7 days, and
# matched on a normalised company name: exact first, then unique prefix. Tests never touch the
# network — they pass a parsed fixture.
NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NSE_CACHE_FILE = "EQUITY_L.csv"
NSE_CACHE_DAYS = 7
_NAME_DROP = {"LIMITED", "LTD", "LTD.", "INDIA", "THE", "CO", "CO.", "COMPANY", "PVT", "PRIVATE", "AND", "&", "OF"}


def data_dir() -> str:
    """Persistent scratch for caches (the Docker data volume next to the DB), never the repo."""
    return os.environ.get("SHARE_MASTER_DATA_DIR", os.path.join(
        os.path.dirname(os.path.abspath(os.environ.get("VEGA_DB_PATH", "/data/vega_data.db"))), "share_master"))


def norm_company(name: Any) -> str:
    s = re.sub(r"[^A-Z0-9 ]+", " ", str(name or "").upper().replace("&", " AND "))
    toks = [t for t in s.split() if t not in _NAME_DROP]
    return " ".join(toks)


def parse_nse_equity_list(text: str | bytes) -> dict:
    """EQUITY_L.csv → {"by_name": {norm_name: SYMBOL}, "by_isin": {ISIN: SYMBOL}, "names": [...] sorted, "count": n}."""
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", "replace")
    by_name: dict[str, str] = {}
    by_isin: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(str(text or "").lstrip("﻿"))):
        row = {_hkey(k): (v or "").strip() for k, v in row.items() if k}
        sym, name = row.get("symbol", ""), row.get("name of company", "")
        if not sym or not name:
            continue
        key = norm_company(name)
        if key and key not in by_name:
            by_name[key] = sym.upper()
        isin = row.get("isin number", "").upper()
        if _ISIN.fullmatch(isin) and isin not in by_isin:
            by_isin[isin] = sym.upper()
    return {"by_name": by_name, "by_isin": by_isin, "names": sorted(by_name), "count": len(by_name)}


def fetch_nse_equity_list(timeout: float = 20.0) -> str | None:
    """Raw CSV text from NSE, or None. Never raises (monkeypatched in tests)."""
    try:
        req = urllib.request.Request(NSE_EQUITY_URL, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8-sig", "replace")
    except Exception:
        return None


def nse_equity_list(force: bool = False) -> dict:
    """The parsed list, from the 7-day cache in data_dir() or a fresh download. A download
    failure falls back to a stale cache; no cache at all → an empty list (nothing resolves by
    name, codes stay unverified) and the import reply says so."""
    path = os.path.join(data_dir(), NSE_CACHE_FILE)
    text, age_days = None, None
    try:
        st = os.stat(path)
        age_days = (datetime.now().timestamp() - st.st_mtime) / 86400
        if not force and age_days <= NSE_CACHE_DAYS:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
    except OSError:
        pass
    if text is None:
        fresh = fetch_nse_equity_list()
        if fresh and "SYMBOL" in fresh[:200].upper():
            text = fresh
            try:
                os.makedirs(data_dir(), exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(fresh)
                os.replace(tmp, path)
                age_days = 0
            except OSError:
                pass
        elif age_days is not None:                       # stale cache beats nothing
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                text = None
    out = parse_nse_equity_list(text) if text else {"by_name": {}, "by_isin": {}, "names": [], "count": 0}
    out["cache_age_days"] = round(age_days, 1) if age_days is not None else None
    out["source"] = "cache" if text and age_days is not None and age_days > 0 else ("download" if text else "none")
    return out


def resolve_by_name(company: Any, nse: dict | None = None) -> tuple[str, str] | None:
    """(SYMBOL, how) from the NSE list by normalised company name — exact, then unique prefix
    either way (HDFC truncates: "RELIANCE INDUSTRIAL INFRA"), only when the shorter side is long
    enough to mean something ("TATA" alone never resolves). None when nothing is certain."""
    key = norm_company(company)
    by_name = (nse or {}).get("by_name") or {}
    if key and by_name:
        if key in by_name:
            return by_name[key], "nse-exact"
        if len(key) >= 8:
            cands = [n for n in by_name if n.startswith(key) or (len(n) >= 8 and key.startswith(n + " "))]
            if len(cands) == 1:
                return by_name[cands[0]], "nse-prefix"
    return None


def resolve_ticker(code: Any, company: Any = "", nse: dict | None = None) -> tuple[str, bool, str]:
    """(ticker, verified, how). Seed map first; then the NSE list by normalised company name,
    exact then unique prefix either way; else the stripped HDFC code, unverified."""
    stripped, mapped = hdfc_code_to_ticker(code)
    if mapped:
        return stripped, True, "map"
    hit = resolve_by_name(company, nse)
    if hit:
        return hit[0], True, hit[1]
    return stripped, False, "unresolved"


def resolve_ticker_isin(isin: Any, company: Any = "", nse: dict | None = None) -> tuple[str, bool, str]:
    """(ticker, verified, how) for a depository row: the NSE list's ISIN column first ("nse-isin"),
    then the name (Angel prints "TATA COMMUNICATIONS-EQ": the -EQ/-BE series suffix is dropped
    before matching); else the ISIN itself stands in as the ticker, unverified — never a guess."""
    isin = str(isin or "").strip().upper()
    by_isin = (nse or {}).get("by_isin") or {}
    if isin in by_isin:
        return by_isin[isin], True, "nse-isin"
    hit = resolve_by_name(_SERIES_SUFFIX.sub("", str(company or "").strip().upper()), nse)
    if hit:
        return hit[0], True, hit[1]
    return isin, False, "unresolved"


def holdings_from_json(doc: dict, holder: str = "", nse: dict | None = None) -> dict:
    """The CoS's transcribed exports (pf/<holder>_<date>.json), two shapes:
      HDFC-derived   {holder, holdings: [{code, ticker, name, qty, avg, cmp, cur, pl_pct}]}
      Angel-derived  {holder, broker: "Angel One", holdings: [{isin, name, qty, value, cmp, ticker}]}
    A ticker that is null or ends in '?' is unverified — re-resolved here (ISIN column, then
    company name, from the NSE list). Same reply shape as parse_hdfc_csv."""
    holder = str(holder or doc.get("holder") or "").strip()[:60]
    broker = str(doc.get("broker") or "").strip()[:40]
    holdings, skipped, unverified, seen = [], [], [], set()
    for n, h in enumerate(doc.get("holdings") or [], start=1):
        if not isinstance(h, dict):
            continue
        code = str(h.get("code") or "").strip().upper()
        isin = str(h.get("isin") or "").strip().upper()
        given = str(h.get("ticker") or "").strip().upper()
        ok = bool(given) and not given.endswith("?")
        ticker = given.rstrip("?")
        how = "given"
        if not ok and isin:
            ticker, ok, how = resolve_ticker_isin(isin, h.get("name"), nse)
        elif not ok:
            ticker, ok, how = resolve_ticker(code or ticker, h.get("name"), nse)
            ticker = ticker or given.rstrip("?")
        ticker = clean_symbol(ticker)
        qty = _num(h.get("qty"))
        if not ticker or not qty or qty <= 0:
            skipped.append({"row": n, "code": code, "reason": "no ticker or no positive qty"})
            continue
        if ticker in seen:
            skipped.append({"row": n, "code": code, "reason": f"duplicate of {ticker}"})
            continue
        seen.add(ticker)
        if not ok:
            unverified.append(ticker)
        cmp_, avg, value = _num(h.get("cmp")), _num(h.get("avg")), _num(h.get("cur") if h.get("cur") is not None else h.get("value"))
        invested = _num(h.get("invested"))
        if invested is None and avg is not None:
            invested = round(qty * avg, 2)
        if value is None and cmp_ is not None:
            value = round(qty * cmp_, 2)
        pnl = round(value - invested, 2) if value is not None and invested is not None else None
        pnl_pct = _num(h.get("pl_pct"))
        if pnl_pct is None:
            pnl_pct = _pct(pnl, invested)
        src = "angel-json" if isin or broker.lower().startswith("angel") else "hdfc-json"
        holdings.append({"holder": holder, "ticker": ticker, "hdfc_code": code[:20], "isin": isin[:12], "broker": broker or ("Angel One" if src == "angel-json" else "HDFC"),
                         "company": str(h.get("name") or "")[:120],
                         "qty": qty, "avg_price": avg, "cmp": cmp_, "invested": invested, "value": value, "pnl": pnl,
                         "pnl_pct": pnl_pct, "ticker_verified": ok, "resolved_by": how, "source": src,
                         "bse_code": bse_code_for(ticker, code, h.get("bse_code"))})
    return {"holdings": holdings, "skipped": skipped, "unverified": unverified, "holder": holder,
            "as_of": str(doc.get("as_of") or "")[:20],
            "resolved_by": {how: sum(1 for h in holdings if h["resolved_by"] == how)
                            for how in sorted({h["resolved_by"] for h in holdings})}}


# ── positions (F&O + MTF + collateral sells) ─────────────────────────────────
POSITION_KEYS = ("account", "instrument", "side", "qty", "avg", "ltp", "pl", "product")
_INSTRUMENT = re.compile(r"^(?P<und>[A-Z0-9&\-]+)\s+(?P<d>\d{1,2})-(?P<m>[A-Za-z]{3})-(?P<y>\d{2,4})(?:\s+(?P<strike>[\d.]+)\s+(?P<ot>CE|PE))?(?:\s+(?P<fut>FUT))?$")
_MONTHS = {m: i for i, m in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), start=1)}


def parse_instrument(s: Any) -> dict:
    """'NIFTY 29-Dec-26 25000 CE' → {underlying, expiry: date, strike, opt_type, kind: option};
    'BANKNIFTY 30-Oct-26 FUT' → kind future; 'POLYCAB' → kind equity. Unparseable → equity."""
    text = re.sub(r"\s+", " ", str(s or "").strip().upper())
    m = _INSTRUMENT.match(text)
    if not m:
        return {"underlying": text.split(" ")[0] if text else "", "expiry": None, "strike": None, "opt_type": None, "kind": "equity"}
    mon = _MONTHS.get(m.group("m").upper())
    y = int(m.group("y"))
    y = y + 2000 if y < 100 else y
    try:
        expiry = date(y, mon, int(m.group("d"))) if mon else None
    except ValueError:
        expiry = None
    if m.group("ot"):
        return {"underlying": m.group("und"), "expiry": expiry, "strike": _num(m.group("strike")), "opt_type": m.group("ot"), "kind": "option"}
    return {"underlying": m.group("und"), "expiry": expiry, "strike": None, "opt_type": None, "kind": "future"}


def validate_positions(items: Any) -> tuple[list[dict], list[dict]]:
    """Rows with exactly POSITION_KEYS (extra keys ignored, missing ones rejected and said)."""
    good, bad = [], []
    for n, it in enumerate(items if isinstance(items, list) else [], start=1):
        if not isinstance(it, dict):
            bad.append({"row": n, "reason": "not an object"})
            continue
        missing = [k for k in POSITION_KEYS if k not in it]
        if missing:
            bad.append({"row": n, "reason": f"missing {missing}"})
            continue
        acc, inst = str(it["account"] or "").strip()[:40], re.sub(r"\s+", " ", str(it["instrument"] or "").strip())[:80]
        side = str(it["side"] or "").strip().upper()
        if not acc or not inst or side not in ("BUY", "SELL"):
            bad.append({"row": n, "reason": "account, instrument and side BUY|SELL are required"})
            continue
        good.append({"account": acc, "instrument": inst, "side": side, "qty": _num(it["qty"]), "avg": _num(it["avg"]),
                     "ltp": _num(it["ltp"]), "pl": _num(it["pl"]), "product": str(it["product"] or "").strip().upper()[:20]})
    return good, bad


def position_rows(rows: list[dict], now: datetime | date | None = None) -> list[dict]:
    """Adds kind, expiry, days_to_expiry and premium_left (= qty × ltp, options only)."""
    today = now.date() if isinstance(now, datetime) else (now or datetime.now(IST).date())
    out = []
    for r in rows:
        p = parse_instrument(r.get("instrument"))
        d = dict(r)
        d["kind"], d["underlying"], d["strike"], d["opt_type"] = p["kind"], p["underlying"], p["strike"], p["opt_type"]
        d["expiry"] = p["expiry"].isoformat() if p["expiry"] else None
        d["days_to_expiry"] = (p["expiry"] - today).days if p["expiry"] else None
        qty, ltp = _num(r.get("qty")), _num(r.get("ltp"))
        d["premium_left"] = round(qty * ltp, 2) if p["kind"] == "option" and qty is not None and ltp is not None else None
        out.append(d)
    out.sort(key=lambda d: (d["account"], d["days_to_expiry"] if d["days_to_expiry"] is not None else 10 ** 6, d["instrument"]))
    return out


def positions_summary(rows: list[dict]) -> dict:
    per: dict[str, dict] = {}
    for r in rows:
        a = per.setdefault(r["account"], {"account": r["account"], "n": 0, "pl": 0.0, "premium_left": 0.0, "options": 0,
                                          "nearest_expiry": None, "nearest_days": None, "as_of": r.get("as_of")})
        a["n"] += 1
        a["pl"] += r.get("pl") or 0
        if r.get("kind") == "option":
            a["options"] += 1
            a["premium_left"] += r.get("premium_left") or 0
        dte = r.get("days_to_expiry")
        if dte is not None and (a["nearest_days"] is None or dte < a["nearest_days"]):
            a["nearest_days"], a["nearest_expiry"] = dte, r.get("expiry")
    for a in per.values():
        a["pl"], a["premium_left"] = round(a["pl"], 2), round(a["premium_left"], 2)
    return {"accounts": sorted(per.values(), key=lambda a: a["account"]), "n": len(rows),
            "pl": round(sum(a["pl"] for a in per.values()), 2),
            "expiring_7d": sum(1 for r in rows if r.get("days_to_expiry") is not None and r["days_to_expiry"] <= 7)}


def fetch_positions_live() -> list[dict] | None:
    """Hook for the HDFC positions feed once Shares CFO reconnects (its /positions/live reply
    maps onto POSITION_KEYS). Returns None today: the source is manual, via
    POST /api/share-master/positions/import. No broker code here by Aman's instruction."""
    return None


def parse_hdfc_csv(text: str | bytes, holder: str = "", nse: dict | None = None) -> dict:
    """Raw HDFC Securities portfolio CSV → {"holdings": [...], "skipped": [...], "unverified": [...]}.
    Columns are found by header name, first occurrence (the export repeats '% Chg.'), so an extra
    trailing value or a reordered column does not matter. Numbers come from the file as written;
    '-' is None. A row without a code or a positive qty is skipped and said."""
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", "replace")
    rows = rows_from_csv(str(text or "").lstrip("﻿"))
    hdr_i = next((i for i, r in enumerate(rows) if any(_hkey(c) == "stock name" for c in r)), None)
    if hdr_i is None:
        return {"holdings": [], "skipped": [{"row": 0, "reason": "no 'Stock Name' header — is this the HDFC portfolio export?"}],
                "unverified": [], "columns": {}}
    headers = [_hkey(h) for h in rows[hdr_i]]
    idx: dict[str, int] = {}
    for name in HDFC_CSV_COLUMNS:
        k = _hkey(name)
        if k in headers:
            idx[name] = headers.index(k)
    missing = [c for c in ("Stock Name", "Qty") if c not in idx]
    if missing:
        return {"holdings": [], "skipped": [{"row": hdr_i + 1, "reason": f"missing columns {missing}"}], "unverified": [],
                "columns": {k: v for k, v in idx.items()}}

    def cell(r: list, name: str):
        i = idx.get(name)
        v = r[i] if i is not None and i < len(r) else None
        return None if v is None or str(v).strip() in ("", "-") else v

    holdings, skipped, unverified, seen = [], [], [], set()
    for n, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 2):
        code = str(cell(r, "Stock Name") or "").strip()
        if not code:
            if any(str(x or "").strip() for x in r):
                skipped.append({"row": n, "reason": "no stock code"})
            continue
        company = str(cell(r, "Company Name") or "").strip()
        ticker, ok, how = resolve_ticker(code, company, nse)
        qty = _num(cell(r, "Qty"))
        if not ticker or not qty or qty <= 0:
            skipped.append({"row": n, "code": code, "reason": "no positive qty"})
            continue
        if ticker in seen:
            skipped.append({"row": n, "code": code, "reason": f"duplicate of {ticker}"})
            continue
        seen.add(ticker)
        if not ok:
            unverified.append(ticker)
        cmp_, avg = _num(cell(r, "CMP")), _num(cell(r, "Average Cost Value"))
        invested, value, pnl = _num(cell(r, "Invested Value")), _num(cell(r, "Current Value")), _num(cell(r, "Unrealized Profit/Loss"))
        if invested is None and avg is not None:
            invested = round(qty * avg, 2)
        if value is None and cmp_ is not None:
            value = round(qty * cmp_, 2)
        if pnl is None and invested is not None and value is not None:
            pnl = round(value - invested, 2)
        holdings.append({"holder": str(holder or "").strip()[:60], "ticker": ticker, "hdfc_code": code.upper()[:20],
                         "company": company[:120], "qty": qty, "avg_price": avg,
                         "cmp": cmp_, "invested": invested, "value": value, "pnl": pnl, "pnl_pct": _pct(pnl, invested),
                         "ticker_verified": ok, "resolved_by": how, "source": "hdfc-csv", "bse_code": hdfc_code_bse(code)})
    return {"holdings": holdings, "skipped": skipped, "unverified": unverified, "columns": idx,
            "resolved_by": {how: sum(1 for h in holdings if h["resolved_by"] == how) for how in ("map", "nse-exact", "nse-prefix", "unresolved")}}


# ── Angel One "DP Transaction Cum Holding" statement (PDF → text) ───────────
# Aman uploads the PDF Angel sends (A23). `pdftotext -layout` (poppler) or pypdf turns it into text;
# each script is a block that starts with a line `INE…  NAME` and ends with its CLOSING BALANCE
# line (debit, credit, qty, amount). The same ISIN header repeats across page breaks — the last
# CLOSING line wins. qty 0 scripts (sold out) are listed as skipped, never shown as holdings.
# No average cost in a DP statement: avg/invested/P&L stay blank, cmp = amount / qty.
_ISIN = re.compile(r"IN[A-Z0-9]{10}")
_ANGEL_HEADER = re.compile(r"^\s*(?:ISIN\s*[:\-]?\s*)?(IN[A-Z0-9]{10})\s{2,}(\S.*?)\s*$")
_ANGEL_CLOSING = re.compile(r"CLOSING\s+BALANCE(.*)$", re.I)
_NUM_TOKEN = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")


def _angel_num(tok: str) -> float | None:
    return _num(tok.replace(",", ""))


def parse_angel_dp_text(text: str | bytes, holder: str = "", nse: dict | None = None) -> dict:
    """Angel One DP Transaction Cum Holding statement text → {"holdings": [...], "skipped": [...],
    "unverified": [...], "resolved_by": {...}, "scripts": n}. Ticker from the NSE list's ISIN column,
    then the company name, else the ISIN stands in, unverified."""
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    holder = str(holder or "").strip()[:60]
    scripts: dict[str, dict] = {}                   # isin → {name, qty, amount, closing_lines, first_line}
    current: str | None = None
    for ln_no, raw in enumerate(str(text or "").replace("\f", "\n").splitlines(), start=1):
        m = _ANGEL_HEADER.match(raw)
        if m:
            isin, name = m.group(1).upper(), re.sub(r"\s+", " ", m.group(2)).strip()
            sc = scripts.setdefault(isin, {"name": name, "qty": None, "amount": None, "closing_lines": 0, "first_line": ln_no, "bad": None})
            if not sc["name"]:
                sc["name"] = name
            current = isin
            continue
        c = _ANGEL_CLOSING.search(raw)
        if not c or current is None:
            continue
        nums = _NUM_TOKEN.findall(c.group(1))
        sc = scripts[current]
        if len(nums) < 4:
            sc["bad"] = f"line {ln_no}: CLOSING BALANCE has {len(nums)} number(s), need debit credit qty amount"
            continue
        _debit, _credit, qty, amount = (_angel_num(x) for x in nums[-4:])
        sc["qty"], sc["amount"], sc["closing_lines"], sc["bad"] = qty, amount, sc["closing_lines"] + 1, None
    holdings, skipped, unverified, seen = [], [], [], set()
    for isin, sc in scripts.items():
        qty, amount = sc["qty"], sc["amount"]
        if sc["closing_lines"] == 0:
            skipped.append({"isin": isin, "name": sc["name"], "reason": sc["bad"] or f"line {sc['first_line']}: no CLOSING BALANCE line"})
            continue
        if qty is None or qty <= 0:
            skipped.append({"isin": isin, "name": sc["name"], "reason": f"closing qty {qty if qty is not None else '?'} — not held"})
            continue
        ticker, ok, how = resolve_ticker_isin(isin, sc["name"], nse)
        if ticker in seen:
            skipped.append({"isin": isin, "name": sc["name"], "reason": f"duplicate of {ticker}"})
            continue
        seen.add(ticker)
        if not ok:
            unverified.append(ticker)
        cmp_ = round(amount / qty, 2) if amount is not None else None
        holdings.append({"holder": holder, "broker": "Angel One", "isin": isin, "ticker": ticker, "hdfc_code": "",
                         "company": sc["name"][:120], "name": sc["name"][:120], "qty": qty, "avg_price": None, "cmp": cmp_,
                         "invested": None, "value": amount, "pnl": None, "pnl_pct": None,
                         "ticker_verified": ok, "resolved_by": how, "source": "angel-dp",
                         "closing_lines": sc["closing_lines"]})
    return {"holdings": holdings, "skipped": skipped, "unverified": unverified, "scripts": len(scripts),
            "resolved_by": {how: sum(1 for h in holdings if h["resolved_by"] == how) for how in ("nse-isin", "nse-exact", "nse-prefix", "unresolved")}}


def pdf_to_text(data: bytes, timeout: float = 60.0) -> str:
    """PDF bytes → text, layout preserved: `pdftotext -layout` when poppler is installed, else
    pypdf (layout mode). Raises ValueError when neither can read it."""
    errs = []
    if shutil.which("pdftotext"):
        try:
            r = subprocess.run(["pdftotext", "-layout", "-", "-"], input=data, capture_output=True, timeout=timeout)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace")
            errs.append(f"pdftotext rc={r.returncode} {r.stderr.decode('utf-8', 'replace')[:120].strip()}")
        except Exception as e:
            errs.append(f"pdftotext: {type(e).__name__}: {str(e)[:120]}")
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        pages = []
        for pg in reader.pages:
            try:
                pages.append(pg.extract_text(extraction_mode="layout") or "")
            except TypeError:                         # older pypdf: no layout mode
                pages.append(pg.extract_text() or "")
        text = "\f".join(pages)
        if text.strip():
            return text
        errs.append("pypdf: no text layer (scanned image?)")
    except ImportError:
        errs.append("pypdf not installed")
    except Exception as e:
        errs.append(f"pypdf: {type(e).__name__}: {str(e)[:120]}")
    raise ValueError("PDF text could not be extracted — " + "; ".join(errs))


def holdings_from_csv_rows(rows: list[dict]) -> list[dict]:
    """share_master_holdings rows → the holdings shape portfolio_rows() takes. The account is the
    holder; an unverified code carries the note so the tab says so."""
    out = []
    for r in rows:
        out.append({"account": str(r.get("holder") or "?"), "ticker": r.get("ticker"), "qty": r.get("qty"),
                    "avg_price": r.get("avg_price"), "ltp": r.get("cmp"), "company": r.get("company") or "",
                    "ticker_verified": bool(r.get("ticker_verified", 1)), "hdfc_code": r.get("hdfc_code") or "",
                    "bse_code": bse_code_for(r.get("ticker"), r.get("hdfc_code"), r.get("bse_code")),
                    "source": f"{r.get('source') or 'hdfc-csv'} {str(r.get('uploaded_at') or '')[:10]}".strip()})
    return out


def bse_codes_for(holdings: list[dict]) -> dict[str, str]:
    """{ticker: BSE scrip code} for the holdings that carry one — the .BO fallback mdo_levels.fetch_ltp takes."""
    out: dict[str, str] = {}
    for h in holdings:
        t = clean_symbol(h.get("ticker"))
        c = bse_code_for(t, h.get("hdfc_code"), h.get("bse_code"))
        if t and c:
            out[t] = c
    return out


def flag_for(weight_pct: float | None, pnl_pct: float | None) -> str:
    flags = []
    if weight_pct is not None and weight_pct > CAP_WEIGHT_PCT:
        flags.append("CAP")
    if pnl_pct is not None:
        if pnl_pct <= L30_PCT:
            flags.append("L30")
        elif pnl_pct <= L15_PCT:
            flags.append("L15")
    return "+".join(flags)


def portfolio_rows(holdings: list[dict], ltps: dict[str, float | None] | None = None) -> list[dict]:
    """invested, value, pnl, pnl_pct, weight_pct (of the whole book's value) and the flag per
    holding. The ltp is the fetched price, else the holding's own last price, else None (then
    value/pnl/weight stay None — never a guess). Sorted account, then value desc."""
    ltps = {norm_ticker(k): _num(v) for k, v in (ltps or {}).items()}
    rows = []
    for h in holdings:
        t = clean_symbol(h.get("ticker"))
        qty, avg = _num(h.get("qty")), _num(h.get("avg_price"))
        if not t or qty is None:
            continue
        ltp = ltps.get(t)
        price_note = ""                                   # Directive 17: no price → the reason, never a blank
        unpriced = unpriced_note(t)
        if unpriced:                                      # Aman's standing (UNPRICED): no price, the reason on the row
            ltp, price_note = None, unpriced
        elif ltp is None or ltp <= 0:
            ltp = _num(h.get("ltp"))
            if ltp is not None and ltp <= 0:
                ltp = None
            price_note = ("broker/CSV price (Yahoo n/a)" if ltp is not None
                          else "price unavailable: Yahoo n/a, no broker price")
        invested = round(qty * avg, 2) if avg is not None else None
        value = round(qty * ltp, 2) if ltp is not None else None
        pnl = round(value - invested, 2) if value is not None and invested is not None else None
        rows.append({"account": str(h.get("account") or "?"), "ticker": t, "qty": qty, "avg_price": avg, "ltp": ltp,
                     "invested": invested, "value": value, "pnl": pnl, "pnl_pct": _pct(pnl, invested),
                     "weight_pct": None, "flag": "", "source": str(h.get("source") or "")[:60], "price_note": price_note,
                     "company": str(h.get("company") or "")[:120], "ticker_verified": bool(h.get("ticker_verified", True))})
    total = sum(r["value"] for r in rows if r["value"] is not None)
    for r in rows:
        r["weight_pct"] = _pct(r["value"], total) if total else None
        r["flag"] = flag_for(r["weight_pct"], r["pnl_pct"])
        if not r["ticker_verified"]:
            r["flag"] = "+".join(x for x in (r["flag"], "unverified ticker") if x)
        if unpriced_note(r["ticker"]):
            r["flag"] = "+".join(x for x in (r["flag"], unpriced_note(r["ticker"])) if x)
    rows.sort(key=lambda r: (r["account"], -(r["value"] or 0), r["ticker"]))
    return rows


def join_levels(rows: list[dict], levels: list[dict]) -> list[dict]:
    """Each held stock shows its buy/sell level when it is on Aman's list (by ticker), else None."""
    by = {norm_ticker(l.get("ticker")): l for l in levels or [] if l.get("active", True)}
    for r in rows:
        l = by.get(norm_ticker(r.get("ticker")))
        r["buy_level"] = _num(l.get("buy_level")) if l else None
        r["sell_level"] = _num(l.get("sell_level")) if l else None
        r["level_note"] = (str(l.get("note") or "")[:120] if l else "")
    return rows


# ── levels import ─────────────────────────────────────────────────────────────
_HEADERS = {
    "ticker": ("ticker", "symbol", "nse symbol", "nse", "scrip", "script", "stock", "stock name", "share",
               "share name", "name", "company", "company name", "security", "instrument", "code"),
    "buy": ("buy", "buy level", "buy at", "buy below", "buy price", "buy zone", "buy_level", "entry", "entry level",
            "entry price", "accumulate", "buy lvl", "bl"),
    "sell": ("sell", "sell level", "sell at", "sell above", "sell price", "sell zone", "sell_level", "target",
             "target price", "tgt", "exit", "exit level", "sell lvl", "sl level"),
    "note": ("note", "notes", "remark", "remarks", "comment", "comments", "view", "reason"),
}


def _hkey(h: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(h or "").lower()).strip()


def _guess_columns(headers: list[Any]) -> dict[str, int]:
    """{'ticker': col, 'buy': col, 'sell': col, 'note': col} from messy header text. Exact
    alias first, then 'contains'. The same column is never claimed twice."""
    keys = [_hkey(h) for h in headers]
    found: dict[str, int] = {}
    for field, aliases in _HEADERS.items():
        for i, k in enumerate(keys):
            if k in aliases and i not in found.values():
                found[field] = i
                break
    for field, aliases in _HEADERS.items():
        if field in found:
            continue
        for i, k in enumerate(keys):
            if i in found.values() or not k:
                continue
            if any(re.search(r"\b" + re.escape(a) + r"\b", k) for a in aliases if len(a) > 2):
                found[field] = i
                break
    return found


def parse_levels_table(rows: list, default_note: str = "") -> dict:
    """Rows from a CSV/XLSX (list of dicts, or list of lists whose first row is the header) →
    {"levels": [{ticker, buy_level, sell_level, note}], "skipped": [...], "columns": {...}}.
    A row needs a ticker and at least one positive level; a bad level is skipped and said."""
    if not rows:
        return {"levels": [], "skipped": [], "columns": {}}
    first_row = 2                                  # sheet row of the first data line (1-based, header is row 1)
    if isinstance(rows[0], dict):
        headers = list(rows[0].keys())
        body = [[r.get(h) for h in headers] for r in rows if isinstance(r, dict)]
    else:
        # the header may not be the first line (a title row above it): take the first row that maps a ticker
        headers, body = [], []
        for i, r in enumerate(rows):
            cols = _guess_columns(list(r or []))
            if "ticker" in cols and ("buy" in cols or "sell" in cols):
                headers, body = list(r), [list(x or []) for x in rows[i + 1:]]
                first_row = i + 2
                break
        if not headers:
            headers, body = list(rows[0] or []), [list(x or []) for x in rows[1:]]
    cols = _guess_columns(headers)
    if "ticker" not in cols or not ("buy" in cols or "sell" in cols):
        return {"levels": [], "skipped": [{"row": 0, "reason": f"could not find ticker + buy/sell columns in {headers!r}"}],
                "columns": {k: str(headers[v]) for k, v in cols.items()}}

    def cell(r: list, field: str):
        i = cols.get(field)
        return r[i] if i is not None and i < len(r) else None

    levels, skipped, seen = [], [], {}
    for n, r in enumerate(body, start=first_row):
        raw_t = cell(r, "ticker")
        t = clean_symbol(raw_t).replace(" ", "")
        if not t:
            if any(str(x or "").strip() for x in r):
                skipped.append({"row": n, "reason": "no ticker"})
            continue
        buy, sell = _num(cell(r, "buy")), _num(cell(r, "sell"))
        if (buy is not None and buy <= 0) or (sell is not None and sell <= 0):
            skipped.append({"row": n, "ticker": t, "reason": "level must be a positive number"})
            continue
        if buy is None and sell is None:
            skipped.append({"row": n, "ticker": t, "reason": "no buy or sell level"})
            continue
        note = str(cell(r, "note") or "").strip() or default_note
        if t in seen:                              # a repeat row merges into the first
            prev = seen[t]
            prev["buy_level"] = buy if buy is not None else prev["buy_level"]
            prev["sell_level"] = sell if sell is not None else prev["sell_level"]
            continue
        item = {"ticker": t, "buy_level": buy, "sell_level": sell, "note": note[:500]}
        seen[t] = item
        levels.append(item)
    return {"levels": levels, "skipped": skipped, "columns": {k: str(headers[v]) for k, v in cols.items()}}


def rows_from_csv(text: str) -> list[list]:
    return [row for row in csv.reader(io.StringIO(str(text or "")))]


def rows_from_xlsx(data: bytes) -> list[list]:
    """Every row of the first non-empty sheet, values only."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True) if any(c not in (None, "") for c in r)]
        if rows:
            return rows
    return []


# ── summary + workbook ────────────────────────────────────────────────────────
def summarise(rows: list[dict], calls: list[dict], levels: list[dict], accounts: list[dict] | None = None,
              as_of: str = "", positions: list[dict] | None = None) -> dict:
    per: dict[str, dict] = {}
    for r in rows:
        a = per.setdefault(r["account"], {"account": r["account"], "n": 0, "invested": 0.0, "value": 0.0, "pnl": 0.0,
                                          "flags": 0, "ok": True, "note": ""})
        a["n"] += 1
        a["invested"] += r["invested"] or 0
        a["value"] += r["value"] or 0
        a["pnl"] += r["pnl"] or 0
        a["flags"] += 1 if r["flag"] else 0
    for st in accounts or []:
        a = per.setdefault(st["account"], {"account": st["account"], "n": 0, "invested": 0.0, "value": 0.0, "pnl": 0.0,
                                           "flags": 0, "ok": True, "note": ""})
        a["ok"] = bool(st.get("ok"))
        a["note"] = st.get("note") or st.get("reason") or ""
    for a in per.values():
        for k in ("invested", "value", "pnl"):
            a[k] = round(a[k], 2)
        a["pnl_pct"] = _pct(a["pnl"], a["invested"])
    total = {"n": len(rows), "invested": round(sum(a["invested"] for a in per.values()), 2),
             "value": round(sum(a["value"] for a in per.values()), 2), "pnl": round(sum(a["pnl"] for a in per.values()), 2)}
    total["pnl_pct"] = _pct(total["pnl"], total["invested"])
    priced = [r for r in rows if r["pnl_pct"] is not None]
    gainers = sorted(priced, key=lambda r: -r["pnl_pct"])[:TOP_N]
    losers = sorted(priced, key=lambda r: r["pnl_pct"])[:TOP_N]
    counts = {s: sum(1 for c in calls if c.get("status") == s) for s in STATUSES}
    counts["total"] = len(calls)
    return {"as_of": as_of, "accounts": sorted(per.values(), key=lambda a: a["account"]), "total": total,
            "top_gainers": [{k: r[k] for k in ("account", "ticker", "pnl", "pnl_pct")} for r in gainers if r["pnl_pct"] > 0],
            "top_losers": [{k: r[k] for k in ("account", "ticker", "pnl", "pnl_pct")} for r in losers if r["pnl_pct"] < 0],
            "calls": counts, "levels": len([l for l in levels if l.get("active", True)]),
            "flagged": sum(1 for r in rows if r["flag"]),
            "unverified": sum(1 for r in rows if "unverified" in str(r.get("flag") or "")),
            "stale_accounts": [a["account"] for a in per.values() if not a["ok"]],
            "positions": positions_summary(positions or [])}


def build_workbook(rows: list[dict], calls: list[dict], levels: list[dict], as_of: str | datetime,
                   accounts: list[dict] | None = None, summary: dict | None = None,
                   positions: list[dict] | None = None, holders: dict[str, list[dict]] | None = None) -> bytes:
    """The .xlsx Aman opens: Portfolio (grouped by holder, subtotals, Holder filter), Mausaji Calls,
    Positions (F&O/MTF/collateral), Levels, Summary. Frozen headers, Indian number formats, colours
    on flags and outcomes. Every cell is a value, never a formula that needs recalculation."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    as_of_txt = as_of.astimezone(IST).strftime("%d %b %Y %H:%M IST") if isinstance(as_of, datetime) else str(as_of)
    positions = positions or []
    summary = summary or summarise(rows, calls, levels, accounts, as_of_txt, positions)
    HEAD = Font(bold=True, color="FFFFFF")
    HEAD_FILL = PatternFill("solid", fgColor="1F3A5F")
    FILLS = {"CAP": "FFE699", "L15": "F8CBAD", "L30": "FF7C80", "CAP+L15": "F4B183", "CAP+L30": "FF5050",
             "hit_target": "C6EFCE", "hit_stop": "FFC7CE", "expired": "D9D9D9", "open": "FFFFFF", "stale": "EDEDED"}
    NUM, PCT, INT = "#,##0.00", '0.00"%"', "#,##0"

    def header(ws, cols: list[str], row: int = 1):
        for i, c in enumerate(cols, start=1):
            cell = ws.cell(row=row, column=i, value=c)
            cell.font, cell.fill = HEAD, HEAD_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.freeze_panes = ws.cell(row=row + 1, column=1)

    def widths(ws, ws_widths: list[int]):
        for i, w in enumerate(ws_widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

    def fill(cell, key: str):
        color = FILLS.get(key)
        if color and color != "FFFFFF":
            cell.fill = PatternFill("solid", fgColor=color)

    wb = Workbook()
    # ── Portfolio ──
    ws = wb.active
    ws.title = "Portfolio"
    ws["A1"] = f"Portfolio — as of {as_of_txt}"
    ws["A1"].font = Font(bold=True, size=13)
    r = 2
    for st in accounts or []:
        if st.get("ok") and st.get("reason"):            # CSV-fed holder: say the upload, not "live"
            line = f"{st['account']}: {st['reason']}"
        elif st.get("ok"):
            line = f"{st['account']}: live ({st.get('n', 0)} holdings" + (f", fetched {str(st.get('fetched_at'))[:16]}" if st.get("fetched_at") else "") + ")"
        else:
            line = f"{st['account']}: {st.get('reason') or 'no data'}" + (f" — showing last snapshot {st['snap_date']}" if st.get("snap_date") else " — no snapshot on file")
        ws.cell(row=r, column=1, value=line).font = Font(italic=True, color="305496" if st.get("ok") else "C00000")
        r += 1
    if not (accounts or []):
        ws.cell(row=r, column=1, value="No broker account answered — nothing shown is invented; the table below is the last snapshot on file.").font = Font(italic=True, color="C00000")
        r += 1
    r += 1
    holders = holders or {}

    def held(ticker: Any) -> str:
        return lv.held_text(holders.get(norm_ticker(ticker)))

    cols = ["Holder", "Ticker", "Company", "Qty", "Avg price", "CMP", "Invested", "Value", "P&L", "P&L %", "Weight %",
            "Buy ≤", "Sell ≥", "Flag", "Snapshot", "Source", "Held by (all holders)"]
    header_row = r
    header(ws, cols, r)
    stale = {st["account"] for st in (accounts or []) if not st.get("ok")}

    def total_row(label: str, group: list[dict], bold_fill: str | None = None):
        nonlocal r
        r += 1
        inv = round(sum(x["invested"] or 0 for x in group), 2)
        val = round(sum(x["value"] or 0 for x in group), 2)
        pnl = round(val - inv, 2) if group else 0.0
        vals = [label, f"{len(group)} holdings", "", "", "", "", inv, val, pnl, _pct(pnl, inv), None, "", "", "", "", "", ""]
        for i, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.font = Font(bold=True)
            if i in (7, 8, 9):
                c.number_format = NUM
            elif i == 10:
                c.number_format = PCT
            if bold_fill:
                c.fill = PatternFill("solid", fgColor=bold_fill)

    # grouped by holder (rows arrive sorted holder, value desc): holder rows, then a subtotal;
    # a grand total at the end. The Holder column carries the auto-filter so Excel filters one holder.
    holder_names: list[str] = []
    for p in rows:
        if p["account"] not in holder_names:
            holder_names.append(p["account"])
    for holder in holder_names:
        group = [p for p in rows if p["account"] == holder]
        for p in group:
            r += 1
            flag = p["flag"] + (" STALE" if p["account"] in stale else "")
            cmp_cell = p["ltp"] if p["ltp"] is not None else (p.get("price_note") or "price unavailable")   # Directive 17
            vals = [p["account"], p["ticker"], p.get("company") or "", p["qty"], p["avg_price"], cmp_cell, p["invested"], p["value"],
                    p["pnl"], p["pnl_pct"], p["weight_pct"], p.get("buy_level"), p.get("sell_level"), flag,
                    p.get("snap_date") or "", p.get("source") or "", held(p["ticker"])]
            for i, v in enumerate(vals, start=1):
                c = ws.cell(row=r, column=i, value=v)
                if i == 4:
                    c.number_format = INT
                elif i in (5, 6, 7, 8, 9, 12, 13):
                    c.number_format = NUM
                elif i in (10, 11):
                    c.number_format = PCT
            if p["ltp"] is None:
                ws.cell(row=r, column=6).font = Font(italic=True, color="C00000")
            base_flag = p["flag"].replace("+unverified ticker", "").replace("unverified ticker", "")
            if base_flag:
                fill(ws.cell(row=r, column=14), base_flag)
                fill(ws.cell(row=r, column=2), base_flag)
            if "unverified" in p["flag"]:
                fill(ws.cell(row=r, column=2), "stale")
                ws.cell(row=r, column=2).font = Font(italic=True, color="7F7F7F")
            if p["account"] in stale:
                fill(ws.cell(row=r, column=1), "stale")
            ltp = _num(p["ltp"])
            if lv.is_hit("buy", ltp, _num(p.get("buy_level"))):
                fill(ws.cell(row=r, column=12), "hit_target")
            if lv.is_hit("sell", ltp, _num(p.get("sell_level"))):
                fill(ws.cell(row=r, column=13), "hit_stop")
        total_row(f"{holder} total", group, "DDEBF7")
    if rows:
        total_row("ALL HOLDERS", rows, "BDD7EE")
    widths(ws, [14, 14, 28, 9, 11, 14, 14, 14, 13, 9, 9, 10, 10, 18, 11, 20, 30])
    ws.auto_filter.ref = f"A{header_row}:Q{max(r, header_row)}"

    # ── Mausaji Calls ──
    ws = wb.create_sheet("Mausaji Calls")
    cols = ["Date", "Ticker", "Held by", "Action", "Entry", "Target", "Stop", "Timeframe", "Status", "LTP at call", "Last LTP",
            "Last checked", "Mausaji's words", "Msg id", "Chat"]
    header(ws, cols)
    r = 1
    for c_ in sorted(calls, key=lambda c: (str(c.get("call_date") or ""), c.get("id") or 0), reverse=True):
        r += 1
        last = c_.get("last_ltp")
        if last is None and str(c_.get("status") or "open") == "open":
            last = "price unavailable (Yahoo n/a)" if c_.get("last_checked") else "not checked yet"
        vals = [c_.get("call_date"), c_.get("ticker"), held(c_.get("ticker")), c_.get("action"), c_.get("entry"), c_.get("target"),
                c_.get("stop"), c_.get("timeframe") or "", c_.get("status") or "open", c_.get("ltp_at_call"), last,
                str(c_.get("last_checked") or "")[:16], c_.get("quote") or "", c_.get("message_id"), c_.get("chat_name") or ""]
        for i, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=i, value=v)
            if i in (5, 6, 7, 10, 11):
                cell.number_format = NUM
            if i == 13:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        fill(ws.cell(row=r, column=9), str(c_.get("status") or "open"))
    widths(ws, [11, 14, 26, 8, 10, 10, 10, 12, 11, 11, 14, 17, 60, 8, 18])
    if r > 1:
        ws.auto_filter.ref = f"A1:O{r}"

    # ── Positions (F&O + MTF + collateral sells) ──
    ws = wb.create_sheet("Positions")
    cols = ["Account", "Instrument", "Kind", "Side", "Qty", "Avg", "LTP", "P&L", "Product", "Expiry", "Days to expiry",
            "Premium left (qty×ltp)", "As of", "Source"]
    header(ws, cols)
    r = 1
    pos_accounts: list[str] = []
    for p in positions:
        if p["account"] not in pos_accounts:
            pos_accounts.append(p["account"])
    for acc in pos_accounts:
        group = [p for p in positions if p["account"] == acc]
        for p in group:
            r += 1
            vals = [p["account"], p["instrument"], p.get("kind") or "", p["side"], p.get("qty"), p.get("avg"), p.get("ltp"), p.get("pl"),
                    p.get("product") or "", p.get("expiry") or "", p.get("days_to_expiry"), p.get("premium_left"),
                    str(p.get("as_of") or "")[:16], p.get("source") or "manual"]
            for i, v in enumerate(vals, start=1):
                c = ws.cell(row=r, column=i, value=v)
                if i == 5:
                    c.number_format = INT
                elif i in (6, 7, 8, 12):
                    c.number_format = NUM
            pl = _num(p.get("pl"))
            if pl is not None:
                fill(ws.cell(row=r, column=8), "hit_target" if pl >= 0 else "hit_stop")
            dte = p.get("days_to_expiry")
            if dte is not None and dte <= 7:
                fill(ws.cell(row=r, column=11), "CAP" if dte > 2 else "L30")
        r += 1
        pl_sum = round(sum(_num(p.get("pl")) or 0 for p in group), 2)
        prem = round(sum(p.get("premium_left") or 0 for p in group if p.get("kind") == "option"), 2)
        for i, v in enumerate([f"{acc} total", f"{len(group)} positions", "", "", "", "", "", pl_sum, "", "", "", prem, "", ""], start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="DDEBF7")
            if i in (8, 12):
                c.number_format = NUM
    if not positions:
        ws.cell(row=2, column=1, value="No positions on file — import via POST /api/share-master/positions/import (manual until the HDFC feed reconnects)").font = Font(italic=True, color="7F7F7F")
    widths(ws, [10, 30, 8, 6, 9, 11, 11, 14, 11, 11, 9, 16, 17, 10])
    if positions:
        ws.auto_filter.ref = f"A1:N{r}"

    # ── Levels ──
    ws = wb.create_sheet("Levels")
    cols = ["Ticker", "Buy ≤", "Best entry", "Sell ≥", "LTP", "To buy %", "To sell %", "Status", "Held by", "Note", "Active"]
    header(ws, cols)
    r = 1
    for l in levels:
        r += 1
        ltp = _num(l.get("ltp"))
        buy, sell = _num(l.get("buy_level")), _num(l.get("sell_level"))
        status = "AT BUY" if lv.is_hit("buy", ltp, buy) else ("AT SELL" if lv.is_hit("sell", ltp, sell) else "")
        vals = [l.get("ticker"), buy, _num(l.get("best_entry")), sell, ltp if ltp is not None else "price unavailable (Yahoo n/a)",
                lv.distance_pct(ltp, buy), lv.distance_pct(ltp, sell), status, held(l.get("ticker")),
                l.get("note") or "", "yes" if l.get("active", True) else "paused"]
        for i, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=i, value=v)
            if i in (2, 3, 4, 5):
                cell.number_format = NUM
            elif i in (6, 7):
                cell.number_format = PCT
        if ltp is None:
            ws.cell(row=r, column=5).font = Font(italic=True, color="C00000")
        if status:
            fill(ws.cell(row=r, column=8), "hit_target" if status == "AT BUY" else "hit_stop")
    widths(ws, [14, 11, 11, 11, 14, 10, 10, 10, 26, 40, 8])

    # ── Summary ──
    ws = wb.create_sheet("Summary")
    ws["A1"] = "Share Master — summary"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"], ws["B2"] = "Last refresh", as_of_txt
    ws["A3"], ws["B3"] = "Holdings", summary["total"]["n"]
    ws["A4"], ws["B4"] = "Stale accounts", ", ".join(summary["stale_accounts"]) or "none"
    r = 6
    header(ws, ["Account", "Holdings", "Invested", "Value", "P&L", "P&L %", "Flags", "Status"], r)
    ws.freeze_panes = None
    for a in summary["accounts"]:
        r += 1
        vals = [a["account"], a["n"], a["invested"], a["value"], a["pnl"], a["pnl_pct"], a["flags"],
                "live" if a["ok"] else (a.get("note") or "stale")]
        for i, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=i, value=v)
            if i in (3, 4, 5):
                cell.number_format = NUM
            elif i == 6:
                cell.number_format = PCT
        if not a["ok"]:
            fill(ws.cell(row=r, column=8), "hit_stop")
    r += 1
    t = summary["total"]
    for i, v in enumerate(["TOTAL", t["n"], t["invested"], t["value"], t["pnl"], t["pnl_pct"], summary["flagged"], ""], start=1):
        cell = ws.cell(row=r, column=i, value=v)
        cell.font = Font(bold=True)
        if i in (3, 4, 5):
            cell.number_format = NUM
        elif i == 6:
            cell.number_format = PCT
    r += 2
    for title, items in (("Top gainers", summary["top_gainers"]), ("Top losers", summary["top_losers"])):
        header(ws, [title, "Account", "P&L", "P&L %"], r)
        for it in items:
            r += 1
            ws.cell(row=r, column=1, value=it["ticker"])
            ws.cell(row=r, column=2, value=it["account"])
            ws.cell(row=r, column=3, value=it["pnl"]).number_format = NUM
            ws.cell(row=r, column=4, value=it["pnl_pct"]).number_format = PCT
        if not items:
            r += 1
            ws.cell(row=r, column=1, value="none")
        r += 2
    header(ws, ["Mausaji calls", "Count"], r)
    for k in ("open", "hit_target", "hit_stop", "expired", "total"):
        r += 1
        ws.cell(row=r, column=1, value=k.replace("_", " "))
        ws.cell(row=r, column=2, value=summary["calls"].get(k, 0))
    r += 2
    ws.cell(row=r, column=1, value="Levels on the list")
    ws.cell(row=r, column=2, value=summary["levels"])
    r += 2
    ps = summary.get("positions") or {"accounts": [], "n": 0, "pl": 0, "expiring_7d": 0}
    header(ws, ["Positions (account)", "Count", "P&L", "Premium left", "Nearest expiry", "Days"], r)
    for a in ps["accounts"]:
        r += 1
        for i, v in enumerate([a["account"], a["n"], a["pl"], a["premium_left"], a.get("nearest_expiry") or "", a.get("nearest_days")], start=1):
            c = ws.cell(row=r, column=i, value=v)
            if i in (3, 4):
                c.number_format = NUM
    r += 1
    for i, v in enumerate(["ALL ACCOUNTS", ps["n"], ps["pl"], "", f"{ps['expiring_7d']} expiring ≤7d", ""], start=1):
        c = ws.cell(row=r, column=i, value=v)
        c.font = Font(bold=True)
        if i == 3:
            c.number_format = NUM
    ws.freeze_panes = None
    widths(ws, [22, 14, 14, 14, 14, 10, 8, 40])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── I/O seams (monkeypatched in tests) ───────────────────────────────────────
def fetch_book(timeout: float = 25.0) -> dict:
    """Shares CFO /portfolio. {"error": ...} when unreachable or unconfigured — never raises."""
    token = os.environ.get("CFO_API_TOKEN", "").strip()
    url = f"{sharescfo_url()}/portfolio" + (f"?token={urllib.parse.quote(token)}" if token else "")
    try:
        req = urllib.request.Request(url, headers={"X-CFO-Token": token} if token else {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read() or b"{}")
        return data if isinstance(data, dict) else {"error": "bad reply"}
    except Exception as e:
        return {"error": str(e)[:200]}


def fetch_ltps(tickers: list[str], bse_codes: dict[str, str] | None = None) -> dict[str, float | None]:
    return lv.fetch_ltp(tickers, bse_codes=bse_codes) if bse_codes else lv.fetch_ltp(tickers)


def vault_dir() -> str:
    return os.environ.get("VAULT_DIR", os.path.join(
        os.path.dirname(os.path.abspath(os.environ.get("VEGA_DB_PATH", "/data/vega_data.db"))), "vault"))


def vault_write(data: bytes, rel: str = VAULT_FILE) -> str:
    """Same contract as PUT /api/vault/put: atomic, previous version kept as .prev. Returns the path."""
    full = safe_vault_path(vault_dir(), rel)
    if not full:
        raise ValueError(f"{rel}: outside the vault areas")
    if len(data) > VAULT_MAX_BYTES:
        raise ValueError(f"{rel}: {len(data)} bytes exceeds the vault limit")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if os.path.exists(full):
        shutil.copy2(full, full + ".prev")
    tmp = full + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o600)
    os.replace(tmp, full)
    return full


# ── endpoints ─────────────────────────────────────────────────────────────────
def register(app, vdb: Callable[[], Awaitable[Any]], levels: dict | None = None) -> dict:
    """Mount /api/share-master*, /api/levels/import. `levels` is mdo_levels.register()'s dict
    (levels_list + levels_set); without it the Levels tab is empty and import is refused."""
    import asyncio

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        cols = {r[1] for r in await db.execute_fetchall("PRAGMA table_info(share_master_holdings)")}
        for col in ("isin", "broker", "bse_code"):       # tables created before the Angel import / the BSE fallback
            if col not in cols:
                await db.execute(f"ALTER TABLE share_master_holdings ADD COLUMN {col} TEXT DEFAULT ''")
        await db.commit()

    async def _memory_get_json(key: str):
        db = await vdb()
        rows = await db.execute_fetchall("SELECT value FROM bot_memory WHERE bot=? AND key=? AND status='active'", (BOT_ID, key))
        if not rows:
            return None
        try:
            return json.loads(dict(rows[0])["value"] or "null")
        except ValueError:
            return None

    async def _memory_set_json(key: str, value, source: str) -> None:
        db = await vdb()
        await db.execute(
            "INSERT INTO bot_memory (bot,key,value,source,status) VALUES (?,?,?,?,'active') "
            "ON CONFLICT(bot,key) DO UPDATE SET value=excluded.value, source=excluded.source, updated_at=datetime('now')",
            (BOT_ID, key, json.dumps(value)[:4000], source[:200]))
        await db.commit()

    async def _audit(db, action: str, path: str, nbytes: int, ok: bool, note: str = ""):
        await db.execute("INSERT INTO vault_audit (action,path,bytes,actor,ok,note) VALUES (?,?,?,?,?,?)",
                         (action, path[:300], nbytes, BOT_ID, 1 if ok else 0, note[:200]))

    # ── reads ──
    async def latest_snapshot() -> tuple[list[dict], dict[str, str]]:
        """Every account's most recent snapshot rows + {account: snap_date}."""
        db = await vdb()
        dates = {r["account"]: r["d"] for r in await db.execute_fetchall(
            "SELECT account, MAX(snap_date) AS d FROM portfolio_snapshot GROUP BY account")}
        rows: list[dict] = []
        for acc, d in dates.items():
            rows += [dict(r) for r in await db.execute_fetchall(
                "SELECT * FROM portfolio_snapshot WHERE account=? AND snap_date=? ORDER BY value DESC, ticker", (acc, d))]
        return rows, dates

    async def calls_all(status: str = "", limit: int = 2000) -> list[dict]:
        db = await vdb()
        q, p = "SELECT * FROM mausaji_calls", []
        if status:
            q += " WHERE status=?"; p.append(status)
        q += " ORDER BY call_date DESC, id DESC LIMIT ?"; p.append(min(int(limit), 10000))
        return [dict(r) for r in await db.execute_fetchall(q, p)]

    async def levels_rows() -> list[dict]:
        if not levels:
            return []
        return (await levels["levels_list"]()).get("levels") or []

    async def csv_holdings_all() -> list[dict]:
        db = await vdb()
        return [dict(r) for r in await db.execute_fetchall(
            "SELECT * FROM share_master_holdings ORDER BY holder, value DESC, ticker")]

    async def csv_holders() -> dict[str, dict]:
        """{holder: {uploaded_at, n, unverified}} — what the CSV fallback can cover."""
        db = await vdb()
        out = {}
        for r in await db.execute_fetchall(
                "SELECT holder, MAX(uploaded_at) AS up, COUNT(*) AS n, SUM(CASE WHEN ticker_verified=0 THEN 1 ELSE 0 END) AS unv, "
                "MAX(source) AS src, MAX(broker) AS broker FROM share_master_holdings GROUP BY holder"):
            r = dict(r)
            out[r["holder"]] = {"uploaded_at": r["up"], "n": int(r["n"]), "unverified": int(r["unv"] or 0),
                                "source": r.get("src") or "hdfc-csv", "broker": r.get("broker") or ""}
        return out

    async def holders_map() -> dict[str, list[dict]]:
        """{ticker: [{holder, qty}]} — holdings joined by ticker across every holder (Directive 18):
        each account's latest broker snapshot, plus the CSV holders that snapshot does not cover."""
        rows, _dates = await latest_snapshot()
        seen = {(r["account"], r["ticker"]) for r in rows}
        snap_accounts = {r["account"].lower() for r in rows}
        entries = [{"holder": r["account"], "ticker": r["ticker"], "qty": r["qty"]} for r in rows]
        for r in await csv_holdings_all():
            if r["holder"].lower() in snap_accounts or (r["holder"], r["ticker"]) in seen:
                continue
            entries.append({"holder": r["holder"], "ticker": r["ticker"], "qty": r["qty"]})
        out: dict[str, list[dict]] = {}
        for e in entries:
            out.setdefault(norm_ticker(e["ticker"]), []).append({"holder": e["holder"], "qty": e["qty"]})
        for lst in out.values():
            lst.sort(key=lambda x: -(x["qty"] or 0))
        return out

    if levels and callable(levels.get("set_holders")):
        levels["set_holders"](holders_map)

    async def positions_all(now: datetime | None = None) -> list[dict]:
        db = await vdb()
        rows = [dict(r) for r in await db.execute_fetchall(
            "SELECT account, instrument, side, qty, avg, ltp, pl, product, as_of, source, imported_at FROM share_master_positions "
            "ORDER BY account, instrument")]
        return position_rows(rows, now or datetime.now(IST))

    async def positions_store(items: list[dict], as_of: str, source: str = "manual") -> dict:
        """Replace-all per account present in this import (a screenshot set is the whole book)."""
        db = await vdb()
        accounts = sorted({it["account"] for it in items})
        for acc in accounts:
            await db.execute("DELETE FROM share_master_positions WHERE account=?", (acc,))
        stamp = datetime.now(IST).isoformat(timespec="minutes")
        n = 0
        for it in items:
            await db.execute(
                "INSERT INTO share_master_positions (account, instrument, side, qty, avg, ltp, pl, product, as_of, source, imported_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account, instrument, side, product) DO UPDATE SET qty=excluded.qty, "
                "avg=excluded.avg, ltp=excluded.ltp, pl=excluded.pl, as_of=excluded.as_of, source=excluded.source, imported_at=excluded.imported_at",
                (it["account"], it["instrument"], it["side"], it["qty"], it["avg"], it["ltp"], it["pl"], it["product"],
                 str(as_of or "")[:30], str(source or "manual")[:30], stamp))
            n += 1
        await db.commit()
        return {"stored": n, "accounts": accounts, "as_of": str(as_of or "")[:30], "imported_at": stamp}

    def _csv_status(holder: str, info: dict, now: datetime) -> dict:
        up = str(info.get("uploaded_at") or "")[:10]
        try:
            age = (now.astimezone(IST).date() - date.fromisoformat(up)).days
        except ValueError:
            age = None
        fresh = age is not None and age <= CSV_STALE_DAYS
        src = str(info.get("source") or "hdfc-csv")
        angel = src.startswith("angel")
        what = "Angel One DP statement" if angel else "HDFC CSV"
        reason = (f"{what} uploaded {up} ({info.get('n', 0)} holdings; broker session not connected — {'statement' if angel else 'CSV'} is the fallback)"
                  if fresh else f"{what} from {up} is {age if age is not None else '?'} days old — upload a fresh export or reconnect the broker")
        if info.get("unverified"):
            reason += (f"; {info['unverified']} ISIN(s) not in the NSE list (unverified ticker)" if angel
                       else f"; {info['unverified']} code(s) not in the HDFC→NSE map (unverified ticker)")
        return {"account": holder, "ok": fresh, "reason": reason, "fetched_at": info.get("uploaded_at"), "n": info.get("n", 0),
                "source": src, "broker": info.get("broker") or ("Angel One" if angel else "HDFC")}

    async def account_statuses(live: list[dict] | None, dates: dict[str, str]) -> list[dict]:
        """Merge what the bridge said now with what is on file, so a silent account is named."""
        out = {st["account"]: dict(st) for st in (live or []) if st.get("account") != "*"}
        bridge_err = next((st["reason"] for st in (live or []) if st.get("account") == "*"), None)
        for acc in dates:
            out.setdefault(acc, {"account": acc, "ok": False, "reason": bridge_err or "not in today's broker reply", "n": 0})
        for acc, st in out.items():
            st["snap_date"] = dates.get(acc)
            if not st.get("ok"):
                st["note"] = f"{acc}: {st.get('reason') or 'no data'}" + (
                    f" — last snapshot {st['snap_date']}" if st.get("snap_date") else " — no snapshot on file")
            elif str(st.get("source") or "").startswith(("hdfc-", "angel-")):
                st["note"] = f"{acc}: {st.get('reason')}"
            else:
                st["note"] = f"{acc}: live, {st.get('n', 0)} holdings"
        if bridge_err and not out:
            out["*"] = {"account": "*", "ok": False, "reason": bridge_err, "note": bridge_err, "n": 0, "snap_date": None}
        return sorted(out.values(), key=lambda s: s["account"])

    async def state(live_accounts: list[dict] | None = None, now: datetime | None = None) -> dict:
        now = now or datetime.now(IST)
        rows, dates = await latest_snapshot()
        for r in rows:
            r.pop("id", None); r.pop("created_at", None)
            r["ticker_verified"] = "unverified" not in str(r.get("flag") or "")
        if live_accounts is None:                     # a plain GET: what the last refresh saw, plus the CSV holders on file
            live_accounts = await _memory_get_json(ACCOUNTS_KEY) or []
            csv_now = {h: _csv_status(h, info, now) for h, info in (await csv_holders()).items()}
            live_accounts = [st for st in live_accounts if st.get("account") not in csv_now or st.get("ok")]
            live_accounts += [st for h, st in csv_now.items() if h.lower() not in {str(s["account"]).lower() for s in live_accounts}]
        accounts = await account_statuses(live_accounts, dates)
        calls = await calls_all()
        lvls = await levels_rows()
        join_levels(rows, lvls)
        holders = await holders_map()
        for c_ in calls:                               # Directive 18: every list says who holds the share
            c_["held_by"] = holders.get(norm_ticker(c_.get("ticker")), [])
            c_["held_text"] = lv.held_text(c_["held_by"])
        positions = await positions_all(now)
        summary = summarise(rows, calls, lvls, accounts, now.strftime("%d %b %Y %H:%M IST"), positions)
        last = max(dates.values(), default=None)
        return {"as_of": now.isoformat(), "portfolio": {"rows": rows, "accounts": accounts, "snap_date": last},
                "calls": calls, "levels": lvls, "positions": positions, "positions_source": "manual (CoS-transcribed); HDFC feed hook pending",
                "holders": holders, "complete": True,
                "summary": summary, "vault_file": VAULT_FILE, "mausaji_chat": mausaji_chat()}

    async def holdings_store(items: list[dict], holder: str) -> dict:
        """Replace the holder's CSV holdings with this upload (the export is the whole account)."""
        db = await vdb()
        await db.execute("DELETE FROM share_master_holdings WHERE holder=?", (holder,))
        stamp = datetime.now(IST).isoformat(timespec="minutes")
        for h in items:
            await db.execute(
                "INSERT INTO share_master_holdings (holder, ticker, hdfc_code, company, qty, avg_price, cmp, invested, value, pnl, "
                "pnl_pct, ticker_verified, source, uploaded_at, isin, broker, bse_code) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(holder, ticker) DO UPDATE SET qty=excluded.qty, avg_price=excluded.avg_price, cmp=excluded.cmp, "
                "invested=excluded.invested, value=excluded.value, pnl=excluded.pnl, pnl_pct=excluded.pnl_pct, "
                "ticker_verified=excluded.ticker_verified, uploaded_at=excluded.uploaded_at, company=excluded.company, hdfc_code=excluded.hdfc_code, "
                "source=excluded.source, isin=excluded.isin, broker=excluded.broker, bse_code=excluded.bse_code",
                (holder, h["ticker"], h.get("hdfc_code") or "", h.get("company") or "", h.get("qty"), h.get("avg_price"), h.get("cmp"),
                 h.get("invested"), h.get("value"), h.get("pnl"), h.get("pnl_pct"), 1 if h.get("ticker_verified", True) else 0,
                 str(h.get("source") or "hdfc-csv")[:30], stamp, str(h.get("isin") or "")[:12], str(h.get("broker") or "")[:40],
                 bse_code_for(h["ticker"], h.get("hdfc_code"), h.get("bse_code"))[:12]))
        await db.commit()
        return {"holder": holder, "stored": len(items), "uploaded_at": stamp}

    # ── writes ──
    async def calls_insert(items: list[dict]) -> dict:
        db = await vdb()
        inserted, dups, bad = [], 0, 0
        for it in items or []:
            if not isinstance(it, dict):
                bad += 1
                continue
            t, a, mid = clean_symbol(it.get("ticker"))[:40], _action(it.get("action")), _int(it.get("message_id"))
            if not t or not a or mid is None:
                bad += 1
                continue
            cur = await db.execute(
                "INSERT OR IGNORE INTO mausaji_calls (call_date, ticker, action, entry, target, stop, timeframe, quote, "
                "message_id, chat_name, ltp_at_call) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (str(it.get("call_date") or date.today().isoformat())[:10], t, a, _num(it.get("entry")), _num(it.get("target")),
                 _num(it.get("stop")), str(it.get("timeframe") or "")[:40], str(it.get("quote") or "")[:QUOTE_MAX], mid,
                 str(it.get("chat_name") or "")[:200], _num(it.get("ltp_at_call"))))
            if cur.rowcount:
                inserted.append({"id": cur.lastrowid, "ticker": t, "action": a, "message_id": mid})
            else:
                dups += 1
        await db.commit()
        return {"inserted": len(inserted), "duplicates": dups, "rejected": bad, "calls": inserted}

    async def snapshot_store(rows: list[dict], snap_date: str) -> int:
        """Today's snapshot for an account is exactly what this refresh saw: rows of the same
        (snap_date, account) that are not in this batch go (e.g. the CSV copy once the broker
        session is live again). Other accounts' rows are untouched."""
        db = await vdb()
        n = 0
        for acc in sorted({r["account"] for r in rows}):
            await db.execute("DELETE FROM portfolio_snapshot WHERE snap_date=? AND account=?", (snap_date, acc))
        for r in rows:
            await db.execute(
                "INSERT INTO portfolio_snapshot (snap_date, account, ticker, qty, avg_price, ltp, invested, value, pnl, pnl_pct, "
                "weight_pct, flag, source, company) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(snap_date, account, ticker) DO UPDATE SET "
                "qty=excluded.qty, avg_price=excluded.avg_price, ltp=excluded.ltp, invested=excluded.invested, value=excluded.value, "
                "pnl=excluded.pnl, pnl_pct=excluded.pnl_pct, weight_pct=excluded.weight_pct, flag=excluded.flag, source=excluded.source, "
                "company=excluded.company",
                (snap_date, r["account"], r["ticker"], r["qty"], r["avg_price"], r["ltp"], r["invested"], r["value"], r["pnl"],
                 r["pnl_pct"], r["weight_pct"], r["flag"], r["source"], r.get("company") or ""))
            n += 1
        await db.commit()
        return n

    async def outcomes_update(ltps: dict[str, float | None], now: datetime) -> dict:
        db = await vdb()
        open_calls = await calls_all(status="open")
        changes = apply_outcomes(open_calls, ltps, now)
        stamp = now.isoformat(timespec="minutes")
        counts = {"hit_target": 0, "hit_stop": 0, "expired": 0, "checked": len(open_calls)}
        for ch in changes:
            await db.execute("UPDATE mausaji_calls SET status=?, last_ltp=?, last_checked=? WHERE id=?",
                             (ch["status"], ch["last_ltp"], stamp, ch["id"]))
            if ch["changed"]:
                counts[ch["status"]] += 1
        # a call parsed today without a price at the time gets today's price as its reference
        today = now.date().isoformat()
        await db.execute_fetchall("SELECT 1")
        for c in open_calls:
            if c.get("ltp_at_call") is None and str(c.get("extracted_at") or "")[:10] in (today, now.astimezone(IST).date().isoformat()):
                px = _num(ltps.get(clean_symbol(c["ticker"])))
                if px is not None:
                    await db.execute("UPDATE mausaji_calls SET ltp_at_call=? WHERE id=? AND ltp_at_call IS NULL", (px, c["id"]))
        await db.commit()
        return counts

    async def refresh(now: datetime | None = None, build: bool = True) -> dict:
        """Portfolio snapshot from the bridge → prices → outcomes → workbook → vault. The Mausaji
        parse (the only LLM step) is the bot's job; this endpoint never spends."""
        now = now or datetime.now(IST)
        book = await asyncio.to_thread(fetch_book)
        holdings, live_accounts = holdings_from_book(book)
        # CSV fallback: a holder whose broker session is not live today is served from the last
        # HDFC export Aman uploaded (match on the account label / creds key, case-insensitive).
        live_ok = {str(st["account"]).lower() for st in live_accounts if st.get("ok")}
        csv_rows = await csv_holdings_all()
        by_holder: dict[str, list[dict]] = {}
        for r in csv_rows:
            by_holder.setdefault(r["holder"], []).append(r)
        for holder, hrows in by_holder.items():
            if holder.lower() in live_ok:
                continue
            holdings += holdings_from_csv_rows(hrows)
            live_accounts = [st for st in live_accounts if str(st["account"]).lower() != holder.lower()]
            live_accounts.append(_csv_status(holder, {"uploaded_at": max(str(r.get("uploaded_at") or "") for r in hrows),
                                                      "n": len(hrows), "unverified": sum(1 for r in hrows if not r.get("ticker_verified", 1)),
                                                      "source": max(str(r.get("source") or "") for r in hrows) or "hdfc-csv",
                                                      "broker": max(str(r.get("broker") or "") for r in hrows)}, now))
        lvls = await levels_rows()
        open_calls = await calls_all(status="open")
        tickers = sorted({h["ticker"] for h in holdings} | {clean_symbol(c["ticker"]) for c in open_calls}
                         | {norm_ticker(l.get("ticker")) for l in lvls})
        bse = bse_codes_for(holdings)                    # BSE-only holdings: Yahoo <scrip code>.BO after the NSE pass
        ltps = (await asyncio.to_thread(fetch_ltps, tickers, bse) if bse else await asyncio.to_thread(fetch_ltps, tickers)) if tickers else {}
        for l in lvls:                                   # the Levels tab shows the freshest price we have
            t = norm_ticker(l.get("ticker"))
            if _num(ltps.get(t)) is not None:
                l["ltp"] = ltps[t]
        rows = portfolio_rows(holdings, ltps)
        snap_date = now.astimezone(IST).date().isoformat()
        stored = await snapshot_store(rows, snap_date) if rows else 0
        outcomes = await outcomes_update(ltps, now)
        await _memory_set_json(ACCOUNTS_KEY, [{k: st_.get(k) for k in ("account", "ok", "reason", "fetched_at", "n", "source")}
                                              for st_ in live_accounts], f"{BOT_ID} refresh {now:%Y-%m-%d %H:%M}")
        st = await state(live_accounts, now)
        st["levels"] = lvls
        st["summary"] = summarise(st["portfolio"]["rows"], st["calls"], lvls, st["portfolio"]["accounts"],
                                  now.strftime("%d %b %Y %H:%M IST"), st["positions"])
        result = {"snap_date": snap_date, "stored": stored, "outcomes": outcomes,
                  "ltp_missing": sorted({h["ticker"] for h in holdings if _num(ltps.get(h["ticker"])) is None}),
                  "ltp_missing_other": sorted(t for t in tickers if _num(ltps.get(t)) is None and t not in {h["ticker"] for h in holdings}), **st}
        if build:
            data = build_workbook(st["portfolio"]["rows"], st["calls"], lvls, now, st["portfolio"]["accounts"], st["summary"],
                                  st["positions"], st["holders"])
            db = await vdb()
            try:
                path = await asyncio.to_thread(vault_write, data)
                await _audit(db, "put", VAULT_FILE, len(data), True, "share-master refresh")
                result["vault"] = {"path": VAULT_FILE, "bytes": len(data), "saved": True, "file": path}
            except Exception as e:
                await _audit(db, "put", VAULT_FILE, len(data), False, str(e)[:200])
                result["vault"] = {"path": VAULT_FILE, "bytes": len(data), "saved": False, "error": str(e)[:200]}
            await db.commit()
        return result

    async def mausaji_messages(since_id: int = 0, limit: int = MAUSAJI_MAX_PER_RUN) -> dict:
        """Mausaji's own messages (from_me=0) after the watermark, oldest first."""
        db = await vdb()
        pat = f"%{mausaji_chat().lower()}%"
        rows = [dict(r) for r in await db.execute_fetchall(
            "SELECT id, group_name, sender, text, timestamp, jid, chat_kind, from_me FROM whatsapp_messages "
            "WHERE lower(group_name) LIKE ? AND COALESCE(from_me, 0)=0 AND id > ? AND text != '' ORDER BY id LIMIT ?",
            (pat, int(since_id), min(int(limit), 5000)))]
        total = await db.execute_fetchall("SELECT COUNT(*) AS n FROM whatsapp_messages WHERE lower(group_name) LIKE ?", (pat,))
        return {"chat": mausaji_chat(), "messages": rows, "count": len(rows),
                "max_id": max((r["id"] for r in rows), default=int(since_id)),
                "chat_total": int(dict(total[0])["n"]) if total else 0}

    # ── routes ──
    @app.get("/api/share-master")
    async def share_master_get():
        return await state()

    @app.get("/api/share-master/xlsx")
    async def share_master_xlsx():
        from starlette.responses import Response
        now = datetime.now(IST)
        st = await state(None, now)
        data = build_workbook(st["portfolio"]["rows"], st["calls"], st["levels"], now, st["portfolio"]["accounts"], st["summary"],
                              st["positions"], st["holders"])
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="Share_Master_{now:%Y-%m-%d}.xlsx"'})

    @app.post("/api/share-master/refresh")
    async def share_master_refresh(body: dict | None = None):
        body = body or {}
        return await refresh(build=body.get("build", True) in (True, 1, "1", "true"))

    @app.get("/api/share-master/mausaji/messages")
    async def share_master_mausaji(since_id: int = 0, limit: int = MAUSAJI_MAX_PER_RUN):
        return await mausaji_messages(since_id, limit)

    @app.post("/api/share-master/calls")
    async def share_master_calls_post(body: dict):
        items = body.get("calls")
        if not isinstance(items, list):
            raise HTTPException(400, "body must be {\"calls\": [...]}")
        return await calls_insert(items)

    @app.get("/api/share-master/calls")
    async def share_master_calls_get(status: str = "", limit: int = 500):
        if status and status not in STATUSES:
            raise HTTPException(400, f"status must be one of {', '.join(STATUSES)}")
        calls = await calls_all(status, limit)
        return {"calls": calls, "count": len(calls)}

    @app.post("/api/share-master/portfolio/import")
    async def portfolio_import(request: Request, holder: str = "", dry_run: int = 0, broker: str = ""):
        """A broker export, as Aman downloads it. Accepts multipart (fields `file` + `holder`, optional
        `broker`), raw text/csv with ?holder=, or JSON {"csv": "...", "holder": "..."} / {"holder", "holdings": [...]}
        (the CoS's transcribed pf/*.json, HDFC- or Angel-derived) / {"holder", "broker": "angel", "text": "..."}.
        broker=angel (or a .pdf upload) means an Angel One DP Transaction Cum Holding statement: a PDF is
        turned into text (pdftotext -layout, else pypdf) and parsed by parse_angel_dp_text; otherwise the
        HDFC Securities portfolio CSV. Replaces that holder's uploaded holdings; the daily refresh uses them
        whenever the broker session for that holder is not live. Nothing from the file is written to the repo."""
        ctype = (request.headers.get("content-type") or "").lower()
        text, dry, raw, fname = "", bool(dry_run), b"", ""
        if ctype.startswith("multipart/"):
            try:
                form = await request.form()
            except Exception as e:
                raise HTTPException(400, f"multipart body could not be read: {str(e)[:120]}")
            up = form.get("file") or form.get("csv")
            if up is None:
                raise HTTPException(400, "multipart needs a 'file' field")
            if hasattr(up, "read"):
                raw = await up.read()
                fname = str(getattr(up, "filename", "") or "").lower()
            else:
                raw = str(up).encode()
            holder = holder or str(form.get("holder") or "")
            broker = broker or str(form.get("broker") or "")
            dry = dry or str(form.get("dry_run") or "") in ("1", "true")
        doc = None
        if ctype.startswith("application/json"):
            try:
                body = json.loads((await request.body()) or b"{}")
            except json.JSONDecodeError:
                raise HTTPException(400, "bad json")
            if not isinstance(body, dict):
                raise HTTPException(400, "body must be an object")
            text = str(body.get("csv") or body.get("text") or "")
            if not text and body.get("csv_base64"):
                text = base64.b64decode(str(body["csv_base64"])).decode("utf-8-sig", "replace")
            if not text and body.get("pdf_base64"):
                raw, fname = base64.b64decode(str(body["pdf_base64"])), "upload.pdf"
            if isinstance(body.get("holdings"), list):      # the CoS's transcribed export (pf/<holder>_<date>.json)
                doc = body
            holder = holder or str(body.get("holder") or "")
            broker = broker or str(body.get("broker") or "")
            dry = dry or bool(body.get("dry_run"))
        elif not ctype.startswith("multipart/"):
            raw = await request.body()
        holder = re.sub(r"\s+", " ", holder).strip()[:60]
        if not holder:
            raise HTTPException(400, "holder is required — whose account is this export? (e.g. Aditi)")
        angel = broker.strip().lower().startswith("angel") or fname.endswith(".pdf") or raw[:5] == b"%PDF-"
        if raw and (fname.endswith(".pdf") or raw[:5] == b"%PDF-"):
            try:
                text = await asyncio.to_thread(pdf_to_text, raw)
            except Exception as e:
                raise HTTPException(400, f"PDF could not be read: {str(e)[:200]}")
        elif raw:
            text = raw.decode("utf-8-sig", "replace")
        if doc is None and not text.strip():
            raise HTTPException(400, "empty file")
        nse = await asyncio.to_thread(nse_equity_list)          # cached 7 days; no network when the cache is fresh
        if doc is not None:
            parsed = holdings_from_json(doc, holder, nse)
        elif angel:
            parsed = parse_angel_dp_text(text, holder, nse)
        else:
            parsed = parse_hdfc_csv(text, holder, nse)
        parsed["nse_list"] = {"count": nse.get("count", 0), "isins": len(nse.get("by_isin") or {}), "source": nse.get("source"),
                              "cache_age_days": nse.get("cache_age_days")}
        parsed["format"] = "angel-dp" if (doc is None and angel) else ("json" if doc is not None else "hdfc-csv")
        if not parsed["holdings"]:
            raise HTTPException(400, {"detail": "no holdings parsed", **{k: v for k, v in parsed.items() if k != "holdings"}})
        if dry:
            return {"dry_run": True, "holder": holder, "count": len(parsed["holdings"]), **parsed}
        res = await holdings_store(parsed["holdings"], holder)
        return {**res, "count": len(parsed["holdings"]), "unverified": parsed["unverified"], "skipped": parsed["skipped"],
                "resolved_by": parsed.get("resolved_by"), "nse_list": parsed["nse_list"], "format": parsed["format"],
                "scripts": parsed.get("scripts"),
                "holdings": [{k: h.get(k) for k in ("ticker", "hdfc_code", "isin", "company", "qty", "avg_price", "cmp", "value", "pnl_pct", "ticker_verified", "resolved_by")}
                             for h in parsed["holdings"]]}

    @app.post("/api/share-master/positions/import")
    async def positions_import(body: dict):
        """Body: {"positions": [{account, instrument, side, qty, avg, ltp, pl, product}, ...], "as_of": "...",
        "source": "manual"}. Exactly those keys per row. Replace-all per account present in the list.
        Manual for now (Aman's screenshots transcribed by the CoS); fetch_positions_live() is the hook
        for the HDFC feed once Shares CFO reconnects."""
        items = body.get("positions")
        if not isinstance(items, list) or not items:
            raise HTTPException(400, "body must be {\"positions\": [...]} with at least one row")
        good, bad = validate_positions(items)
        if bad and not good:
            raise HTTPException(400, {"detail": "no valid positions", "rejected": bad})
        if body.get("dry_run"):
            return {"dry_run": True, "valid": len(good), "rejected": bad, "positions": position_rows(good)}
        res = await positions_store(good, str(body.get("as_of") or ""), str(body.get("source") or "manual"))
        return {**res, "rejected": bad, "summary": positions_summary(await positions_all())}

    @app.get("/api/share-master/holders")
    async def holders_get():
        """Who holds what: {ticker: [{holder, qty}]} across every holder. levels-alert reads this so each
        WhatsApp line says 'held: Aman 500, Aditi 100' or 'held: nobody' (Directive 18)."""
        h = await holders_map()
        return {"holders": h, "tickers": len(h), "as_of": datetime.now(IST).isoformat()}

    @app.get("/api/share-master/positions")
    async def positions_get():
        rows = await positions_all()
        return {"positions": rows, "count": len(rows), "summary": positions_summary(rows),
                "source": "manual (CoS-transcribed); HDFC feed hook pending"}

    @app.get("/api/share-master/portfolio/csv")
    async def portfolio_csv_get():
        rows = await csv_holdings_all()
        return {"holdings": rows, "holders": await csv_holders(), "count": len(rows)}

    @app.post("/api/levels/import")
    async def levels_import(request: Request):
        """Body: {"rows": [...]} (dicts or lists, header first) | {"csv": "text"} | {"xlsx_base64": "..."},
        plus optional "note", "dry_run": true. Each parsed row is upserted on its own, so one bad row
        never blocks the rest; the reply lists what went in and what was skipped and why."""
        if not levels:
            raise HTTPException(503, "levels module not mounted")
        try:
            body = json.loads((await request.body()) or b"{}")
        except json.JSONDecodeError:
            raise HTTPException(400, "bad json")
        if not isinstance(body, dict):
            raise HTTPException(400, "body must be an object")
        rows = body.get("rows")
        if rows is None and body.get("csv"):
            rows = rows_from_csv(str(body["csv"]))
        if rows is None and body.get("xlsx_base64"):
            try:
                rows = rows_from_xlsx(base64.b64decode(str(body["xlsx_base64"])))
            except Exception as e:
                raise HTTPException(400, f"xlsx could not be read: {str(e)[:120]}")
        if not isinstance(rows, list):
            raise HTTPException(400, "send rows (list), csv (text) or xlsx_base64")
        parsed = parse_levels_table(rows, default_note=str(body.get("note") or "")[:500])
        source = str(body.get("source") or "import")[:60]
        if body.get("dry_run"):
            return {"dry_run": True, **parsed, "upserted": [], "errors": []}
        upserted, errors = [], []
        for item in parsed["levels"]:
            try:
                await levels["levels_set"](dict(item), source=source)
                upserted.append(item["ticker"])
            except HTTPException as e:
                errors.append({"ticker": item["ticker"], "reason": str(e.detail)})
        return {"upserted": upserted, "errors": errors, "skipped": parsed["skipped"], "columns": parsed["columns"],
                "count": len(upserted)}

    return {"ensure_schema": ensure_schema, "state": state, "refresh": refresh, "calls_insert": calls_insert,
            "mausaji_messages": mausaji_messages, "outcomes_update": outcomes_update, "holdings_store": holdings_store,
            "positions_store": positions_store, "holders_map": holders_map}
