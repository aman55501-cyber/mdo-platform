"""LLM-assisted Screener column mapper — robust header → canonical-field resolution.

Screener.in's "Export to Excel" lets you pick ANY columns and it renames them freely,
so a fixed header table silently drops a field the day your export says "ROE %" instead
of "Return on equity", or "Sub-Industry" instead of "Industry". This resolves the mapping
the durable way:

  1. STATIC first — the deterministic candidate list (unchanged behaviour).
  2. Only for the canonical fields the static pass could NOT find, ask Claude which of
     the REMAINING real headers each one is.

Safe by construction — the LLM is only ever a *header-string* matcher:

  * It never sees a single data value and never emits a number. Cell values are still
    parsed deterministically downstream (`to_float`), so the model cannot alter, invent,
    round, or reorder a figure. It can only say "field X lives in column named Y".
  * Every header it returns is validated against the REAL header list; a hallucinated or
    paraphrased column name is dropped, not trusted.
  * Fully degradable: no ANTHROPIC_API_KEY, an API error, or a timeout → you get exactly
    today's static mapping. The LLM can only ADD a field the static pass missed, never
    remove or change one it found.
  * Resolved once per unique header-set and cached to disk — never on a per-row hot path,
    and a restart doesn't re-call.

`resolve()` takes the candidates + field descriptions by injection (no import back into
fundamentals), and `call_fn` is injectable so the mapping logic is unit-testable offline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import httpx

log = logging.getLogger("shares_cfo.screener_map")

API_URL = "https://api.anthropic.com/v1/messages"
CACHE_NAME = ".header_map_cache.json"

# Human descriptions of each canonical field, given to the model so it can disambiguate
# headers it has never seen. Text (name) fields are called out as text on purpose.
FIELD_DESC = {
    "pe": "trailing price-to-earnings ratio (P/E), a number",
    "pb": "price-to-book ratio (P/B), a number",
    "de": "debt-to-equity (D/E) as a plain ratio, a number",
    "roe": "return on equity, a percentage number",
    "roce": "return on capital employed, a percentage number",
    "industry_pe": "the peer/industry median P/E, a number",
    "promoter_holding": "promoter shareholding, a percentage number",
    "pledge": "percentage of promoter holding that is pledged, a percentage number",
    "dividend_yield": "dividend yield, a percentage number",
    "market_cap": "market capitalisation in Rupees Crore, a number",
    "industry": "the stock's industry / sub-sector NAME as text, e.g. 'Auto Ancillary'",
    "sector": "the stock's broad sector NAME as text, e.g. 'Automobile'",
}


def enabled() -> bool:
    """LLM mapping is on when a key exists and it isn't explicitly disabled."""
    if os.environ.get("CFO_SCREENER_LLM_MAP", "1").strip().lower() in ("0", "false", "no"):
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


def _static_map(headers, candidates) -> dict:
    """The deterministic pass: first candidate header that is literally present wins.
    Identical to the original COLMAP behaviour — never regresses."""
    present = set(headers)
    out = {}
    for canon, cands in candidates.items():
        for hdr in cands:
            if hdr in present:
                out[canon] = hdr
                break
    return out


def _cache_key(headers, canon_fields) -> str:
    """Stable key over the header-set AND the canonical schema, so adding a field or
    changing an export's columns busts the cache naturally."""
    sig = "\x01".join(sorted(map(str, headers))) + "\x02" + "\x01".join(sorted(canon_fields))
    return hashlib.sha1(sig.encode("utf-8", "replace")).hexdigest()


def _cache_load(cache_dir: Path, key: str) -> dict | None:
    try:
        blob = json.loads((cache_dir / CACHE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = blob.get(key) if isinstance(blob, dict) else None
    return entry if isinstance(entry, dict) else None


def _cache_store(cache_dir: Path, key: str, mapping: dict) -> None:
    path = cache_dir / CACHE_NAME
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(blob, dict):
            blob = {}
    except (OSError, ValueError):
        blob = {}
    blob[key] = mapping
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(blob, indent=0), encoding="utf-8")
    except OSError as exc:
        log.info("header-map cache write failed: %s", exc)


def _build_prompt(headers, missing, descriptions) -> str:
    hdr_lines = "\n".join(f'- "{h}"' for h in headers)
    field_lines = "\n".join(f"- {c}: {descriptions.get(c, c)}" for c in missing)
    return (
        "You are mapping spreadsheet columns from a Screener.in stock export. Below is the "
        "EXACT list of column headers, and the canonical fields I still need to locate.\n\n"
        "For each canonical field, tell me which ONE header holds that data. Copy the header "
        "text VERBATIM from the list — character for character. If no header fits a field, "
        "OMIT that field entirely. Never invent a header, never guess, never paraphrase.\n\n"
        "Return ONLY a JSON object of {canonical_field: \"exact header text\"} and nothing "
        "else — no prose, no code fence.\n\n"
        f"HEADERS:\n{hdr_lines}\n\nCANONICAL FIELDS STILL NEEDED:\n{field_lines}\n"
    )


def _parse_json_object(text: str) -> dict:
    """Pull the first {...} JSON object out of a model reply, tolerantly."""
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _default_call(prompt: str, timeout: float) -> str:
    """The real Anthropic call. Key from env only, never logged. Returns the reply text."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return ""
    model = os.environ.get("CFO_LLM_MODEL", "claude-sonnet-5").strip() or "claude-sonnet-5"
    try:
        r = httpx.post(
            API_URL,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 700,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout,
        )
        if r.status_code >= 400:
            log.info("screener-map HTTP %s", r.status_code)  # never log body/key
            return ""
        blocks = (r.json() or {}).get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    except Exception as exc:
        log.info("screener-map call failed: %s", exc)
        return ""


def _validate(llm_map, headers, missing, taken) -> dict:
    """Keep only fields we asked for, whose value is a REAL header not already claimed.
    This is the guardrail against a hallucinated or duplicated column name."""
    present = set(headers)
    want = set(missing)
    used = set(taken)
    out = {}
    for canon, hdr in (llm_map or {}).items():
        if canon not in want or not isinstance(hdr, str):
            continue
        hdr = hdr.strip()
        if hdr in present and hdr not in used:
            out[canon] = hdr
            used.add(hdr)
    return out


def resolve(headers, candidates, descriptions=None, cache_dir=None,
            timeout: float = 12.0, call_fn=None) -> dict:
    """Return {canonical_field: exact_header} for every field found in `headers`.

    Static pass always runs; the LLM pass only fills fields the static pass missed, is
    cached per header-set, and is skipped entirely when disabled/unavailable. `call_fn`
    (prompt, timeout) -> reply-text is injectable for tests.
    """
    headers = [h for h in (headers or []) if isinstance(h, str) and h.strip()]
    descriptions = descriptions or FIELD_DESC
    static = _static_map(headers, candidates)
    missing = [c for c in candidates if c not in static]
    if not missing or not headers:
        return static

    use_llm = enabled() if call_fn is None else True
    if not use_llm:
        return static

    key = _cache_key(headers, list(candidates.keys()))
    cdir = Path(cache_dir) if cache_dir else None
    if cdir is not None:
        cached = _cache_load(cdir, key)
        if cached is not None:
            # cache holds the FULL resolved map for this header-set; trust static for the
            # deterministic part, overlay the cached LLM-found fields.
            return {**static, **{k: v for k, v in cached.items() if v in set(headers)}}

    call = call_fn or _default_call
    reply = call(_build_prompt(headers, missing, descriptions), timeout)
    llm_found = _validate(_parse_json_object(reply), headers, missing, static.values())
    resolved = {**static, **llm_found}
    if cdir is not None:
        _cache_store(cdir, key, resolved)
    return resolved
