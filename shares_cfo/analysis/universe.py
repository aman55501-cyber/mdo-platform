"""The whole Screener universe — merged, indexed, searchable.

Turns the drop-zone (one or many Premium exports) into a single in-memory index of every
listed company, so the console can search/screen the entire market — not just the rows of
the newest file, and not with an O(n) scan per lookup.

Design:
  * MERGE every .csv/.xlsx in the drop-zone, deduped by NSE code. Later files (newer
    mtime) win on conflict — drop one giant "all companies" export, OR several market-cap
    slices, OR a focused screen as an overlay; they compose. Each file's headers are
    resolved once by the LLM column-mapper (screener_map), so mixed layouts merge cleanly.
  * INDEX by code once and cache to disk (.universe_index.json) keyed by a fingerprint of
    the file set (name+mtime+size). Rebuilds only when the drop-zone changes; otherwise a
    restart loads the cached index instantly.
  * Never scraped — every record traces to a file Aman exported and dropped. No network.

All ingestion reuses fundamentals' deterministic mapping (numbers via to_float; industry/
sector as text). This module adds only the merge, the index, and search/screen on top.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from . import fundamentals as F

log = logging.getLogger("shares_cfo.universe")

INDEX_CACHE = F.SCREENER_DIR / ".universe_index.json"

# numeric canonical fields we let the screener filter/sort on (text fields handled apart)
NUMERIC_FIELDS = ("pe", "pb", "de", "roe", "roce", "industry_pe",
                  "promoter_holding", "pledge", "dividend_yield", "market_cap")

_MEMO: dict = {"fp": None, "index": None}


def _sources() -> list[Path]:
    """Every export in the drop-zone, OLDEST first so newer files overwrite on merge."""
    if not F.SCREENER_DIR.exists():
        return []
    files = [p for p in F.SCREENER_DIR.glob("*")
             if p.suffix.lower() in (".csv", ".xlsx", ".xls")]
    return sorted(files, key=lambda p: p.stat().st_mtime)


def _fingerprint(paths: list[Path]) -> str:
    """Stable id of the current file set — busts the cache when any file changes/appears."""
    parts = []
    for p in paths:
        try:
            st = p.stat()
            parts.append(f"{p.name}:{int(st.st_mtime)}:{st.st_size}")
        except OSError:
            continue
    return hashlib.sha1("|".join(parts).encode("utf-8", "replace")).hexdigest()


def _code_of(row: dict) -> str:
    code = str(row.get("NSE Code") or row.get("Symbol") or row.get("Ticker") or "").strip().upper()
    if code:
        return code
    name = F._row_name(row)
    return name.split()[0] if name else ""


def _build(paths: list[Path]) -> dict:
    """Merge all files into {code: record}. Later files win. One mapping resolve per file."""
    index: dict = {}
    for path in paths:
        rows = F._rows_from_file(path)
        if not rows:
            continue
        mapping = F.resolve_mapping(list(rows[0].keys()))
        for row in rows:
            code = _code_of(row)
            if not code:
                continue
            fields = F._map_row(row, mapping)
            if not fields and code in index:
                continue  # nothing new to add for an already-seen code
            index[code] = {"code": code, "name": F._row_name(row) or code,
                           "fields": fields, "source": path.name}
    return index


def _cache_read(fp: str) -> dict | None:
    try:
        blob = json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(blob, dict) or blob.get("fp") != fp:
        return None
    recs = blob.get("records")
    return {r["code"]: r for r in recs} if isinstance(recs, list) else None


def _cache_write(fp: str, index: dict) -> None:
    try:
        INDEX_CACHE.write_text(
            json.dumps({"fp": fp, "records": list(index.values())}, separators=(",", ":")),
            encoding="utf-8")
    except OSError as exc:
        log.info("universe cache write failed: %s", exc)


def get_index(refresh: bool = False) -> dict:
    """The merged {code: record} index — memoised in-process, disk-cached, rebuilt only
    when the drop-zone changes. Safe to call from a thread (endpoints use to_thread)."""
    paths = _sources()
    fp = _fingerprint(paths)
    if not refresh and _MEMO["fp"] == fp and _MEMO["index"] is not None:
        return _MEMO["index"]
    index = None if refresh else _cache_read(fp)
    if index is None:
        index = _build(paths)
        _cache_write(fp, index)
    _MEMO["fp"], _MEMO["index"] = fp, index
    return index


def record(code: str) -> dict | None:
    """One company's record by NSE code (exact), or None."""
    return get_index().get((code or "").strip().upper())


def search(query: str, limit: int = 25) -> list[dict]:
    """Find any listed company by code or name. Ranked: exact code, code-prefix, name-hit."""
    q = (query or "").strip().upper()
    if not q:
        return []
    idx = get_index()
    scored = []
    for rec in idx.values():
        code, name = rec["code"], rec["name"].upper()
        if code == q:
            rank = 0
        elif code.startswith(q):
            rank = 1
        elif q in code:
            rank = 2
        elif name.startswith(q):
            rank = 3
        elif q in name:
            rank = 4
        else:
            continue
        scored.append((rank, code, rec))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [_public(r) for _, _, r in scored[:max(1, limit)]]


def _match(rec: dict, filters: dict) -> bool:
    f = rec["fields"]
    for key, cond in (filters or {}).items():
        if key in ("sector", "industry", "name"):
            hay = (rec["name"] if key == "name" else f.get(key) or "").upper()
            if str(cond).strip().upper() not in hay:
                return False
            continue
        val = f.get(key)
        if val is None:
            return False   # can't confirm a numeric filter without the value -> exclude
        if isinstance(cond, dict):
            if cond.get("min") is not None and val < cond["min"]:
                return False
            if cond.get("max") is not None and val > cond["max"]:
                return False
        else:
            if val != cond:
                return False
    return True


def screen(filters: dict | None = None, sort_by: str = "market_cap",
           desc: bool = True, limit: int = 100) -> dict:
    """Filter the universe by fundamental thresholds; return a ranked slice + the count.

    filters: {"pe": {"max": 20}, "roe": {"min": 15}, "market_cap": {"min": 1000},
              "sector": "auto", "industry": "ancillary"}  (numeric -> min/max, text -> contains)
    """
    idx = get_index()
    hits = [rec for rec in idx.values() if _match(rec, filters or {})]
    key = sort_by if sort_by in NUMERIC_FIELDS else "market_cap"
    hits.sort(key=lambda r: (r["fields"].get(key) is None, -(r["fields"].get(key) or 0) if desc
                             else (r["fields"].get(key) or 0)))
    return {"count": len(hits), "sort_by": key, "desc": desc,
            "results": [_public(r) for r in hits[:max(1, limit)]]}


def _public(rec: dict) -> dict:
    """Flatten a record for the API: code, name, sector/industry, and the numeric fields."""
    f = rec["fields"]
    out = {"code": rec["code"], "name": rec["name"],
           "sector": f.get("sector"), "industry": f.get("industry")}
    for k in NUMERIC_FIELDS:
        if f.get(k) is not None:
            out[k] = f[k]
    return out


def stats() -> dict:
    """Coverage of the merged universe — companies, source files, field fill rates."""
    paths = _sources()
    idx = get_index()
    n = len(idx) or 1
    fill = {k: round(sum(1 for r in idx.values() if r["fields"].get(k) is not None) / n * 100, 1)
            for k in NUMERIC_FIELDS + ("industry", "sector")}
    return {"companies": len(idx), "files": [p.name for p in paths],
            "file_count": len(paths), "field_fill_pct": fill,
            "cached": INDEX_CACHE.exists()}
