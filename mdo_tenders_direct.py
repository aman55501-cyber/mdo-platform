"""tenders-direct — public tender listings read straight from the buyers' own pages. Rules only, zero LLM spend.

Replaces the Tender247 / Grok dependency for the first look (fleet_gaps: "tender_watch has no Tender247 access").
No login, no API key, no scraping library: urllib + the stdlib html.parser. Each site is one public listing page;
every table on the page is read, the header row names the columns (title / tender no / published / closing /
organisation / value), and each data row becomes one tenders_direct row keyed UNIQUE(source, tender_id). A row is
"matched" when its title or organisation carries one of TENDERS_KEYWORDS (default: washery, washing, beneficiation,
RCR, road cum rail, coal transportation, coal loading, rake loading, siding, surface transport, crushing,
overburden) and, when TENDERS_MIN_VALUE_CR is set, its stated value is not below it (an unstated value never
disqualifies — nothing is invented, the row just says "value n/a").

Sites (public pages, no login):
  secl             SECL tender notices            https://www.secl-cil.in/tenders
  secl-etender     SECL e-tenders (NIC listing)   https://coalindiatenders.nic.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page
  coalindia        Coal India tenders             https://www.coalindia.in/tenders/
  ntpc             NTPC tenders                   https://www.ntpctender.com/
  eprocure         CPP portal, latest active      https://eprocure.gov.in/eprocure/app?page=FrontEndLatestActiveTenders&service=page
  mstc             MSTC coal e-auction notices    https://www.mstcecommerce.com/auctionhome/coal/index.jsp
A site that fails (timeout, HTTP error, anti-bot 403, TLS) is reported per site in the heartbeat line and never
crashes the run (Directive 5). A page that answers but yields no rows is reported as "0 rows (layout?)" so a
changed layout announces itself instead of looking like a quiet day.

New matches go into the existing tender pipeline through the tender door's body (mdo_cos_api.tender_ingest,
source "direct:<site>") so tender-go-no-go sees them, and Aman gets ONE WhatsApp message per run only when there
are new matches: "Tenders · N new:" + one line per tender (≤10 lines): title — org — due <date> — url.

Run by `python mdo_agent.py tenders-direct` (fleet.yaml: tenders-direct) at 06:30 and 18:30 IST through
POST /api/tenders/direct/run. Heartbeat every run: "tenders-direct: S sites ok/F failed, P pages, M matched
(N new)" + the per-site failures. The pure helpers above register() take plain values and touch nothing —
tests/test_tenders_direct.py runs them on canned HTML per site.
"""
from __future__ import annotations

import asyncio
import hashlib
import html as _html
import os
import re
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from mdo_cos import IST

BOT_ID = "tenders-direct"
KEYWORDS_DEFAULT = ("washery;washing;beneficiation;RCR;road cum rail;coal transportation;coal loading;rake loading;"
                    "siding;surface transport;crushing;overburden")
PUSH_MAX_LINES = 10
FETCH_TIMEOUT = 25
MAX_ROWS_PER_SITE = 400
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) MDO-tenders-direct/1.0 (public tender notices; +aman.55501@gmail.com)"
SITES: tuple[dict, ...] = (
    {"key": "secl", "label": "SECL tenders", "org": "SECL", "parser": "table",
     "url": "https://www.secl-cil.in/tenders"},
    {"key": "secl-etender", "label": "SECL e-tenders (NIC)", "org": "SECL", "parser": "cpp",
     "url": "https://coalindiatenders.nic.in/nicgep/app?page=FrontEndLatestActiveTenders&service=page"},
    {"key": "coalindia", "label": "Coal India tenders", "org": "Coal India", "parser": "table",
     "url": "https://www.coalindia.in/tenders/"},
    {"key": "ntpc", "label": "NTPC tenders", "org": "NTPC", "parser": "table",
     "url": "https://ntpctender.ntpc.co.in/"},
    {"key": "eprocure", "label": "CPP portal (eprocure)", "org": "", "parser": "cpp",
     "url": "https://eprocure.gov.in/eprocure/app?page=FrontEndLatestActiveTenders&service=page"},
    {"key": "mstc", "label": "MSTC coal e-auction notices", "org": "MSTC", "parser": "table",
     "url": "https://www.mstcecommerce.com/auctionhome/coal/index.jsp"},
)
BLOCKED_CODES = {401, 403, 406, 429, 503}
CATEGORY_KEYWORDS = (                    # first match wins; the pipeline category tender-go-no-go reads
    ("Coal washing", ("washery", "washing", "beneficiation")),
    ("RCR", ("rcr", "road cum rail", "road-cum-rail")),
    ("Coal transport", ("coal transportation", "surface transport", "transportation", "transport")),
    ("Loading", ("coal loading", "rake loading", "loading", "siding")),
    ("Mining services", ("overburden", "crushing")),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenders_direct (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,                             -- site key: secl | secl-etender | coalindia | ntpc | eprocure | mstc
    tender_id TEXT NOT NULL,                          -- the site's reference, else a hash of url/title
    title TEXT NOT NULL DEFAULT '',
    org TEXT NOT NULL DEFAULT '',
    published TEXT NOT NULL DEFAULT '',               -- YYYY-MM-DD or ''
    due TEXT NOT NULL DEFAULT '',                     -- YYYY-MM-DD or ''
    value_text TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    matched INTEGER NOT NULL DEFAULT 0,
    keywords TEXT NOT NULL DEFAULT '',                -- the keywords that matched, comma-separated
    category TEXT NOT NULL DEFAULT '',
    first_seen TEXT DEFAULT (datetime('now')),
    last_seen TEXT DEFAULT (datetime('now')),
    pushed_at TEXT,
    pipeline_posted INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source, tender_id)
);
CREATE INDEX IF NOT EXISTS idx_tenders_direct_due ON tenders_direct(matched, due);
CREATE TABLE IF NOT EXISTS tenders_direct_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at TEXT DEFAULT (datetime('now')),
    sites_ok INTEGER DEFAULT 0, sites_failed INTEGER DEFAULT 0, pages INTEGER DEFAULT 0,
    rows INTEGER DEFAULT 0, matched INTEGER DEFAULT 0, new INTEGER DEFAULT 0, pushed INTEGER DEFAULT 0,
    line TEXT DEFAULT '', sites_json TEXT DEFAULT '{}'
);
"""


# ═════════════════════════════════════════════════════════════════════════════
# Pure helpers — no database, no network
# ═════════════════════════════════════════════════════════════════════════════

def _query_tz(s: str) -> str:
    """'2026-10-09T08:00:00 05:30' → '+05:30': an unescaped '+' in a query string arrives as a space."""
    return re.sub(r" (\d\d:\d\d)$", r"+\1", s.strip())

def keywords(raw: str | None = None) -> list[str]:
    """TENDERS_KEYWORDS — semicolon (or comma) separated, matched case-insensitively; duplicates dropped."""
    raw = os.environ.get("TENDERS_KEYWORDS", KEYWORDS_DEFAULT) if raw is None else raw
    out, seen = [], set()
    for part in re.split(r"[;,]", str(raw or "")):
        p = " ".join(part.split())
        if p and p.lower() not in seen:
            seen.add(p.lower()); out.append(p)
    return out or keywords(KEYWORDS_DEFAULT)


def min_value_cr(raw: str | None = None) -> float:
    """TENDERS_MIN_VALUE_CR — rows whose stated value is below this are not matched; 0 = no floor (default)."""
    raw = os.environ.get("TENDERS_MIN_VALUE_CR", "0") if raw is None else raw
    try:
        return max(0.0, float(str(raw or "0").strip()))
    except ValueError:
        return 0.0


def sites() -> list[dict]:
    """The site list; TENDERS_SITES_OFF (comma-separated keys) switches a site off without a code change."""
    off = {s.strip().lower() for s in os.environ.get("TENDERS_SITES_OFF", "").split(",") if s.strip()}
    return [dict(s) for s in SITES if s["key"] not in off]


def _clean(s: Any) -> str:
    return " ".join(_html.unescape(str(s or "")).replace("\xa0", " ").split())


class _TableParser(HTMLParser):
    """Every table on the page → rows → cells {text, href}. Nested tables (the CPP layout) are kept apart: text
    inside an inner table belongs to the inner table only. Anchors are collected too for a list-style fallback."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict]]] = []
        self.anchors: list[dict] = []
        self._stack: list[list[list[dict]]] = []            # open tables
        self._row: list[list[dict]] = []                     # open row per open table
        self._cell: list[dict | None] = []                   # open cell per open table
        self._href: str | None = None
        self._atext: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
            return
        if tag == "table":
            self._stack.append([]); self._row.append([]); self._cell.append(None)
        elif tag == "tr" and self._stack:
            if self._row[-1]:
                self._stack[-1].append(self._row[-1])
            self._row[-1] = []
            self._cell[-1] = None
        elif tag in ("td", "th") and self._stack:
            self._cell[-1] = {"text": "", "href": "", "head": tag == "th"}
            self._row[-1].append(self._cell[-1])
        elif tag == "a":
            self._href = a.get("href") or ""
            self._atext = []
            if self._stack and self._cell[-1] is not None and not self._cell[-1]["href"] and self._href:
                self._cell[-1]["href"] = self._href
        elif tag == "br" and self._stack and self._cell[-1] is not None:
            self._cell[-1]["text"] += " | "

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
            return
        if tag == "table" and self._stack:
            if self._row[-1]:
                self._stack[-1].append(self._row[-1])
            self.tables.append(self._stack.pop()); self._row.pop(); self._cell.pop()
        elif tag == "tr" and self._stack:
            if self._row[-1]:
                self._stack[-1].append(self._row[-1])
            self._row[-1] = []
            self._cell[-1] = None
        elif tag in ("td", "th") and self._stack:
            self._cell[-1] = None
        elif tag == "a":
            if self._href is not None:
                self.anchors.append({"text": _clean("".join(self._atext)), "href": self._href})
            self._href, self._atext = None, []

    def handle_data(self, data):
        if self._skip:
            return
        if self._href is not None:
            self._atext.append(data)
        if self._stack and self._cell[-1] is not None:
            self._cell[-1]["text"] += data


def parse_tables(html: str) -> tuple[list[list[list[dict]]], list[dict]]:
    """(tables, anchors). Cell texts are whitespace-collapsed; '|' marks a <br> inside a cell."""
    p = _TableParser()
    try:
        p.feed(html or "")
        p.close()
    except Exception:
        pass
    tables = []
    for t in p.tables:
        rows = []
        for r in t:
            rows.append([{"text": _clean(c["text"]).strip(" |"), "href": c["href"].strip(), "head": c["head"]} for c in r])
        tables.append(rows)
    return tables, p.anchors


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_DATE_PATTERNS = (
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),                                   # 2026-10-09
    re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"),                            # 09-10-2026, 09/10/2026
    re.compile(r"\b(\d{1,2})[-\s/]([A-Za-z]{3})[a-z]*[-\s/,]+(\d{4})\b"),              # 09-Oct-2026, 9 October 2026
    re.compile(r"\b([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b"),                 # Oct 9, 2026
)


def parse_date(s: Any) -> str:
    """The first date in the text as YYYY-MM-DD, '' when none is written. Day-first for numeric forms (Indian sites)."""
    t = _clean(s)
    if not t:
        return ""
    for i, rx in enumerate(_DATE_PATTERNS):
        m = rx.search(t)
        if not m:
            continue
        try:
            if i == 0:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif i == 1:
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif i == 2:
                d, mo, y = int(m.group(1)), _MONTHS.get(m.group(2).lower(), 0), int(m.group(3))
            else:
                mo, d, y = _MONTHS.get(m.group(1).lower(), 0), int(m.group(2)), int(m.group(3))
            if mo and 2000 <= y <= 2100:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


_VALUE_RX = re.compile(r"(?:₹|rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\.?|lakhs?|lacs?|lakh|million|mn)?", re.I)


def value_cr(text: Any) -> float | None:
    """A stated value in crores, or None when the text carries no money amount (then the floor never applies)."""
    t = _clean(text).lower()
    if not t or t in ("na", "n/a", "-", "--", "nil", "not applicable"):
        return None
    best = None
    for m in _VALUE_RX.finditer(t):
        raw = m.group(1).replace(",", "")
        if not raw or raw == "." or not re.search(r"\d", raw):
            continue
        try:
            n = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or "").lower()
        if unit.startswith("cr"):
            v = n
        elif unit.startswith(("lakh", "lac")):
            v = n / 100.0
        elif unit in ("million", "mn"):
            v = n / 10.0
        elif n >= 100000:                      # bare rupees
            v = n / 1e7
        else:
            continue                           # a bare small number is a serial or a count, not money
        best = v if best is None else max(best, v)
    return best


def match_keywords(text: Any, kws: list[str] | None = None) -> list[str]:
    """The keywords present in the text (case-insensitive; short ones like RCR on word boundaries)."""
    t = " " + re.sub(r"[^a-z0-9]+", " ", _clean(text).lower()) + " "
    hits = []
    for k in (kws if kws is not None else keywords()):
        kn = re.sub(r"[^a-z0-9]+", " ", k.lower()).strip()
        if not kn:
            continue
        if len(kn) <= 4 or " " in kn:
            if re.search(r"(?<![a-z0-9])" + re.escape(kn) + r"(?![a-z0-9])", t):
                hits.append(k)
        elif kn in t:
            hits.append(k)
    return hits


def category_for(matched: list[str], title: str = "") -> str:
    probe = " ".join(matched + [title]).lower()
    for cat, words in CATEGORY_KEYWORDS:
        if any(w in probe for w in words):
            return cat
    return "Other"


def classify(t: dict, kws: list[str] | None = None, floor_cr: float | None = None) -> dict:
    """Adds matched / keywords / category / value_cr to a parsed tender. Pure."""
    hits = match_keywords(f"{t.get('title', '')} {t.get('org', '')}", kws)
    floor = min_value_cr() if floor_cr is None else floor_cr
    v = value_cr(t.get("value_text", ""))
    matched = bool(hits) and not (floor > 0 and v is not None and v < floor)
    return {**t, "matched": matched, "keywords": hits, "category": category_for(hits, t.get("title", "")) if hits else "",
            "value_cr": v}


_HEAD = {
    "title": re.compile(r"title|description|name of (the )?work|work|subject|tender details|details|particulars|item", re.I),
    "tender_id": re.compile(r"tender\s*(no|id|ref|number|notice)|ref\.?\s*no|reference|nit\s*no|notice\s*no|^id$|e-?tender", re.I),
    "published": re.compile(r"publish|issue|start|uploaded|posted|date of (nit|notice)", re.I),
    "due": re.compile(r"clos|due|last date|submission|bid end|end date|deadline|valid (till|upto)", re.I),
    "org": re.compile(r"organi[sz]ation|department|company|subsidiar|area|unit|region|buyer|agency|project", re.I),
    "value": re.compile(r"value|cost|amount|estimat|emd", re.I),
}
_ORDER = ("tender_id", "due", "published", "value", "org", "title")        # specific columns first; title is the widest


def header_map(cells: list[dict]) -> dict[str, int]:
    """Column index per field for a header row, {} when the row is not a header (fewer than 2 known columns,
    or no title column). A cell that says title/description is the title even when it also says "Tender ID"
    (the CPP "Title and Ref.No./Tender ID" column); the id is then split out of the cell text."""
    out: dict[str, int] = {}
    for i, c in enumerate(cells):
        txt = c["text"]
        if not txt or len(txt) > 80:
            continue
        if "title" not in out and _HEAD["title"].search(txt) and not (
                _HEAD["tender_id"].search(txt) and not re.search(r"title|description|details", txt, re.I)):
            out["title"] = i
            continue
        for field in _ORDER:
            if field in out or field == "title":
                continue
            if _HEAD[field].search(txt):
                if field == "published" and _HEAD["due"].search(txt):
                    continue
                out[field] = i
                break
    if "title" not in out and "tender_id" in out and len(cells) >= 2:
        # "Tender No | <unnamed wide column>" style: title = the first column not otherwise taken
        free = [i for i in range(len(cells)) if i not in out.values() and cells[i]["text"] and len(cells[i]["text"]) <= 40
                and not re.match(r"^(s\.?\s*no\.?|sr\.?\s*no\.?|sl\.?\s*no\.?|sl|#)$", cells[i]["text"], re.I)]
        if free:
            out["title"] = free[0]
    return out if len(out) >= 2 and "title" in out else {}


def _abs(href: str, base: str) -> str:
    if not href or href.startswith(("javascript:", "#")):
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    try:
        from urllib.parse import urljoin
        return urljoin(base, href)
    except Exception:
        return href


def _tender_id_of(raw: str, url: str, title: str) -> str:
    rid = _clean(raw)[:80]
    if rid and (not rid.isdigit() or len(rid) >= 5):          # a bare short number is a serial, not a reference
        return rid
    return "h:" + hashlib.sha1((url or title).encode("utf-8", "replace")).hexdigest()[:12]


_BRACKETS = re.compile(r"\[([^\]]*)\]")


def _cpp_title(cell_text: str) -> tuple[str, str]:
    """CPP/NIC 'Title and Ref.No./Tender ID' cell: '[title][ref no][tender id]' → (title, id)."""
    parts = [p.strip() for p in _BRACKETS.findall(cell_text) if p.strip()]
    if not parts:
        t = cell_text.strip(" |")
        return t, ""
    title = parts[0]
    tid = parts[-1] if len(parts) > 1 else ""
    return title, tid


def _cpp_org(cell_text: str) -> str:
    segs = [s.strip() for s in re.split(r"\|\||\|", cell_text) if s.strip()]
    if not segs:
        return ""
    return " / ".join(segs[-2:]) if len(segs) > 1 else segs[0]


def rows_to_tenders(table: list[list[dict]], site: dict) -> list[dict]:
    """One table → tenders, using the first header row the table has. Rows without a title are skipped."""
    out: list[dict] = []
    hmap: dict[str, int] = {}
    for row in table:
        if not hmap:
            hmap = header_map(row)
            continue
        if len(row) <= hmap["title"]:
            continue
        cells = row
        tcell = cells[hmap["title"]]
        raw_title = tcell["text"]
        if site.get("parser") == "cpp":
            title, tid = _cpp_title(raw_title)
        else:
            title, tid = raw_title, ""
        if "tender_id" in hmap and hmap["tender_id"] < len(cells):
            tid = cells[hmap["tender_id"]]["text"] or tid
        title = _clean(title)[:300]
        if not title or _HEAD["title"].search(title) and len(title) < 25 and header_map(row):
            continue                                              # a repeated header row
        url = ""
        for idx in (hmap["title"], hmap.get("tender_id", -1)):
            if 0 <= idx < len(cells) and cells[idx]["href"]:
                url = _abs(cells[idx]["href"], site["url"]); break
        if not url:
            for c in cells:
                if c["href"]:
                    url = _abs(c["href"], site["url"]); break
        org_text = cells[hmap["org"]]["text"] if "org" in hmap and hmap["org"] < len(cells) else ""
        org = _cpp_org(org_text) if site.get("parser") == "cpp" else _clean(org_text)
        if org and site.get("parser") != "cpp" and site.get("org") and site["org"].lower() not in org.lower():
            org = f"{site['org']} / {org}"                        # "NTPC / Lara" — the buyer first, then its unit
        t = {
            "source": site["key"], "title": title,
            "tender_id": _tender_id_of(tid, url, title),
            "org": (org or site.get("org") or "")[:120],
            "published": parse_date(cells[hmap["published"]]["text"]) if "published" in hmap and hmap["published"] < len(cells) else "",
            "due": parse_date(cells[hmap["due"]]["text"]) if "due" in hmap and hmap["due"] < len(cells) else "",
            "value_text": _clean(cells[hmap["value"]]["text"])[:80] if "value" in hmap and hmap["value"] < len(cells) else "",
            "url": url[:500],
        }
        out.append(t)
        if len(out) >= MAX_ROWS_PER_SITE:
            break
    return out


def parse_listing(html: str, site: dict) -> list[dict]:
    """Every tender the page lists, across all its tables; de-duplicated on (source, tender_id). Never raises."""
    tables, _anchors = parse_tables(html)
    out, seen = [], set()
    for table in tables:
        for t in rows_to_tenders(table, site):
            k = (t["source"], t["tender_id"])
            if k in seen:
                continue
            seen.add(k); out.append(t)
    return out


def probe_summary(html: str, url: str, max_links: int = 40) -> dict:
    """A compact picture of a fetched page, for tuning a parser: size, <title>, every table's first rows, links."""
    tables, links = parse_tables(html)
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = _clean(re.sub(r"<[^>]+>", " ", body))
    return {"url": url, "ok": True, "bytes": len(html), "title": _clean(title.group(1)) if title else "",
            "scripts": len(re.findall(r"(?i)<script", html)), "text_head": text[:600],
            "tables": [{"rows": len(t), "first_rows": [[c["text"][:70] for c in r][:8] for r in t[:4]]} for t in tables[:8]],
            "links": [{"text": _clean(l.get("text", ""))[:80], "href": l.get("href", "")[:160]} for l in links[:max_links]]}


def fetch_page(url: str, timeout: int = FETCH_TIMEOUT) -> dict:
    """GET one public page. {ok, status, html, reason}. Never raises; a block (403/429/503) is named as such."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                                               "Accept-Language": "en-IN,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(6 * 1024 * 1024)
            charset = r.headers.get_content_charset() or "utf-8"
            try:
                html = raw.decode(charset, "replace")
            except LookupError:
                html = raw.decode("utf-8", "replace")
            return {"ok": True, "status": int(r.status or 200), "html": html, "reason": ""}
    except urllib.error.HTTPError as e:
        code = int(e.code)
        if code in BLOCKED_CODES:
            return {"ok": False, "status": code, "html": "", "reason": f"blocked (HTTP {code} — anti-bot/maintenance)"}
        return {"ok": False, "status": code, "html": "", "reason": f"HTTP {code}"}
    except ssl.SSLError as e:
        return {"ok": False, "status": 0, "html": "", "reason": f"tls error: {str(e)[:60]}"}
    except (socket.timeout, TimeoutError):
        return {"ok": False, "status": 0, "html": "", "reason": f"timeout after {timeout}s"}
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ssl.SSLError):
            return {"ok": False, "status": 0, "html": "", "reason": f"tls error: {str(reason)[:60]}"}
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return {"ok": False, "status": 0, "html": "", "reason": f"timeout after {timeout}s"}
        return {"ok": False, "status": 0, "html": "", "reason": f"unreachable: {str(reason)[:60]}"}
    except Exception as e:
        return {"ok": False, "status": 0, "html": "", "reason": f"{type(e).__name__}: {str(e)[:60]}"}


def push_text(new_rows: list[dict]) -> str:
    """ONE WhatsApp message: "Tenders · N new:" then ≤10 lines "title — org — due <date> — url"."""
    n = len(new_rows)
    lines = [f"Tenders · {n} new:"]
    for t in sorted(new_rows, key=lambda r: (r.get("due") or "9999-12-31", r.get("title") or ""))[:PUSH_MAX_LINES]:
        due = t.get("due") or "n/a"
        bits = [_clean(t.get("title"))[:120], _clean(t.get("org")) or "org n/a", f"due {due}"]
        if t.get("url"):
            bits.append(t["url"])
        lines.append("• " + " — ".join(bits))
    if n > PUSH_MAX_LINES:
        lines.append(f"… +{n - PUSH_MAX_LINES} more — see Morning › Tenders")
    return "\n".join(lines)


def heartbeat_line(ok: int, failed: int, pages: int, matched: int, new: int, failures: dict[str, str] | None = None,
                   empty: list[str] | None = None) -> str:
    """"tenders-direct: S sites ok/F failed, P pages, M matched (N new)" + per-site failures and empty pages."""
    line = f"{BOT_ID}: {ok} sites ok/{failed} failed, {pages} pages, {matched} matched ({new} new)"
    for key, why in (failures or {}).items():
        line += f" · {key}: {why}"
    if empty:
        line += " · 0 rows (layout?): " + ", ".join(empty)
    return line


def _parse_now(v: Any) -> datetime:
    if isinstance(v, datetime):
        d = v
    elif v:
        try:
            d = datetime.fromisoformat(_query_tz(str(v).replace("Z", "+00:00")))
        except ValueError:
            d = datetime.now(IST)
    else:
        d = datetime.now(IST)
    return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(IST)


# ═════════════════════════════════════════════════════════════════════════════
# Registration — tables, endpoints, the run the bot triggers
# ═════════════════════════════════════════════════════════════════════════════
def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict],
             tender_ingest: Callable[..., Awaitable[dict]] | None = None) -> dict:
    """Mount /api/tenders/direct/*. `send_cos` is the same function POST /api/cos/send wraps; `tender_ingest` is the
    tender door's body (mdo_cos_api.register()['tender_ingest']) so new matches land in vwlr_tender_pipeline."""
    import asyncio
    import json

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    def _row(r) -> dict:
        d = dict(r)
        d["matched"] = bool(d.get("matched"))
        d["pipeline_posted"] = bool(d.get("pipeline_posted"))
        d["keywords"] = [k for k in str(d.get("keywords") or "").split(",") if k]
        return d

    async def last_run(db) -> dict | None:
        rows = await db.execute_fetchall("SELECT * FROM tenders_direct_runs ORDER BY id DESC LIMIT 1")
        if not rows:
            return None
        d = dict(rows[0])
        try:
            d["sites"] = json.loads(d.pop("sites_json") or "{}")
        except ValueError:
            d["sites"] = {}
        return d

    async def upsert(db, t: dict, stamp: str) -> bool:
        """INSERT the row or refresh last_seen (and fill blanks). Returns True when the row is new."""
        cur = await db.execute(
            "INSERT OR IGNORE INTO tenders_direct (source, tender_id, title, org, published, due, value_text, url, matched, "
            "keywords, category, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (t["source"], t["tender_id"], t["title"], t["org"], t["published"], t["due"], t["value_text"], t["url"],
             1 if t["matched"] else 0, ",".join(t["keywords"]), t["category"], stamp, stamp))
        if cur.rowcount == 1:
            return True
        await db.execute(
            "UPDATE tenders_direct SET last_seen=?, due=CASE WHEN due='' THEN ? ELSE due END, "
            "published=CASE WHEN published='' THEN ? ELSE published END, "
            "value_text=CASE WHEN value_text='' THEN ? ELSE value_text END, url=CASE WHEN url='' THEN ? ELSE url END "
            "WHERE source=? AND tender_id=?",
            (stamp, t["due"], t["published"], t["value_text"], t["url"], t["source"], t["tender_id"]))
        return False

    async def run(now_v: Any = None) -> dict:
        """One sweep of every site: fetch → parse → upsert → classify; new matches → tender door + one push;
        the heartbeat line always, with per-site failures named (Directive 5)."""
        now = _parse_now(now_v)
        stamp = now.astimezone(timezone.utc).isoformat()
        kws, floor = keywords(), min_value_cr()
        out: dict[str, Any] = {"as_of": now.isoformat(), "keywords": kws, "min_value_cr": floor, "sites": {},
                               "sites_ok": 0, "sites_failed": 0, "pages": 0, "rows": 0, "matched": 0, "new": 0,
                               "new_matched": [], "pushed": 0, "push_failed": 0, "push": {}, "text": "",
                               "pipeline_posted": 0, "status": "clean", "line": "", "note": ""}
        db = await vdb()
        await ensure_schema(db)
        failures: dict[str, str] = {}
        ever_ok: set[str] = set()          # sites that have answered in some earlier run: only their failure is news
        for r in await db.execute_fetchall("SELECT sites_json FROM tenders_direct_runs ORDER BY id DESC LIMIT 200"):
            try:
                ever_ok.update(k for k, v in json.loads(dict(r)["sites_json"] or "{}").items() if v.get("ok"))
            except (ValueError, AttributeError):
                pass
        empty: list[str] = []
        parse_errors: list[str] = []       # a parser that blows up is always news
        new_matched: list[dict] = []
        for site in sites():
            info: dict[str, Any] = {"label": site["label"], "url": site["url"], "ok": False, "status": 0, "rows": 0,
                                    "matched": 0, "new": 0, "reason": ""}
            out["sites"][site["key"]] = info
            try:
                fetched = await asyncio.to_thread(fetch_page, site["url"])
            except Exception as e:                                   # never let one site end the run
                fetched = {"ok": False, "status": 0, "html": "", "reason": f"{type(e).__name__}: {str(e)[:60]}"}
            info["status"] = fetched.get("status", 0)
            if not fetched.get("ok"):
                info["reason"] = fetched.get("reason") or "failed"
                failures[site["key"]] = info["reason"]
                out["sites_failed"] += 1
                continue
            info["ok"] = True
            out["sites_ok"] += 1
            out["pages"] += 1
            try:
                tenders = parse_listing(fetched["html"], site)
            except Exception as e:
                tenders = []
                info["reason"] = f"parse error: {type(e).__name__}"
                parse_errors.append(site["key"])
            if not tenders:
                empty.append(site["key"])
            for t in tenders:
                t = classify(t, kws, floor)
                is_new = await upsert(db, t, stamp)
                info["rows"] += 1
                out["rows"] += 1
                if t["matched"]:
                    info["matched"] += 1
                    out["matched"] += 1
                    if is_new:
                        info["new"] += 1
                        out["new"] += 1
                        new_matched.append(t)
            await db.commit()
        out["new_matched"] = [{k: t[k] for k in ("source", "tender_id", "title", "org", "due", "value_text", "url", "category", "keywords")}
                              for t in new_matched]
        # new matches → the tender pipeline through the door's body (source direct:<site>)
        posted = 0
        if new_matched and tender_ingest is not None:
            by_site: dict[str, list[dict]] = {}
            for t in new_matched:
                by_site.setdefault(t["source"], []).append(t)
            for key, ts in by_site.items():
                items = [{"buyer": t["org"], "title": t["title"], "category": t["category"], "due_date": t["due"] or None,
                          "url": t["url"], "source": f"direct:{key}", "status": "evaluating",
                          "notes": " · ".join(x for x in (f"value {t['value_text']}" if t["value_text"] else "", f"ref {t['tender_id']}") if x)}
                         for t in ts]
                try:
                    r = await tender_ingest(items, f"direct:{key}")
                    posted += int(r.get("added") or 0)
                except Exception as e:
                    out["note"] = (out["note"] + " · " if out["note"] else "") + f"tender door failed ({key}): {str(e)[:80]}"
            if posted:
                for t in new_matched:
                    await db.execute("UPDATE tenders_direct SET pipeline_posted=1 WHERE source=? AND tender_id=?",
                                     (t["source"], t["tender_id"]))
                await db.commit()
        elif new_matched:
            out["note"] = (out["note"] + " · " if out["note"] else "") + "tender door not wired — stored only"
        out["pipeline_posted"] = posted
        # ONE WhatsApp message, only when there are NEW matching tenders
        if new_matched:
            text = push_text(new_matched)
            out["text"] = text
            try:
                push = send_cos(text) or {}
            except Exception as e:
                push = {"sent": False, "reason": str(e)[:200]}
            out["push"] = push
            if push.get("sent"):
                out["pushed"] = 1
                for t in new_matched:
                    await db.execute("UPDATE tenders_direct SET pushed_at=? WHERE source=? AND tender_id=?",
                                     (stamp, t["source"], t["tender_id"]))
                await db.commit()
            else:
                out["push_failed"] = 1
                out["status"] = "warning"
        line = heartbeat_line(out["sites_ok"], out["sites_failed"], out["pages"], out["matched"], out["new"], failures, empty)
        if new_matched:
            line += " · 1 message pushed" if out["pushed"] else " · push NOT delivered"
        if posted:
            line += f" · {posted} → pipeline"
        if out["note"]:
            line += " · " + out["note"]
        if out["sites_failed"] and out["sites_ok"] == 0:
            out["status"] = "error"
        elif (parse_errors or any(k in ever_ok for k in failures)) and out["status"] == "clean":
            out["status"] = "warning"       # a site that used to answer has stopped; one never reached stays in the line, not the alarm
            bad = [k for k in failures if k in ever_ok] + parse_errors
            line += " · REGRESSION: " + ", ".join(bad)
            out["line"] = line
        out["line"] = line
        await db.execute(
            "INSERT INTO tenders_direct_runs (ran_at, sites_ok, sites_failed, pages, rows, matched, new, pushed, line, sites_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (stamp, out["sites_ok"], out["sites_failed"], out["pages"], out["rows"], out["matched"], out["new"], out["pushed"],
             line[:1000], json.dumps(out["sites"])[:4000]))
        await db.commit()
        return out

    async def upcoming(days: int = 30, now_v: Any = None) -> dict:
        """Matched tenders due inside the next `days` (IST), by due date; undated matches listed after them."""
        days = max(1, min(int(days or 30), 400))
        now = _parse_now(now_v)
        today = now.strftime("%Y-%m-%d")
        until = (now + timedelta(days=days)).strftime("%Y-%m-%d")
        db = await vdb()
        await ensure_schema(db)
        dated = [_row(r) for r in await db.execute_fetchall(
            "SELECT * FROM tenders_direct WHERE matched=1 AND due>=? AND due<=? ORDER BY due, source, id LIMIT 200", (today, until))]
        undated = [_row(r) for r in await db.execute_fetchall(
            "SELECT * FROM tenders_direct WHERE matched=1 AND due='' AND last_seen>=? ORDER BY first_seen DESC, id DESC LIMIT 50",
            ((now - timedelta(days=days)).astimezone(timezone.utc).isoformat(),))]
        return {"items": dated, "undated": undated, "count": len(dated), "days": days, "as_of": now.isoformat(),
                "from": today, "until": until, "state": await last_run(db), "keywords": keywords(), "min_value_cr": min_value_cr(),
                "sites": [{"key": s["key"], "label": s["label"], "url": s["url"]} for s in sites()]}

    async def recent(days: int = 7, matched: int | None = 1, source: str = "", limit: int = 200, now_v: Any = None) -> dict:
        days = max(1, min(int(days or 7), 400))
        now = _parse_now(now_v)
        since = (now - timedelta(days=days)).astimezone(timezone.utc).isoformat()
        q, params = "SELECT * FROM tenders_direct WHERE first_seen >= ?", [since]
        if matched is not None:
            q += " AND matched=?"; params.append(1 if int(matched) else 0)
        if source:
            if source not in {s["key"] for s in SITES}:
                raise HTTPException(400, f"source must be one of {', '.join(s['key'] for s in SITES)}")
            q += " AND source=?"; params.append(source)
        q += " ORDER BY first_seen DESC, id DESC LIMIT ?"; params.append(max(1, min(int(limit or 200), 1000)))
        db = await vdb()
        await ensure_schema(db)
        items = [_row(r) for r in await db.execute_fetchall(q, params)]
        return {"items": items, "count": len(items), "days": days, "source": source, "as_of": now.isoformat()}

    async def stats(now_v: Any = None) -> dict:
        now = _parse_now(now_v)
        db = await vdb()
        await ensure_schema(db)
        by: dict[str, dict] = {s["key"]: {"label": s["label"], "url": s["url"], "rows": 0, "matched": 0} for s in sites()}
        for r in await db.execute_fetchall("SELECT source, COUNT(*) AS n, SUM(matched) AS m FROM tenders_direct GROUP BY source"):
            d = dict(r)
            by.setdefault(d["source"], {"label": d["source"], "url": "", "rows": 0, "matched": 0}).update(
                {"rows": int(d["n"] or 0), "matched": int(d["m"] or 0)})
        tot = dict((await db.execute_fetchall("SELECT COUNT(*) AS n, COALESCE(SUM(matched),0) AS m FROM tenders_direct"))[0])
        runs = int(dict((await db.execute_fetchall("SELECT COUNT(*) AS n FROM tenders_direct_runs"))[0])["n"] or 0)
        return {"as_of": now.isoformat(), "total": int(tot["n"] or 0), "matched": int(tot["m"] or 0), "by_source": by,
                "keywords": keywords(), "min_value_cr": min_value_cr(), "runs": runs, "state": await last_run(db)}

    # ── endpoints ─────────────────────────────────────────────────────────────
    @app.get("/api/tenders/direct/upcoming")
    async def tenders_direct_upcoming(days: int = 30, now: str | None = None):
        return await upcoming(days, now)

    @app.get("/api/tenders/direct/recent")
    async def tenders_direct_recent(days: int = 7, matched: int = 1, source: str = "", limit: int = 200):
        return await recent(days, matched, source, limit)

    @app.get("/api/tenders/direct/stats")
    async def tenders_direct_stats():
        return await stats()

    @app.get("/api/tenders/direct/probe")
    async def tenders_direct_probe(site: str, links: int = 40):
        """What this server actually receives from one listed site: status, title, the tables' first rows and the
        first links. For fixing a parser against the real page; keyed like every other /api route, public pages only."""
        match = [x for x in SITES if x["key"] == site.strip().lower()]
        if not match:
            raise HTTPException(404, f"unknown site; one of: {', '.join(x['key'] for x in SITES)}")
        got = await asyncio.to_thread(fetch_page, match[0]["url"])
        if not got["ok"]:
            return {"site": site, "url": match[0]["url"], "ok": False, "status": got["status"], "reason": got["reason"]}
        return probe_summary(got["html"], match[0]["url"], max(0, min(int(links), 200)))

    @app.post("/api/tenders/direct/run")
    async def tenders_direct_run(body: dict | None = None):
        body = body or {}
        return await run(body.get("now"))

    return {"ensure_schema": ensure_schema, "run": run, "upcoming": upcoming, "recent": recent, "stats": stats}
