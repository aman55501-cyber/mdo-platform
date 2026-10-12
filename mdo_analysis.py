"""share-analysis — entry zones, near-buy and near-sell status for every share Aman holds, has a position in, or has on Mausaji's list.

Aman, chat 2026-10-12: "suggest apt entry price for each share that I don't own, which shares are near buy zone, which near sell zone ... work it
for all of my portfolio, positions and Mausaji list and create tabs in the Share Master only ... keep track of the Nifty 25000CE".

Rules (capital-rules): no fixed targets (so no target prices — only a sell ZONE, and only where a holder is in profit), never book a loss, ideas only
as proposals, holder column everywhere, no LLM (Directive 15). Technicals only: Yahoo gives no fundamentals to this server (HTTP 401), so the
fundamentals column says so instead of inventing one. Every number is computed from the last 1y of daily bars.
"""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable

from mdo_cos import IST

BOT_ID = "share-analysis"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
FUNDAMENTALS_NOTE = "no fundamentals feed (Yahoo refuses this server); upload a Screener export to add it"
NIFTY_KEY = ("NIFTY", 25000.0, "2026-12-29")          # the position Aman asked to track
NIFTY_BUY_PRICE = 222.0                                # Aman, 2026-10-12: sell only above his buy price

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ran_at TEXT NOT NULL, universe INTEGER DEFAULT 0, ok INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0, line TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS analysis_rows (
    run_id INTEGER NOT NULL, ticker TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (run_id, ticker)
);
CREATE TABLE IF NOT EXISTS nifty_ce_log (
    day TEXT PRIMARY KEY, spot REAL, vix REAL, recorded_ltp REAL, recorded_asof TEXT, model_ltp REAL, status TEXT, line TEXT
);
"""


# ═════════════════════════════════════════════════════════════════════════════
# Pure helpers
# ═════════════════════════════════════════════════════════════════════════════
def _num(v: Any) -> float | None:
    try:
        f = float(str(v).replace(",", ""))
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def parse_chart(data: Any) -> list[dict]:
    """Yahoo v8 chart JSON → bars [{d,o,h,l,c,v}] oldest first, rows with no close dropped. Never raises."""
    try:
        res = data["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return []
    out = []
    for i, t in enumerate(ts):
        try:
            c = _num(q["close"][i])
            if c is None:
                continue
            h, l, o, v = _num(q["high"][i]), _num(q["low"][i]), _num(q["open"][i]), _num(q["volume"][i])
            out.append({"d": datetime.fromtimestamp(int(t), IST).date().isoformat(), "o": o if o is not None else c,
                        "h": h if h is not None else c, "l": l if l is not None else c, "c": c, "v": v or 0.0})
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


def sma(vals: list[float], n: int) -> float | None:
    return sum(vals[-n:]) / n if len(vals) >= n else None


def rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(len(closes) - n, len(closes)):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100.0 - 100.0 / (1.0 + rs)


def atr(bars: list[dict], n: int = 14) -> float | None:
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(len(bars) - n, len(bars)):
        b, p = bars[i], bars[i - 1]
        trs.append(max(b["h"] - b["l"], abs(b["h"] - p["c"]), abs(b["l"] - p["c"])))
    return sum(trs) / n


def indicators(bars: list[dict]) -> dict:
    """Last close, 20/50/200-day averages, RSI14, ATR14, 52-week position, 20-day swing low, 60-day swing high, relative volume."""
    if len(bars) < 30:
        return {}
    closes = [b["c"] for b in bars]
    last = closes[-1]
    hi, lo = max(b["h"] for b in bars), min(b["l"] for b in bars)
    vols = [b["v"] for b in bars[-21:-1]]
    avg_v = sum(vols) / len(vols) if vols else 0.0
    return {
        "last": last, "as_of": bars[-1]["d"], "prev": closes[-2], "day_pct": (last / closes[-2] - 1) * 100,
        "sma20": sma(closes, 20), "sma50": sma(closes, 50), "sma200": sma(closes, 200), "rsi": rsi(closes), "atr": atr(bars),
        "hi52": hi, "lo52": lo, "pos52": (last - lo) / (hi - lo) * 100 if hi > lo else None,
        "swing_low20": min(b["l"] for b in bars[-20:]), "swing_high60": max(b["h"] for b in bars[-60:]),
        "rvol": (bars[-1]["v"] / avg_v) if avg_v else None, "bars": len(bars),
    }


def trend_text(ind: dict) -> str:
    last, s50, s200 = ind.get("last"), ind.get("sma50"), ind.get("sma200")
    if not last or not s50:
        return "not enough history"
    if s200 and last > s50 > s200:
        return "uptrend (above 50 and 200-day averages)"
    if s200 and last < s50 < s200:
        return "downtrend (below 50 and 200-day averages)"
    return "above 50-day average" if last > s50 else "below 50-day average"


def parse_zone(note: str) -> tuple[float | None, float | None]:
    """'… · zone 1,965 - 2,040 · …' → (1965.0, 2040.0). None, None when the note has no zone."""
    m = re.search(r"zone\s+([\d,\.]+)\s*-\s*([\d,\.]+)", note or "")
    if not m:
        return None, None
    a, b = _num(m.group(1)), _num(m.group(2))
    return (min(a, b), max(a, b)) if a is not None and b is not None else (None, None)


def source_kind(note: str) -> str:
    n = note or ""
    if "Mausaji (direct" in n:
        return "Mausaji direct"
    if "Mausaji (fwd" in n:
        return "Mausaji fwd"
    if "Mausaji (mention" in n:
        return "Mausaji mention"
    if "Mausaji" in n:
        return "Mausaji"
    return "Other"


def support_below(ind: dict) -> float | None:
    """Nearest support under the price: the highest of the 20-day swing low and the 20/50/200-day averages that sit below it."""
    last = ind.get("last") or 0
    cands = [ind.get("swing_low20")] + [ind.get(k) for k in ("sma20", "sma50", "sma200")]
    below = [c for c in cands if c and c < last]
    return max(below) if below else None


# Aman, chat 2026-10-12: "dont sell hindustan zinc". Never flagged as a sell candidate.
NO_SELL = {"HINDZINC": "Aman, 2026-10-12: do not sell Hindustan Zinc"}


def assess(ind: dict, zone: tuple[float | None, float | None], holders: list[dict], source: str = "", ticker: str = "") -> dict:
    """Status, suggested entry band, invalidation and sell-zone flag for one share. holders = [{holder, qty, avg}] (avg 0/None = cost unknown).
    No targets: the sell side is a ZONE (near resistance / stretched), reported only for holders in profit."""
    last = ind["last"]
    lo, hi = zone
    sup = support_below(ind)
    atr_ = ind.get("atr") or last * 0.03
    rsi_ = ind.get("rsi")
    status, entry_lo, entry_hi, why = "", None, None, ""
    if lo is not None and hi is not None:
        if lo * 0.99 <= last <= hi * 1.01:
            status, entry_lo, entry_hi = "IN BUY ZONE", lo, min(hi, round(last * 1.01, 2))
            why = "price is inside Mausaji's zone"
        elif last > hi * 1.01:
            gap = (last / hi - 1) * 100
            if gap <= 4:
                status, entry_lo, entry_hi = "NEAR BUY ZONE", hi, round(hi * 1.01, 2)
                why = f"{gap:.1f}% above the zone top"
            else:
                pull = max(hi, sup) if sup and sup <= last else hi
                status, entry_lo, entry_hi = "WAIT (above zone)", round(pull * 0.99, 2), round(pull * 1.01, 2)
                why = f"{gap:.1f}% above the zone top; pullback band at {'support' if pull != hi else 'zone top'}"
        else:
            status = "BELOW ZONE"
            s20 = ind.get("sma20")
            entry_lo, entry_hi = (round(s20 * 0.99, 2), round(s20 * 1.01, 2)) if s20 else (None, None)
            why = "price is under the zone; wait for a base, entry on reclaim of the 20-day average"
    else:
        if sup:
            status, entry_lo, entry_hi = "NO ZONE (technical band)", round(sup * 0.99, 2), round(sup * 1.01, 2)
            why = "no Mausaji zone; band is the nearest support"
        else:
            status, why = "NO ZONE", "no zone and no support under the price"
    base = entry_lo if entry_lo is not None else last
    invalid = round(min(ind.get("swing_low20") or base, base - 1.5 * atr_), 2) if base else None
    # sell side
    prof = [h for h in holders if (h.get("avg") or 0) > 0 and last > h["avg"]]
    unknown = [h for h in holders if not (h.get("avg") or 0) > 0]
    stretched = bool((rsi_ is not None and rsi_ >= 70) or (ind.get("pos52") is not None and ind["pos52"] >= 90)
                     or (ind.get("swing_high60") and last >= ind["swing_high60"] * 0.97))
    if ticker.upper() in NO_SELL:
        sell = "HOLD (no-sell rule: " + NO_SELL[ticker.upper()] + ")"
    elif not holders:
        sell = ""
    elif prof and stretched:
        sell = "NEAR SELL ZONE (profit holders: " + ", ".join(h["holder"] for h in prof) + ")"
    elif prof:
        sell = "HOLD (in profit, not stretched)"
    elif unknown and len(unknown) == len(holders):
        sell = "HOLD (cost unknown - fill cost price before any sale)"
    else:
        sell = "HOLD (below cost - no loss booking)"
    checks = [source == "Mausaji direct", status == "IN BUY ZONE", bool(ind.get("sma50") and last >= ind["sma50"] * 0.97),
              rsi_ is not None and 30 <= rsi_ <= 65, bool(ind.get("rvol") is not None and ind["rvol"] >= 0.8)]
    return {"status": status, "entry_low": entry_lo, "entry_high": entry_hi, "invalidation": invalid, "why": why, "sell": sell,
            "checks": sum(checks), "check_names": "direct call · in zone · not below 50-day · RSI 30-65 · volume ok"}


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(spot: float, strike: float, years: float, vol: float, rate: float = 0.065) -> float:
    """Black-Scholes call, no dividends. A model estimate, never the traded price."""
    if years <= 0 or vol <= 0:
        return max(spot - strike, 0.0)
    d1 = (math.log(spot / strike) + (rate + vol * vol / 2) * years) / (vol * math.sqrt(years))
    d2 = d1 - vol * math.sqrt(years)
    return spot * norm_cdf(d1) - strike * math.exp(-rate * years) * norm_cdf(d2)


def spot_for_price(target: float, strike: float, years: float, vol: float, lo: float = 10000.0, hi: float = 60000.0) -> float:
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs_call(mid, strike, years, vol) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 0)


def nifty_status(spot: float, vix: float, day: date, recorded_ltp: float | None, qty: float, avg: float) -> dict:
    """The Nifty 29-Dec-26 25000 CE: Aman sells only above his buy price (222). Model price uses India VIX as implied vol (an estimate)."""
    expiry = date.fromisoformat(NIFTY_KEY[2])
    years = max((expiry - day).days, 0) / 365.0
    vol = max(vix, 8.0) / 100.0
    model = bs_call(spot, NIFTY_KEY[1], years, vol)
    need_spot = spot_for_price(avg, NIFTY_KEY[1], years, vol) if years > 0 else NIFTY_KEY[1] + avg
    price = recorded_ltp if recorded_ltp is not None else model
    status = "HOLD - below buy price" if price < avg else "ABOVE BUY PRICE - Aman may sell (his click)"
    line = (f"Nifty {spot:,.0f} vs strike {NIFTY_KEY[1]:,.0f} ({(NIFTY_KEY[1] / spot - 1) * 100:+.1f}% away) · {(expiry - day).days} days left · "
            f"option {price:,.1f} vs buy {avg:,.0f} · P&L {(price - avg) * qty:,.0f} · Nifty needed for {avg:,.0f} today ≈ {need_spot:,.0f} · "
            f"expiry break-even {NIFTY_KEY[1] + avg:,.0f} · {status}")
    return {"model_ltp": round(model, 2), "need_spot": need_spot, "breakeven": NIFTY_KEY[1] + avg, "status": status, "line": line,
            "price_used": price, "days_left": (expiry - day).days}


def fetch_history(symbol: str, timeout: float = 20.0) -> tuple[list[dict], str]:
    try:
        req = urllib.request.Request(YAHOO_CHART.format(symbol=urllib.parse.quote(symbol)), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return parse_chart(json.loads(r.read() or b"null")), ""
    except Exception as e:
        return [], f"{type(e).__name__}: {str(e)[:100]}"


# ═════════════════════════════════════════════════════════════════════════════
# Registration
# ═════════════════════════════════════════════════════════════════════════════
def register(app, vdb: Callable[[], Awaitable[Any]], sm: dict, send_cos: Callable[..., Any] | None = None) -> dict:
    import asyncio
    hooks: dict[str, Any] = {"fetch_history": fetch_history}

    async def ensure_schema():
        db = await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def universe(st: dict) -> tuple[dict, dict]:
        """{ticker: {zone, source, note, holders:[{holder,qty,avg}], tags:set}} from portfolio rows, levels and F&O underlyings."""
        uni: dict[str, dict] = {}
        for r in st["portfolio"]["rows"]:
            t = r["ticker"]
            u = uni.setdefault(t, {"zone": (None, None), "source": "", "note": "", "holders": [], "tags": set()})
            u["holders"].append({"holder": r["account"], "qty": r.get("qty") or 0, "avg": r.get("avg_price") or 0})
            u["tags"].add("portfolio")
        for l in st["levels"]:
            t = l["ticker"]
            u = uni.setdefault(t, {"zone": (None, None), "source": "", "note": "", "holders": [], "tags": set()})
            u["zone"], u["source"], u["note"] = parse_zone(l.get("note") or ""), source_kind(l.get("note") or ""), l.get("note") or ""
            if l.get("buy_level") and u["zone"] == (None, None):
                u["zone"] = (None, float(l["buy_level"]))
            u["tags"].add("mausaji" if u["source"].startswith("Mausaji") else "levels")
        for p in st["positions"]:
            und = p.get("underlying")
            if und and und not in ("NIFTY", "BANKNIFTY"):
                u = uni.setdefault(und, {"zone": (None, None), "source": "", "note": "", "holders": [], "tags": set()})
                u["tags"].add("positions")
        return uni, {}

    async def run(now_v: Any = None) -> dict:
        await ensure_schema()
        now = datetime.fromisoformat(str(now_v)) if now_v else datetime.now(IST)
        if now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        st = await sm["state"]()
        uni, _ = await universe(st)
        tickers = sorted(uni)

        def _one(t: str):
            bars, err = hooks["fetch_history"](t + ".NS")
            return t, bars, err
        results = await asyncio.gather(*[asyncio.to_thread(_one, t) for t in tickers])
        db = await vdb()
        cur = await db.execute("INSERT INTO analysis_runs (ran_at) VALUES (?)", (now.isoformat(timespec="minutes"),))
        run_id = cur.lastrowid
        ok = failed = in_zone = near_buy = near_sell = 0
        for t, bars, err in results:
            ind = indicators(bars)
            u = uni[t]
            if not ind:
                failed += 1
                payload = {"ticker": t, "error": err or "not enough price history", "tags": sorted(u["tags"]), "source": u["source"]}
            else:
                ok += 1
                a = assess(ind, u["zone"], u["holders"], u["source"], t)
                in_zone += a["status"] == "IN BUY ZONE"
                near_buy += a["status"] == "NEAR BUY ZONE"
                near_sell += a["sell"].startswith("NEAR SELL")
                payload = {"ticker": t, "tags": sorted(u["tags"]), "source": u["source"], "zone": list(u["zone"]), "holders": u["holders"],
                           "ind": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in ind.items()}, "trend": trend_text(ind),
                           "fundamentals": FUNDAMENTALS_NOTE, **a}
            await db.execute("INSERT OR REPLACE INTO analysis_rows (run_id, ticker, payload) VALUES (?,?,?)", (run_id, t, json.dumps(payload)))
        # the Nifty 25000 CE tracker (one row a day)
        nline = ""
        nif = next((p for p in st["positions"] if str(p.get("instrument", "")).startswith("NIFTY") and "25000" in str(p.get("instrument"))), None)
        if nif:
            nb, _e = hooks["fetch_history"]("^NSEI")
            vb, _e2 = hooks["fetch_history"]("^INDIAVIX")
            if nb:
                spot, vix = nb[-1]["c"], (vb[-1]["c"] if vb else 15.0)
                ns = nifty_status(spot, vix, now.date(), _num(nif.get("ltp")), float(nif.get("qty") or 0), float(nif.get("avg") or NIFTY_BUY_PRICE))
                nline = ns["line"]
                await db.execute("INSERT OR REPLACE INTO nifty_ce_log (day, spot, vix, recorded_ltp, recorded_asof, model_ltp, status, line) VALUES (?,?,?,?,?,?,?,?)",
                                 (now.date().isoformat(), spot, vix, _num(nif.get("ltp")), str(nif.get("as_of") or ""), ns["model_ltp"], ns["status"], nline))
        line = (f"{BOT_ID}: {len(tickers)} shares analysed ({ok} ok, {failed} no data) · {in_zone} in buy zone, {near_buy} near buy zone, "
                f"{near_sell} near sell zone (profit holders only)" + (f" · Nifty 25000CE: {nline[-60:]}" if nline else " · Nifty 25000CE: not on file"))
        await db.execute("UPDATE analysis_runs SET universe=?, ok=?, failed=?, line=? WHERE id=?", (len(tickers), ok, failed, line, run_id))
        await db.commit()
        status = "clean" if ok and failed <= max(3, len(tickers) // 10) else "warning"
        return {"run_id": run_id, "universe": len(tickers), "ok": ok, "failed": failed, "in_zone": in_zone, "near_buy": near_buy,
                "near_sell": near_sell, "line": line, "status": status}

    async def latest() -> dict:
        await ensure_schema()
        db = await vdb()
        r = await db.execute_fetchall("SELECT * FROM analysis_runs WHERE ok > 0 ORDER BY id DESC LIMIT 1")
        if not r:
            return {"run": None, "rows": [], "nifty": []}
        run = dict(r[0])
        rows = [json.loads(x[0]) for x in await db.execute_fetchall("SELECT payload FROM analysis_rows WHERE run_id=? ORDER BY ticker", (run["id"],))]
        nifty = [dict(x) for x in await db.execute_fetchall("SELECT * FROM nifty_ce_log ORDER BY day DESC LIMIT 120")]
        return {"run": run, "rows": rows, "nifty": nifty}

    @app.post("/api/analysis/run")
    async def api_run(body: dict | None = None):
        return await run((body or {}).get("now"))

    @app.get("/api/analysis/latest")
    async def api_latest():
        return await latest()

    return {"ensure_schema": ensure_schema, "run": run, "latest": latest, "hooks": hooks}
