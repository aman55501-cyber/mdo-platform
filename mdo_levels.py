"""Share buy/sell levels — Aman's list, every share every time, alert the moment a level is hit.

Aman, chat 2026-10-09 (market open): notify him about ALL shares on the list; ALWAYS show the
entire list — including shares not yet at their level — for both the buy and the sell side.

Two tables, mounted onto the FastAPI app by mdo_server.py via register():
  share_levels  one row per NSE symbol: buy_level (alert when ltp ≤), sell_level (alert when ltp ≥)
  level_hits    one row per (ticker, side, trading_day) — UNIQUE, so a hit alerts once per day

Pure helpers (no I/O, unit-tested): market_open, snapshot_due, distance_pct, detect_hits,
format_levels. Price fetch (fetch_ltp) is Yahoo Finance over urllib, batch first, never raises.
The bot that drives this is run_levels_alert in mdo_agent.py (fleet.yaml: levels-alert).
"""
from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request

from mdo_cos import IST

BOT_ID = "levels-alert"
MEMORY_KEY = "ltps"                      # bot_memory(bot=levels-alert, key=ltps) = {"as_of": iso, "ltps": {...}}
MARKET_OPEN = (9, 15)                    # NSE cash session, IST
MARKET_CLOSE = (15, 30)
SNAPSHOT_TIMES = ((9, 20), (12, 30), (15, 5))   # full-list pushes, IST (Aman, chat 2026-10-09)
SNAPSHOT_TOLERANCE_MIN = 8                      # the 15-min cron lands within ±8 min of each
YAHOO_QUOTE = "https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbols}"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
SUFFIXES = (".NS", ".BO")                # NSE first, BSE fallback

SCHEMA = """
CREATE TABLE IF NOT EXISTS share_levels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,                 -- NSE symbol, upper, no suffix
    exchange TEXT NOT NULL DEFAULT 'NSE',
    buy_level REAL,                              -- alert when ltp <= buy_level
    sell_level REAL,                             -- alert when ltp >= sell_level
    note TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    source TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS level_hits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('buy','sell')),
    level REAL NOT NULL, ltp REAL NOT NULL,
    hit_at TEXT DEFAULT (datetime('now')), trading_day TEXT NOT NULL,
    UNIQUE(ticker, side, trading_day)
);
CREATE INDEX IF NOT EXISTS idx_level_hits_day ON level_hits(trading_day, id);
"""


# ── pure helpers ──────────────────────────────────────────────────────────────
def norm_ticker(s: Any) -> str:
    t = str(s or "").strip().upper()
    for suf in SUFFIXES:
        if t.endswith(suf):
            t = t[: -len(suf)]
    return t


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(str(v).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def fmt_n(x: float | None) -> str:
    """3500.0 → '3,500'; 152.5 → '152.5'; 3612.57 → '3,612.57'."""
    if x is None:
        return "n/a"
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def market_open(now_ist: datetime) -> bool:
    """NSE cash session: Mon–Fri 09:15–15:30 IST. Exchange holidays are not known here;
    on a holiday the bot fetches stale prices and nothing crosses a level that did not
    already cross — acceptable, and the heartbeat still files."""
    if now_ist.weekday() > 4:
        return False
    m = now_ist.hour * 60 + now_ist.minute
    return MARKET_OPEN[0] * 60 + MARKET_OPEN[1] <= m <= MARKET_CLOSE[0] * 60 + MARKET_CLOSE[1]


def snapshot_due(now_ist: datetime, tolerance_min: int = SNAPSHOT_TOLERANCE_MIN) -> str | None:
    """'HH:MM' of the scheduled full-list time this run falls within (±tolerance), else None."""
    m = now_ist.hour * 60 + now_ist.minute
    for hh, mm in SNAPSHOT_TIMES:
        if abs(m - (hh * 60 + mm)) <= tolerance_min:
            return f"{hh:02d}:{mm:02d}"
    return None


def distance_pct(ltp: float | None, level: float | None) -> float | None:
    """% move from ltp to level: negative = level is below (a buy still to come),
    positive = level is above (a sell still to come)."""
    if ltp is None or level is None or not ltp:
        return None
    return round((level - ltp) / ltp * 100, 2)


def is_hit(side: str, ltp: float | None, level: float | None) -> bool:
    if ltp is None or level is None:
        return False
    return ltp <= level if side == "buy" else ltp >= level


def detect_hits(rows: list[dict], ltps: dict[str, float | None]) -> list[dict]:
    """Every (ticker, side) at or through its level right now. Buy: ltp ≤ buy_level.
    Sell: ltp ≥ sell_level. Inactive rows and rows with no ltp never hit."""
    out = []
    for r in rows:
        if not r.get("active", 1):
            continue
        t = norm_ticker(r.get("ticker"))
        ltp = _num(ltps.get(t))
        for side, key in (("buy", "buy_level"), ("sell", "sell_level")):
            level = _num(r.get(key))
            if is_hit(side, ltp, level):
                out.append({"ticker": t, "side": side, "level": level, "ltp": ltp})
    return out


def nearest_distance(row: dict, ltp: float | None) -> float:
    """Sort key: the smaller the % gap to either level, the higher on the list. A hit is 0.
    No ltp → sorts last (inf)."""
    if ltp is None:
        return math.inf
    gaps = []
    for side, key in (("buy", "buy_level"), ("sell", "sell_level")):
        level = _num(row.get(key))
        if level is None:
            continue
        if is_hit(side, ltp, level):
            return 0.0
        d = distance_pct(ltp, level)
        if d is not None:
            gaps.append(abs(d))
    return min(gaps) if gaps else math.inf


def _side_text(side: str, ltp: float | None, level: float | None) -> str | None:
    if level is None:
        return None
    sign = "≤" if side == "buy" else "≥"
    head = f"{side.upper()} {sign}{fmt_n(level)}"
    if ltp is None:
        return head
    if is_hit(side, ltp, level):
        return head + (" (🟢 AT BUY)" if side == "buy" else " (🔴 AT SELL)")
    d = distance_pct(ltp, level)
    return head + f" ({'−' if d < 0 else '+'}{abs(d):.1f}% away)"


def format_level_line(row: dict, ltp: float | None) -> str:
    t = norm_ticker(row.get("ticker"))
    parts = [f"{t} {'₹' + fmt_n(ltp) if ltp is not None else 'ltp n/a'}"]
    for side, key in (("buy", "buy_level"), ("sell", "sell_level")):
        s = _side_text(side, ltp, _num(row.get(key)))
        if s:
            parts.append(s)
    return " · ".join(parts)


def format_levels(rows: list[dict], ltps: dict[str, float | None], now_ist: datetime,
                  hits_today: list[dict] | None = None) -> str:
    """The whole list, nearest-to-level first, never truncated. Same text the bot pushes
    and GET /api/levels/snapshot returns."""
    rows = [r for r in rows if r.get("active", 1)]
    ltps = {norm_ticker(k): _num(v) for k, v in (ltps or {}).items()}
    ordered = sorted(rows, key=lambda r: (nearest_distance(r, ltps.get(norm_ticker(r.get("ticker")))),
                                          norm_ticker(r.get("ticker"))))
    lines = [f"Levels {now_ist.astimezone(IST):%H:%M} IST · {len(rows)} share{'s' if len(rows) != 1 else ''}"]
    if not rows:
        lines.append("(list is empty — say 'add TCS buy 3500 sell 4200' to start)")
    for r in ordered:
        lines.append(format_level_line(r, ltps.get(norm_ticker(r.get("ticker")))))
    hits = hits_today or []
    if hits:
        parts = []
        for h in hits:
            at = str(h.get("hit_at") or "")
            at = at[11:16] if len(at) >= 16 else at
            parts.append(f"{norm_ticker(h.get('ticker'))} {str(h.get('side', '')).lower()} ₹{fmt_n(_num(h.get('ltp')))}"
                         f" vs ₹{fmt_n(_num(h.get('level')))}" + (f" ({at})" if at else ""))
        lines.append("hits today: " + "; ".join(parts))
    else:
        lines.append("no level hit today")
    return "\n".join(lines)


# ── prices ────────────────────────────────────────────────────────────────────
def _http_json(url: str, timeout: float) -> Any:
    """GET → parsed JSON, or None on any failure. Never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except Exception:
        return None


def _yahoo_batch(tickers: list[str], suffix: str, timeout: float) -> dict[str, float] | None:
    """v7 quote, all symbols in one call. None when the call failed outright (then the
    caller tries the per-symbol chart endpoint, which needs no crumb)."""
    url = YAHOO_QUOTE.format(symbols=urllib.parse.quote(",".join(t + suffix for t in tickers)))
    data = _http_json(url, timeout)
    try:
        result = data["quoteResponse"]["result"]
    except (TypeError, KeyError):
        return None
    out: dict[str, float] = {}
    for q in result or []:
        sym = str(q.get("symbol") or "")
        if not sym.endswith(suffix):
            continue
        px = _num(q.get("regularMarketPrice"))
        if px is not None and px > 0:
            out[norm_ticker(sym)] = round(px, 2)
    return out


def _yahoo_chart(symbol: str, timeout: float) -> float | None:
    data = _http_json(YAHOO_CHART.format(symbol=urllib.parse.quote(symbol)), timeout)
    try:
        px = _num(data["chart"]["result"][0]["meta"].get("regularMarketPrice"))
    except (TypeError, KeyError, IndexError):
        return None
    return round(px, 2) if px is not None and px > 0 else None


def fetch_ltp(tickers: list[str], timeout: float = 10.0) -> dict[str, float | None]:
    """{ticker: last traded price} for every ticker asked, None where unknown. Never raises.

    LEVELS_PRICE_SOURCE (env, optional):
      unset / "yahoo"  Yahoo Finance: one batch quote call per suffix (.NS, then .BO for the
                       ones still missing); a symbol the batch did not answer is retried on the
                       per-symbol chart endpoint, which works where the batch call needs a crumb.
      "none"           fetch nothing (every ltp n/a) — for a day Yahoo is blocked.
      http(s)://...    a custom JSON source; "&symbols=TCS,INFY" is appended and the reply must be
                       {"TCS": 3612.5, ...} or {"ltps": {...}}.
    """
    out: dict[str, float | None] = {}
    for t in tickers:
        t = norm_ticker(t)
        if t:
            out.setdefault(t, None)
    if not out:
        return out
    src = os.environ.get("LEVELS_PRICE_SOURCE", "yahoo").strip()
    try:
        if src.lower() == "none":
            return out
        if src.lower().startswith(("http://", "https://")):
            sep = "&" if "?" in src else "?"
            data = _http_json(src + sep + "symbols=" + urllib.parse.quote(",".join(out)), timeout)
            if isinstance(data, dict):
                data = data.get("ltps", data)
                for k, v in (data or {}).items():
                    k = norm_ticker(k)
                    if k in out and _num(v) is not None:
                        out[k] = round(_num(v), 2)
            return out
        for suffix in SUFFIXES:
            missing = [t for t, v in out.items() if v is None]
            if not missing:
                break
            batch = _yahoo_batch(missing, suffix, timeout)
            if batch:
                out.update({k: v for k, v in batch.items() if k in out})
            for t in [t for t in missing if out[t] is None]:
                px = _yahoo_chart(t + suffix, min(timeout, 6.0))
                if px is not None:
                    out[t] = px
    except Exception:
        pass
    return out


# ── endpoints ─────────────────────────────────────────────────────────────────
def register(app, vdb: Callable[[], Awaitable[Any]]) -> dict:
    """Mount /api/levels*. Returns the helpers the server, the brain and the tests use."""

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def rows_all() -> list[dict]:
        db = await vdb()
        return [dict(r) for r in await db.execute_fetchall("SELECT * FROM share_levels ORDER BY ticker")]

    async def hits_for(day: str) -> list[dict]:
        db = await vdb()
        return [dict(r) for r in await db.execute_fetchall(
            "SELECT ticker, side, level, ltp, hit_at, trading_day FROM level_hits WHERE trading_day=? ORDER BY id",
            (day,))]

    async def last_ltps() -> tuple[dict[str, float | None], str | None]:
        db = await vdb()
        rows = await db.execute_fetchall("SELECT value FROM bot_memory WHERE bot=? AND key=? AND status='active'",
                                         (BOT_ID, MEMORY_KEY))
        if not rows:
            return {}, None
        try:
            data = json.loads(dict(rows[0])["value"] or "{}")
        except ValueError:
            return {}, None
        return {norm_ticker(k): _num(v) for k, v in (data.get("ltps") or {}).items()}, data.get("as_of")

    async def store_ltps(ltps: dict, as_of: str) -> None:
        db = await vdb()
        value = json.dumps({"as_of": as_of, "ltps": {norm_ticker(k): _num(v) for k, v in (ltps or {}).items()}})
        await db.execute(
            "INSERT INTO bot_memory (bot,key,value,source,status) VALUES (?,?,?,?,'active') "
            "ON CONFLICT(bot,key) DO UPDATE SET value=excluded.value, source=excluded.source, updated_at=datetime('now')",
            (BOT_ID, MEMORY_KEY, value[:2000], f"{BOT_ID} run {as_of[:16]}"))
        await db.commit()

    def decorate(r: dict, ltp: float | None) -> dict:
        buy, sell = _num(r.get("buy_level")), _num(r.get("sell_level"))
        nd = nearest_distance(r, ltp)
        return {
            **r, "ticker": norm_ticker(r.get("ticker")), "buy_level": buy, "sell_level": sell,
            "active": bool(r.get("active", 1)), "ltp": ltp,
            "buy_distance_pct": distance_pct(ltp, buy), "sell_distance_pct": distance_pct(ltp, sell),
            "at_buy": is_hit("buy", ltp, buy), "at_sell": is_hit("sell", ltp, sell),
            "nearest_pct": None if nd == math.inf else round(nd, 2),
            "line": format_level_line(r, ltp),
        }

    async def levels_list() -> dict:
        now = datetime.now(IST)
        rows = await rows_all()
        ltps, as_of = await last_ltps()
        hits = await hits_for(now.date().isoformat())
        out = [decorate(r, ltps.get(norm_ticker(r["ticker"]))) for r in rows]
        out.sort(key=lambda d: (not d["active"], d["nearest_pct"] if d["nearest_pct"] is not None else math.inf, d["ticker"]))
        return {"levels": out, "count": len(out), "active": sum(1 for d in out if d["active"]),
                "ltp_as_of": as_of, "hits_today": hits, "market_open": market_open(now),
                "as_of": now.isoformat()}

    async def levels_upsert(items: dict | list, source: str = "api") -> dict:
        """Upsert by ticker. A side that is absent from the body keeps its stored value; a side
        sent as null clears it. A row must end with at least one level."""
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list) or not items:
            raise HTTPException(400, "send one level object or a list of them")
        db = await vdb()
        done = []
        for it in items:
            if not isinstance(it, dict):
                raise HTTPException(400, "each level must be an object")
            t = norm_ticker(it.get("ticker") or it.get("symbol"))
            if not t or not t.replace("&", "").replace("-", "").isalnum():
                raise HTTPException(400, f"bad ticker: {it.get('ticker')!r} — use the NSE symbol, e.g. TCS")
            cur = await db.execute_fetchall("SELECT * FROM share_levels WHERE ticker=?", (t,))
            cur = dict(cur[0]) if cur else None
            merged = {
                "buy_level": _num(cur["buy_level"]) if cur else None,
                "sell_level": _num(cur["sell_level"]) if cur else None,
                "note": (cur["note"] if cur else "") or "",
                "active": int(cur["active"]) if cur else 1,
                "exchange": (cur["exchange"] if cur else "") or "NSE",
            }
            for key in ("buy_level", "sell_level"):
                if key in it:
                    v = _num(it[key])
                    if it[key] not in (None, "") and (v is None or v <= 0):
                        raise HTTPException(400, f"{t}: {key} must be a positive number")
                    merged[key] = v
            if "note" in it:
                merged["note"] = str(it.get("note") or "")[:500]
            if "active" in it:
                merged["active"] = 1 if it["active"] in (True, 1, "1", "true", "yes") else 0
            if "exchange" in it and it["exchange"]:
                merged["exchange"] = str(it["exchange"]).upper()[:10]
            if merged["buy_level"] is None and merged["sell_level"] is None:
                raise HTTPException(400, f"{t}: give a buy level, a sell level, or both")
            if cur:
                await db.execute(
                    "UPDATE share_levels SET buy_level=?, sell_level=?, note=?, active=?, exchange=?, source=?, "
                    "updated_at=datetime('now') WHERE ticker=?",
                    (merged["buy_level"], merged["sell_level"], merged["note"], merged["active"], merged["exchange"],
                     str(it.get("source") or source)[:60], t))
            else:
                await db.execute(
                    "INSERT INTO share_levels (ticker, exchange, buy_level, sell_level, note, active, source) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (t, merged["exchange"], merged["buy_level"], merged["sell_level"], merged["note"], merged["active"],
                     str(it.get("source") or source)[:60]))
            done.append(t)
        await db.commit()
        listing = await levels_list()
        return {"upserted": done, **listing}

    async def levels_delete(ticker: str) -> dict:
        t = norm_ticker(ticker)
        db = await vdb()
        cur = await db.execute("DELETE FROM share_levels WHERE ticker=?", (t,))
        await db.commit()
        if not cur.rowcount:
            raise HTTPException(404, f"{t} is not on the list")
        return {"deleted": t, **(await levels_list())}

    async def snapshot(now: datetime | None = None) -> dict:
        now = now or datetime.now(IST)
        rows = await rows_all()
        ltps, as_of = await last_ltps()
        hits = await hits_for(now.date().isoformat())
        return {"text": format_levels(rows, ltps, now, hits), "ltp_as_of": as_of,
                "count": sum(1 for r in rows if r.get("active", 1)), "hits_today": len(hits)}

    async def record_hits(hits: list[dict], trading_day: str, ltps: dict | None, as_of: str) -> dict:
        """INSERT OR IGNORE each hit (UNIQUE ticker+side+day → once per day); store the ltps the
        bot saw so GET /api/levels can show them. Returns which hits are NEW this run."""
        db = await vdb()
        new = []
        for h in hits or []:
            t, side = norm_ticker(h.get("ticker")), str(h.get("side") or "").lower()
            level, ltp = _num(h.get("level")), _num(h.get("ltp"))
            if not t or side not in ("buy", "sell") or level is None or ltp is None:
                continue
            cur = await db.execute(
                "INSERT OR IGNORE INTO level_hits (ticker, side, level, ltp, hit_at, trading_day) VALUES (?,?,?,?,?,?)",
                (t, side, level, ltp, as_of[:19].replace("T", " "), trading_day))
            if cur.rowcount:
                new.append({"ticker": t, "side": side, "level": level, "ltp": ltp})
        await db.commit()
        if ltps is not None:
            await store_ltps(ltps, as_of)
        return {"new": new, "hits_today": await hits_for(trading_day)}

    @app.get("/api/levels")
    async def levels_get():
        return await levels_list()

    @app.post("/api/levels")
    async def levels_post(request: Request):
        try:
            body = await request.json()            # one object or a list of them (a union body would be embedded)
        except ValueError:
            raise HTTPException(400, "body must be JSON: one level object or a list of them")
        return await levels_upsert(body, source="api")

    @app.get("/api/levels/snapshot")
    async def levels_snapshot():
        return await snapshot()

    @app.post("/api/levels/hits")
    async def levels_hits_post(body: dict):
        now = datetime.now(IST)
        return await record_hits(body.get("hits") or [], str(body.get("trading_day") or now.date().isoformat())[:10],
                                 body.get("ltps"), str(body.get("as_of") or now.isoformat()))

    @app.delete("/api/levels/{ticker}")
    async def levels_del(ticker: str):
        return await levels_delete(ticker)

    return {"ensure_schema": ensure_schema, "levels_list": levels_list, "levels_set": levels_upsert,
            "levels_delete": levels_delete, "levels_snapshot": snapshot, "record_hits": record_hits}
