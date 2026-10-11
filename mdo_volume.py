"""volume-watch — volume, delivery % and bulk/block deals for the shares Aman holds or watches. Zero LLM, no new subscription.

Aman, chat 2026-10-11: "volume is an important measuring tool which I rarely use. Help me incorporate it more in my daily
trading as well as investing" and "bulk deals and others" from NSE. Source: NSE's archive file host, which answers our
server (the NSE API host does not — 403): the daily full bhavcopy (volume, delivery quantity, delivery %) for ~2,800 shares,
and bulk.csv / block.csv. Only the shares Aman holds (any holder) or has a level on are kept, 60 days.

Readings per share (RVOL = volume ÷ mean of the previous 20 sessions):
  distribution   down ≥ 2% on RVOL ≥ 2            → protection: held shares first
  strength       up ≥ 2% on RVOL ≥ 2
  breakout       close above the previous 20-day high on RVOL ≥ 1.5
  quiet at buy   price within 3% above (or below) the buy level on RVOL ≤ 0.8  → sellers are tired
  heavy at buy   same zone on RVOL ≥ 2             → still being sold: wait
  accumulation   delivery % ≥ 1.3× its 20-day mean while price is flat or up
  bulk / block   named client, side, quantity, price on any watched share
One WhatsApp message per trading day (≤ 10 lines, holder column on every line, Directive 18), a heartbeat on every run.
"""
from __future__ import annotations

import csv
import io
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from mdo_cos import IST
from mdo_levels import held_text, norm_ticker

BOT_ID = "volume-watch"
BHAV_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
BULK_URL = "https://nsearchives.nseindia.com/content/equities/bulk.csv"
BLOCK_URL = "https://nsearchives.nseindia.com/content/equities/block.csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
KEEP_DAYS = 60
BACKFILL_DAYS = 32          # calendar days looked back on the first run (≈ 22 sessions)
MIN_GAP_S = 1.0
SERIES_OK = ("EQ", "BE", "BZ", "SM", "ST")
PUSH_MAX = 8

SCHEMA = """
CREATE TABLE IF NOT EXISTS market_bhav (
    day TEXT NOT NULL, symbol TEXT NOT NULL, series TEXT NOT NULL DEFAULT 'EQ',
    prev_close REAL, close REAL, high REAL, low REAL, volume REAL, deliv_qty REAL, deliv_per REAL, trades REAL,
    PRIMARY KEY (day, symbol)
);
CREATE TABLE IF NOT EXISTS market_deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, kind TEXT NOT NULL, symbol TEXT NOT NULL, client TEXT NOT NULL,
    side TEXT NOT NULL, qty REAL, price REAL, pushed_at TEXT,
    UNIQUE (day, kind, symbol, client, side, qty, price)
);
CREATE TABLE IF NOT EXISTS volume_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT NOT NULL, day TEXT, symbols INTEGER, signals INTEGER,
    deals INTEGER, pushed INTEGER, line TEXT
);
"""


def _f(x: Any) -> float | None:
    try:
        s = str(x).strip().replace(",", "")
        return None if s in ("", "-", "nan") else float(s)
    except ValueError:
        return None


def parse_bhav(text: str, wanted: set[str] | None = None) -> list[dict]:
    """sec_bhavdata_full rows → [{symbol, series, day, prev_close, close, high, low, volume, deliv_qty, deliv_per, trades}]."""
    rd = csv.reader(io.StringIO(text))
    head = [h.strip().upper() for h in next(rd, [])]
    ix = {h: i for i, h in enumerate(head)}
    need = ("SYMBOL", "SERIES", "DATE1", "CLOSE_PRICE", "TTL_TRD_QNTY")
    if any(n not in ix for n in need):
        return []
    out = []
    for row in rd:
        if len(row) < len(head):
            continue
        row = [c.strip() for c in row]
        sym, series = row[ix["SYMBOL"]].upper(), row[ix["SERIES"]].upper()
        if series not in SERIES_OK or (wanted is not None and sym not in wanted):
            continue
        try:
            d = datetime.strptime(row[ix["DATE1"]], "%d-%b-%Y").date().isoformat()
        except ValueError:
            continue
        g = lambda k: _f(row[ix[k]]) if k in ix else None
        out.append({"symbol": sym, "series": series, "day": d, "prev_close": g("PREV_CLOSE"), "close": g("CLOSE_PRICE"),
                    "high": g("HIGH_PRICE"), "low": g("LOW_PRICE"), "volume": g("TTL_TRD_QNTY"), "deliv_qty": g("DELIV_QTY"),
                    "deliv_per": g("DELIV_PER"), "trades": g("NO_OF_TRADES")})
    return out


def parse_deals(text: str, kind: str) -> list[dict]:
    """bulk.csv / block.csv → [{day, kind, symbol, client, side, qty, price}]; the 'NO RECORDS' row is nothing."""
    out = []
    rd = csv.reader(io.StringIO(text))
    head = [h.strip().lower() for h in next(rd, [])]
    for row in rd:
        if len(row) < 7 or row[0].strip().upper().startswith("NO RECORDS"):
            continue
        try:
            day = datetime.strptime(row[0].strip(), "%d-%b-%Y").date().isoformat()
        except ValueError:
            continue
        side = row[4].strip().upper()
        out.append({"day": day, "kind": kind, "symbol": row[1].strip().upper(), "client": " ".join(row[3].split())[:120],
                    "side": "BUY" if side.startswith("B") else "SELL", "qty": _f(row[5]), "price": _f(row[6])})
    return out


def _get(url: str, timeout: float = 25.0) -> tuple[str | None, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": "https://www.nseindia.com/"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(12 * 1024 * 1024).decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:100]}"


def compute_signals(hist: list[dict], buy_level: float | None = None) -> list[dict]:
    """hist: that symbol's sessions, oldest→newest (≥ 2). Pure. Returns signal dicts for the LAST session."""
    if len(hist) < 2:
        return []
    last, prior = hist[-1], hist[-21:-1]
    vols = [h["volume"] for h in prior if h.get("volume")]
    if len(vols) < 8 or not last.get("volume") or not last.get("close"):
        return []
    rvol = last["volume"] / (sum(vols) / len(vols))
    base = last.get("prev_close") or prior[-1].get("close")
    chg = (last["close"] / base - 1) * 100 if base else 0.0
    out: list[dict] = []
    if chg <= -2 and rvol >= 2:
        out.append({"kind": "distribution", "rvol": rvol, "chg": chg, "text": f"↓{abs(chg):.1f}% on {rvol:.1f}× volume — heavy selling"})
    if chg >= 2 and rvol >= 2:
        out.append({"kind": "strength", "rvol": rvol, "chg": chg, "text": f"↑{chg:.1f}% on {rvol:.1f}× volume — strength"})
    highs = [h.get("high") or h.get("close") for h in prior if h.get("close")]
    if highs and last["close"] > max(highs) and rvol >= 1.5:
        out.append({"kind": "breakout", "rvol": rvol, "chg": chg, "text": f"closed above the 20-day high on {rvol:.1f}× volume — breakout"})
    if buy_level and last["close"] <= buy_level * 1.03:
        if rvol <= 0.8:
            out.append({"kind": "quiet-at-buy", "rvol": rvol, "chg": chg,
                        "text": f"at/near buy ₹{buy_level:,.0f} (close ₹{last['close']:,.1f}) on {rvol:.1f}× volume — sellers are tired"})
        elif rvol >= 2:
            out.append({"kind": "heavy-at-buy", "rvol": rvol, "chg": chg,
                        "text": f"at/near buy ₹{buy_level:,.0f} (close ₹{last['close']:,.1f}) on {rvol:.1f}× volume — still being sold, wait"})
    dels = [h["deliv_per"] for h in prior if h.get("deliv_per")]
    if dels and last.get("deliv_per") and last["deliv_per"] >= 1.3 * (sum(dels) / len(dels)) and chg >= -0.5:
        out.append({"kind": "accumulation", "rvol": rvol, "chg": chg,
                    "text": f"delivery {last['deliv_per']:.0f}% vs {sum(dels) / len(dels):.0f}% usual, price {chg:+.1f}% — accumulation"})
    return out


ICON = {"distribution": "⚠️", "strength": "📈", "breakout": "🚀", "quiet-at-buy": "🟢", "heavy-at-buy": "🟠", "accumulation": "🧲"}


def lakh(q: float | None) -> str:
    if q is None:
        return "?"
    return f"{q / 1e5:.1f} L" if q >= 1e5 else f"{q:,.0f}"


def push_text(day: str, signals: list[dict], deals: list[dict], held: dict[str, list[dict]]) -> str:
    d = datetime.strptime(day, "%Y-%m-%d")
    rank = {"distribution": 0, "heavy-at-buy": 1, "quiet-at-buy": 2, "breakout": 3, "strength": 4, "accumulation": 5}
    sig = sorted(signals, key=lambda s: (0 if held.get(s["symbol"]) else 1, rank.get(s["kind"], 9), -s["rvol"]))
    lines = [f"Volume · {d:%a %d %b} · {len(signals)} signal{'s' if len(signals) != 1 else ''}, {len(deals)} bulk/block deal{'s' if len(deals) != 1 else ''}"]
    room = PUSH_MAX
    for s in sig[:room]:
        lines.append(f"{ICON.get(s['kind'], '•')} {s['symbol']} {s['text']} (held: {held_text(held.get(s['symbol']))})")
    room = max(0, PUSH_MAX - min(len(sig), PUSH_MAX)) + 2
    for x in sorted(deals, key=lambda x: -(x["qty"] or 0))[:room]:
        lines.append(f"🏦 {x['kind']} {x['symbol']}: {x['client'][:34]} {'bought' if x['side'] == 'BUY' else 'sold'} {lakh(x['qty'])} @ ₹{x['price'] or 0:,.2f} (held: {held_text(held.get(x['symbol']))})")
    extra = len(sig) - PUSH_MAX + len(deals) - room
    if extra > 0:
        lines.append(f"+{extra} more on the dashboard")
    return "\n".join(lines)


def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict], share_master: dict | None = None) -> dict:
    import asyncio
    import time

    hooks: dict[str, Any] = {"get": _get}

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def _table(db, name: str) -> bool:
        return bool(await db.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)))

    async def universe() -> tuple[set[str], dict[str, float]]:
        """(symbols held by anyone or on the levels list, {symbol: buy_level})"""
        db = await vdb()
        syms: set[str] = set()
        buys: dict[str, float] = {}
        if await _table(db, "share_master_holdings"):
            for r in await db.execute_fetchall("SELECT DISTINCT ticker FROM share_master_holdings WHERE COALESCE(ticker_verified,1)=1"):
                t = norm_ticker(dict(r)["ticker"])
                if t:
                    syms.add(t)
        if await _table(db, "share_levels"):
            for r in await db.execute_fetchall("SELECT ticker, buy_level, active FROM share_levels"):
                r = dict(r)
                t = norm_ticker(r["ticker"])
                if t:
                    syms.add(t)
                    if r["active"] and r["buy_level"]:
                        buys[t] = float(r["buy_level"])
        return syms, buys

    async def holders() -> dict[str, list[dict]]:
        if share_master and share_master.get("holders_map"):
            try:
                return await share_master["holders_map"]()
            except Exception:
                pass
        db = await vdb()
        out: dict[str, list[dict]] = {}
        if await _table(db, "share_master_holdings"):
            for r in await db.execute_fetchall("SELECT holder, ticker, qty FROM share_master_holdings ORDER BY holder"):
                r = dict(r)
                out.setdefault(norm_ticker(r["ticker"]), []).append({"holder": r["holder"], "qty": r["qty"]})
        return out

    async def have_day(db, day: str) -> bool:
        return bool(await db.execute_fetchall("SELECT 1 FROM market_bhav WHERE day=? LIMIT 1", (day,)))

    async def ingest_day(db, d: date, wanted: set[str]) -> str:
        """'' stored, 'have' already stored, or the reason (holiday = HTTP 404)."""
        if await have_day(db, d.isoformat()):
            return "have"
        text, err = await asyncio.to_thread(hooks["get"], BHAV_URL.format(ddmmyyyy=d.strftime("%d%m%Y")))
        if text is None:
            return err
        rows = parse_bhav(text, wanted)
        if not rows:
            return "no rows parsed"
        await db.executemany(
            "INSERT OR REPLACE INTO market_bhav (day, symbol, series, prev_close, close, high, low, volume, deliv_qty, deliv_per, trades) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(r["day"], r["symbol"], r["series"], r["prev_close"], r["close"], r["high"], r["low"], r["volume"], r["deliv_qty"], r["deliv_per"], r["trades"]) for r in rows])
        await db.commit()
        return ""

    async def run(now_v: Any = None) -> dict:
        now = _parse_now(now_v)
        db = await vdb()
        await ensure_schema(db)
        wanted, buys = await universe()
        held = await holders()
        out: dict[str, Any] = {"as_of": now.isoformat(), "day": None, "symbols": len(wanted), "signals": [], "deals": [], "pushed": 0,
                               "push_failed": 0, "status": "clean", "line": "", "errors": []}
        if not wanted:
            out["line"] = f"{BOT_ID}: no shares held or on the levels list yet — nothing to watch"
            return out
        stored = {r[0] for r in await db.execute_fetchall("SELECT DISTINCT day FROM market_bhav")}
        first = not stored
        span = BACKFILL_DAYS if first else 7
        newest_ok = None
        fails = 0
        for back in range(span + 1):
            d = now.date() - timedelta(days=back)
            if d.weekday() > 4:
                continue
            if back > 0 and d.isoformat() in stored:
                newest_ok = newest_ok or d.isoformat()
                continue
            res = await ingest_day(db, d, wanted)
            if res in ("", "have"):
                newest_ok = newest_ok or d.isoformat()
            else:
                if res != "HTTP 404":
                    out["errors"].append(f"{d:%d-%b}: {res}")
                    fails += 1
                    if fails >= 3:
                        break
            if res == "":
                await asyncio.sleep(MIN_GAP_S if not hooks.get("fast") else 0)
        await db.execute("DELETE FROM market_bhav WHERE day < ?", ((now.date() - timedelta(days=KEEP_DAYS)).isoformat(),))
        await db.commit()
        days = [r[0] for r in await db.execute_fetchall("SELECT DISTINCT day FROM market_bhav ORDER BY day")]
        if not days:
            out["status"] = "warning"
            out["line"] = f"{BOT_ID}: no bhavcopy reachable" + (f" · {out['errors'][0]}" if out["errors"] else "")
            return out
        target = days[-1]
        out["day"] = target
        sigs: list[dict] = []
        for sym in sorted(wanted):
            hist = [dict(r) for r in await db.execute_fetchall("SELECT * FROM market_bhav WHERE symbol=? AND day<=? ORDER BY day", (sym, target))]
            if not hist or hist[-1]["day"] != target:
                continue
            for s in compute_signals(hist, buys.get(sym)):
                sigs.append({**s, "symbol": sym})
        # bulk / block deals on watched shares, once each
        deals: list[dict] = []
        for url, kind in ((BULK_URL, "bulk"), (BLOCK_URL, "block")):
            text, err = await asyncio.to_thread(hooks["get"], url)
            if text is None:
                out["errors"].append(f"{kind}: {err}")
                continue
            for x in parse_deals(text, kind):
                if x["symbol"] in wanted:
                    cur = await db.execute("INSERT OR IGNORE INTO market_deals (day, kind, symbol, client, side, qty, price) VALUES (?,?,?,?,?,?,?)",
                                           (x["day"], kind, x["symbol"], x["client"], x["side"], x["qty"], x["price"]))
                    if cur.rowcount:
                        deals.append(x)
        await db.commit()
        out["signals"], out["deals"] = sigs, deals
        already = await db.execute_fetchall("SELECT 1 FROM volume_runs WHERE day=? AND pushed=1 LIMIT 1", (target,))
        text = ""
        if (sigs or deals) and not already:
            text = push_text(target, sigs, deals, held)
            out["text"] = text
            try:
                res = send_cos(text) or {}
            except Exception as e:
                res = {"sent": False, "reason": str(e)[:200]}
            if res.get("sent"):
                out["pushed"] = 1
            else:
                out["push_failed"] = 1
                out["status"] = "warning"
        prot = sum(1 for s in sigs if s["kind"] in ("distribution", "heavy-at-buy") and held.get(s["symbol"]))
        line = (f"{BOT_ID}: {target} · {len(wanted)} shares watched, {len(sigs)} signal{'s' if len(sigs) != 1 else ''}"
                f" ({prot} on held shares to protect), {len(deals)} new bulk/block deal{'s' if len(deals) != 1 else ''}"
                + (" · 1 message pushed" if out["pushed"] else (" · push NOT delivered" if out["push_failed"] else (" · already pushed today" if already and (sigs or deals) else " · nothing to push")))
                + (f" · {out['errors'][0]}" if out["errors"] else "") + (" · first run: 30-day history loaded" if first else ""))
        out["line"] = line
        await db.execute("INSERT INTO volume_runs (ran_at, day, symbols, signals, deals, pushed, line) VALUES (?,?,?,?,?,?,?)",
                         (now.isoformat(timespec="minutes"), target, len(wanted), len(sigs), len(deals), out["pushed"], line))
        await db.commit()
        return out

    def _parse_now(v: Any) -> datetime:
        if isinstance(v, datetime):
            d = v
        else:
            try:
                d = datetime.fromisoformat(str(v).replace("Z", "+00:00").replace(" ", "+")) if v else datetime.now(IST)
            except ValueError:
                d = datetime.now(IST)
        return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(IST)

    async def latest() -> dict:
        db = await vdb()
        await ensure_schema(db)
        r = await db.execute_fetchall("SELECT * FROM volume_runs ORDER BY id DESC LIMIT 1")
        deals = [dict(x) for x in await db.execute_fetchall("SELECT * FROM market_deals ORDER BY day DESC, id DESC LIMIT 40")]
        return {"last_run": dict(r[0]) if r else None, "deals": deals}

    async def symbol_history(sym: str, days: int = 30) -> dict:
        db = await vdb()
        await ensure_schema(db)
        sym = norm_ticker(sym)
        rows = [dict(r) for r in await db.execute_fetchall("SELECT * FROM market_bhav WHERE symbol=? ORDER BY day DESC LIMIT ?", (sym, max(1, min(days, 60))))][::-1]
        out = []
        for i, r in enumerate(rows):
            prior = [x["volume"] for x in rows[max(0, i - 20):i] if x.get("volume")]
            r["rvol"] = round(r["volume"] / (sum(prior) / len(prior)), 2) if prior and r.get("volume") and len(prior) >= 8 else None
            out.append(r)
        return {"symbol": sym, "held_by": (await holders()).get(sym, []), "rows": out}

    @app.get("/api/volume/latest")
    async def volume_latest():
        return await latest()

    @app.get("/api/volume/symbol/{sym}")
    async def volume_symbol(sym: str, days: int = 30):
        return await symbol_history(sym, days)

    @app.post("/api/volume/run")
    async def volume_run(body: dict | None = None):
        body = body or {}
        if body.get("now") is not None and not isinstance(body.get("now"), str):
            raise HTTPException(400, "now must be an ISO string")
        return await run(body.get("now"))

    return {"ensure_schema": ensure_schema, "run": run, "latest": latest, "hooks": hooks}
