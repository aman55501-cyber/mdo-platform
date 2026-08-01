"""Per-share news via Google News RSS — free, no API key, works server-side.

EODHD/yfinance news are gated or blocked from a datacenter IP, so we use Google
News' public RSS search, which returns recent headlines for a company. Best-effort:
returns [] on any failure. Cached briefly so tapping a stock is instant on re-open.
"""

from __future__ import annotations

import html
import time
import xml.etree.ElementTree as ET

import httpx

_CACHE: dict[str, tuple[float, list]] = {}
_TTL = 900  # 15 min


def _rel_time(pub: str) -> str:
    """'Mon, 20 Jul 2026 05:30:00 GMT' -> '3h ago' (best-effort)."""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(pub)
        secs = time.time() - dt.timestamp()
        if secs < 3600:
            return f"{int(secs//60)}m ago"
        if secs < 86400:
            return f"{int(secs//3600)}h ago"
        return f"{int(secs//86400)}d ago"
    except Exception:
        return ""


def get_news(query: str, limit: int = 5) -> list[dict]:
    q = query.strip()
    if not q:
        return []
    hit = _CACHE.get(q.lower())
    if hit and (time.time() - hit[0]) < _TTL:
        return hit[1]
    try:
        r = httpx.get("https://news.google.com/rss/search",
                      params={"q": f"{q} stock NSE", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=10.0)
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception:
        return []
    out = []
    for it in root.iter("item"):
        title = it.findtext("title") or ""
        link = it.findtext("link") or ""
        pub = it.findtext("pubDate") or ""
        src_el = it.find("source")
        source = src_el.text if src_el is not None else ""
        if title:
            out.append({"title": html.unescape(title), "source": source,
                        "when": _rel_time(pub), "link": link})
        if len(out) >= limit:
            break
    _CACHE[q.lower()] = (time.time(), out)
    return out
