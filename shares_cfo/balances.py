"""External balances — the parts of net worth that live outside the Indian demat book.

US stocks, crypto (SunCrypto / Binance), bank balances, other trading-account cash.
Manually maintained for now (you type/update each figure; it persists on the state
volume) and folded into a separate "Total Wealth" figure so the live demat net worth
stays clean. USD entries convert to INR at a live USDINR rate (EODHD, with a fallback).

Nothing here touches the trading path or any broker credential.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

BAL_DIR = Path(__file__).resolve().parent / "data" / "state"
_STORE = BAL_DIR / "balances.json"
_LOCK = threading.Lock()

# Buckets the hub offers; free-form label within each. "Crypto" covers SunCrypto/Binance.
BUCKETS = ("US Stocks", "Crypto", "Bank", "Trading Cash", "Other")
_CUR = ("INR", "USD")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> list[dict]:
    if not _STORE.exists():
        return []
    try:
        data = json.loads(_STORE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write(items: list[dict]) -> None:
    BAL_DIR.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def usdinr() -> float:
    """Live USDINR, else CFO_USDINR from env, else a sane fallback. Never raises."""
    try:
        from .analysis import eodhd
        if eodhd.enabled():
            v = eodhd.get_spot("USDINR.FOREX")
            if v and v > 0:
                return float(v)
    except Exception:
        pass
    try:
        return float(os.environ.get("CFO_USDINR", "") or 86.0)
    except ValueError:
        return 86.0


def _to_inr(amount: float, currency: str, rate: float) -> float:
    return amount * rate if (currency or "INR").upper() == "USD" else amount


def upsert(entry: dict) -> dict:
    label = str(entry.get("label", "")).strip()[:60]
    bucket = entry.get("bucket") if entry.get("bucket") in BUCKETS else "Other"
    cur = (entry.get("currency") or "INR").upper()
    if cur not in _CUR:
        cur = "INR"
    try:
        amount = float(entry.get("amount"))
    except (TypeError, ValueError):
        raise ValueError("amount must be a number")
    if not label:
        raise ValueError("label is required")
    with _LOCK:
        items = _load()
        eid = entry.get("id")
        rec = next((i for i in items if i.get("id") == eid), None) if eid else None
        if rec is None:
            rec = {"id": uuid.uuid4().hex[:12], "created_at": _now_iso()}
            items.append(rec)
        rec.update(label=label, bucket=bucket, amount=amount, currency=cur, updated_at=_now_iso())
        _write(items)
    return rec


def delete(entry_id: str) -> bool:
    with _LOCK:
        items = _load()
        remaining = [i for i in items if i.get("id") != entry_id]
        if len(remaining) == len(items):
            return False
        _write(remaining)
    return True


def summary() -> dict:
    """All entries + per-bucket INR subtotals + grand external total, at the live rate."""
    items = _load()
    rate = usdinr()
    by_bucket: dict = {}
    out_items = []
    total = 0.0
    for it in items:
        inr = _to_inr(it.get("amount") or 0, it.get("currency", "INR"), rate)
        total += inr
        by_bucket[it["bucket"]] = round(by_bucket.get(it["bucket"], 0.0) + inr, 2)
        out_items.append({**it, "inr_value": round(inr, 2)})
    out_items.sort(key=lambda x: -x["inr_value"])
    return {"items": out_items, "by_bucket": by_bucket,
            "total_external_inr": round(total, 2), "usdinr": round(rate, 2),
            "buckets": list(BUCKETS)}
