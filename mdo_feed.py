"""Decision Feed — the one place decisions arrive.

Every domain (capital, VWLR, hotel, compliance) publishes findings here instead of
inventing its own alerting. This module owns the three disciplines that keep a feed
worth reading:

  * **Dedup + cooldown** — the same finding cannot interrupt twice inside its window.
    (The pattern is lifted from `shares_cfo/proactive.py`, which already proved it on
    the capital side.)
  * **Severity routing** — `critical` pushes to the phone now, `important` batches into
    a digest, `info` waits in the app.
  * **Proposed actions** — an item can carry a drafted action Aman approves with one tap.

Action *kinds* decide what approval is allowed to do:

    internal  changes only our own data (file a task, file intel)  -> executes
    outward   reaches a real person (a WhatsApp message)           -> executes, always audited
    money     moves money or places an order                       -> REFUSED in v1

The money refusal is policy, enforced here on the approval path — not merely a button
left unbuilt. Turning it on is a deliberate act (`MDO_FEED_MONEY_ACTIONS=1`), and even
then it only stops this layer from refusing; the broker guardrails still apply.

Nothing in this module ever blocks on the notifier. An item is stored first; delivery is
best-effort and recorded.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

IST = timezone(timedelta(hours=5, minutes=30))

SEVERITIES = ("critical", "important", "info")
ACTION_KINDS = ("internal", "outward", "money")

# Terminal states — an item here has been dealt with and never executes again.
DECIDED = ("approved", "rejected", "executed", "failed", "refused", "expired")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def cooldown_minutes(severity: str) -> int:
    """How long the same `key` stays quiet after being published. [A3] — tunable."""
    return {
        "critical": _int_env("MDO_FEED_COOLDOWN_CRITICAL", 180),
        "important": _int_env("MDO_FEED_COOLDOWN_IMPORTANT", 720),
        "info": _int_env("MDO_FEED_COOLDOWN_INFO", 1440),
    }.get(severity, 720)


def expiry_hours() -> int:
    """Undecided items stop cluttering the feed after this long. [A7] — tunable."""
    return _int_env("MDO_FEED_EXPIRY_HOURS", 168)  # 7 days


def money_actions_enabled() -> bool:
    """v1 default: OFF. Money never moves from an approval tap."""
    return os.environ.get("MDO_FEED_MONEY_ACTIONS", "").strip() in ("1", "true", "yes")


def notify_policy(severity: str) -> str:
    """push = interrupt him now · digest = batch it · silent = it waits in the app."""
    return {"critical": "push", "important": "digest"}.get(severity, "silent")


def _now() -> datetime:
    return datetime.now(IST)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


SCHEMA = """
-- One row per finding that might need Aman. The `key` is the dedup identity: the same
-- key inside its cooldown window is suppressed rather than published again.
CREATE TABLE IF NOT EXISTS feed_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    source TEXT DEFAULT '',                 -- which check/agent/engine produced it
    domain TEXT DEFAULT 'general',          -- market|capital|vwlr|hotel|compliance|projects|banking
    severity TEXT NOT NULL DEFAULT 'info',  -- critical|important|info
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    evidence_json TEXT DEFAULT '[]',        -- what the finding is based on; never invented
    action_type TEXT DEFAULT '',            -- registered handler name; blank = nothing to do
    action_payload_json TEXT DEFAULT '{}',
    action_kind TEXT DEFAULT '',            -- internal|outward|money
    status TEXT NOT NULL DEFAULT 'new',     -- new|notified|approved|rejected|executed|failed|refused|expired
    notify_policy TEXT DEFAULT 'silent',    -- push|digest|silent (decided at publish time)
    notified_at TEXT,
    notify_result TEXT DEFAULT '',
    decided_at TEXT,
    decided_by TEXT DEFAULT '',
    executed_at TEXT,
    result TEXT DEFAULT '',
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feed_key     ON feed_items(key, created_at);
CREATE INDEX IF NOT EXISTS idx_feed_status  ON feed_items(status, severity);

-- Append-only. Every state change of every item lands here, including refusals.
CREATE TABLE IF NOT EXISTS feed_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER,
    event TEXT NOT NULL,
    detail TEXT DEFAULT '',
    at TEXT NOT NULL
);
"""


async def ensure_schema(db) -> None:
    await db.executescript(SCHEMA)
    await db.commit()


async def _audit(db, item_id: int | None, event: str, detail: str = "") -> None:
    await db.execute(
        "INSERT INTO feed_audit (item_id, event, detail, at) VALUES (?,?,?,?)",
        (item_id, event, detail[:2000], _iso(_now())),
    )


def _row_to_dict(row) -> dict:
    d = dict(row)
    for src, dst in (("evidence_json", "evidence"), ("action_payload_json", "action_payload")):
        try:
            d[dst] = json.loads(d.get(src) or ("[]" if "evidence" in dst else "{}"))
        except (ValueError, TypeError):
            d[dst] = [] if "evidence" in dst else {}
    return d


# ── Action registry ────────────────────────────────────────────────────────
# A handler is an async callable taking the payload dict and returning a dict.
# Registering declares the kind, which is what the approval path enforces.

_ACTIONS: dict[str, tuple[str, Callable[[dict], Awaitable[Any]]]] = {}


def register_action(name: str, kind: str, handler: Callable[[dict], Awaitable[Any]]) -> None:
    if kind not in ACTION_KINDS:
        raise ValueError(f"unknown action kind {kind!r}; expected one of {ACTION_KINDS}")
    _ACTIONS[name] = (kind, handler)


def action_kind(name: str) -> str:
    return _ACTIONS.get(name, ("", None))[0]


def registered_actions() -> dict[str, str]:
    return {name: kind for name, (kind, _) in _ACTIONS.items()}


def clear_actions() -> None:
    """Test seam — the registry is process-global."""
    _ACTIONS.clear()


# ── Publishing ─────────────────────────────────────────────────────────────

async def publish(
    db,
    *,
    key: str,
    title: str,
    severity: str = "info",
    source: str = "",
    domain: str = "general",
    body: str = "",
    evidence: list | None = None,
    action_type: str = "",
    action_payload: dict | None = None,
) -> dict | None:
    """File a finding. Returns the new item, or None when suppressed by cooldown.

    Suppression is recorded in the audit trail — a quiet feed must still be able to
    prove it was quiet on purpose.
    """
    if severity not in SEVERITIES:
        raise ValueError(f"unknown severity {severity!r}; expected one of {SEVERITIES}")

    now = _now()
    cooldown = cooldown_minutes(severity)
    if cooldown > 0:  # a zero cooldown means "never suppress", not "suppress everything"
        window_start = _iso(now - timedelta(minutes=cooldown))
        async with db.execute(
            "SELECT id FROM feed_items WHERE key = ? AND created_at >= ? ORDER BY id DESC LIMIT 1",
            (key, window_start),
        ) as cur:
            recent = await cur.fetchone()
        if recent:
            await _audit(db, recent["id"], "suppressed",
                         f"duplicate of key={key} inside {cooldown}min cooldown")
            await db.commit()
            return None

    kind = action_kind(action_type) if action_type else ""
    if action_type and not kind:
        # An unregistered action would be undiscoverable at approval time. Fail at
        # publish, where the producer can still be fixed.
        raise ValueError(f"action_type {action_type!r} is not registered")

    policy = notify_policy(severity)
    cur = await db.execute(
        """INSERT INTO feed_items
           (key, source, domain, severity, title, body, evidence_json,
            action_type, action_payload_json, action_kind, status, notify_policy,
            expires_at, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,'new',?,?,?,?)""",
        (key, source, domain, severity, title, body,
         json.dumps(evidence or []), action_type,
         json.dumps(action_payload or {}), kind, policy,
         _iso(now + timedelta(hours=expiry_hours())), _iso(now), _iso(now)),
    )
    item_id = cur.lastrowid
    await _audit(db, item_id, "published", f"{severity}/{domain} via {source or 'unknown'}")
    await db.commit()
    return await get_item(db, item_id)


async def get_item(db, item_id: int) -> dict | None:
    async with db.execute("SELECT * FROM feed_items WHERE id = ?", (item_id,)) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None


async def list_items(
    db,
    *,
    status: str | None = None,
    severity: str | None = None,
    domain: str | None = None,
    pending_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    sql = "SELECT * FROM feed_items WHERE 1=1"
    args: list[Any] = []
    if status:
        sql += " AND status = ?"
        args.append(status)
    if pending_only:
        sql += f" AND status NOT IN ({','.join('?' * len(DECIDED))})"
        args.extend(DECIDED)
    if severity:
        sql += " AND severity = ?"
        args.append(severity)
    if domain:
        sql += " AND domain = ?"
        args.append(domain)
    # critical first, then newest — the order he should read them in.
    sql += (" ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'important' THEN 1 ELSE 2 END,"
            " id DESC LIMIT ?")
    args.append(max(1, min(int(limit), 500)))
    async with db.execute(sql, args) as cur:
        rows = await cur.fetchall()
    return [_row_to_dict(r) for r in rows]


async def mark_notified(db, item_id: int, result: str = "") -> None:
    now = _iso(_now())
    await db.execute(
        "UPDATE feed_items SET status = CASE WHEN status='new' THEN 'notified' ELSE status END,"
        " notified_at = ?, notify_result = ?, updated_at = ? WHERE id = ?",
        (now, result[:500], now, item_id),
    )
    await _audit(db, item_id, "notified", result)
    await db.commit()


async def expire_stale(db) -> int:
    """Undecided items past their expiry stop taking up attention. [A7]"""
    now = _iso(_now())
    async with db.execute(
        "SELECT id FROM feed_items WHERE expires_at IS NOT NULL AND expires_at <= ?"
        f" AND status NOT IN ({','.join('?' * len(DECIDED))})",
        (now, *DECIDED),
    ) as cur:
        ids = [r["id"] for r in await cur.fetchall()]
    for i in ids:
        await db.execute(
            "UPDATE feed_items SET status='expired', updated_at=? WHERE id=?", (now, i))
        await _audit(db, i, "expired", "undecided past expiry")
    await db.commit()
    return len(ids)


# ── Deciding ───────────────────────────────────────────────────────────────

async def decide(db, item_id: int, decision: str, actor: str = "aman") -> dict:
    """Approve or reject. Approval of an actionable item runs it — subject to policy.

    Returns the updated item with an `outcome` describing what actually happened, so
    the caller never has to infer it from status alone.
    """
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")

    item = await get_item(db, item_id)
    if item is None:
        return {"error": "no such feed item", "id": item_id}
    if item["status"] in DECIDED:
        # Guard against a double tap executing an action twice.
        return {**item, "outcome": "already_decided",
                "error": f"item already {item['status']}"}

    now = _iso(_now())

    if decision == "reject":
        await db.execute(
            "UPDATE feed_items SET status='rejected', decided_at=?, decided_by=?,"
            " updated_at=? WHERE id=?", (now, actor, now, item_id))
        await _audit(db, item_id, "rejected", f"by {actor}")
        await db.commit()
        return {**(await get_item(db, item_id)), "outcome": "rejected"}

    # ── approved ──
    await _audit(db, item_id, "approved", f"by {actor}")

    if not item["action_type"]:
        await db.execute(
            "UPDATE feed_items SET status='approved', decided_at=?, decided_by=?,"
            " updated_at=? WHERE id=?", (now, actor, now, item_id))
        await db.commit()
        return {**(await get_item(db, item_id)), "outcome": "acknowledged"}

    kind = item["action_kind"] or action_kind(item["action_type"])

    if kind == "money" and not money_actions_enabled():
        detail = ("refused by v1 policy: money actions never execute from an approval tap "
                  "(set MDO_FEED_MONEY_ACTIONS=1 deliberately to change this)")
        await db.execute(
            "UPDATE feed_items SET status='refused', decided_at=?, decided_by=?, result=?,"
            " updated_at=? WHERE id=?", (now, actor, detail, now, item_id))
        await _audit(db, item_id, "refused", detail)
        await db.commit()
        return {**(await get_item(db, item_id)), "outcome": "refused", "reason": detail}

    entry = _ACTIONS.get(item["action_type"])
    if entry is None:
        detail = f"no handler registered for action {item['action_type']!r}"
        await db.execute(
            "UPDATE feed_items SET status='failed', decided_at=?, decided_by=?, result=?,"
            " updated_at=? WHERE id=?", (now, actor, detail, now, item_id))
        await _audit(db, item_id, "failed", detail)
        await db.commit()
        return {**(await get_item(db, item_id)), "outcome": "failed", "error": detail}

    _, handler = entry
    try:
        result = await handler(item["action_payload"] or {})
        detail = json.dumps(result, default=str)[:2000]
        await db.execute(
            "UPDATE feed_items SET status='executed', decided_at=?, decided_by=?, result=?,"
            " executed_at=?, updated_at=? WHERE id=?",
            (now, actor, detail, now, now, item_id))
        await _audit(db, item_id, "executed", detail)
        await db.commit()
        # `result` stays the stored string; the handler's own return travels separately
        # so callers never have to guess which type they are holding.
        return {**(await get_item(db, item_id)), "outcome": "executed",
                "action_result": result}
    except Exception as e:  # a handler blowing up must never lose the item
        detail = f"{type(e).__name__}: {e}"[:2000]
        await db.execute(
            "UPDATE feed_items SET status='failed', decided_at=?, decided_by=?, result=?,"
            " updated_at=? WHERE id=?", (now, actor, detail, now, item_id))
        await _audit(db, item_id, "failed", detail)
        await db.commit()
        return {**(await get_item(db, item_id)), "outcome": "failed", "error": detail}


async def audit_trail(db, item_id: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM feed_audit WHERE item_id = ? ORDER BY id", (item_id,)) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def counts(db) -> dict:
    """Headline numbers for the app badge and the digest."""
    async with db.execute(
        "SELECT severity, COUNT(*) n FROM feed_items"
        f" WHERE status NOT IN ({','.join('?' * len(DECIDED))}) GROUP BY severity",
        DECIDED,
    ) as cur:
        rows = await cur.fetchall()
    out = {s: 0 for s in SEVERITIES}
    for r in rows:
        out[r["severity"]] = r["n"]
    out["pending_total"] = sum(out[s] for s in SEVERITIES)
    return out
