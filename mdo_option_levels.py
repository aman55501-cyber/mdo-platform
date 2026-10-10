"""Option levels — a tiny watcher beside the share levels, zero capital, zero LLM.

Aman, 2026-10-09 (AMAN_PENDING A24): "NIFTY 29-Dec-26 25000 CE — alert when price goes below 30;
AA account holds 29,250." One table, one upsert endpoint, one check:

  option_levels   instrument (PK, e.g. "NIFTY 29-Dec-26 25000 CE"), alert_below, alert_above, note,
                  held (Directive 18: the holder rides on every line), active, and the crossing state
                  (last_ltp, last_state below|inside|above, last_alerted_at)

Price source: NSE's public option-chain JSON (needs a first GET to www.nseindia.com with a browser
User-Agent for cookies, then the JSON). Wrapped: on any failure the check says "option price
unavailable" and nothing is invented. Checked every 15 min in market hours from the wa-sweep mausaji
run (mdo_agent.run_wa_sweep → POST /api/levels/options/check). Push once per crossing; while still
beyond the level, repeat at most every 60 minutes. Push text:
  "NIFTY 29-Dec-26 25000 CE at 27.5 — below your 30 alert. Held: AA 29,250. Research only."
Seed: data/option_levels_import_2026-10-09.json — applied once at startup (ensure_schema → seed, marker in
bot_memory) so the self-deploying VPS needs no manual step; tools/import_levels.py POSTs the same file by hand.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request

from mdo_cos import IST
from mdo_levels import _num, fmt_n

NSE_HOME = "https://www.nseindia.com"
NSE_CHAIN = "https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
NSE_CHAIN_EQUITY = "https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
INDEX_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REPEAT_MIN = 60                       # while still beyond the level, at most one push per hour
SEED_GLOB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "option_levels_import_*.json")
SEED_MARK = ("option-levels", "seeded")   # bot_memory row: the seed file is applied once, so a deleted row stays deleted
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_INSTR = re.compile(r"^\s*(?P<sym>[A-Z&\-]+)\s+(?P<d>\d{1,2})-(?P<mon>[A-Za-z]{3})-(?P<y>\d{2}|\d{4})\s+(?P<strike>\d+(?:\.\d+)?)\s+(?P<ot>CE|PE)\s*$",
                    re.IGNORECASE)

SCHEMA = """
CREATE TABLE IF NOT EXISTS option_levels (
    instrument TEXT PRIMARY KEY,                  -- "NIFTY 29-Dec-26 25000 CE"
    symbol TEXT DEFAULT '', expiry TEXT DEFAULT '', strike REAL, opt_type TEXT DEFAULT '',
    alert_below REAL, alert_above REAL,
    note TEXT DEFAULT '', held TEXT DEFAULT '',   -- held: "AA 29,250" (Directive 18)
    active INTEGER NOT NULL DEFAULT 1,
    last_ltp REAL, last_ltp_at TEXT, last_state TEXT DEFAULT '', last_alerted_at TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
"""


# ── pure helpers ──────────────────────────────────────────────────────────────

def _query_tz(s: str) -> str:
    """'2026-10-09T08:00:00 05:30' → '+05:30': an unescaped '+' in a query string arrives as a space."""
    return re.sub(r" (\d\d:\d\d)$", r"+\1", s.strip())

def parse_instrument(s: Any) -> dict | None:
    """'NIFTY 29-Dec-26 25000 CE' → {instrument, symbol, expiry '29-Dec-2026' (NSE's spelling), strike, opt_type}."""
    m = _INSTR.match(str(s or ""))
    if not m:
        return None
    mon = MONTHS.get(m.group("mon").lower())
    if not mon:
        return None
    y = int(m.group("y"))
    y = y + 2000 if y < 100 else y
    try:
        d = datetime(y, mon, int(m.group("d")))
    except ValueError:
        return None
    sym, ot = m.group("sym").upper(), m.group("ot").upper()
    strike = float(m.group("strike"))
    expiry = f"{d.day:02d}-{d:%b}-{d.year}"
    canon = f"{sym} {d.day:02d}-{d:%b}-{d.year % 100:02d} {fmt_n(strike)} {ot}".replace(",", "")
    return {"instrument": canon, "symbol": sym, "expiry": expiry, "strike": strike, "opt_type": ot}


def price_from_chain(chain: Any, expiry: str, strike: float, opt_type: str) -> float | None:
    """records.data[*] with expiryDate == expiry and strikePrice == strike → CE/PE lastPrice, else None."""
    try:
        rows = chain["records"]["data"]
    except (TypeError, KeyError):
        return None
    for r in rows or []:
        try:
            if str(r.get("expiryDate") or "") != expiry or float(r.get("strikePrice")) != float(strike):
                continue
            leg = r.get(opt_type.upper()) or {}
            px = _num(leg.get("lastPrice"))
            return px if px is not None and px > 0 else None
        except (TypeError, ValueError, AttributeError):
            continue
    return None


def state_of(ltp: float | None, below: float | None, above: float | None) -> str:
    if ltp is None:
        return ""
    if below is not None and ltp < below:
        return "below"
    if above is not None and ltp > above:
        return "above"
    return "inside"


def should_alert(row: dict, ltp: float | None, now: datetime, repeat_min: int = REPEAT_MIN) -> tuple[bool, str]:
    """(push?, new state). Push on the crossing into below/above (state changed) and then at most every
    `repeat_min` while it stays there. Back inside → no push, state reset so the next crossing pushes again."""
    st = state_of(ltp, _num(row.get("alert_below")), _num(row.get("alert_above")))
    if st in ("", "inside"):
        return False, st
    if str(row.get("last_state") or "") != st:
        return True, st
    last = row.get("last_alerted_at")
    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00")) if last else None
    except ValueError:
        last_dt = None
    if last_dt is None:
        return True, st
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    return (now.astimezone(timezone.utc) - last_dt >= timedelta(minutes=repeat_min)), st


def alert_text(row: dict, ltp: float, state: str) -> str:
    level = _num(row.get("alert_below")) if state == "below" else _num(row.get("alert_above"))
    held = str(row.get("held") or "").strip() or "nobody"
    return f"{row['instrument']} at {fmt_n(ltp)} — {state} your {fmt_n(level)} alert. Held: {held}. Research only."


# ── NSE fetch (never raises) ──────────────────────────────────────────────────
def fetch_option_chain(symbol: str, timeout: float = 12.0) -> Any:
    """Cookie dance then the JSON. None on any failure."""
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        hdrs = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", "Referer": NSE_HOME + "/"}
        with opener.open(urllib.request.Request(NSE_HOME, headers=hdrs), timeout=timeout) as r:
            r.read(2048)
        url = (NSE_CHAIN if symbol.upper() in INDEX_SYMBOLS else NSE_CHAIN_EQUITY).format(symbol=symbol.upper())
        with opener.open(urllib.request.Request(url, headers={**hdrs, "Accept": "application/json"}), timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except Exception:
        return None


# ── endpoints ─────────────────────────────────────────────────────────────────
def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict]) -> dict:
    hooks: dict[str, Any] = {"fetch_chain": fetch_option_chain}

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()
        try:
            await seed(db)
        except Exception:
            pass                                   # a bad seed file never blocks the backend; the importer can be run by hand

    async def seed(db=None, force: bool = False) -> dict:
        """Apply the newest data/option_levels_import_*.json once (marker in bot_memory). Same rows the
        importer POSTs, so a VPS that self-deploys needs no manual step. `force` re-applies it."""
        db = db if db is not None else await vdb()
        files = sorted(glob.glob(SEED_GLOB))
        if not files:
            return {"seeded": 0, "reason": "no seed file"}
        have_mem = bool(await db.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_memory'"))
        if have_mem and not force:
            done = await db.execute_fetchall("SELECT value FROM bot_memory WHERE bot=? AND key=?", SEED_MARK)
            if done and dict(done[0])["value"] == os.path.basename(files[-1]):
                return {"seeded": 0, "reason": "already applied", "file": os.path.basename(files[-1])}
        with open(files[-1], encoding="utf-8") as f:
            doc = json.load(f)
        n = 0
        for it in doc.get("options") or []:
            p = parse_instrument(it.get("instrument"))
            below, above = _num(it.get("alert_below")), _num(it.get("alert_above"))
            if not p or (below is None and above is None):
                continue
            await db.execute(
                "INSERT INTO option_levels (instrument, symbol, expiry, strike, opt_type, alert_below, alert_above, note, held, active) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(instrument) DO UPDATE SET alert_below=excluded.alert_below, "
                "alert_above=excluded.alert_above, note=excluded.note, held=excluded.held, active=excluded.active, updated_at=datetime('now')",
                (p["instrument"], p["symbol"], p["expiry"], p["strike"], p["opt_type"], below, above,
                 str(it.get("note") or "")[:500], str(it.get("held") or "")[:120], 1 if it.get("active", 1) in (True, 1, "1") else 0))
            n += 1
        if have_mem:
            await db.execute("INSERT INTO bot_memory (bot,key,value,source,status) VALUES (?,?,?,?,'active') "
                             "ON CONFLICT(bot,key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
                             (*SEED_MARK, os.path.basename(files[-1]), "mdo_option_levels.seed"))
        await db.commit()
        return {"seeded": n, "file": os.path.basename(files[-1])}

    def _row(r) -> dict:
        d = dict(r)
        d["active"] = bool(d.get("active", 1))
        for k in ("strike", "alert_below", "alert_above", "last_ltp"):
            d[k] = _num(d.get(k))
        return d

    async def rows_all() -> list[dict]:
        db = await vdb()
        return [_row(r) for r in await db.execute_fetchall("SELECT * FROM option_levels ORDER BY instrument")]

    async def upsert(items: dict | list, source: str = "api") -> dict:
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list) or not items:
            raise HTTPException(400, "send one option level or a list of them")
        db = await vdb()
        done = []
        for it in items:
            if not isinstance(it, dict):
                raise HTTPException(400, "each option level must be an object")
            p = parse_instrument(it.get("instrument"))
            if not p:
                raise HTTPException(400, f"bad instrument: {it.get('instrument')!r} — use e.g. 'NIFTY 29-Dec-26 25000 CE'")
            cur = await db.execute_fetchall("SELECT * FROM option_levels WHERE instrument=?", (p["instrument"],))
            cur = dict(cur[0]) if cur else None
            merged = {"alert_below": _num(cur["alert_below"]) if cur else None,
                      "alert_above": _num(cur["alert_above"]) if cur else None,
                      "note": (cur["note"] if cur else "") or "", "held": (cur["held"] if cur else "") or "",
                      "active": int(cur["active"]) if cur else 1}
            for key in ("alert_below", "alert_above"):
                if key in it:
                    v = _num(it[key])
                    if it[key] not in (None, "") and (v is None or v <= 0):
                        raise HTTPException(400, f"{p['instrument']}: {key} must be a positive number")
                    merged[key] = v
            if "note" in it:
                merged["note"] = str(it.get("note") or "")[:500]
            if "held" in it:
                merged["held"] = str(it.get("held") or "")[:120]
            if "active" in it:
                merged["active"] = 1 if it["active"] in (True, 1, "1", "true", "yes") else 0
            if merged["alert_below"] is None and merged["alert_above"] is None:
                raise HTTPException(400, f"{p['instrument']}: give alert_below, alert_above, or both")
            if cur:
                await db.execute(
                    "UPDATE option_levels SET alert_below=?, alert_above=?, note=?, held=?, active=?, updated_at=datetime('now') "
                    "WHERE instrument=?",
                    (merged["alert_below"], merged["alert_above"], merged["note"], merged["held"], merged["active"], p["instrument"]))
            else:
                await db.execute(
                    "INSERT INTO option_levels (instrument, symbol, expiry, strike, opt_type, alert_below, alert_above, note, held, active) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (p["instrument"], p["symbol"], p["expiry"], p["strike"], p["opt_type"], merged["alert_below"],
                     merged["alert_above"], merged["note"], merged["held"], merged["active"]))
            done.append(p["instrument"])
        await db.commit()
        return {"upserted": done, "options": await rows_all()}

    async def delete(instrument: str) -> dict:
        p = parse_instrument(instrument)
        name = p["instrument"] if p else str(instrument or "").strip()
        db = await vdb()
        cur = await db.execute("DELETE FROM option_levels WHERE instrument=?", (name,))
        await db.commit()
        if not cur.rowcount:
            raise HTTPException(404, f"{name} is not on the option list")
        return {"deleted": name, "options": await rows_all()}

    async def check(now_v: Any = None, ltps: dict | None = None) -> dict:
        """Fetch each active instrument's last price (one chain call per symbol), apply the crossing rule,
        push, store the state. `ltps` ({instrument: price}) replaces the fetch — tests, or a manual run."""
        try:
            now = datetime.fromisoformat(_query_tz(str(now_v).replace("Z", "+00:00"))) if now_v else datetime.now(IST)
        except ValueError:
            now = datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        rows = [r for r in await rows_all() if r["active"]]
        if not rows:
            return {"checked": 0, "prices": {}, "pushed": [], "unavailable": [], "line": "no option levels set"}
        chains: dict[str, Any] = {}
        prices: dict[str, float | None] = {}
        for r in rows:
            if ltps is not None:
                prices[r["instrument"]] = _num(ltps.get(r["instrument"]))
                continue
            sym = r["symbol"]
            if sym not in chains:
                chains[sym] = await asyncio.to_thread(hooks["fetch_chain"], sym)
            prices[r["instrument"]] = price_from_chain(chains[sym], r["expiry"], r["strike"], r["opt_type"])
        db = await vdb()
        pushed, unavailable, parts = [], [], []
        stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        for r in rows:
            ltp = prices.get(r["instrument"])
            if ltp is None:
                unavailable.append(r["instrument"])
                parts.append(f"{r['instrument']} price unavailable")
                continue
            go, st = should_alert(r, ltp, now)
            sent = False
            if go:
                text = alert_text(r, ltp, st)
                try:
                    sent = bool((send_cos(text) or {}).get("sent"))
                except Exception:
                    sent = False
                if sent:
                    pushed.append(text)
            await db.execute(
                "UPDATE option_levels SET last_ltp=?, last_ltp_at=?, last_state=?, last_alerted_at=CASE WHEN ? THEN ? ELSE last_alerted_at END, "
                "updated_at=datetime('now') WHERE instrument=?",
                (ltp, stamp, st, 1 if sent else 0, stamp, r["instrument"]))
            tag = {"below": f"below {fmt_n(_num(r.get('alert_below')))}", "above": f"above {fmt_n(_num(r.get('alert_above')))}"}.get(st, "inside")
            parts.append(f"{r['instrument']} ₹{fmt_n(ltp)} ({tag}{', pushed' if sent else (', push NOT delivered' if go else '')})")
        await db.commit()
        line = "option price unavailable" if len(unavailable) == len(rows) else "option " + "; ".join(parts)
        return {"checked": len(rows), "prices": prices, "pushed": pushed, "unavailable": unavailable, "line": line,
                "as_of": now.isoformat()}

    @app.get("/api/levels/options")
    async def options_get():
        return {"options": await rows_all(), "as_of": datetime.now(IST).isoformat()}

    @app.post("/api/levels/options")
    async def options_post(request: Request):
        try:
            body = await request.json()            # one object or a list of them
        except ValueError:
            raise HTTPException(400, "body must be JSON: one option level or a list of them")
        return await upsert(body)

    @app.post("/api/levels/options/check")
    async def options_check(body: dict | None = None):
        body = body or {}
        return await check(body.get("now"), body.get("ltps") if isinstance(body.get("ltps"), dict) else None)

    @app.delete("/api/levels/options/{instrument}")
    async def options_delete(instrument: str):
        return await delete(instrument)

    def set_fetch_chain(fn) -> None:
        hooks["fetch_chain"] = fn

    return {"ensure_schema": ensure_schema, "seed": seed, "upsert": upsert, "check": check, "rows": rows_all,
            "delete": delete, "set_fetch_chain": set_fetch_chain}
