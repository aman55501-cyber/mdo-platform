"""corp-actions — NSE corporate announcements and corporate actions for every share the family holds or watches.
Rules only, zero LLM spend.

Every day 18:30 IST (`python mdo_agent.py corp-actions`, fleet.yaml: corp-actions) the bot takes every ticker in
share_master_holdings (all holders, Directive 18) and share_levels, and pulls NSE's two public JSON endpoints
per ticker — corporate-announcements (board meetings, results, buybacks, AGM/e-voting, …) and
corporates-corporateActions (dividends, bonus, split, rights, record dates) — with the same cookie dance
mdo_option_levels uses, at most one request per second. Rows land in corp_actions (UNIQUE on ticker, subject,
announced_at). ONE WhatsApp push per run, NEW rows only, each line "TICKER · kind · date · held: Ashok 3000,
Aman 500", at most MAX_PUSH_LINES then "+N more on the dashboard"; zero new → nothing pushed. The heartbeat is
always "corp-actions: T tickers checked, N new (R results, D dividends, O other) — NSE ok", or "— NSE
unavailable" when NSE did not answer: nothing is invented, the next run catches up. Morning page card
"Corporate actions": the next 14 days by ex/record date (GET /api/corp-actions/upcoming?days=14).

The pure helpers above register() take plain values and touch nothing — tests/test_corp_actions.py runs them
with canned NSE JSON; the fetch is a hook the tests replace.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from mdo_cos import IST
from mdo_levels import held_text, norm_ticker

BOT_ID = "corp-actions"
NSE_HOME = "https://www.nseindia.com"
NSE_ANNOUNCEMENTS = NSE_HOME + "/api/corporate-announcements?index=equities&symbol={symbol}"
NSE_ACTIONS = NSE_HOME + "/api/corporates-corporateActions?index=equities&symbol={symbol}"
NSE_PAGE = NSE_HOME + "/get-quotes/equity?symbol={symbol}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
MIN_GAP_S = 1.0                     # NSE rate limit: one request per second, never more
MAX_PUSH_LINES = 25
KEEP_DAYS = 30                      # announcements older than this are not stored (the first run would otherwise push months of history)
UNAVAILABLE_AFTER = 3               # consecutive tickers with no answer at all → "NSE unavailable", stop hammering
KINDS = ("results", "dividend", "buyback", "bonus", "split", "rights", "agm", "board_meeting", "record_date", "other")
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_ISIN = re.compile(r"IN[A-Z0-9]{10}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS corp_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'other',
    subject TEXT NOT NULL,
    ex_date TEXT DEFAULT '', record_date TEXT DEFAULT '',   -- ISO dates when NSE gave them
    announced_at TEXT NOT NULL,                             -- ISO datetime (IST) of the announcement / broadcast
    url TEXT DEFAULT '', source TEXT DEFAULT 'announcement', -- announcement | action
    company TEXT DEFAULT '',
    pushed_at TEXT, created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, subject, announced_at)
);
CREATE INDEX IF NOT EXISTS idx_corp_actions_dates ON corp_actions(ex_date, record_date);
CREATE TABLE IF NOT EXISTS corp_actions_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at TEXT NOT NULL, tickers INTEGER DEFAULT 0, new INTEGER DEFAULT 0, failed INTEGER DEFAULT 0,
    nse_ok INTEGER DEFAULT 1, line TEXT DEFAULT '', pushed INTEGER DEFAULT 0
);
"""


# ═════════════════════════════════════════════════════════════════════════════
# Pure helpers — no database, no network
# ═════════════════════════════════════════════════════════════════════════════
def parse_nse_date(s: Any) -> str:
    """'07-Oct-2026' / '09-Oct-2026 17:32:11' / ISO → ISO date; '-' or blank → ''."""
    s = str(s or "").strip()
    if not s or s == "-":
        return ""
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})-(\d{4})", s)
    if m and m.group(2).lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
        except ValueError:
            return ""
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return ""


def parse_nse_datetime(s: Any) -> str:
    """'09-Oct-2026 17:32:11' → '2026-10-09T17:32:11'; a bare date → 'YYYY-MM-DDT00:00:00'; else ''."""
    s = str(s or "").strip()
    d = parse_nse_date(s)
    if not d:
        return ""
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s[10:] if len(s) > 10 else "")
    hh, mm, ss = (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else (0, 0, 0)
    return f"{d}T{hh:02d}:{mm:02d}:{ss:02d}"


def classify(subject: Any, desc: Any = "") -> str:
    t = f"{desc or ''} {subject or ''}".lower()
    if "buyback" in t or "buy back" in t or "buy-back" in t:
        return "buyback"
    if "bonus" in t:
        return "bonus"
    if "split" in t or "sub-division" in t or "subdivision" in t or "sub division" in t:
        return "split"
    if "rights" in t:
        return "rights"
    if "dividend" in t:
        return "dividend"
    if "result" in t:
        return "results"
    if "annual general meeting" in t or re.search(r"\bagm\b", t) or re.search(r"\begm\b", t) or "postal ballot" in t or "e-voting" in t or "evoting" in t:
        return "agm"
    if "board meeting" in t:
        return "board_meeting"
    if "record date" in t:
        return "record_date"
    return "other"


def _clean(s: Any, n: int = 300) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def rows_from_announcements(ticker: str, data: Any) -> list[dict]:
    """NSE corporate-announcements JSON → rows. Keys seen on the live endpoint: symbol, desc (category), an_dt /
    dt (announced), attchmntText (the text), attchmntFile (PDF url), sm_name (company)."""
    out = []
    items = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None) or []
    for it in items:
        if not isinstance(it, dict):
            continue
        desc, text = _clean(it.get("desc"), 120), _clean(it.get("attchmntText"), 240)
        subject = f"{desc}: {text}" if desc and text and text.lower() != desc.lower() else (text or desc)
        announced = parse_nse_datetime(it.get("an_dt") or it.get("dt") or it.get("sort_date") or it.get("exchdisstime"))
        if not subject or not announced:
            continue
        out.append({"ticker": norm_ticker(it.get("symbol") or ticker) or ticker, "kind": classify(subject, desc), "subject": subject[:300],
                    "ex_date": "", "record_date": "", "announced_at": announced, "url": _clean(it.get("attchmntFile"), 300),
                    "source": "announcement", "company": _clean(it.get("sm_name"), 120)})
    return out


def rows_from_actions(ticker: str, data: Any) -> list[dict]:
    """NSE corporates-corporateActions JSON → rows. Keys seen live: symbol, subject ('Dividend - Rs 2 Per Share'),
    exDate, recDate, bcStartDate/bcEndDate, caBroadcastDate, comp."""
    out = []
    items = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else None) or []
    for it in items:
        if not isinstance(it, dict):
            continue
        subject = _clean(it.get("subject"), 300)
        ex, rec = parse_nse_date(it.get("exDate")), parse_nse_date(it.get("recDate"))
        announced = parse_nse_datetime(it.get("caBroadcastDate") or it.get("bcStartDate") or ex or rec)
        if not subject or not announced:
            continue
        sym = norm_ticker(it.get("symbol") or ticker) or ticker
        out.append({"ticker": sym, "kind": classify(subject), "subject": subject, "ex_date": ex, "record_date": rec,
                    "announced_at": announced, "url": NSE_PAGE.format(symbol=urllib.parse.quote(sym)), "source": "action",
                    "company": _clean(it.get("comp"), 120)})
    return out


def fmt_day(d: str) -> str:
    try:
        x = date.fromisoformat(str(d)[:10])
    except ValueError:
        return str(d or "")[:10] or "?"
    return f"{x.day:02d} {x:%b}"


def row_date(r: dict) -> str:
    return r.get("ex_date") or r.get("record_date") or str(r.get("announced_at") or "")[:10]


def line_for(r: dict, held: list[dict] | None) -> str:
    """'TICKER · kind · date · held: Ashok 3000, Aman 500' (Directive 18: the holder column on every share line)."""
    kind = str(r.get("kind") or "other").replace("_", " ")
    return f"{r['ticker']} · {kind} · {fmt_day(row_date(r))} · held: {held_text(held)}"


def push_text(new_rows: list[dict], holders: dict[str, list[dict]], today: date, max_lines: int = MAX_PUSH_LINES) -> str:
    """The one WhatsApp message: header, one line per NEW row (nearest date first), '+N more on the dashboard'."""
    rows = sorted(new_rows, key=lambda r: (row_date(r), r["ticker"], r["kind"]))
    lines = [f"Corporate actions · {len(rows)} new ({today.day:02d} {today:%b})"]
    for r in rows[:max_lines]:
        lines.append(line_for(r, holders.get(norm_ticker(r["ticker"]))))
    if len(rows) > max_lines:
        lines.append(f"+{len(rows) - max_lines} more on the dashboard")
    return "\n".join(lines)


def heartbeat_line(tickers: int, new_rows: list[dict], nse_ok: bool, failed: int = 0) -> str:
    r = sum(1 for x in new_rows if x["kind"] == "results")
    d = sum(1 for x in new_rows if x["kind"] == "dividend")
    o = len(new_rows) - r - d
    tail = "NSE ok" if nse_ok else f"NSE unavailable ({failed} of {tickers} tickers unanswered)"
    return f"{BOT_ID}: {tickers} tickers checked, {len(new_rows)} new ({r} results, {d} dividends, {o} other) — {tail}"


def _parse_now(now_v: Any) -> datetime:
    if isinstance(now_v, datetime):
        now = now_v
    else:
        try:
            now = datetime.fromisoformat(str(now_v).replace("Z", "+00:00")) if now_v else datetime.now(IST)
        except ValueError:
            now = datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    return now.astimezone(IST)


# ── NSE fetch (rate-limited, never raises) ───────────────────────────────────
def make_fetcher(sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic, timeout: float = 12.0):
    """fetch(kind, symbol) → (data | None, error). One cookie dance per fetcher, ≥ MIN_GAP_S between requests."""
    state: dict[str, Any] = {"opener": None, "last": 0.0}
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", "Referer": NSE_HOME + "/"}

    def _wait():
        gap = MIN_GAP_S - (clock() - state["last"])
        if gap > 0:
            sleep(gap)
        state["last"] = clock()

    def _opener():
        if state["opener"] is None:
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
            _wait()
            with opener.open(urllib.request.Request(NSE_HOME, headers=hdrs), timeout=timeout) as r:
                r.read(2048)
            state["opener"] = opener
        return state["opener"]

    def fetch(kind: str, symbol: str) -> tuple[Any, str]:
        url = (NSE_ANNOUNCEMENTS if kind == "announcements" else NSE_ACTIONS).format(symbol=urllib.parse.quote(symbol.upper()))
        try:
            opener = _opener()
            _wait()
            with opener.open(urllib.request.Request(url, headers={**hdrs, "Accept": "application/json"}), timeout=timeout) as r:
                return json.loads(r.read() or b"null"), ""
        except Exception as e:
            state["opener"] = None                      # a 401/403 means the cookie went stale: dance again next time
            return None, f"{type(e).__name__}: {str(e)[:120]}"

    return fetch


# ═════════════════════════════════════════════════════════════════════════════
# Registration — tables, endpoints, the run the bot triggers
# ═════════════════════════════════════════════════════════════════════════════
def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict], share_master: dict | None = None) -> dict:
    import asyncio

    hooks: dict[str, Any] = {"make_fetcher": make_fetcher}

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def _table(db, name: str) -> bool:
        return bool(await db.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)))

    async def tickers() -> list[str]:
        """Every ticker held (all holders) or watched, NSE-shaped, sorted. Unverified codes are skipped: NSE cannot
        know a BSE-only scrip or a stripped HDFC code, and a 'failure' there would be noise."""
        db = await vdb()
        out: set[str] = set()
        if await _table(db, "share_master_holdings"):
            for r in await db.execute_fetchall("SELECT DISTINCT ticker FROM share_master_holdings WHERE COALESCE(ticker_verified,1)=1"):
                t = norm_ticker(dict(r)["ticker"])
                if t and not _ISIN.fullmatch(t):          # an unresolved Angel row keeps its ISIN as the ticker
                    out.add(t)
        if await _table(db, "share_levels"):
            for r in await db.execute_fetchall("SELECT DISTINCT ticker FROM share_levels"):
                t = norm_ticker(dict(r)["ticker"])
                if t:
                    out.add(t)
        return sorted(out)

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

    async def store(rows: list[dict], cutoff: str) -> list[dict]:
        """INSERT OR IGNORE; returns the rows that were new. Announcements older than the cutoff are not stored."""
        db = await vdb()
        new = []
        for r in rows:
            if r["source"] == "announcement" and r["announced_at"] < cutoff:
                continue
            cur = await db.execute(
                "INSERT OR IGNORE INTO corp_actions (ticker, kind, subject, ex_date, record_date, announced_at, url, source, company) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (r["ticker"], r["kind"], r["subject"], r["ex_date"], r["record_date"], r["announced_at"], r["url"], r["source"], r["company"]))
            if cur.rowcount:
                new.append({**r, "id": cur.lastrowid})
        await db.commit()
        return new

    async def run(now_v: Any = None) -> dict:
        now = _parse_now(now_v)
        today = now.date()
        cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()
        syms = await tickers()
        fetch = hooks["make_fetcher"]()
        new_rows: list[dict] = []
        failed, consecutive, checked, errors = 0, 0, 0, []
        nse_ok = True
        for sym in syms:
            ann, e1 = await asyncio.to_thread(fetch, "announcements", sym)
            act, e2 = await asyncio.to_thread(fetch, "actions", sym)
            checked += 1
            if ann is None and act is None:
                failed += 1
                consecutive += 1
                errors.append(f"{sym}: {e1 or e2}")
                if consecutive >= UNAVAILABLE_AFTER and failed == checked:
                    nse_ok = False
                    break
                continue
            consecutive = 0
            rows = rows_from_announcements(sym, ann) + rows_from_actions(sym, act)
            new_rows += await store(rows, cutoff)
        if failed and failed == checked:
            nse_ok = False
        held = await holders()
        text, push, sent = "", {}, False
        if new_rows:
            text = push_text(new_rows, held, today)
            try:
                push = send_cos(text) or {}
            except Exception as e:
                push = {"sent": False, "reason": str(e)[:200]}
            sent = bool(push.get("sent"))
            if sent:
                db = await vdb()
                stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                await db.executemany("UPDATE corp_actions SET pushed_at=? WHERE id=?", [(stamp, r["id"]) for r in new_rows])
                await db.commit()
        line = heartbeat_line(len(syms) if nse_ok else checked, new_rows, nse_ok, failed)
        if nse_ok and failed:
            line += f" · {failed} tickers unanswered"
        if new_rows and not sent:
            line += " · push NOT delivered"
        db = await vdb()
        await db.execute("INSERT INTO corp_actions_runs (ran_at, tickers, new, failed, nse_ok, line, pushed) VALUES (?,?,?,?,?,?,?)",
                         (now.isoformat(timespec="minutes"), checked, len(new_rows), failed, 1 if nse_ok else 0, line, 1 if sent else 0))
        await db.commit()
        status = "clean" if nse_ok and (not new_rows or sent) else "warning"
        return {"tickers": len(syms), "checked": checked, "new": len(new_rows), "failed": failed, "nse_ok": nse_ok,
                "items": [{k: r.get(k) for k in ("id", "ticker", "kind", "subject", "ex_date", "record_date", "announced_at", "url", "source", "company")}
                          for r in new_rows],
                "pushed": 1 if sent else 0, "push_failed": 1 if (new_rows and not sent) else 0, "push": push, "text": text,
                "line": line, "status": status, "errors": errors[:10], "as_of": now.isoformat()}

    def _with_held(rows: list[dict], held: dict[str, list[dict]]) -> list[dict]:
        for r in rows:
            r["held_by"] = held.get(norm_ticker(r["ticker"]), [])
            r["held_text"] = held_text(r["held_by"])
            r["date"] = row_date(r)
        return rows

    async def upcoming(days: int = 14, now_v: Any = None) -> dict:
        """Rows whose ex/record date falls in today..today+days, nearest first, with the holder column."""
        days = max(0, min(int(days or 14), 400))
        now = _parse_now(now_v)
        today = now.date()
        end = (today + timedelta(days=days)).isoformat()
        db = await vdb()
        rows = [dict(r) for r in await db.execute_fetchall(
            "SELECT * FROM corp_actions WHERE (ex_date BETWEEN ? AND ?) OR (record_date BETWEEN ? AND ?) "
            "ORDER BY CASE WHEN ex_date != '' THEN ex_date ELSE record_date END, ticker", (today.isoformat(), end, today.isoformat(), end))]
        held = await holders()
        last = await db.execute_fetchall("SELECT * FROM corp_actions_runs ORDER BY id DESC LIMIT 1")
        return {"as_of": now.isoformat(), "today": today.isoformat(), "days": days, "items": _with_held(rows, held),
                "last_run": dict(last[0]) if last else None, "tickers_watched": len(await tickers())}

    async def recent(days: int = 7, limit: int = 100) -> dict:
        days = max(0, min(int(days or 7), 400))
        db = await vdb()
        since = (datetime.now(IST).date() - timedelta(days=days)).isoformat()
        rows = [dict(r) for r in await db.execute_fetchall(
            "SELECT * FROM corp_actions WHERE announced_at >= ? ORDER BY announced_at DESC, id DESC LIMIT ?",
            (since, max(1, min(int(limit or 100), 1000))))]
        return {"days": days, "items": _with_held(rows, await holders())}

    # ── endpoints ─────────────────────────────────────────────────────────────
    @app.get("/api/corp-actions/upcoming")
    async def corp_actions_upcoming(days: int = 14, now: str | None = None):
        return await upcoming(days, now)

    @app.get("/api/corp-actions/recent")
    async def corp_actions_recent(days: int = 7, limit: int = 100):
        return await recent(days, limit)

    @app.get("/api/corp-actions/tickers")
    async def corp_actions_tickers():
        t = await tickers()
        return {"tickers": t, "count": len(t)}

    @app.post("/api/corp-actions/run")
    async def corp_actions_run(body: dict | None = None):
        body = body or {}
        if body.get("now") is not None and not isinstance(body.get("now"), str):
            raise HTTPException(400, "now must be an ISO string")
        return await run(body.get("now"))

    return {"ensure_schema": ensure_schema, "run": run, "upcoming": upcoming, "recent": recent, "tickers": tickers, "hooks": hooks}
