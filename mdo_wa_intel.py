"""WhatsApp Intelligence — classify chats → extract business signals → weekly pulse.

Aman's two phones (bridge accounts "1" and "2") mix personal and business
chats. The bridge POSTs every chat (groups and 1:1 DMs) to
/api/whatsapp/message; this module decides what may be kept:

  wa_chats      one row per chat: business | personal | unclear (quarantine)
  biz_signals   what the business chats say: leads, quotes, receivables, delays …
  biz_register  assets / liabilities / capital / debt / resources / commitments / vision
  biz_pulse     the weekly picture (business-pulse bot)

A chat classified `personal` stores NOTHING and its history is deleted the
moment the verdict lands. `unclear` chats are stored but never analysed until
the wa-classifier bot (or Aman, by reply) decides.

Mounted by mdo_server.py via register(). The pure helpers at the top of the
file take plain dicts and touch no database, so tests/test_wa_intel.py runs
them without a server. Three bots in fleet.yaml drive the pipeline from
mdo_agent.py: wa-classifier (every 2h), wa-intel (every 6h), business-pulse
(weekly). Rules that bind all of it (CHIEF_OF_STAFF.md §1): never invent a
number or an entity, every signal cites its evidence message ids, every run
heartbeats even when empty.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

# ── Aman's entity registry (prompts may name these and nothing else) ─────────
ENTITIES: list[tuple[str, str]] = [
    ("VWLR", "coal washery, logistics, tenders"),
    ("Hotel ANS International", "hotel operations"),
    ("ANS Inn Pvt Ltd", "holding company — NOT hotel operations"),
    ("Dadu Developers", "real estate"),
    ("Dadu Builders", "real estate"),
    ("Raigarh Land Venture", "real estate"),
    ("Rukmani Infrastructure", "real estate"),
    ("Aditi Investments", "investment partnership: Aman / Ashok / Sudha"),
    ("Eureka", "share-trading partnership with cousin"),
    ("MD's Office", "Aman's own office"),
    ("family/personal", "family and personal — not a business"),
]
ENTITY_NAMES = [e[0] for e in ENTITIES]
_ENTITY_LOOKUP = {e[0].lower(): e[0] for e in ENTITIES}

SIGNAL_KINDS = ("lead", "quote", "order", "receivable", "payable", "payment_done", "delay", "bottleneck",
                "decision_needed", "commitment", "complaint", "asset", "liability", "capital", "debt",
                "resource", "risk", "idea")
RED_KINDS = ("decision_needed", "complaint")      # plus payable due within 3 days
REGISTER_KINDS = ("asset", "liability", "capital", "debt", "resource", "commitment")
FOLLOWUP_KINDS = ("lead", "quote", "order", "receivable", "payment_done", "commitment")   # what closes a sales gap
REGISTER_CATEGORIES = ("asset", "liability", "capital", "debt", "resource", "commitment", "vision")
CLASSIFICATIONS = ("business", "personal", "unclear")
SIGNAL_STATUSES = ("open", "done", "dismissed")
AUTO_CONFIDENCE = 0.85
QUESTION_PREFIXES = ("kya", "when", "kab", "please send", "status")

SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_chats (
    jid TEXT PRIMARY KEY,
    account TEXT DEFAULT '1', name TEXT DEFAULT '', kind TEXT DEFAULT 'group',     -- group|dm
    classification TEXT NOT NULL DEFAULT 'unclear',                                -- business|personal|unclear
    entity TEXT DEFAULT '', confidence REAL, reason TEXT DEFAULT '',
    decided_by TEXT DEFAULT '', decided_at TEXT,                                    -- auto|aman|''
    first_seen TEXT, last_seen TEXT, msg_count INTEGER DEFAULT 0,
    participants TEXT DEFAULT '', asked_job_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_wa_chats_class ON wa_chats(classification);
CREATE TABLE IF NOT EXISTS biz_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT DEFAULT (datetime('now')),
    entity TEXT DEFAULT '', chat_jid TEXT DEFAULT '', chat_name TEXT DEFAULT '',
    kind TEXT NOT NULL, counterparty TEXT DEFAULT '',
    amount REAL, currency TEXT DEFAULT 'INR', due_date TEXT DEFAULT '',
    summary TEXT DEFAULT '', evidence_ids TEXT DEFAULT '[]', snippet TEXT DEFAULT '',
    confidence REAL, status TEXT NOT NULL DEFAULT 'open',                          -- open|done|dismissed
    owner TEXT DEFAULT '', bot_id TEXT DEFAULT '',
    fingerprint TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_biz_signals_status ON biz_signals(status, kind);
CREATE TABLE IF NOT EXISTS biz_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,                                                        -- asset|liability|capital|debt|resource|commitment|vision
    entity TEXT DEFAULT '', item TEXT NOT NULL, value REAL, unit TEXT DEFAULT 'INR',
    as_of TEXT DEFAULT '', source TEXT DEFAULT '', status TEXT DEFAULT 'active', notes TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS biz_pulse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT, period_end TEXT, entity TEXT DEFAULT 'group',
    report_json TEXT DEFAULT '{}', summary TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
"""
# Columns the bridge now sends; added to the existing table with a guarded ALTER.
WA_MSG_COLUMNS = {
    "account": "TEXT DEFAULT '1'",
    "chat_kind": "TEXT DEFAULT 'group'",
    "from_me": "INTEGER DEFAULT 0",
    "wa_msg_id": "TEXT DEFAULT ''",
}


# ═════════════════════════════════════════════════════════════════════════════
# Pure helpers — no database, no network (tests/test_wa_intel.py)
# ═════════════════════════════════════════════════════════════════════════════
def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def canonical_entity(name: Any) -> str:
    """Map a model's entity string onto the registry; anything else is ''."""
    n = _norm(name)
    if not n:
        return ""
    if n in _ENTITY_LOOKUP:
        return _ENTITY_LOOKUP[n]
    for key, canon in _ENTITY_LOOKUP.items():
        if key in n or n in key:
            return canon
    return ""


def parse_ts(v: Any) -> datetime | None:
    """ISO string, sqlite 'YYYY-MM-DD HH:MM:SS', or epoch seconds/milliseconds → aware UTC."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)):
        secs = float(v) / (1000.0 if v > 1e11 else 1.0)
        try:
            return datetime.fromtimestamp(secs, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(v).strip()
    if re.fullmatch(r"\d{10,13}(\.\d+)?", s):
        return parse_ts(float(s))
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso_week(when: Any = None) -> str:
    d = parse_ts(when) or datetime.now(timezone.utc)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def signal_fingerprint(entity: str, kind: str, counterparty: str, due_or_week: str) -> str:
    """Stable identity of a signal: same entity + kind + counterparty + due date
    (or the ISO week it was raised, when no due date) → the same 16-hex string,
    whatever the casing or spacing. Used as the UNIQUE dedup key."""
    raw = "|".join(_norm(x) for x in (entity, kind, counterparty, due_or_week))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def is_question(text: Any) -> bool:
    t = _norm(text)
    if not t:
        return False
    return t.endswith("?") or any(t.startswith(p) for p in QUESTION_PREFIXES)


def response_metrics(messages: list[dict], now: datetime | None = None, unanswered_hours: int = 24) -> list[dict]:
    """Per (chat, sender): median reply latency in minutes and the number of
    that sender's questions nobody else answered within `unanswered_hours`.

    A reply is a message whose immediately preceding message in the same chat
    came from a different sender; its latency is the gap between the two.
    A question (text ending '?' or starting kya/when/kab/please send/status)
    counts as unanswered when the next message from someone else arrived more
    than 24h later, or never arrived and the question is already older than 24h.
    Messages without a parseable timestamp are ignored."""
    by_chat: dict[str, list[tuple[datetime, str, str, Any]]] = {}
    latest: datetime | None = None
    for m in messages or []:
        ts = parse_ts(m.get("timestamp"))
        if ts is None:
            continue
        chat = str(m.get("chat_jid") or m.get("jid") or m.get("chat") or m.get("group_name") or "")
        sender = str(m.get("sender") or ("me" if m.get("from_me") else "")).strip() or "?"
        by_chat.setdefault(chat, []).append((ts, sender, str(m.get("text") or ""), m.get("id")))
        latest = ts if latest is None or ts > latest else latest
    now = now or latest or datetime.now(timezone.utc)
    limit = timedelta(hours=unanswered_hours)
    stats: dict[tuple[str, str], dict] = {}

    def rec(chat: str, sender: str) -> dict:
        return stats.setdefault((chat, sender), {"latencies": [], "questions": 0, "unanswered": 0})

    for chat, rows in by_chat.items():
        rows.sort(key=lambda r: r[0])
        for i, (ts, sender, text, _mid) in enumerate(rows):
            r = rec(chat, sender)
            if i > 0 and rows[i - 1][1] != sender:
                r["latencies"].append((ts - rows[i - 1][0]).total_seconds() / 60.0)
            if is_question(text):
                r["questions"] += 1
                reply_ts = next((row[0] for row in rows[i + 1:] if row[1] != sender), None)
                if reply_ts is None:
                    if now - ts > limit:
                        r["unanswered"] += 1
                elif reply_ts - ts > limit:
                    r["unanswered"] += 1
    out = []
    for (chat, sender), r in stats.items():
        lat = r["latencies"]
        out.append({
            "chat": chat, "sender": sender, "replies": len(lat),
            "median_reply_min": round(statistics.median(lat), 1) if lat else None,
            "questions": r["questions"], "unanswered_24h": r["unanswered"],
        })
    out.sort(key=lambda x: (-(x["median_reply_min"] or 0), -x["unanswered_24h"], x["chat"], x["sender"]))
    return out


# ── tolerant JSON ─────────────────────────────────────────────────────────────
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_OBJECT = re.compile(r"\{[^{}]*\}", re.S)


def _loads(s: str) -> Any:
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return json.loads(_TRAILING_COMMA.sub(r"\1", s))


def extract_json(text: Any) -> Any:
    """Best-effort JSON out of model text: code fences, prose around it, trailing
    commas, a truncated tail. Returns None when nothing parses."""
    if text is None:
        return None
    if isinstance(text, (dict, list)):          # already parsed (an API body)
        return text
    s = str(text).strip()
    if not s:
        return None
    m = _FENCE.search(s)
    if m:
        s = m.group(1).strip()
    candidates = [s]
    starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
    if starts:
        start = min(starts)
        end = max(s.rfind("}"), s.rfind("]")) + 1
        if end > start:
            candidates.append(s[start:end])
    for c in candidates:
        try:
            return _loads(c)
        except (json.JSONDecodeError, RecursionError):
            continue
    # Truncated output: salvage every complete {...} object we can find.
    objs = []
    for m in _OBJECT.finditer(s):
        try:
            o = _loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if isinstance(o, dict):
            objs.append(o)
    return objs or None


def _as_float(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return float(str(v).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None


def _as_ids(v: Any) -> list[int]:
    out: list[int] = []
    for x in (v if isinstance(v, list) else [v]):
        try:
            n = int(str(x).strip().lstrip("#"))
        except (TypeError, ValueError):
            continue
        if n not in out:
            out.append(n)
    return out


_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _as_date(v: Any) -> str:
    s = str(v or "").strip()[:10]
    if not _DATE.match(s):
        return ""
    try:
        date.fromisoformat(s)
    except ValueError:
        return ""
    return s


# ── classification ────────────────────────────────────────────────────────────
def classify_prompt(chat: dict, samples: list, entities: list | None = None) -> str:
    ents = entities or ENTITIES
    ent_lines = "\n".join(f"- {x[0]} — {x[1]}" if isinstance(x, (tuple, list)) else f"- {x}" for x in ents)
    parts = chat.get("participants") or []
    if isinstance(parts, str):
        try:
            parts = json.loads(parts or "[]")
        except json.JSONDecodeError:
            parts = [parts]
    lines = []
    for s in (samples or [])[:30]:
        if isinstance(s, dict):
            lines.append(f"- [{str(s.get('sender') or '?')[:40]}] {str(s.get('text') or '')[:300]}")
        else:
            lines.append(f"- {str(s)[:300]}")
    return (
        "You classify ONE WhatsApp chat on Aman Agrawal's phone (ANS Group, Raigarh CG) as business or personal.\n\n"
        f"CHAT: name \"{str(chat.get('name') or '')[:120]}\" · kind {chat.get('kind') or 'group'} · "
        f"phone account {chat.get('account') or '1'} · {int(chat.get('msg_count') or 0)} messages seen\n"
        + (f"PARTICIPANTS: {', '.join(str(p)[:40] for p in parts[:40])}\n" if parts else "")
        + "\nENTITIES — the only businesses that exist. Never name another:\n" + ent_lines
        + "\n\nSAMPLE MESSAGES (oldest first):\n" + ("\n".join(lines) if lines else "(none yet)")
        + "\n\nRULES:\n"
        "- personal = family, friends, social, jokes, forwards, school, religion, shopping with no work content.\n"
        "- business = any work for one of the entities: sites, staff, vendors, clients, payments, tenders, bookings, property.\n"
        "- mixed → business (it is kept; only the business parts are analysed).\n"
        "- A wrong 'personal' deletes the chat's history for good, so when unsure answer unclear with confidence below 0.85.\n"
        "- entity: one name from the list, or '' for personal/unclear. Never invent an entity.\n\n"
        "Return ONLY this JSON object:\n"
        '{"classification":"business|personal|unclear","entity":"","confidence":0.0,"reason":"one line quoting the evidence"}'
    )


def parse_classification(text: Any) -> dict | None:
    obj = extract_json(text)
    if isinstance(obj, list):
        obj = next((o for o in obj if isinstance(o, dict) and "classification" in o), None)
    if not isinstance(obj, dict):
        return None
    cls = _norm(obj.get("classification"))
    if cls not in CLASSIFICATIONS:
        return None
    conf = _as_float(obj.get("confidence"))
    conf = 0.0 if conf is None else max(0.0, min(1.0, conf))
    entity = canonical_entity(obj.get("entity")) if cls == "business" else ""
    if cls == "business" and obj.get("entity") and not entity:
        conf = min(conf, AUTO_CONFIDENCE - 0.01)       # an invented entity never auto-applies
    return {"classification": cls, "entity": entity, "confidence": round(conf, 3),
            "reason": str(obj.get("reason") or "")[:400]}


# ── signal extraction ─────────────────────────────────────────────────────────
def extract_prompt(chat: dict, messages: list[dict], entities: list | None = None, now: datetime | None = None) -> str:
    ents = entities or ENTITIES
    ent_lines = "\n".join(f"- {x[0]} — {x[1]}" if isinstance(x, tuple) else f"- {x}" for x in ents)
    now = now or datetime.now(timezone.utc)
    rows = []
    for m in messages:
        who = str(m.get("sender") or ("me (Aman)" if m.get("from_me") else "?"))[:40]
        rows.append(f"{m.get('id')} | {str(m.get('timestamp') or '')[:19]} | {who} | {str(m.get('text') or '')[:500]}")
    return (
        "You extract BUSINESS SIGNALS from WhatsApp messages for Aman Agrawal (ANS Group, Raigarh CG).\n\n"
        f"CHAT: \"{str(chat.get('name') or '')[:120]}\" · kind {chat.get('kind') or 'group'} · account {chat.get('account') or '1'}"
        f" · classified entity: {chat.get('entity') or '(not set — pick from the list or leave empty)'}\n"
        f"NOW: {now.strftime('%Y-%m-%d %H:%M')} (use it only to resolve 'kal/tomorrow/parso' into a date)\n\n"
        "ENTITIES — the only ones that exist, never invent another:\n" + ent_lines
        + "\n\nMESSAGES (id | time | sender | text):\n" + "\n".join(rows)
        + "\n\nSIGNAL KINDS: " + ", ".join(SIGNAL_KINDS) + "\n"
        "- lead: someone wants to buy/book/hire · quote: a price was given · order: confirmed work/booking\n"
        "- receivable: money owed TO us · payable: money we owe · payment_done: a payment happened\n"
        "- delay / bottleneck: work stuck, waiting on someone, repeated chasing · decision_needed: Aman must decide\n"
        "- commitment: a promise with a date · complaint: a client/guest/partner is unhappy · risk · idea\n"
        "- asset / liability / capital / debt / resource: something that belongs in the business register\n\n"
        "RULES:\n"
        "- Every signal cites one or more evidence_ids FROM THIS BATCH and a verbatim snippet copied from one of them.\n"
        "- amount: only a number written in the messages, as written (no conversion, no arithmetic); otherwise null.\n"
        "- due_date: only when stated or unambiguous; otherwise ''.\n"
        "- counterparty: the person or company named in the messages, or ''. Never invent one.\n"
        "- Greetings, forwards, jokes, chit-chat, duplicates of an earlier line → no signal.\n"
        "- An empty list is a valid answer.\n\n"
        "Return ONLY this JSON object:\n"
        '{"signals":[{"kind":"","entity":"","counterparty":"","amount":null,"currency":"INR","due_date":"",'
        '"summary":"one line","evidence_ids":[],"snippet":"","confidence":0.0}]}'
    )


def parse_signals(text: Any, allowed_ids: set | None = None) -> list[dict]:
    """Model text → clean signal dicts. Drops anything without a known kind,
    evidence ids (inside `allowed_ids` when given) or a summary. Never raises."""
    obj = extract_json(text)
    if isinstance(obj, dict):
        items = obj.get("signals")
        if items is None:
            items = [obj] if "kind" in obj else []
    elif isinstance(obj, list):
        items = obj
    else:
        return []
    out: list[dict] = []
    allowed = {int(x) for x in allowed_ids} if allowed_ids else None
    for it in items:
        if not isinstance(it, dict):
            continue
        kind = _norm(it.get("kind")).replace(" ", "_")
        if kind not in SIGNAL_KINDS:
            continue
        ids = _as_ids(it.get("evidence_ids", it.get("evidence")))
        if allowed is not None:
            ids = [i for i in ids if i in allowed]
        summary = str(it.get("summary") or "").strip()
        if not ids or not summary:
            continue
        conf = _as_float(it.get("confidence"))
        out.append({
            "kind": kind, "entity": canonical_entity(it.get("entity")),
            "counterparty": str(it.get("counterparty") or "").strip()[:120],
            "amount": _as_float(it.get("amount")),
            "currency": (str(it.get("currency") or "INR").strip().upper() or "INR")[:8],
            "due_date": _as_date(it.get("due_date")), "summary": summary[:500],
            "evidence_ids": ids[:50], "snippet": str(it.get("snippet") or "").strip()[:300],
            "confidence": None if conf is None else max(0.0, min(1.0, conf)),
        })
    return out


def is_red(signal: dict, today: date | None = None) -> bool:
    """🔴 on the phone: a decision for Aman, a complaint, or a payable due within 3 days."""
    kind = signal.get("kind")
    if kind in RED_KINDS:
        return True
    if kind == "payable" and signal.get("due_date"):
        try:
            due = date.fromisoformat(str(signal["due_date"])[:10])
        except ValueError:
            return False
        return due <= (today or datetime.now(timezone.utc).date()) + timedelta(days=3)
    return False


def red_line(signal: dict) -> str:
    sid = signal.get("id")
    head = f"🔴 wa#{sid} " if sid else "🔴 "
    amt = signal.get("amount")
    money = f" · {signal.get('currency') or 'INR'} {amt:,.0f}" if isinstance(amt, (int, float)) else ""
    due = f" · due {signal['due_date']}" if signal.get("due_date") else ""
    ev = ",".join(str(i) for i in (signal.get("evidence_ids") or [])[:5])
    return (f"{head}{signal.get('kind')} [{signal.get('entity') or 'entity?'}] {str(signal.get('summary') or '')[:160]}"
            f"{money}{due} — {signal.get('chat_name') or signal.get('chat_jid') or ''} (msgs {ev})")[:600]


# ── pulse ─────────────────────────────────────────────────────────────────────
_STOP = set("""the and for with from this that have will been were they them their there what when kya hai hain
nahi nahin kar karo karna wala wali hoga hogi please send sent also just only very into about abhi aaj kal tak bhi
koi kuch sab liye raha rahe rahi tha thi the our are was not but can could should would need needs still yet
sir bhai bhaiya jee ji madam""".split())


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9]{3,}", _norm(text)) if w not in _STOP}


def pulse_compute(signals: list[dict], metrics: list[dict] | None, now: datetime | None = None,
                  gap_days: int = 7) -> dict:
    """Deterministic part of the weekly pulse — every number here is traceable
    to signal ids, so the model only has to narrate.

    sales_gap:        open leads/quotes older than `gap_days` with no later
                      lead/quote/order/receivable/payment/commitment for the
                      same entity + counterparty (no order, no follow-up).
    efficiency:       the response_metrics table, slowest first.
    bottlenecks:      delay/bottleneck signals clustered per chat by shared
                      keywords; a cluster of ≥2 is recurring.
    register_changes: open signals of register kinds, ready to post.
    next_steps:       empty — the model fills it, each with owner + ETA + ids.
    """
    now = now or datetime.now(timezone.utc)
    signals = [s for s in (signals or []) if isinstance(s, dict)]
    by_kind: dict[str, int] = {}
    open_sigs = [s for s in signals if (s.get("status") or "open") == "open"]
    for s in open_sigs:
        by_kind[s.get("kind", "?")] = by_kind.get(s.get("kind", "?"), 0) + 1

    def cp_key(s: dict) -> str:
        return _norm(s.get("entity")) + "|" + _norm(s.get("counterparty"))

    # sales gap
    sales_gap = []
    for s in open_sigs:
        if s.get("kind") not in ("lead", "quote"):
            continue
        created = parse_ts(s.get("created_at"))
        if created is None:
            continue
        age = (now - created).days
        if age < gap_days:
            continue
        later = [o for o in signals if o is not s and cp_key(o) == cp_key(s) and s.get("counterparty")
                 and o.get("kind") in FOLLOWUP_KINDS and (parse_ts(o.get("created_at")) or created) > created]
        if later:
            continue
        sales_gap.append({"signal_id": s.get("id"), "kind": s.get("kind"), "entity": s.get("entity"),
                          "counterparty": s.get("counterparty"), "age_days": age,
                          "amount": s.get("amount"), "summary": str(s.get("summary") or "")[:200]})
    sales_gap.sort(key=lambda g: -g["age_days"])

    # bottlenecks: cluster per chat by shared keywords (union-find)
    stuck = [s for s in open_sigs if s.get("kind") in ("delay", "bottleneck")]
    parent = list(range(len(stuck)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    kws = [_keywords(f"{s.get('summary', '')} {s.get('counterparty', '')}") for s in stuck]
    for i in range(len(stuck)):
        for j in range(i + 1, len(stuck)):
            if stuck[i].get("chat_jid") == stuck[j].get("chat_jid") and kws[i] & kws[j]:
                parent[find(i)] = find(j)
    clusters: dict[int, list[int]] = {}
    for i in range(len(stuck)):
        clusters.setdefault(find(i), []).append(i)
    bottlenecks = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        shared = set.intersection(*(kws[i] for i in members)) if members else set()
        if not shared:
            counts: dict[str, int] = {}
            for i in members:
                for w in kws[i]:
                    counts[w] = counts.get(w, 0) + 1
            shared = {w for w, c in counts.items() if c >= 2}
        bottlenecks.append({
            "chat_jid": stuck[members[0]].get("chat_jid"), "chat_name": stuck[members[0]].get("chat_name"),
            "entity": stuck[members[0]].get("entity"), "keywords": sorted(shared)[:5], "count": len(members),
            "signal_ids": [stuck[i].get("id") for i in members],
        })
    bottlenecks.sort(key=lambda b: -b["count"])

    # register changes
    register_changes = [{
        "signal_id": s.get("id"), "category": s.get("kind"), "entity": s.get("entity"),
        "item": (s.get("counterparty") or str(s.get("summary") or "")[:120]), "value": s.get("amount"),
        "unit": s.get("currency") or "INR", "as_of": str(s.get("created_at") or "")[:10],
    } for s in open_sigs if s.get("kind") in REGISTER_KINDS]

    def money(kind: str) -> dict:
        rows = [s for s in open_sigs if s.get("kind") == kind and isinstance(s.get("amount"), (int, float))]
        return {"total": round(sum(float(s["amount"]) for s in rows), 2), "signal_ids": [s.get("id") for s in rows],
                "uncounted_ids": [s.get("id") for s in open_sigs if s.get("kind") == kind and s.get("amount") is None]}

    metrics = list(metrics or [])
    return {
        "as_of": now.strftime("%Y-%m-%d"),
        "totals": {"open": len(open_sigs), "all": len(signals), "by_kind": dict(sorted(by_kind.items()))},
        "sales_gap": sales_gap,
        "efficiency": {"table": metrics[:25], "unanswered_total": sum(int(m.get("unanswered_24h") or 0) for m in metrics)},
        "bottlenecks": bottlenecks,
        "register_changes": register_changes,
        "money": {"receivable": money("receivable"), "payable": money("payable")},
        "decisions_needed": [{"signal_id": s.get("id"), "summary": str(s.get("summary") or "")[:200]}
                             for s in open_sigs if s.get("kind") == "decision_needed"],
        "next_steps": [],
    }


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: Any) -> set[str]:
    out = set()
    for tok in _NUM.findall(str(text or "")):
        n = tok.replace(",", "")
        if n.endswith(".0"):
            n = n[:-2]
        out.add(n)
        out.add(n.lstrip("0") or "0")
    return out


def verify_numbers(text: str, allowed_source: Any) -> list[str]:
    """Numbers in `text` that do not appear anywhere in `allowed_source`
    (any JSON-able input). Empty list = every figure is traceable."""
    allowed = numbers_in(allowed_source if isinstance(allowed_source, str) else json.dumps(allowed_source, default=str))
    return sorted(n for n in numbers_in(text) if n not in allowed and (n.lstrip("0") or "0") not in allowed)


def pulse_prompt(computed: dict, signals: list[dict], register: list[dict], now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    slim = [{k: s.get(k) for k in ("id", "kind", "entity", "counterparty", "amount", "currency", "due_date",
                                   "summary", "status", "chat_name", "created_at")} for s in signals[:300]]
    return (
        "You write the weekly BUSINESS PULSE for Aman Agrawal (ANS Group, Raigarh CG) from WhatsApp-derived signals.\n"
        f"WEEK ENDING: {now.strftime('%A %d %B %Y')}\n\n"
        "COMPUTED (every figure below is already traced to signal ids — narrate it, do not recompute):\n"
        + json.dumps(computed, default=str)[:30000]
        + "\n\nSIGNALS (id, kind, entity, counterparty, amount, due, summary):\n" + json.dumps(slim, default=str)[:40000]
        + "\n\nREGISTER (assets / liabilities / capital / debt / resources / commitments / vision):\n"
        + json.dumps(register[:100], default=str)[:10000]
        + "\n\nRULES (CHIEF_OF_STAFF.md §1.6 — every fact carries a source):\n"
        "- EVERY number you write must appear verbatim in the input above, and every figure cites its signal id(s) as #id.\n"
        "- No totals, averages, percentages or dates you compute yourself. If a number is not in the input, do not write it.\n"
        "- Never invent a counterparty, an entity, or an amount. Entities: " + ", ".join(ENTITY_NAMES) + ".\n"
        "- Cover: sales gap, efficiency (who is slow / what is unanswered), recurring bottlenecks, money owed both ways,\n"
        "  register changes to post, decisions waiting on Aman. Empty sections say 'nothing this week'.\n"
        "- At most 5 next steps. Each has an owner (a named person or Aman), an ETA, and the signal ids it rests on.\n"
        "- Lakh/crore wording is fine ONLY if the exact figure also appears as written in the input.\n\n"
        "Return ONLY this JSON object:\n"
        '{"headline":"one line for the phone","narrative":"markdown, at most 15 lines",'
        '"next_steps":[{"step":"","owner":"","eta":"","signal_ids":[]}]}'
    )


def parse_pulse(text: Any) -> dict | None:
    obj = extract_json(text)
    if isinstance(obj, list):
        obj = next((o for o in obj if isinstance(o, dict) and ("narrative" in o or "next_steps" in o)), None)
    if not isinstance(obj, dict):
        return None
    steps = []
    for st in (obj.get("next_steps") or [])[:5]:
        if not isinstance(st, dict):
            continue
        step = str(st.get("step") or "").strip()
        if not step:
            continue
        steps.append({"step": step[:300], "owner": str(st.get("owner") or "").strip()[:60],
                      "eta": str(st.get("eta") or "").strip()[:60], "signal_ids": _as_ids(st.get("signal_ids"))})
    return {"headline": str(obj.get("headline") or "").strip()[:200],
            "narrative": str(obj.get("narrative") or "").strip()[:6000], "next_steps": steps}


# ═════════════════════════════════════════════════════════════════════════════
# Server side — register(app, vdb, publish_feed, send_cos, create_job)
# ═════════════════════════════════════════════════════════════════════════════
def _enabled() -> bool:
    return os.environ.get("WA_INTEL_ENABLED", "1").strip() != "0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def register(app, vdb: Callable[[], Awaitable[Any]], publish_feed: Callable[..., Awaitable[Any]],
             send_cos: Callable[[str], dict], create_job: Callable[[dict], Awaitable[dict]]) -> dict:
    """Mount /api/wa/* and return the hooks mdo_server's ingest path needs."""

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        rows = await db.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name='whatsapp_messages'")
        if rows:
            cols = {r[1] for r in await db.execute_fetchall("PRAGMA table_info(whatsapp_messages)")}
            for col, decl in WA_MSG_COLUMNS.items():
                if col not in cols:
                    await db.execute(f"ALTER TABLE whatsapp_messages ADD COLUMN {col} {decl}")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_wa_msg_id ON whatsapp_messages(account, wa_msg_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_wa_msg_jid ON whatsapp_messages(jid, id)")
        await db.commit()

    # ── ingest (called by /api/whatsapp/message with the open connection) ─
    async def ingest(db, body: dict) -> dict:
        """Upsert the chat, apply the personal gate, dedup on wa_msg_id, store.
        Returns {"stored": True, "id": ...} or {"stored": False, "reason": ...}."""
        jid = str(body.get("chat_jid") or body.get("jid") or "")[:100]
        account = str(body.get("account") or "1")[:8]
        kind = "dm" if str(body.get("chat_kind") or "group").lower() == "dm" else "group"
        name = str(body.get("group") or body.get("chat_name") or "")[:200]
        text = str(body.get("text", ""))[:2000]
        timestamp = str(body.get("timestamp", ""))[:50]
        sender = str(body.get("sender", ""))[:100]
        from_me = 1 if str(body.get("from_me") or "0") in ("1", "true", "True") else 0
        wa_msg_id = str(body.get("wa_msg_id") or "")[:120]
        parts = body.get("participants")
        parts_json = json.dumps([str(p)[:60] for p in parts][:200]) if isinstance(parts, list) and parts else ""
        seen = (parse_ts(timestamp) or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")

        if wa_msg_id:
            dup = await db.execute_fetchall(
                "SELECT id FROM whatsapp_messages WHERE account=? AND wa_msg_id=? LIMIT 1", (account, wa_msg_id))
            if dup:
                return {"received": True, "stored": False, "reason": "duplicate", "id": dict(dup[0])["id"]}

        classification = "unclear"
        if jid and _enabled():
            await db.execute(
                "INSERT INTO wa_chats (jid, account, name, kind, first_seen, last_seen, msg_count, participants) "
                "VALUES (?,?,?,?,?,?,1,?) ON CONFLICT(jid) DO UPDATE SET "
                "name=CASE WHEN excluded.name!='' THEN excluded.name ELSE wa_chats.name END, "
                "account=excluded.account, kind=excluded.kind, last_seen=excluded.last_seen, "
                "msg_count=wa_chats.msg_count+1, "
                "participants=CASE WHEN excluded.participants!='' THEN excluded.participants ELSE wa_chats.participants END",
                (jid, account, name, kind, seen, seen, parts_json))
            row = await db.execute_fetchall("SELECT classification FROM wa_chats WHERE jid=?", (jid,))
            classification = dict(row[0])["classification"] if row else "unclear"
            if classification == "personal":
                await db.commit()
                return {"received": True, "stored": False, "reason": "personal"}

        cur = await db.execute(
            "INSERT INTO whatsapp_messages (group_name, sender, text, timestamp, jid, account, chat_kind, from_me, wa_msg_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (name, sender, text, timestamp, jid, account, kind, from_me, wa_msg_id))
        await db.commit()
        return {"received": True, "stored": True, "id": cur.lastrowid, "classification": classification, "chat_kind": kind}

    # ── chats ──────────────────────────────────────────────────────────────
    def _chat(r) -> dict:
        d = dict(r)
        try:
            d["participants"] = json.loads(d.get("participants") or "[]")
        except json.JSONDecodeError:
            d["participants"] = []
        return d

    async def classify_apply(jid: str, classification: str, entity: str = "", decided_by: str = "aman",
                             confidence: float | None = None, reason: str = "") -> dict:
        """The ONE code path for a verdict (endpoint, bot and reply all land here).
        personal → the chat's messages, extractions and open signals are gone."""
        classification = _norm(classification)
        if classification not in CLASSIFICATIONS:
            raise HTTPException(400, "classification must be business|personal|unclear")
        if decided_by not in ("auto", "aman", ""):
            raise HTTPException(400, "decided_by must be auto|aman")
        db = await vdb()
        rows = await db.execute_fetchall("SELECT * FROM wa_chats WHERE jid=?", (jid,))
        if not rows:
            raise HTTPException(404, f"no chat {jid}")
        entity = canonical_entity(entity) if classification == "business" else ""
        deleted = {"messages": 0, "extractions": 0, "signals_dismissed": 0}
        if classification == "personal":
            cur = await db.execute(
                "DELETE FROM media_extractions WHERE message_id IN (SELECT id FROM whatsapp_messages WHERE jid=?)", (jid,))
            deleted["extractions"] = cur.rowcount
            cur = await db.execute("DELETE FROM whatsapp_messages WHERE jid=?", (jid,))
            deleted["messages"] = cur.rowcount
            cur = await db.execute("UPDATE biz_signals SET status='dismissed' WHERE chat_jid=? AND status='open'", (jid,))
            deleted["signals_dismissed"] = cur.rowcount
        await db.execute(
            "UPDATE wa_chats SET classification=?, entity=?, confidence=?, reason=?, decided_by=?, decided_at=? WHERE jid=?",
            (classification, entity, confidence, str(reason or "")[:400], decided_by, _now_iso(), jid))
        await db.commit()
        return {"ok": True, "jid": jid, "classification": classification, "entity": entity,
                "decided_by": decided_by, **deleted}

    @app.get("/api/wa/chats")
    async def wa_chats(classification: str = "", account: str = "", with_samples: int = 0, limit: int = 200):
        db = await vdb()
        q, p = "SELECT * FROM wa_chats WHERE 1=1", []
        if classification:
            q += " AND classification=?"; p.append(classification)
        if account:
            q += " AND account=?"; p.append(account)
        q += " ORDER BY last_seen DESC LIMIT ?"; p.append(min(int(limit), 1000))
        chats = [_chat(r) for r in await db.execute_fetchall(q, p)]
        if with_samples:
            for c in chats:
                rows = await db.execute_fetchall(
                    "SELECT sender, text FROM whatsapp_messages WHERE jid=? AND text!='' AND text NOT LIKE '[media]%' "
                    "ORDER BY id DESC LIMIT 30", (c["jid"],))
                c["samples"] = [dict(r) for r in reversed(rows)]
        return {"chats": chats, "count": len(chats)}

    @app.post("/api/wa/chats/classify")
    async def wa_chats_classify(body: dict):
        conf = _as_float(body.get("confidence"))
        return await classify_apply(str(body.get("jid") or ""), str(body.get("classification") or ""),
                                    str(body.get("entity") or ""), str(body.get("decided_by") or "aman"),
                                    conf, str(body.get("reason") or ""))

    @app.post("/api/wa/chats/asked")
    async def wa_chats_asked(body: dict):
        """The classifier records which cos_job is waiting on Aman, so it never re-asks."""
        db = await vdb()
        cur = await db.execute("UPDATE wa_chats SET asked_job_id=? WHERE jid=?",
                               (int(body.get("job_id") or 0) or None, str(body.get("jid") or "")))
        await db.commit()
        return {"ok": cur.rowcount == 1}

    async def apply_verdicts() -> dict:
        """Resolved cos_jobs whose payload says action=wa_classify → apply Aman's answer
        through classify_apply (decided_by aman). Returns what was applied."""
        db = await vdb()
        try:
            rows = await db.execute_fetchall(
                "SELECT * FROM cos_jobs WHERE status!='open' AND payload_json LIKE '%wa_classify%' ORDER BY id")
        except Exception:
            return {"applied": 0, "note": "cos_jobs has no payload_json column"}
        applied, skipped = [], []
        for r in rows:
            job = dict(r)
            try:
                payload = json.loads(job.get("payload_json") or "{}")
            except json.JSONDecodeError:
                payload = {}
            if payload.get("action") != "wa_classify" or not payload.get("jid"):
                continue
            jid = str(payload["jid"])
            chat = await db.execute_fetchall("SELECT classification, asked_job_id FROM wa_chats WHERE jid=?", (jid,))
            if not chat or dict(chat[0])["classification"] != "unclear":
                continue                       # already decided (endpoint, bot or an earlier pass)
            verdict, entity = "", ""
            if job["status"] == "chosen":
                m = re.search(r"option\s+(\d+)", str(job.get("answer") or ""))
                opts = json.loads(job.get("options_json") or "[]")
                idx = int(m.group(1)) - 1 if m else -1
                choice = _norm(opts[idx]) if 0 <= idx < len(opts) else ""
                if choice.startswith("personal"):
                    verdict = "personal"
                elif choice.startswith("business"):
                    verdict = "business"
                    tail = choice.split(":", 1)[1].strip() if ":" in choice else ""
                    entity = "" if tail in ("", "other entity") else canonical_entity(tail)
            elif job["status"] == "approved":
                verdict = "business"
                entity = canonical_entity(payload.get("guess_entity") or "")
            elif job["status"] == "rejected":
                verdict = "personal"
            if not verdict:
                skipped.append({"job": job["id"], "jid": jid, "status": job["status"], "answer": job.get("answer")})
                continue
            res = await classify_apply(jid, verdict, entity, "aman", None,
                                       f"reply to job #{job['id']} ({job.get('answer_source') or 'reply'}): {job.get('answer')}")
            applied.append({"job": job["id"], "jid": jid, "classification": verdict, "entity": entity,
                            "messages_deleted": res.get("messages", 0)})
        return {"applied": len(applied), "details": applied, "skipped": skipped}

    @app.post("/api/wa/verdicts/apply")
    async def wa_verdicts_apply():
        return await apply_verdicts()

    @app.get("/api/wa/messages")
    async def wa_messages(classification: str = "business", since_id: int = 0, limit: int = 2000, jid: str = ""):
        """Messages joined to their chat's verdict — what wa-intel reads."""
        db = await vdb()
        q = ("SELECT m.id, m.jid AS chat_jid, c.name AS chat_name, c.entity, c.account, c.kind AS chat_kind, "
             "m.sender, m.text, m.timestamp, m.from_me, m.created_at FROM whatsapp_messages m "
             "JOIN wa_chats c ON c.jid = m.jid WHERE m.id > ?")
        p: list = [int(since_id)]
        if classification:
            q += " AND c.classification=?"; p.append(classification)
        if jid:
            q += " AND m.jid=?"; p.append(jid)
        q += " ORDER BY m.id LIMIT ?"; p.append(min(int(limit), 5000))
        rows = [dict(r) for r in await db.execute_fetchall(q, p)]
        return {"messages": rows, "count": len(rows), "max_id": max((r["id"] for r in rows), default=int(since_id))}

    # ── signals ────────────────────────────────────────────────────────────
    def _sig(r) -> dict:
        d = dict(r)
        try:
            d["evidence_ids"] = json.loads(d.get("evidence_ids") or "[]")
        except json.JSONDecodeError:
            d["evidence_ids"] = []
        return d

    @app.get("/api/wa/signals")
    async def wa_signals(status: str = "open", entity: str = "", kind: str = "", limit: int = 100, days: int = 0):
        db = await vdb()
        q, p = "SELECT * FROM biz_signals WHERE 1=1", []
        if status:
            q += " AND status=?"; p.append(status)
        if entity:
            q += " AND entity=?"; p.append(entity)
        if kind:
            q += " AND kind=?"; p.append(kind)
        if days:
            q += " AND created_at >= datetime('now', ?)"; p.append(f"-{int(days)} days")
        q += " ORDER BY id DESC LIMIT ?"; p.append(min(int(limit), 1000))
        rows = [_sig(r) for r in await db.execute_fetchall(q, p)]
        return {"signals": rows, "count": len(rows)}

    async def signals_insert(items: list[dict], bot_id: str = "") -> dict:
        db = await vdb()
        week = iso_week()
        inserted, duplicates, alerts, ids = 0, 0, [], []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            s = parse_signals({"signals": [raw]}, None)
            if not s:
                continue
            s = s[0]
            s["chat_jid"] = str(raw.get("chat_jid") or "")[:100]
            s["chat_name"] = str(raw.get("chat_name") or "")[:200]
            fp = signal_fingerprint(s["entity"], s["kind"], s["counterparty"], s["due_date"] or week)
            cur = await db.execute(
                "INSERT OR IGNORE INTO biz_signals (entity, chat_jid, chat_name, kind, counterparty, amount, currency, "
                "due_date, summary, evidence_ids, snippet, confidence, owner, bot_id, fingerprint) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s["entity"], s["chat_jid"], s["chat_name"], s["kind"], s["counterparty"], s["amount"], s["currency"],
                 s["due_date"], s["summary"], json.dumps(s["evidence_ids"]), s["snippet"], s["confidence"],
                 str(raw.get("owner") or "")[:60], str(bot_id or raw.get("bot_id") or "")[:60], fp))
            if cur.rowcount:
                inserted += 1
                s["id"] = cur.lastrowid
                ids.append(cur.lastrowid)
                if is_red(s):
                    line = red_line(s)
                    try:
                        push = send_cos(line)
                    except Exception as e:           # a failed push never loses the signal
                        push = {"sent": False, "reason": str(e)[:120]}
                    alerts.append({"id": s["id"], "line": line, "push": push})
            else:
                duplicates += 1
        await db.commit()
        return {"inserted": inserted, "duplicates": duplicates, "ids": ids, "alerts": alerts}

    @app.post("/api/wa/signals")
    async def wa_signals_post(body: dict):
        items = body.get("signals") if isinstance(body.get("signals"), list) else [body]
        return await signals_insert(items[:500], str(body.get("bot_id") or ""))

    @app.post("/api/wa/signals/{signal_id}/status")
    async def wa_signal_status(signal_id: int, body: dict):
        status = _norm(body.get("status"))
        if status not in SIGNAL_STATUSES:
            raise HTTPException(400, "status must be open|done|dismissed")
        db = await vdb()
        cur = await db.execute("UPDATE biz_signals SET status=?, owner=COALESCE(?, owner) WHERE id=?",
                               (status, body.get("owner"), int(signal_id)))
        await db.commit()
        if not cur.rowcount:
            raise HTTPException(404, f"no signal {signal_id}")
        return {"ok": True, "id": int(signal_id), "status": status}

    # ── register ───────────────────────────────────────────────────────────
    @app.get("/api/wa/register")
    async def wa_register_get(category: str = "", entity: str = "", status: str = "active"):
        db = await vdb()
        q, p = "SELECT * FROM biz_register WHERE 1=1", []
        if category:
            q += " AND category=?"; p.append(category)
        if entity:
            q += " AND entity=?"; p.append(entity)
        if status:
            q += " AND status=?"; p.append(status)
        q += " ORDER BY category, entity, item"
        rows = [dict(r) for r in await db.execute_fetchall(q, p)]
        return {"register": rows, "count": len(rows)}

    @app.post("/api/wa/register")
    async def wa_register_post(body: dict):
        """Add a line (or update one by id). Source is mandatory: a register
        line with no source is an invented number."""
        category = _norm(body.get("category"))
        if category not in REGISTER_CATEGORIES:
            raise HTTPException(400, "category must be one of " + "|".join(REGISTER_CATEGORIES))
        item = str(body.get("item") or "").strip()
        source = str(body.get("source") or "").strip()
        if not item or not source:
            raise HTTPException(400, "item and source are required")
        db = await vdb()
        vals = (category, canonical_entity(body.get("entity")) or str(body.get("entity") or "")[:80], item[:300],
                _as_float(body.get("value")), str(body.get("unit") or "INR")[:16], str(body.get("as_of") or "")[:10],
                source[:300], str(body.get("status") or "active")[:20], str(body.get("notes") or "")[:1000])
        if body.get("id"):
            cur = await db.execute(
                "UPDATE biz_register SET category=?, entity=?, item=?, value=?, unit=?, as_of=?, source=?, status=?, "
                "notes=?, updated_at=datetime('now') WHERE id=?", (*vals, int(body["id"])))
            if not cur.rowcount:
                raise HTTPException(404, f"no register line {body['id']}")
            rid = int(body["id"])
        else:
            cur = await db.execute(
                "INSERT INTO biz_register (category, entity, item, value, unit, as_of, source, status, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?)", vals)
            rid = cur.lastrowid
        await db.commit()
        return {"ok": True, "id": rid}

    # ── pulse ──────────────────────────────────────────────────────────────
    @app.get("/api/wa/pulse/input")
    async def wa_pulse_input(days: int = 90, metric_days: int = 14):
        """Everything business-pulse reasons over: open signals (plus the
        closed ones in the window, so a quote with a later order is not a
        gap), response metrics over recent business messages, the register."""
        db = await vdb()
        sigs = [_sig(r) for r in await db.execute_fetchall(
            "SELECT * FROM biz_signals WHERE created_at >= datetime('now', ?) OR status='open' ORDER BY id",
            (f"-{int(days)} days",))]
        msgs = [dict(r) for r in await db.execute_fetchall(
            "SELECT m.id, m.jid AS chat_jid, m.sender, m.text, m.timestamp, m.from_me FROM whatsapp_messages m "
            "JOIN wa_chats c ON c.jid=m.jid WHERE c.classification='business' AND m.created_at >= datetime('now', ?) "
            "ORDER BY m.id", (f"-{int(metric_days)} days",))]
        names = {dict(r)["jid"]: dict(r)["name"] for r in await db.execute_fetchall("SELECT jid, name FROM wa_chats")}
        metrics = response_metrics(msgs)
        for m in metrics:
            m["chat_name"] = names.get(m["chat"], m["chat"])
        reg = [dict(r) for r in await db.execute_fetchall("SELECT * FROM biz_register WHERE status='active' ORDER BY category, entity")]
        return {"signals": sigs, "metrics": metrics, "register": reg, "messages_scanned": len(msgs),
                "days": int(days), "metric_days": int(metric_days)}

    @app.post("/api/wa/pulse")
    async def wa_pulse_post(body: dict):
        """Save a pulse, publish it to the Decision Feed, push the roll-up line."""
        db = await vdb()
        report = body.get("report_json") if isinstance(body.get("report_json"), dict) else {}
        summary = str(body.get("summary") or "")[:2000]
        cur = await db.execute(
            "INSERT INTO biz_pulse (period_start, period_end, entity, report_json, summary) VALUES (?,?,?,?,?)",
            (str(body.get("period_start") or "")[:10], str(body.get("period_end") or "")[:10],
             str(body.get("entity") or "group")[:60], json.dumps(report, default=str)[:400000], summary))
        await db.commit()
        pid = cur.lastrowid
        headline = str(body.get("headline") or summary.split("\n")[0] or f"Business pulse #{pid}")[:200]
        feed = None
        try:
            item = await publish_feed(
                key=f"wa.pulse.{body.get('period_end') or pid}", title=headline, severity="info",
                source="business-pulse", domain="general", body=str(report.get("narrative") or summary)[:8000],
                evidence=[{"pulse_id": pid, "signal_ids": [s.get("id") for s in (report.get("signals") or [])][:50]}])
            feed = item["id"] if item else None
        except Exception as e:
            feed = f"feed error: {str(e)[:120]}"
        push = {"sent": False, "reason": "push=false"}
        if body.get("push", True):
            try:
                push = send_cos(f"📊 pulse #{pid} · {headline}"[:600])
            except Exception as e:
                push = {"sent": False, "reason": str(e)[:120]}
        return {"ok": True, "id": pid, "feed_item": feed, "push": push}

    @app.get("/api/wa/pulse/latest")
    async def wa_pulse_latest():
        db = await vdb()
        rows = await db.execute_fetchall("SELECT * FROM biz_pulse ORDER BY id DESC LIMIT 1")
        if not rows:
            return {"pulse": None}
        d = dict(rows[0])
        try:
            d["report"] = json.loads(d.pop("report_json") or "{}")
        except json.JSONDecodeError:
            d["report"] = {}
        return {"pulse": d}

    # ── stats ──────────────────────────────────────────────────────────────
    async def stats() -> dict:
        db = await vdb()
        by_class = {r[0]: r[1] for r in await db.execute_fetchall(
            "SELECT classification, COUNT(*) FROM wa_chats GROUP BY classification")}
        by_kind = {r[0]: r[1] for r in await db.execute_fetchall(
            "SELECT kind, COUNT(*) FROM biz_signals WHERE status='open' GROUP BY kind")}
        asked = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM wa_chats WHERE classification='unclear' AND asked_job_id IS NOT NULL"))[0][0]
        msgs7 = (await db.execute_fetchall(
            "SELECT COUNT(*) FROM whatsapp_messages WHERE created_at >= datetime('now','-7 days')"))[0][0]
        total_msgs = (await db.execute_fetchall("SELECT COUNT(*) FROM whatsapp_messages"))[0][0]
        pulses = (await db.execute_fetchall("SELECT COUNT(*) FROM biz_pulse"))[0][0]
        return {
            "enabled": _enabled(),
            "chats": {"by_classification": {c: by_class.get(c, 0) for c in CLASSIFICATIONS},
                      "awaiting_aman": asked, "total": sum(by_class.values())},
            "signals": {"open_by_kind": by_kind, "open_total": sum(by_kind.values())},
            "messages": {"last_7d": msgs7, "total": total_msgs},
            "pulses": pulses, "as_of": _now_iso(),
        }

    @app.get("/api/wa/stats")
    async def wa_stats():
        return await stats()

    return {"ensure_schema": ensure_schema, "ingest": ingest, "classify_apply": classify_apply,
            "apply_verdicts": apply_verdicts, "signals_insert": signals_insert, "stats": stats}
