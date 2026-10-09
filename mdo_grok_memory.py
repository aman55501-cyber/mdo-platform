"""Grok memory — two-way memory between the fleet and Grok.

Grok reaches the fleet two ways: the xAI API bots on the VPS (x-watch, singhvi,
via mdo_agent.ask_grok) and Aman's Grok subscription tasks, which report by
email and are filed by the grok-relay Routine. Neither remembered what the other
had already found, so the same tender or call arrived three times.

This module gives both sides one table and one read-only page:

  grok_memory            every tender / call / news item / fact Grok has reported,
                         deduplicated on (kind, key) with first_seen / last_seen /
                         times_seen, so a repeat bumps a counter instead of a row.
  /api/grok/memory       GET (filter) · POST (upsert, single or list) · POST /{id}/status
                         — app-key auth like every other /api/* route.
  /api/grok/context      the CONTEXT PACK: plain text ≤ 6 KB that a Grok task opens
                         first — objectives, entities, the tender and market lenses,
                         what is already known (do not re-report), the output format.
                         Its own token (GROK_CONTEXT_TOKEN), exempt from the app key
                         like the tender door, every fetch audited, ≤60 fetches/hour,
                         cached 10 minutes in-process.
  /api/grok/context-internal   the same text for the VPS bots, behind the app key.

The pack NEVER carries personal chat content, phone numbers, tokens, bank data or
WhatsApp text: build_context only ever sees agenda titles, the entity register,
fleet charters and grok_memory rows, and scrubs phone-like and token-like strings
from the free text it is given.

Registered onto the FastAPI app by mdo_server.py via register(app, vdb).
"""
from __future__ import annotations

import hmac
import json
import os
import re
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException, Request
from starlette.responses import PlainTextResponse

from mdo_cos import IST

SOURCES = ("x-watch", "singhvi", "grok-relay", "grok-subscription")
KINDS = ("tender", "call", "news", "fact")
SENTIMENTS = ("positive", "negative", "neutral", "")
STATUSES = ("open", "done", "dismissed")
PACK_MAX_BYTES = 6 * 1024          # hard cap on the context pack
PACK_TTL_SECONDS = 600             # in-process cache
KNOWN_DAYS = 14                    # "already known" window
RATE_LIMIT_PER_HOUR = 60           # crude, in-process, successful fetches of /api/grok/context

# Buyers and client sites the x-watch scout is charged with (mdo_agent.BOT_RULES["x-watch"];
# fleet.yaml x-watch / tender-go-no-go charters name the lens: coal washing + RCR, margin first).
TENDER_BUYERS = ["CIL", "SECL", "WCL", "MCL", "NTPC", "NALCO", "GeM", "CPPP"]
CLIENT_SITES = ["Vedanta/BALCO Korba", "JSPL Raigarh", "SAIL Bhilai", "NTPC Sipat"]
CRUDE_KEYWORDS_DEFAULT = ["Brent", "WTI", "OPEC", "OPEC+", "crude inventories (EIA/API)",
                          "Strait of Hormuz", "sanctions", "INR/USD"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS grok_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
    source TEXT NOT NULL DEFAULT '',          -- x-watch|singhvi|grok-relay|grok-subscription
    kind TEXT NOT NULL,                       -- tender|call|news|fact
    key TEXT NOT NULL,                        -- normalised dedup key
    entity TEXT DEFAULT '', text TEXT DEFAULT '', url TEXT DEFAULT '',
    sentiment TEXT DEFAULT '',                -- positive|negative|neutral|''
    first_seen TEXT DEFAULT (datetime('now')), last_seen TEXT DEFAULT (datetime('now')),
    times_seen INTEGER DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'open',      -- open|done|dismissed
    UNIQUE(kind, key)
);
CREATE INDEX IF NOT EXISTS idx_grok_memory_seen ON grok_memory(kind, last_seen);
CREATE TABLE IF NOT EXISTS grok_context_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    ip TEXT DEFAULT '', ok INTEGER DEFAULT 1, bytes INTEGER DEFAULT 0, note TEXT DEFAULT ''
);
"""

# ── normalisation (pure) ─────────────────────────────────────────────────────
_URL = re.compile(r"https?://[^\s)\]>\"'<]+")
_TENDER_ID = re.compile(
    r"(?:tender\s*(?:id|no\.?|number|ref\.?)?|NIT\s*(?:no\.?|number)?|RFQ|RFP|GeM(?:/|\s)*bid|bid\s*(?:no\.?|id))"
    r"[\s:#/.-]*([A-Za-z0-9][A-Za-z0-9/._-]{3,})", re.IGNORECASE)
_PHONEISH = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
# a long run of letters+digits with no hyphen (hex / base64-ish); slugs keep their hyphens and survive
_TOKENISH = re.compile(r"(?<![\w/.])(?=[A-Za-z0-9_]*\d)(?=[A-Za-z0-9_]*[A-Za-z])[A-Za-z0-9_]{32,}(?![\w/])")
_PATHISH = re.compile(r"\S+/\S+")       # URLs, paths, tender ids like SECL/2026/CW-14 — never scrubbed


def slug(s: Any, limit: int = 80) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")
    return s[:limit].strip("-")


def extract_url(*texts: Any) -> str:
    for t in texts:
        m = _URL.search(str(t or ""))
        if m:
            return m.group(0).rstrip(".,;")
    return ""


def extract_tender_id(*texts: Any) -> str:
    for t in texts:
        for m in _TENDER_ID.finditer(str(t or "")):
            tid = m.group(1).rstrip(".,;:")
            if any(ch.isdigit() for ch in tid):
                return tid
    return ""


def norm_url(url: Any) -> str:
    u = str(url or "").strip().lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    u = u.split("?")[0].split("#")[0].rstrip("/")
    return u[:200]


def tender_key(tender_id: Any, buyer: Any, title: Any) -> str:
    tid = slug(tender_id, 60)
    if tid:
        return "id:" + tid
    return (slug(buyer, 40) or "unknown") + "/" + (slug(title, 80) or "untitled")


def call_key(ticker: Any, direction: Any, day: Any) -> str:
    d = day.isoformat() if isinstance(day, (date, datetime)) else str(day or "")[:10]
    return f"{str(ticker or '').strip().upper()[:40]}:{str(direction or '').strip().upper()[:8]}:{d}"


def news_key(url: Any, title: Any) -> str:
    return norm_url(url) or slug(title, 100) or ""


def make_key(kind: str, item: dict) -> str:
    """The dedup key for an item that did not bring one."""
    if kind == "tender":
        return tender_key(item.get("tender_id") or extract_tender_id(item.get("title"), item.get("text")),
                          item.get("buyer") or item.get("entity"), item.get("title") or item.get("text"))
    if kind == "call":
        return call_key(item.get("stock") or item.get("ticker") or item.get("entity"),
                        item.get("action") or item.get("direction"),
                        item.get("date") or item.get("day") or date.today())
    return news_key(item.get("url"), item.get("title") or item.get("text"))


def scrub(text: Any, limit: int = 300) -> str:
    """Free text that may enter the pack: one line, no phone-like or token-like strings."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    keep: list[str] = []

    def protect(m):
        keep.append(m.group(0))
        return f"\x00{len(keep) - 1}\x00"

    s = _PATHISH.sub(protect, s)
    s = _PHONEISH.sub(lambda m: "[redacted]" if sum(ch.isdigit() for ch in m.group(0)) >= 10 else m.group(0), s)
    s = _TOKENISH.sub("[redacted]", s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], s)
    return s[:limit]


def normalise_item(item: dict, default_source: str = "grok-relay") -> dict | str:
    """One inbound row → the stored shape, or the one-word reason it is rejected."""
    if not isinstance(item, dict):
        return "not an object"
    kind = str(item.get("kind") or "").strip().lower()
    if kind not in KINDS:
        return "bad kind"
    source = str(item.get("source") or default_source).strip().lower()
    if source not in SOURCES:
        return "bad source"
    key = str(item.get("key") or "").strip()[:200]
    key = (key.upper() if kind == "call" else key.lower()) or make_key(kind, item)   # same shape as call_key / slug
    if not key:
        return "no key"
    sentiment = str(item.get("sentiment") or "").strip().lower()
    if sentiment not in SENTIMENTS:
        sentiment = ""
    text = scrub(item.get("text") or item.get("title") or "", 1000)
    url = str(item.get("url") or item.get("source_url") or "").strip()[:500]
    if url and not url.startswith("http"):
        url = ""
    return {"source": source, "kind": kind, "key": key,
            "entity": scrub(item.get("entity") or item.get("buyer") or item.get("stock") or "", 80),
            "text": text, "url": url, "sentiment": sentiment}


# ── what the bots hand over (pure) ───────────────────────────────────────────
_TENDERISH = re.compile(r"\b(tender|nit|rfq|rfp|bid|e-?procurement|gem)\b", re.IGNORECASE)


def finding_to_memory(f: dict, source: str = "x-watch", now: datetime | None = None) -> dict | None:
    """An x-watch finding (level/title/detail/entity/domain) → a grok_memory row, or None."""
    if not isinstance(f, dict):
        return None
    title = str(f.get("title") or "").strip()
    detail = str(f.get("detail") or "").strip()
    if not title:
        return None
    blob = f"{title} {detail}"
    url = str(f.get("url") or f.get("source_url") or "").strip() or extract_url(detail, title)
    low = blob.lower()
    if "market-negative" in low or "negative" in low:
        sentiment = "negative"
    elif "market-positive" in low or "positive" in low:
        sentiment = "positive"
    elif "neutral" in low:
        sentiment = "neutral"
    else:
        sentiment = ""
    entity = str(f.get("entity") or "").strip()
    if _TENDERISH.search(blob) and str(f.get("domain") or "").lower() in ("vwlr", "tender", "tenders", ""):
        kind = "tender"
        key = tender_key(extract_tender_id(title, detail), entity, title)
    else:
        kind = "news"
        key = news_key(url, title)
    return {"source": source, "kind": kind, "key": key, "entity": entity,
            "text": (title + (" — " + detail if detail else ""))[:1000], "url": url, "sentiment": sentiment}


def call_to_memory(c: dict, now: datetime | None = None, source: str = "singhvi") -> dict | None:
    """A parsed Singhvi call (mdo_agent.parse_singhvi_calls shape) → a grok_memory row."""
    stock, action = str(c.get("stock") or "").strip().upper(), str(c.get("action") or "").strip().upper()
    if not stock or action not in ("BUY", "SELL"):
        return None
    day = (now or datetime.now(IST)).date()
    lv = " ".join(f"{lbl} {c[k]:g}" for lbl, k in (("@", "entry"), ("SL", "stop"), ("TG", "target"))
                  if isinstance(c.get(k), (int, float)))
    text = f"{action} {stock} {lv} {c.get('timeframe') or ''}".strip()
    if c.get("rationale"):
        text += " — " + str(c["rationale"])
    return {"source": source, "kind": "call", "key": call_key(stock, action, day), "entity": stock,
            "text": text[:1000], "url": str(c.get("source_url") or "")[:500],
            "sentiment": "positive" if action == "BUY" else "negative"}


# ── the context pack (pure) ──────────────────────────────────────────────────
def keywords_from_fleet(fleet: dict) -> dict:
    """Crude keywords from the x-watch charter (fleet.yaml); buyers and client sites from
    the scout's standing orders. Nothing here is invented: every list has a file behind it."""
    crude = list(CRUDE_KEYWORDS_DEFAULT)
    for b in (fleet or {}).get("bots") or []:
        if b.get("id") == "x-watch":
            works = str((b.get("charter") or {}).get("works") or "")
            m = re.search(r"Crude watch keywords every run:\s*(.+?)\s*[—\-]{1,2}\s*crude-moving", works, re.S)
            if m:
                found = [k.strip() for k in m.group(1).replace("\n", " ").split(",") if k.strip()]
                if found:
                    crude = found
    return {"tender_buyers": list(TENDER_BUYERS), "client_sites": list(CLIENT_SITES), "crude": crude}


def _since_utc(now: datetime, days: int) -> str:
    return (now.astimezone(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _title_from_pipeline_notes(notes: Any) -> str:
    s = str(notes or "")
    s = re.sub(r"^\[[^\]]*\]\s*", "", s)
    return s.split(" — ")[0].strip()


def known_keys(recent_memory: list[dict], filed_tenders: list[dict], queued_calls: list[dict],
               now: datetime) -> dict[str, list[str]]:
    """Per kind, the keys Grok must not report again: grok_memory rows, tenders already in
    the pipeline table, Singhvi calls already queued today. Ordered, deduplicated."""
    out: dict[str, list[str]] = {k: [] for k in KINDS}

    def add(kind: str, key: str):
        key = scrub(key, 120)
        if key and key not in out[kind]:
            out[kind].append(key)

    for r in recent_memory or []:
        kind = str(r.get("kind") or "")
        if kind in out:
            add(kind, str(r.get("key") or ""))
    for t in filed_tenders or []:
        title = _title_from_pipeline_notes(t.get("notes"))
        add("tender", tender_key(extract_tender_id(t.get("notes"), t.get("url")), t.get("buyer"), title))
    day = now.astimezone(IST).date()
    for c in queued_calls or []:
        add("call", call_key(c.get("ticker") or c.get("stock"), c.get("direction") or c.get("action"), day))
    return out


def build_context(objectives: list[dict], entities: list, keywords: dict, recent_memory: list[dict],
                  filed_tenders: list[dict], queued_calls: list[dict], now: datetime) -> str:
    """The plain-text pack a Grok task opens first. ≤ PACK_MAX_BYTES, UTF-8. Pure."""
    now_ist = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
    kw = keywords or {}
    buyers = [str(x) for x in (kw.get("tender_buyers") or TENDER_BUYERS)]
    sites = [str(x) for x in (kw.get("client_sites") or CLIENT_SITES)]
    crude = [str(x) for x in (kw.get("crude") or CRUDE_KEYWORDS_DEFAULT)]

    obj_lines = []
    for o in objectives or []:
        if not isinstance(o, dict) or o.get("confirmed") is not True:
            continue
        status = str(o.get("status") or "").strip()
        obj_lines.append(f"- {o.get('id')}: {scrub(o.get('title'), 240)}" + (f" [{status}]" if status and status != "live" else ""))
    ent_lines = []
    for e in entities or []:
        if isinstance(e, dict):
            name, desc = e.get("name"), e.get("description") or e.get("desc") or ""
        else:
            name, desc = (list(e) + ["", ""])[:2]
        if name:
            ent_lines.append(f"- {scrub(name, 60)}" + (f" — {scrub(desc, 80)}" if desc else ""))

    known = known_keys(recent_memory, filed_tenders, queued_calls, now)
    head = (
        f"MDO FLEET CONTEXT PACK · {now_ist:%a %d %b %Y %H:%M} IST · read-only · regenerated every 10 min\n"
        "For Grok tasks and bots working for Aman Agrawal (ANS Group, Raigarh CG). Extract, never judge; never\n"
        "invent; NONE FOUND is a valid answer; never submit, pay, download paid documents, or execute anything.\n\n"
        "## Objectives (agenda.yaml, confirmed only — Aman's own words, nothing added)\n"
        + ("\n".join(obj_lines) if obj_lines else "- (none confirmed)") + "\n\n"
        "## Entities\n" + ("\n".join(ent_lines) if ent_lines else "- (none)") + "\n\n"
        "## Tender lens\n"
        "Only COAL WASHING and RCR (rake/coal handling) contracts matter. Margin first: an upfront profit margin\n"
        "good enough that no cuts are needed elsewhere; then eligibility, closing date, decision deadline. Every\n"
        "other tender is one line, not analysed. A qualifying coal-washing/RCR NIT, or one closing inside 72h, is\n"
        "urgent the hour it appears. Bid decisions are Aman's click.\n"
        f"Buyers of interest: {', '.join(buyers)}. Client sites: {', '.join(sites)}.\n\n"
        "## Market lens\n"
        f"Prime drivers: crude and major global factors — {', '.join(crude)}; tag crude-moving news\n"
        "positive/negative for Indian equities with the source piece. Rules: no fixed targets; NEVER book a loss;\n"
        "patient — a position is averaged only when a later exit scope is stated; trade suggestions only at >80%\n"
        "conviction with the reasoning and the invalidation (stop) level; proposals only, nothing executes.\n\n"
    )
    tail = (
        "\n## Output format (email tables, pipe-separated, header row first, one row per item)\n"
        "[GROK-TENDER] buyer|title|tender id|category|publish|closing|value|EMD|eligibility|location|URL\n"
        "[GROK-SINGHVI] stock|action|entry|stop|target|timeframe|rationale|source\n"
        "Only what the source states; a value not in the source stays blank (a call without entry/stop/target is\n"
        "not queued); URL on every row; dates YYYY-MM-DD; amounts as written (lakh/crore). Subject line = the tag.\n"
    )

    def known_block(per_kind: int) -> str:
        labels = (("tender", "tenders"), ("call", "calls (queued today / this fortnight)"),
                  ("news", "news"), ("fact", "facts"))
        lines = [f"## Already known — do not re-report (last {KNOWN_DAYS} days; repeats are counted, not resent)"]
        for kind, label in labels:
            keys = known.get(kind) or []
            if not keys:
                lines.append(f"{label}: none")
                continue
            shown = keys[:per_kind]
            more = f" (+{len(keys) - len(shown)} more)" if len(keys) > len(shown) else ""
            lines.append(f"{label}: " + "; ".join(shown) + more)
        return "\n".join(lines) + "\n"

    per_kind = 60
    text = head + known_block(per_kind) + tail
    while len(text.encode("utf-8")) > PACK_MAX_BYTES and per_kind > 0:
        per_kind = per_kind // 2 if per_kind > 4 else per_kind - 1
        text = head + known_block(per_kind) + tail
    raw = text.encode("utf-8")
    if len(raw) > PACK_MAX_BYTES:
        text = raw[:PACK_MAX_BYTES].decode("utf-8", "ignore")
    return text


# ── registration ─────────────────────────────────────────────────────────────
def _parse_since(s: str | None, now: datetime) -> str | None:
    """'24h' / '7d' / ISO date or datetime → sqlite-comparable UTC string."""
    if not s:
        return None
    s = str(s).strip().lower()
    m = re.fullmatch(r"(\d+)\s*([hd])", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = timedelta(hours=n) if unit == "h" else timedelta(days=n)
        return (now.astimezone(timezone.utc) - delta).strftime("%Y-%m-%d %H:%M:%S")
    try:
        dt = datetime.fromisoformat(s.replace("z", ""))
    except ValueError:
        raise HTTPException(400, "since: use 24h, 7d or an ISO date")
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def register(app, vdb: Callable[[], Awaitable[Any]]) -> dict:
    """Mount the grok memory endpoints. Returns helpers for the server and tests."""
    import mdo_cos_api
    import mdo_wa_intel

    cache: dict[str, Any] = {"text": "", "at": 0.0}
    hits: deque[float] = deque()

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    def invalidate() -> None:
        cache["text"], cache["at"] = "", 0.0

    def reset_rate() -> None:
        hits.clear()

    def rate_ok() -> bool:
        t = time.monotonic()
        while hits and t - hits[0] > 3600:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_PER_HOUR:
            return False
        hits.append(t)
        return True

    # ── memory ────────────────────────────────────────────────────────────
    async def upsert(items: list, default_source: str = "grok-relay") -> dict:
        db = await vdb()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        new, bumped, ids, skipped = 0, 0, [], {}
        for raw in items[:200]:
            row = normalise_item(raw, default_source)
            if isinstance(row, str):
                skipped[row] = skipped.get(row, 0) + 1
                continue
            existing = await db.execute_fetchall("SELECT id FROM grok_memory WHERE kind=? AND key=?", (row["kind"], row["key"]))
            if existing:
                await db.execute(
                    "UPDATE grok_memory SET times_seen=times_seen+1, last_seen=?, updated_at=?, source=?, "
                    "text=CASE WHEN ?!='' THEN ? ELSE text END, url=CASE WHEN ?!='' THEN ? ELSE url END, "
                    "entity=CASE WHEN ?!='' THEN ? ELSE entity END, sentiment=CASE WHEN ?!='' THEN ? ELSE sentiment END "
                    "WHERE id=?",
                    (now, now, row["source"], row["text"], row["text"], row["url"], row["url"],
                     row["entity"], row["entity"], row["sentiment"], row["sentiment"], existing[0][0]))
                bumped += 1
                ids.append(existing[0][0])
            else:
                cur = await db.execute(
                    "INSERT INTO grok_memory (source,kind,key,entity,text,url,sentiment,first_seen,last_seen,times_seen,status) "
                    "VALUES (?,?,?,?,?,?,?,?,?,1,'open')",
                    (row["source"], row["kind"], row["key"], row["entity"], row["text"], row["url"], row["sentiment"], now, now))
                new += 1
                ids.append(cur.lastrowid)
        await db.commit()
        if new or bumped:
            invalidate()
        return {"stored": new + bumped, "new": new, "bumped": bumped, "ids": ids, "skipped": skipped}

    async def memory_list(kind: str = "", entity: str = "", status: str = "", since: str = "",
                          sentiment: str = "", limit: int = 100) -> list[dict]:
        q, params = "SELECT * FROM grok_memory WHERE 1=1", []
        if kind:
            kinds = [k.strip().lower() for k in kind.split(",") if k.strip()]
            q += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += kinds
        if entity:
            q += " AND entity LIKE ?"
            params.append(f"%{entity}%")
        if status:
            q += " AND status=?"
            params.append(status.strip().lower())
        if sentiment:
            sents = [s.strip().lower() for s in sentiment.split(",") if s.strip()]
            q += f" AND sentiment IN ({','.join('?' * len(sents))})"
            params += sents
        s = _parse_since(since, datetime.now(timezone.utc))
        if s:
            q += " AND last_seen >= ?"
            params.append(s)
        q += " ORDER BY last_seen DESC, id DESC LIMIT ?"
        params.append(max(1, min(int(limit or 100), 500)))
        db = await vdb()
        return [dict(r) for r in await db.execute_fetchall(q, params)]

    @app.get("/api/grok/memory")
    async def grok_memory_get(kind: str = "", entity: str = "", status: str = "", since: str = "",
                              sentiment: str = "", limit: int = 100):
        rows = await memory_list(kind, entity, status, since, sentiment, limit)
        return {"memory": rows, "count": len(rows)}

    @app.post("/api/grok/memory")
    async def grok_memory_post(request: Request):
        """One row or a list. Upsert on (kind, key): a repeat bumps times_seen and
        last_seen and keeps first_seen. Keys are computed when absent."""
        try:
            body = json.loads((await request.body()) or b"{}")
        except json.JSONDecodeError:
            raise HTTPException(400, "bad json")
        items = body if isinstance(body, list) else (body.get("items") if isinstance(body, dict) and isinstance(body.get("items"), list) else [body])
        res = await upsert(items)
        if not res["stored"] and res["skipped"] and len(items) == 1:
            raise HTTPException(400, "rejected: " + ", ".join(res["skipped"]))
        return res

    @app.post("/api/grok/memory/{mem_id}/status")
    async def grok_memory_status(mem_id: int, body: dict):
        status = str(body.get("status") or "").strip().lower()
        if status not in STATUSES:
            raise HTTPException(400, "status must be one of " + ", ".join(STATUSES))
        db = await vdb()
        cur = await db.execute("UPDATE grok_memory SET status=?, updated_at=datetime('now') WHERE id=?", (status, mem_id))
        await db.commit()
        if not cur.rowcount:
            raise HTTPException(404, "no such memory row")
        invalidate()
        return {"id": mem_id, "status": status}

    # ── the pack ──────────────────────────────────────────────────────────
    async def build_pack(now: datetime | None = None) -> str:
        now = now or datetime.now(IST)
        agenda = mdo_cos_api.load_yaml(mdo_cos_api.AGENDA_PATH)
        fleet = mdo_cos_api.load_yaml(mdo_cos_api.FLEET_PATH)
        db = await vdb()
        since = _since_utc(now, KNOWN_DAYS)
        # every status: a row Aman marked done or dismissed is still something Grok must not re-report
        recent = [dict(r) for r in await db.execute_fetchall(
            "SELECT kind, key, entity, last_seen FROM grok_memory WHERE last_seen >= ? "
            "ORDER BY last_seen DESC LIMIT 400", (since,))]
        try:
            tenders = [dict(r) for r in await db.execute_fetchall(
                "SELECT buyer, notes, url, due_date FROM vwlr_tender_pipeline WHERE created_at >= ? ORDER BY id DESC LIMIT 100",
                (since,))]
        except Exception:
            tenders = []
        try:
            calls = [dict(r) for r in await db.execute_fetchall(
                "SELECT ticker, direction FROM singhvi_calls WHERE date=?", (now.astimezone(IST).date().isoformat(),))]
        except Exception:
            calls = []
        return build_context(agenda.get("objectives") or [], mdo_wa_intel.ENTITIES, keywords_from_fleet(fleet),
                             recent, tenders, calls, now)

    async def pack_cached() -> tuple[str, bool]:
        if cache["text"] and time.monotonic() - cache["at"] < PACK_TTL_SECONDS:
            return cache["text"], True
        text = await build_pack()
        cache["text"], cache["at"] = text, time.monotonic()
        return text, False

    async def audit(ip: str, ok: bool, nbytes: int, note: str = "") -> None:
        db = await vdb()
        await db.execute("INSERT INTO grok_context_audit (ip, ok, bytes, note) VALUES (?,?,?,?)",
                         (ip[:64], 1 if ok else 0, nbytes, note[:200]))
        await db.commit()

    def _token_ok(request: Request, k: str) -> bool:
        tok = os.environ.get("GROK_CONTEXT_TOKEN", "").strip()
        got = (request.headers.get("x-grok-context-token") or k or "").strip()
        return bool(tok) and bool(got) and hmac.compare_digest(got, tok)

    @app.get("/api/grok/context")
    async def grok_context(request: Request, k: str = ""):
        """The read-only context pack for Grok tasks. Token in ?k= or X-Grok-Context-Token;
        exempt from the app key (mdo_server middleware). Every fetch is audited."""
        ip = (request.client.host if request.client else "") or ""
        if not _token_ok(request, k):
            await audit(ip, False, 0, "bad or missing token")
            raise HTTPException(403, "bad or missing context token")
        if not rate_ok():
            await audit(ip, False, 0, "rate limit")
            raise HTTPException(429, f"rate limit: {RATE_LIMIT_PER_HOUR} fetches per hour")
        text, cached = await pack_cached()
        await audit(ip, True, len(text.encode("utf-8")), "cached" if cached else "built")
        return PlainTextResponse(text, headers={"Cache-Control": "no-store"})

    @app.get("/api/grok/context-internal")
    async def grok_context_internal():
        """The same pack for the VPS bots (mdo_agent.ask_grok), behind the app key."""
        text, cached = await pack_cached()
        return {"context": text, "bytes": len(text.encode("utf-8")), "cached": cached}

    @app.get("/api/grok/context/audit")
    async def grok_context_audit(limit: int = 50):
        db = await vdb()
        rows = await db.execute_fetchall("SELECT * FROM grok_context_audit ORDER BY id DESC LIMIT ?", (min(int(limit), 500),))
        return {"audit": [dict(r) for r in rows]}

    return {"ensure_schema": ensure_schema, "upsert": upsert, "memory_list": memory_list, "build_pack": build_pack,
            "invalidate": invalidate, "reset_rate": reset_rate}
