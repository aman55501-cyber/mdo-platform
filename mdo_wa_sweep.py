"""wa-sweep — Aman's eyes on the Mausaji chat and the site groups. Rule-based, zero LLM spend.

Aman, chat 2026-10-09: "be sweeping whatsapp constantly specially during market hours for 'Bantu
Mausaji' chat for shares, and other washery, siding, hotel groups for project bottlenecks resolving
in real time. hourly/halfhourly checks… set alerts on specific chats… does not involve capital
upfront." Answered the same day (AMAN_PENDING A13): watched chats = Bantu Mausaji, Vedanta Daily
Report, Washery Civil Update, Ans Management, VWLR Indent Planning, Core Group; silence over 1 hour
is intolerable; chat priorities come later.

Reads the message store the bridges already fill (whatsapp_messages + wa_chats, owned by
mdo_wa_intel.py — nothing is duplicated here). Three tables of its own:
  wa_sweep_state   one row per watched chat: mode (mausaji|ops), watermark (last message id seen),
                   last push time (the 30-minute rule), silence episode marker, priority
  wa_sweep_flags   what the rules found: call | mention | bottleneck | silence, open until acked
  wa_sweep_runs    one row per run, so the 21:00 IST daily line can add the day up

Three modes, all driven by `python mdo_agent.py wa-sweep <mode>` (fleet.yaml: wa-sweep):
  mausaji  the Mausaji chat: every new message about a share → one WhatsApp line to Aman at once
           (ticker · what Mausaji said · current price · list level · HELD BY · research only)
  ops      the site/ops groups: bottleneck words → flag; pushed at once when that chat had no push
           in the last 30 min, otherwise batched into one message; a chat silent for more than
           WA_SWEEP_IDLE_HOURS inside 08:00–20:00 IST → one silence flag per episode, pushed at once
  daily    one line with the day's totals and the chats currently matched, so Aman can correct the set

Rules that bind (CHIEF_OF_STAFF.md): nothing here is an order (every share line ends "research only");
no price is invented ("price n/a"); every share line carries the holder (Directive 18); every run
reports even when all counts are zero (Directive 5); no secrets in code. The pure helpers above
register() take plain values and touch nothing — tests/test_wa_sweep.py runs them without a server.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

import mdo_levels as lv
from mdo_cos import IST
from mdo_wa_intel import parse_ts

BOT_ID = "wa-sweep"
MODES = ("mausaji", "ops", "daily")
MAUSAJI_CHAT_DEFAULT = "Bantu Mausaji"
WATCH_CHATS_DEFAULT = "Bantu Mausaji;Vedanta Daily Report;Washery Civil Update;Ans Management;VWLR Indent Planning;Core Group"
GROUPS_REGEX_DEFAULT = r"washery|siding|hotel|ans|vwlr|rake|plant|site|loader|dispatch"
IDLE_HOURS_DEFAULT = 1.0                 # Aman, 2026-10-09: more than 1 hour of silence is intolerable
PUSH_GAP_MIN = 30                        # a chat is pushed at once only if its last push is older than this
BACKFILL_HOURS = 2                       # a chat seen for the first time: only its last 2h are judged
BUSINESS_START, BUSINESS_END = time(8, 0), time(20, 0)   # IST window the silence check counts
QUOTE_MAX = 200
BATCH_MAX_LINES = 10
PRIORITIES = ("high", "normal", "low")
FLAG_KINDS = ("call", "mention", "bottleneck", "silence")

SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_sweep_state (
    chat_jid TEXT PRIMARY KEY,
    chat_name TEXT DEFAULT '', account TEXT DEFAULT '', kind TEXT DEFAULT 'group',
    mode TEXT NOT NULL DEFAULT 'ops',                 -- mausaji | ops
    last_msg_id INTEGER NOT NULL DEFAULT 0,           -- watermark: highest whatsapp_messages.id judged
    last_push_at TEXT,                                -- UTC ISO of the last push that named this chat
    silence_since TEXT DEFAULT '',                    -- last-message time the open silence flag was raised for
    priority TEXT NOT NULL DEFAULT 'normal',          -- high | normal | low (Aman sets; shown, not yet used)
    first_swept_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS wa_sweep_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_jid TEXT NOT NULL, chat_name TEXT DEFAULT '', account TEXT DEFAULT '',
    message_id INTEGER, sender TEXT DEFAULT '',
    kind TEXT NOT NULL,                               -- call | mention | bottleneck | silence
    ticker TEXT DEFAULT '', text TEXT DEFAULT '', detail_json TEXT DEFAULT '{}',
    msg_at TEXT DEFAULT '', day TEXT DEFAULT '',      -- msg_at UTC ISO; day = IST date the flag was raised
    created_at TEXT DEFAULT (datetime('now')),
    status TEXT NOT NULL DEFAULT 'open',              -- open | ack
    pushed_at TEXT, acked_at TEXT,
    UNIQUE(chat_jid, message_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_wa_sweep_flags_status ON wa_sweep_flags(status, id);
CREATE INDEX IF NOT EXISTS idx_wa_sweep_flags_day ON wa_sweep_flags(day, kind);
CREATE TABLE IF NOT EXISTS wa_sweep_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL, ran_at TEXT DEFAULT (datetime('now')), day TEXT DEFAULT '',
    chats INTEGER DEFAULT 0, new_msgs INTEGER DEFAULT 0, flags INTEGER DEFAULT 0, pushed INTEGER DEFAULT 0,
    note TEXT DEFAULT ''
);
"""

fmt_n, _num, norm_ticker = lv.fmt_n, lv._num, lv.norm_ticker


# ═════════════════════════════════════════════════════════════════════════════
# Pure helpers — no database, no network
# ═════════════════════════════════════════════════════════════════════════════
def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&\-']+", " ", str(s or "").lower())).strip()


def mausaji_chat() -> str:
    return (os.environ.get("MAUSAJI_CHAT") or MAUSAJI_CHAT_DEFAULT).strip() or MAUSAJI_CHAT_DEFAULT


def watch_chats(raw: str | None = None) -> list[str]:
    """WA_SWEEP_CHATS — semicolon-separated chat names, matched case-insensitively (exact or contained)."""
    raw = os.environ.get("WA_SWEEP_CHATS", WATCH_CHATS_DEFAULT) if raw is None else raw
    out, seen = [], set()
    for part in str(raw or "").split(";"):
        p = part.strip()
        if p and p.lower() not in seen:
            seen.add(p.lower()); out.append(p)
    return out


def groups_regex(raw: str | None = None) -> re.Pattern:
    """WA_SWEEP_GROUPS — a regex over group names, case-insensitive. A broken pattern falls back to the default."""
    raw = os.environ.get("WA_SWEEP_GROUPS", GROUPS_REGEX_DEFAULT) if raw is None else raw
    try:
        return re.compile(str(raw or GROUPS_REGEX_DEFAULT), re.IGNORECASE)
    except re.error:
        return re.compile(GROUPS_REGEX_DEFAULT, re.IGNORECASE)


def idle_hours() -> float:
    v = _num(os.environ.get("WA_SWEEP_IDLE_HOURS", ""))
    return v if v is not None and v > 0 else IDLE_HOURS_DEFAULT


def chat_mode(name: Any, kind: Any = "group", *, mausaji: str | None = None, watch: list[str] | None = None,
              regex: re.Pattern | None = None) -> str | None:
    """'mausaji' when the chat name carries the Mausaji chat name; 'ops' when the name is on the watched list
    (exact or contained, any kind) or, for a group, matches the WA_SWEEP_GROUPS regex; else None."""
    n = str(name or "").strip().lower()
    if not n:
        return None
    m = (mausaji if mausaji is not None else mausaji_chat()).lower()
    if m and (n == m or m in n):
        return "mausaji"
    for w in (watch if watch is not None else watch_chats()):
        wl = w.lower()
        if wl == m:
            continue
        if n == wl or wl in n:
            return "ops"
    rx = regex if regex is not None else groups_regex()
    if str(kind or "group").lower() == "group" and rx.search(n):
        return "ops"
    return None


# ── Mausaji: tickers and calls ───────────────────────────────────────────────
# Words that are (or could be) NSE symbols but mean something else in a chat line. Lowercase.
_TICKER_STOP = {
    "idea", "india", "gold", "silver", "power", "bank", "cash", "call", "best", "take", "note", "star", "tips", "shop",
    "mind", "like", "time", "next", "one", "two", "max", "min", "all", "any", "for", "and", "the", "now", "new", "old",
    "buy", "sell", "hold", "target", "entry", "exit", "stop", "loss", "book", "zone", "rate", "gain", "high", "low",
    "open", "close", "level", "market", "share", "stock", "price", "today", "good", "bad", "yes", "plan", "trend",
    "move", "risk", "safe", "free", "care", "fast", "slow", "wait", "run", "hit", "top", "down", "crude", "nifty",
    "sensex", "limited", "ltd", "international", "industries", "india", "company", "services", "group", "finance",
    "capital", "trading", "energy", "steel", "cement", "motors", "pharma", "infra", "tech", "life", "home", "city",
    "lelo", "becho", "bech", "karo", "abhi", "mat", "hai", "nahi", "kya", "aur", "toh", "bhi", "par", "pe", "ke", "ko",
    "ki", "ka", "ye", "wo", "le", "de", "lo", "do", "to", "ho", "ab", "aas", "paas", "mahine", "din", "saal", "sl",
}
_NUM_RX = r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_CALL_WORDS = {
    "buy": r"buy|lelo|le\s?lo|lena|le\s?le|le\s?lena|kharid(?:o|lo|na)?|khareed(?:o|lo)?|entry|enter|accumulate|add|lelena",
    "sell": r"sell|bech(?:o|na|\s?do)?|exit|book|nikal(?:o|\s?do)?",
    "target": r"target|tgt|tp|t1|t2",
    "sl": r"sl|stop\s?loss|stoploss|stop",
}
_CALL_RX = {k: re.compile(rf"\b(?:{v})\b", re.IGNORECASE) for k, v in _CALL_WORDS.items()}
_NUM_AFTER = {k: re.compile(rf"\b(?:{v})\b[^0-9\n]{{0,24}}?{_NUM_RX}", re.IGNORECASE) for k, v in _CALL_WORDS.items()}
_NUM_BEFORE = {k: re.compile(rf"{_NUM_RX}[^0-9\n]{{0,16}}?\b(?:{v})\b", re.IGNORECASE) for k, v in _CALL_WORDS.items()}
_HOLD_RX = re.compile(r"\b(?:hold|rakho|rakhna|rakh lo|wait)\b", re.IGNORECASE)
_AVOID_RX = re.compile(r"\b(?:mat|avoid|don'?t|nahi lena|na lo|mat lena|mat lo)\b", re.IGNORECASE)


def ticker_index(levels_rows: list[dict] | None, nse_symbols: Any = ()) -> dict:
    """What a Mausaji line can name: {'listed': {TCS,…} (share_levels), 'nse': {…} (EQUITY_L.csv symbols),
    'words': {'advent': 'ADVENTHTL'} (company-name words from share_levels notes, unique ones only)}."""
    listed, words, dup = set(), {}, set()
    for r in levels_rows or []:
        t = norm_ticker(r.get("ticker"))
        if not t:
            continue
        listed.add(t)
        head = str(r.get("note") or "").split("·")[0]
        for w in _norm(head).split():
            if len(w) < 5 or w in _TICKER_STOP or w.isdigit():
                continue
            if w in words and words[w] != t:
                dup.add(w)
            words.setdefault(w, t)
    for w in dup:
        words.pop(w, None)
    nse = {norm_ticker(s) for s in (nse_symbols or ()) if norm_ticker(s)}
    return {"listed": listed, "nse": nse, "words": words}


def find_tickers(text: Any, index: dict | None) -> list[str]:
    """Tickers named in the text, in order of appearance: share_levels tickers (any length ≥2), NSE symbols
    (≥4 chars), company-name words from the notes. Never a stop word. Empty when nothing is known."""
    index = index or {}
    listed, nse, words = index.get("listed") or set(), index.get("nse") or set(), index.get("words") or {}
    out: list[str] = []
    for tok in _norm(text).split():
        up = tok.upper()
        hit = None
        if tok not in _TICKER_STOP:
            if up in listed and len(up) >= 2:
                hit = up
            elif up in nse and len(up) >= 4:
                hit = up
        if hit is None and tok in words:
            hit = words[tok]
        if hit and hit not in out:
            out.append(hit)
    return out


def parse_call(text: Any) -> dict:
    """{'action': buy|sell|hold|avoid|None, 'buy': n, 'sell': n, 'target': n, 'sl': n} — numbers found next to
    the call words (Hindi in Roman script and English), None where absent. Nothing is inferred."""
    s = str(text or "")
    out: dict[str, Any] = {"action": None, "buy": None, "sell": None, "target": None, "sl": None}
    for key in ("buy", "sell", "target", "sl"):
        m = _NUM_AFTER[key].search(s) or _NUM_BEFORE[key].search(s)
        if m:
            out[key] = _num(m.group(1))
    if _AVOID_RX.search(s):
        out["action"] = "avoid"
    elif _CALL_RX["buy"].search(s) and not (out["buy"] is None and out["sell"] is not None and _CALL_RX["sell"].search(s)):
        out["action"] = "buy"
    elif _CALL_RX["sell"].search(s):
        out["action"] = "sell"
    elif _HOLD_RX.search(s):
        out["action"] = "hold"
    return out


def analyse_mausaji(text: Any, index: dict | None) -> dict | None:
    """A Mausaji message → {'tickers': [...], 'call': {...}, 'kind': 'call'|'mention'} or None when it is not
    about a share (no ticker named, no call word with a number)."""
    tickers = find_tickers(text, index)
    call = parse_call(text)
    has_call = call["action"] is not None or any(call[k] is not None for k in ("buy", "sell", "target", "sl"))
    if tickers:
        return {"tickers": tickers, "call": call, "kind": "call" if has_call else "mention"}
    if has_call and any(call[k] is not None for k in ("buy", "sell", "target", "sl")):
        return {"tickers": [], "call": call, "kind": "call"}
    return None


# ── ops: bottleneck words (Hindi in Roman script + English) ──────────────────
BOTTLENECK_WORDS: list[tuple[str, str]] = [
    ("pending", r"pending"),
    ("ruka", r"ruk(?:a|i|e|ega|egi)?(?:\s+(?:hua|hui|hai|gaya|gayi))?|rukwa\w*"),
    ("band", r"band|bandh"),
    ("breakdown", r"break\s?down"),
    ("stuck", r"stuck|atka|atki|atak|fasa|fasi|phasa|phas\s?gay[ai]"),
    ("nahi aaya", r"n[ah]*i\s+(?:aaya|aayi|aya|ayi|aaye|pahuncha|pohcha|mila|mili|hua|hui|chala|chali)"),
    ("delay", r"delay(?:ed|s)?|deri|der\s+ho"),
    ("late", r"late"),
    ("shortage", r"shortage|short\s+(?:hai|h|ho|supply)|kam\s+(?:hai|pad|h)"),
    ("kami", r"kami"),
    ("payment", r"payment|bakaya|udhar"),
    ("urgent", r"urgent|turant|emergency|asap"),
    ("problem", r"problem|dikkat|pareshani|samasya"),
    ("issue", r"issue"),
    ("fail", r"fail(?:ed|ure|s)?"),
    ("kharab", r"kharab|kharaab|bigad\w*|toot\s?gay[ai]|tut\s?gay[ai]"),
    ("accident", r"accident|hadsa|injur\w*"),
    ("strike", r"strike|hadtal|hartal|chakka\s?jam|dharna"),
    ("no diesel", r"no\s+diesel|diesel\s+(?:nahi|nhi|khatam|khatm|finish|over)"),
    ("diesel", r"diesel"),
    ("rake nahi", r"rake\s+(?:nahi|nhi|cancel\w*)|no\s+rake"),
    ("wagon", r"wagon\w*"),
    ("demurrage", r"demurrage|demurage|wharfage"),
    ("penalty", r"penalty|jurmana"),
    ("guest complaint", r"guest\s+complain\w*"),
    ("complaint", r"complain\w*|shikayat"),
    ("cancel", r"cancel\w*|radd"),
]
_BOTTLENECK_RX = [(label, re.compile(rf"\b(?:{rx})\b", re.IGNORECASE)) for label, rx in BOTTLENECK_WORDS]


def find_bottleneck(text: Any) -> list[str]:
    """The bottleneck labels a message carries, in list order; [] when it is clean."""
    s = re.sub(r"\s+", " ", str(text or ""))
    out = [label for label, rx in _BOTTLENECK_RX if rx.search(s)]
    if "no diesel" in out and "diesel" in out:
        out.remove("diesel")
    if "guest complaint" in out and "complaint" in out:
        out.remove("complaint")
    return out


# ── time ─────────────────────────────────────────────────────────────────────
def as_dt(v: Any) -> datetime | None:
    d = parse_ts(v)
    return d.astimezone(timezone.utc) if d else None


def business_hours_between(a: datetime | None, b: datetime | None) -> float:
    """Hours of [a, b] that fall inside 08:00–20:00 IST, any day of the week."""
    if a is None or b is None or b <= a:
        return 0.0
    a, b = a.astimezone(IST), b.astimezone(IST)
    total, day = 0.0, a.date()
    while day <= b.date():
        lo = max(a, datetime.combine(day, BUSINESS_START, tzinfo=IST))
        hi = min(b, datetime.combine(day, BUSINESS_END, tzinfo=IST))
        if hi > lo:
            total += (hi - lo).total_seconds() / 3600
        day += timedelta(days=1)
    return round(total, 2)


def age_text(when: Any, now: datetime) -> str:
    d = as_dt(when)
    if d is None:
        return "time n/a"
    mins = int((now.astimezone(timezone.utc) - d).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 24 * 60:
        return f"{mins // 60}h {mins % 60:02d}m ago"
    return f"{mins // (24 * 60)}d ago"


def quote(text: Any, n: int = QUOTE_MAX) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ── lines Aman reads ─────────────────────────────────────────────────────────
def call_text(call: dict | None) -> str:
    """'read: buy 3,500 · target 3,900 · SL 3,350' — only what the words said, or ''."""
    if not call:
        return ""
    parts = []
    if call.get("action"):
        parts.append(str(call["action"]))
    for key, label in (("buy", "buy"), ("sell", "sell"), ("target", "target"), ("sl", "SL")):
        v = _num(call.get(key))
        if v is not None:
            if key == "buy" and call.get("action") == "buy":
                parts[0] = f"buy {fmt_n(v)}"
            elif key == "sell" and call.get("action") == "sell":
                parts[0] = f"sell {fmt_n(v)}"
            else:
                parts.append(f"{label} {fmt_n(v)}")
    return ("read: " + " · ".join(parts)) if parts else ""


def level_text(row: dict | None, ltp: float | None) -> str:
    if not row:
        return "not on list"
    parts = []
    for side, key in (("buy", "buy_level"), ("sell", "sell_level")):
        s = lv._side_text(side, ltp, _num(row.get(key)), _num(row.get("best_entry")) if side == "buy" else None)
        if s:
            parts.append(s)
    return "list: " + " · ".join(parts) if parts else "not on list"


def held_by_text(ticker: str, holders: dict[str, list[dict]] | None) -> str:
    """Directive 18: 'HELD BY Aman 500, Aditi 100' / 'HELD BY nobody' / 'HELD BY holdings n/a' (no holdings table)."""
    if holders is None:
        return "HELD BY holdings n/a"
    return "HELD BY " + lv.held_text(holders.get(norm_ticker(ticker)))


def format_mausaji_line(flag: dict, ltps: dict[str, float | None] | None, levels: dict[str, dict] | None,
                        holders: dict[str, list[dict]] | None, ltp_at: str = "") -> str:
    """ticker · what Mausaji said · current price · list level · HELD BY · research only. One line per message;
    a message naming several shares carries one price/level/held block per share."""
    tickers = [t for t in (flag.get("tickers") or []) if t]
    q = quote(flag.get("text"))
    who = str(flag.get("sender") or "Mausaji").strip() or "Mausaji"
    head = ", ".join(tickers) if tickers else "share?"
    parts = [head, f"{who}: \"{q}\""]
    ct = call_text(flag.get("call"))
    if ct:
        parts.append(ct)
    if tickers:
        for t in tickers:
            ltp = _num((ltps or {}).get(t))
            px = f"₹{fmt_n(ltp)}" + (f" ({ltp_at})" if ltp_at else "") if ltp is not None else "price n/a"
            block = [px if len(tickers) == 1 else f"{t} {px}", level_text((levels or {}).get(t), ltp), held_by_text(t, holders)]
            parts.append(" · ".join(block))
    else:
        parts += ["price n/a (no ticker named)", "not on list", "HELD BY n/a"]
    parts.append("research only")
    return " · ".join(parts)


def format_ops_line(flag: dict, now: datetime) -> str:
    """chat · sender · quote · age (a silence flag: chat · silent Nh · last message at)."""
    chat = str(flag.get("chat_name") or flag.get("chat_jid") or "?")
    if flag.get("kind") == "silence":
        d = flag.get("detail") or {}
        last = as_dt(flag.get("msg_at"))
        last_s = f"{last.astimezone(IST):%H:%M}" if last else "never"
        return (f"🔕 {chat} · silent {fmt_n(_num(d.get('silent_hours')))}h in 08:00–20:00 IST"
                f" · last message {last_s} ({age_text(flag.get('msg_at'), now)})")
    sender = str(flag.get("sender") or "?")
    words = (flag.get("detail") or {}).get("words") or []
    tag = f" [{', '.join(words[:3])}]" if words else ""
    return f"🔴 {chat} · {sender} · \"{quote(flag.get('text'))}\"{tag} · {age_text(flag.get('msg_at'), now)}"


def format_batch(lines: list[str], total: int | None = None) -> str:
    total = len(lines) if total is None else total
    shown = lines[:BATCH_MAX_LINES]
    head = f"wa-sweep · {total} more flag{'s' if total != 1 else ''} (chats pushed in the last {PUSH_GAP_MIN} min):"
    tail = [f"+{total - len(shown)} more on the Morning page"] if total > len(shown) else []
    return "\n".join([head] + shown + tail)


def heartbeat_line(mode: str, chats: int, new_msgs: int, flags: int, pushed: int) -> str:
    return f"wa-sweep {mode}: {chats} chats swept, {new_msgs} new msgs, {flags} flags ({pushed} pushed)"


def announcement_text(ops_chats: list[dict], mausaji_found: bool, seen_groups: list[str],
                      watch: list[str] | None = None, regex: re.Pattern | None = None, mausaji: str | None = None) -> str:
    """The first ops run tells Aman which chats are being watched, so he can correct the set."""
    watch = watch_chats() if watch is None else watch
    rx = groups_regex() if regex is None else regex
    m = mausaji_chat() if mausaji is None else mausaji
    names = sorted({str(c.get("chat_name") or c.get("name") or "?") for c in ops_chats}, key=str.lower)
    line = f"wa-sweep · watching {len(names)} ops chat{'s' if len(names) != 1 else ''}"
    if names:
        line += ": " + ", ".join(names)
    else:
        seen = sorted({s for s in seen_groups if s}, key=str.lower)
        line += " — none match yet"
        line += (f"; group chats seen: {', '.join(seen[:10])}" + (f" +{len(seen) - 10}" if len(seen) > 10 else "")
                 if seen else "; no group chats received from the bridges yet")
    line += f" · Mausaji chat \"{m}\": {'found' if mausaji_found else 'not seen yet'}"
    others = [w for w in watch if w.lower() != m.lower()]
    line += f" · list: {'; '.join(others) if others else '(none)'} · regex: /{rx.pattern}/i · to change: WA_SWEEP_CHATS / WA_SWEEP_GROUPS in .env"
    return line


def daily_summary_text(day: date, totals: dict, ops_chats: list[dict], mausaji_found: bool,
                       mausaji: str | None = None) -> str:
    m = mausaji_chat() if mausaji is None else mausaji
    by = totals.get("flags_by_kind") or {}
    kinds = [f"{by.get(k, 0)} {k}{'s' if by.get(k, 0) != 1 and k != 'silence' else ''}" for k in FLAG_KINDS if by.get(k)]
    names = sorted({str(c.get("chat_name") or "?") for c in ops_chats}, key=str.lower)
    return (f"wa-sweep · {day:%a %d %b} · {totals.get('runs', 0)} runs · {totals.get('new_msgs', 0)} new msgs"
            f" · {totals.get('flags', 0)} flags" + (f" ({', '.join(kinds)})" if kinds else "")
            + f" · {totals.get('pushed', 0)} pushed · {totals.get('open', 0)} open"
            + f" · watching {len(names)} ops chat{'s' if len(names) != 1 else ''}"
            + (": " + ", ".join(names) if names else " (none match)")
            + f" · Mausaji chat \"{m}\": {'found' if mausaji_found else 'not seen yet'}"
            + " · to change: WA_SWEEP_CHATS / WA_SWEEP_GROUPS in .env")


def silent_chats(chats: list[dict], now: datetime, hours: float | None = None) -> list[dict]:
    """Pure half of the silence check: chats whose last message is more than `hours` of business time ago,
    skipping the ones whose silence episode (same last-message time) was already flagged."""
    hours = idle_hours() if hours is None else hours
    out = []
    for c in chats:
        last = as_dt(c.get("last_at"))
        if last is None:
            continue
        silent = business_hours_between(last, now)
        if silent >= hours and (c.get("silence_since") or "") != last.isoformat():
            out.append({**c, "silent_hours": silent, "last_at": last.isoformat()})
    return out


def _cached_nse_symbols() -> set[str]:
    """Symbols from share-master's cached EQUITY_L.csv (7-day cache in its data dir). Never downloads."""
    try:
        import mdo_share_master as sm
        path = os.path.join(sm.data_dir(), sm.NSE_CACHE_FILE)
        with open(path, encoding="utf-8", errors="replace") as f:
            parsed = sm.parse_nse_equity_list(f.read())
        return set((parsed.get("by_name") or {}).values())
    except Exception:
        return set()


# ═════════════════════════════════════════════════════════════════════════════
# Endpoints + the run itself
# ═════════════════════════════════════════════════════════════════════════════
def register(app, vdb: Callable[[], Awaitable[Any]], send_cos: Callable[[str], dict],
             levels: dict | None = None) -> dict:
    """Mount /api/wa/sweep/*. `send_cos` is the same function POST /api/cos/send wraps; `levels` is
    mdo_levels.register()'s dict (levels_list + holders)."""
    hooks: dict[str, Any] = {"nse_symbols": _cached_nse_symbols, "fetch_ltp": lv.fetch_ltp}

    async def ensure_schema(db=None):
        db = db if db is not None else await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    def _utc(d: datetime) -> str:
        return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def _now(v: Any = None) -> datetime:
        d = as_dt(v) if v else None
        return d.astimezone(IST) if d else datetime.now(IST)

    def _flag(r) -> dict:
        d = dict(r)
        try:
            d["detail"] = json.loads(d.pop("detail_json", None) or "{}")
        except ValueError:
            d["detail"] = {}
        return d

    # ── chats ──
    async def matched_chats() -> tuple[list[dict], list[str], bool]:
        """(watched chats with their state, every group name seen, Mausaji chat found?). Upserts wa_sweep_state."""
        db = await vdb()
        m, watch, rx = mausaji_chat(), watch_chats(), groups_regex()
        rows = [dict(r) for r in await db.execute_fetchall(
            "SELECT jid, account, name, kind, classification, first_seen, last_seen, msg_count FROM wa_chats "
            "WHERE classification != 'personal' AND jid != '' ORDER BY name")]
        seen_groups = [r["name"] for r in rows if (r.get("kind") or "group") == "group" and r.get("name")]
        out, mausaji_found = [], False
        for r in rows:
            mode = chat_mode(r.get("name"), r.get("kind"), mausaji=m, watch=watch, regex=rx)
            if mode is None:
                continue
            mausaji_found = mausaji_found or mode == "mausaji"
            await db.execute(
                "INSERT INTO wa_sweep_state (chat_jid, chat_name, account, kind, mode) VALUES (?,?,?,?,?) "
                "ON CONFLICT(chat_jid) DO UPDATE SET chat_name=excluded.chat_name, account=excluded.account, "
                "kind=excluded.kind, mode=excluded.mode, updated_at=datetime('now')",
                (r["jid"], r.get("name") or "", r.get("account") or "", r.get("kind") or "group", mode))
            st = dict((await db.execute_fetchall("SELECT * FROM wa_sweep_state WHERE chat_jid=?", (r["jid"],)))[0])
            out.append({**st, "classification": r.get("classification"), "msg_count": r.get("msg_count"),
                        "first_seen": r.get("first_seen"), "last_seen": r.get("last_seen")})
        await db.commit()
        return out, seen_groups, mausaji_found

    async def last_message_at(jid: str) -> str | None:
        db = await vdb()
        rows = await db.execute_fetchall(
            "SELECT timestamp, created_at FROM whatsapp_messages WHERE jid=? ORDER BY id DESC LIMIT 1", (jid,))
        if not rows:
            return None
        r = dict(rows[0])
        d = as_dt(r.get("timestamp")) or as_dt(r.get("created_at"))
        return d.isoformat() if d else None

    async def chats_view() -> dict:
        chats, seen, found = await matched_chats()
        out = []
        for c in chats:
            out.append({"jid": c["chat_jid"], "name": c["chat_name"], "account": c["account"], "kind": c["kind"],
                        "mode": c["mode"], "priority": c["priority"], "watermark": c["last_msg_id"],
                        "last_push_at": c["last_push_at"], "last_message_at": await last_message_at(c["chat_jid"]),
                        "msg_count": c.get("msg_count") or 0})
        out.sort(key=lambda d: (d["mode"] != "mausaji", str(d["last_message_at"] or ""), d["name"]), reverse=False)
        return {"chats": out, "count": len(out), "mausaji_chat": mausaji_chat(), "mausaji_found": found,
                "watch_chats": watch_chats(), "groups_regex": groups_regex().pattern,
                "idle_hours": idle_hours(), "groups_seen": sorted(set(seen), key=str.lower)}

    async def set_priority(jid: str, priority: str) -> dict:
        p = str(priority or "").strip().lower()
        if p not in PRIORITIES:
            raise HTTPException(400, f"priority must be one of {', '.join(PRIORITIES)}")
        db = await vdb()
        cur = await db.execute("UPDATE wa_sweep_state SET priority=?, updated_at=datetime('now') WHERE chat_jid=?", (p, jid))
        await db.commit()
        if not cur.rowcount:
            raise HTTPException(404, f"{jid} is not a watched chat")
        return {"ok": True, "jid": jid, "priority": p}

    # ── messages + flags ──
    async def new_messages(chat: dict, now: datetime, skip_mine: bool) -> tuple[list[dict], int]:
        """Messages after the chat's watermark (oldest first) and the new watermark. A chat swept for the first
        time is judged on its last BACKFILL_HOURS only; the watermark still jumps to its newest message."""
        db = await vdb()
        since = int(chat.get("last_msg_id") or 0)
        q = ("SELECT id, group_name, sender, text, timestamp, from_me, created_at FROM whatsapp_messages "
             "WHERE jid=? AND id>? ORDER BY id DESC LIMIT 500")
        rows = [dict(r) for r in await db.execute_fetchall(q, (chat["chat_jid"], since))]
        rows.reverse()
        top = await db.execute_fetchall("SELECT MAX(id) AS m FROM whatsapp_messages WHERE jid=?", (chat["chat_jid"],))
        watermark = int(dict(top[0])["m"] or since) if top else since
        if since == 0:
            cutoff = now.astimezone(timezone.utc) - timedelta(hours=BACKFILL_HOURS)
            rows = [r for r in rows if (as_dt(r.get("timestamp")) or as_dt(r.get("created_at")) or cutoff) >= cutoff]
        if skip_mine:
            rows = [r for r in rows if not int(r.get("from_me") or 0)]
        return [r for r in rows if str(r.get("text") or "").strip() and r.get("text") != "[media]"], watermark

    async def set_watermark(jid: str, watermark: int) -> None:
        db = await vdb()
        await db.execute("UPDATE wa_sweep_state SET last_msg_id=MAX(last_msg_id, ?), updated_at=datetime('now') WHERE chat_jid=?",
                         (int(watermark), jid))
        await db.commit()

    async def add_flag(chat: dict, kind: str, now: datetime, message: dict | None = None, ticker: str = "",
                       detail: dict | None = None, msg_at: str = "") -> dict | None:
        """INSERT the flag unless the same message+kind is already flagged, or an identical line (same chat,
        sender, text) was flagged in the last day — the two phones store the same group message twice."""
        db = await vdb()
        text = quote((message or {}).get("text") or "")
        sender = str((message or {}).get("sender") or "")
        mid = int(message["id"]) if message and message.get("id") is not None else None
        if message:
            dup = await db.execute_fetchall(
                "SELECT id FROM wa_sweep_flags WHERE chat_jid=? AND kind=? AND sender=? AND text=? "
                "AND created_at >= datetime('now','-1 day') LIMIT 1", (chat["chat_jid"], kind, sender, text))
            if dup:
                return None
            msg_at = msg_at or ((as_dt(message.get("timestamp")) or as_dt(message.get("created_at")) or now).isoformat())
        cur = await db.execute(
            "INSERT OR IGNORE INTO wa_sweep_flags (chat_jid, chat_name, account, message_id, sender, kind, ticker, text, "
            "detail_json, msg_at, day) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (chat["chat_jid"], chat.get("chat_name") or "", chat.get("account") or "", mid, sender, kind, ticker, text,
             json.dumps(detail or {})[:2000], msg_at, now.astimezone(IST).date().isoformat()))
        await db.commit()
        if not cur.rowcount:
            return None
        rows = await db.execute_fetchall("SELECT * FROM wa_sweep_flags WHERE id=?", (cur.lastrowid,))
        return _flag(rows[0])

    async def mark_pushed(flag_ids: list[int], chat_jids: list[str], now: datetime) -> None:
        db = await vdb()
        stamp = _utc(now)
        for fid in flag_ids:
            await db.execute("UPDATE wa_sweep_flags SET pushed_at=? WHERE id=?", (stamp, int(fid)))
        for jid in set(chat_jids):
            await db.execute("UPDATE wa_sweep_state SET last_push_at=?, updated_at=datetime('now') WHERE chat_jid=?", (stamp, jid))
        await db.commit()

    def _push(text: str) -> bool:
        try:
            res = send_cos(text)
            return bool(isinstance(res, dict) and res.get("sent"))
        except Exception:
            return False

    async def record_run(mode: str, now: datetime, chats: int, new_msgs: int, flags: int, pushed: int, note: str = "") -> None:
        db = await vdb()
        await db.execute("INSERT INTO wa_sweep_runs (mode, ran_at, day, chats, new_msgs, flags, pushed, note) VALUES (?,?,?,?,?,?,?,?)",
                         (mode, _utc(now), now.astimezone(IST).date().isoformat(), chats, new_msgs, flags, pushed, note[:300]))
        await db.commit()

    async def runs_count(mode: str) -> int:
        db = await vdb()
        return int(dict((await db.execute_fetchall("SELECT COUNT(*) AS n FROM wa_sweep_runs WHERE mode=?", (mode,)))[0])["n"])

    # ── the Mausaji side ──
    async def mausaji_context(tickers: list[str]) -> tuple[dict, dict, dict | None, str]:
        """(ltps, level rows by ticker, holders map or None when no holdings table, ltp time)."""
        ltps: dict[str, float | None] = {}
        if tickers:
            try:
                ltps = await asyncio.to_thread(hooks["fetch_ltp"], tickers)
            except Exception:
                ltps = {t: None for t in tickers}
        lvl: dict[str, dict] = {}
        if levels:
            try:
                lvl = {norm_ticker(r["ticker"]): r for r in (await levels["levels_list"]()).get("levels") or [] if r.get("active", True)}
            except Exception:
                lvl = {}
        db = await vdb()
        have_table = bool(await db.execute_fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='share_master_holdings'"))
        holders = None
        if have_table and levels and callable(levels.get("holders")):
            try:
                holders = await levels["holders"]() or {}
            except Exception:
                holders = {}
        return ltps, lvl, holders, f"{datetime.now(IST):%H:%M} IST"

    async def run_mausaji(chats: list[dict], now: datetime) -> dict:
        db = await vdb()
        lrows = [dict(r) for r in await db.execute_fetchall("SELECT ticker, note FROM share_levels WHERE active=1")] \
            if await db.execute_fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name='share_levels'") else []
        try:
            nse = hooks["nse_symbols"]() or set()
        except Exception:
            nse = set()
        index = ticker_index(lrows, nse)
        new_msgs, flags = 0, []
        for c in chats:
            msgs, watermark = await new_messages(c, now, skip_mine=True)
            new_msgs += len(msgs)
            for m in msgs:
                hit = analyse_mausaji(m.get("text"), index)
                if not hit:
                    continue
                f = await add_flag(c, hit["kind"], now, m, ticker=",".join(hit["tickers"]),
                                   detail={"tickers": hit["tickers"], "call": hit["call"]})
                if f:
                    f["tickers"], f["call"] = hit["tickers"], hit["call"]
                    flags.append(f)
            await set_watermark(c["chat_jid"], watermark)
        pushes, failed = [], 0
        if flags:
            tickers = sorted({t for f in flags for t in f["tickers"]})
            ltps, lvl, holders, ltp_at = await mausaji_context(tickers)
            for f in flags:
                text = format_mausaji_line(f, ltps, lvl, holders, ltp_at)
                if _push(text):
                    await mark_pushed([f["id"]], [f["chat_jid"]], now)
                    pushes.append(text)
                else:
                    failed += 1
        return {"new_msgs": new_msgs, "flags": flags, "pushes": pushes, "push_failed": failed}

    # ── the ops side ──
    async def run_ops(chats: list[dict], now: datetime) -> dict:
        new_msgs, flags, silence_flags = 0, [], []
        for c in chats:
            msgs, watermark = await new_messages(c, now, skip_mine=True)
            new_msgs += len(msgs)
            for m in msgs:
                words = find_bottleneck(m.get("text"))
                if not words:
                    continue
                f = await add_flag(c, "bottleneck", now, m, detail={"words": words})
                if f:
                    flags.append(f)
            await set_watermark(c["chat_jid"], watermark)
            last = await last_message_at(c["chat_jid"]) or c.get("first_seen") or c.get("first_swept_at")
            for s in silent_chats([{**c, "last_at": last}], now):
                f = await add_flag(c, "silence", now, None, detail={"silent_hours": s["silent_hours"]}, msg_at=s["last_at"])
                if f:
                    silence_flags.append(f)
                    db = await vdb()
                    await db.execute("UPDATE wa_sweep_state SET silence_since=?, updated_at=datetime('now') WHERE chat_jid=?",
                                     (s["last_at"], c["chat_jid"]))
                    await db.commit()
        # push: silence at once; bottlenecks at once when the chat had no push in the last 30 min, else one batch
        gap = timedelta(minutes=PUSH_GAP_MIN)
        last_push = {c["chat_jid"]: as_dt(c.get("last_push_at")) for c in chats}
        by_chat: dict[str, list[dict]] = {}
        for f in flags:
            by_chat.setdefault(f["chat_jid"], []).append(f)
        pushes, batched, failed = [], [], 0
        for f in silence_flags:
            text = format_ops_line(f, now)
            if _push(text):
                await mark_pushed([f["id"]], [f["chat_jid"]], now); pushes.append(text)
            else:
                failed += 1
        for jid, fl in by_chat.items():
            lp = last_push.get(jid)
            if lp is None or now.astimezone(timezone.utc) - lp >= gap:
                lines = [format_ops_line(f, now) for f in fl]
                text = lines[0] if len(lines) == 1 else "\n".join(lines[:BATCH_MAX_LINES] + (
                    [f"+{len(lines) - BATCH_MAX_LINES} more on the Morning page"] if len(lines) > BATCH_MAX_LINES else []))
                if _push(text):
                    await mark_pushed([f["id"] for f in fl], [jid], now); pushes.append(text)
                else:
                    failed += 1
            else:
                batched += fl
        if batched:
            text = format_batch([format_ops_line(f, now) for f in batched])
            if _push(text):
                await mark_pushed([f["id"] for f in batched], [f["chat_jid"] for f in batched], now); pushes.append(text)
            else:
                failed += 1
        return {"new_msgs": new_msgs, "flags": flags + silence_flags, "pushes": pushes, "push_failed": failed,
                "silence": len(silence_flags)}

    # ── the day ──
    async def day_totals(day: date) -> dict:
        db = await vdb()
        d = day.isoformat()
        r = dict((await db.execute_fetchall(
            "SELECT COUNT(*) AS runs, COALESCE(SUM(new_msgs),0) AS new_msgs, COALESCE(SUM(flags),0) AS flags, "
            "COALESCE(SUM(pushed),0) AS pushed FROM wa_sweep_runs WHERE day=? AND mode != 'daily'", (d,)))[0])
        by = {k: int(v) for k, v in await db.execute_fetchall(
            "SELECT kind, COUNT(*) FROM wa_sweep_flags WHERE day=? GROUP BY kind", (d,))}
        open_n = int(dict((await db.execute_fetchall("SELECT COUNT(*) AS n FROM wa_sweep_flags WHERE status='open'"))[0])["n"])
        return {"day": d, "runs": int(r["runs"]), "new_msgs": int(r["new_msgs"]), "flags": int(r["flags"]),
                "pushed": int(r["pushed"]), "flags_by_kind": by, "open": open_n}

    async def run(mode: str, now_v: Any = None) -> dict:
        mode = str(mode or "").strip().lower()
        if mode not in MODES:
            raise HTTPException(400, f"mode must be one of {', '.join(MODES)}")
        now = _now(now_v)
        chats, seen_groups, mausaji_found = await matched_chats()
        ops_chats = [c for c in chats if c["mode"] == "ops"]
        mau_chats = [c for c in chats if c["mode"] == "mausaji"]
        out: dict[str, Any] = {"mode": mode, "as_of": now.isoformat(), "chats": 0, "new_msgs": 0, "flags": 0, "pushed": 0,
                               "push_failed": 0, "flag_rows": [], "pushes": [], "note": ""}
        if mode == "daily":
            totals = await day_totals(now.date())
            text = daily_summary_text(now.date(), totals, ops_chats, mausaji_found)
            sent = _push(text)
            out.update({"chats": len(chats), "totals": totals, "pushes": [text] if sent else [], "pushed": 1 if sent else 0,
                        "push_failed": 0 if sent else 1, "text": text})
            await record_run(mode, now, len(chats), 0, 0, out["pushed"], "daily summary" + ("" if sent else " NOT delivered"))
            out["line"] = heartbeat_line(mode, len(chats), 0, 0, out["pushed"])
            return out
        swept = mau_chats if mode == "mausaji" else ops_chats
        if mode == "ops" and await runs_count("ops") == 0:
            text = announcement_text(ops_chats, mausaji_found, seen_groups)
            if _push(text):
                out["pushes"].append(text); out["pushed"] += 1
            else:
                out["push_failed"] += 1
            out["announcement"] = text
        res = await (run_mausaji(swept, now) if mode == "mausaji" else run_ops(swept, now))
        out.update({"chats": len(swept), "new_msgs": res["new_msgs"], "flags": len(res["flags"]),
                    "pushed": out["pushed"] + len(res["pushes"]), "push_failed": out["push_failed"] + res["push_failed"],
                    "flag_rows": res["flags"], "pushes": out["pushes"] + res["pushes"], "silence": res.get("silence", 0)})
        if not swept:
            out["note"] = (f"no chat matches \"{mausaji_chat()}\" yet" if mode == "mausaji"
                           else "no ops chat matches WA_SWEEP_CHATS / WA_SWEEP_GROUPS yet")
        await record_run(mode, now, out["chats"], out["new_msgs"], out["flags"], out["pushed"], out["note"])
        out["line"] = heartbeat_line(mode, out["chats"], out["new_msgs"], out["flags"], out["pushed"])
        return out

    # ── flags ──
    async def flags_list(status: str = "open", limit: int = 200, day: str = "", kind: str = "") -> dict:
        db = await vdb()
        q, p = "SELECT * FROM wa_sweep_flags WHERE 1=1", []
        if status:
            q += " AND status=?"; p.append(status)
        if day:
            q += " AND day=?"; p.append(day)
        if kind:
            q += " AND kind=?"; p.append(kind)
        q += " ORDER BY id DESC LIMIT ?"; p.append(min(int(limit), 2000))
        rows = [_flag(r) for r in await db.execute_fetchall(q, p)]
        open_n = int(dict((await db.execute_fetchall("SELECT COUNT(*) AS n FROM wa_sweep_flags WHERE status='open'"))[0])["n"])
        return {"flags": rows, "count": len(rows), "open": open_n, "as_of": datetime.now(IST).isoformat()}

    async def flag_ack(flag_id: int) -> dict:
        db = await vdb()
        cur = await db.execute("UPDATE wa_sweep_flags SET status='ack', acked_at=datetime('now') WHERE id=? AND status='open'",
                               (int(flag_id),))
        await db.commit()
        if not cur.rowcount:
            exists = await db.execute_fetchall("SELECT status FROM wa_sweep_flags WHERE id=?", (int(flag_id),))
            if not exists:
                raise HTTPException(404, f"flag {flag_id} not found")
        return {"ok": True, "id": int(flag_id), "status": "ack"}

    @app.get("/api/wa/sweep/flags")
    async def wa_sweep_flags(status: str = "open", limit: int = 200, day: str = "", kind: str = ""):
        return await flags_list(status, limit, day, kind)

    @app.post("/api/wa/sweep/flags/{flag_id}/ack")
    async def wa_sweep_flag_ack(flag_id: int):
        return await flag_ack(flag_id)

    @app.get("/api/wa/sweep/chats")
    async def wa_sweep_chats():
        return await chats_view()

    @app.post("/api/wa/sweep/chats/{jid}/priority")
    async def wa_sweep_priority(jid: str, body: dict):
        return await set_priority(jid, str((body or {}).get("priority") or ""))

    @app.get("/api/wa/sweep/summary")
    async def wa_sweep_summary(day: str = ""):
        d = date.fromisoformat(day) if day else datetime.now(IST).date()
        return await day_totals(d)

    @app.post("/api/wa/sweep/run")
    async def wa_sweep_run(body: dict):
        body = body or {}
        return await run(str(body.get("mode") or "ops"), body.get("now"))

    def set_nse_symbols(fn: Callable[[], Any]) -> None:
        hooks["nse_symbols"] = fn

    def set_fetch_ltp(fn: Callable[[list[str]], dict]) -> None:
        hooks["fetch_ltp"] = fn

    return {"ensure_schema": ensure_schema, "run": run, "flags": flags_list, "ack": flag_ack, "chats": chats_view,
            "set_priority": set_priority, "day_totals": day_totals, "set_nse_symbols": set_nse_symbols,
            "set_fetch_ltp": set_fetch_ltp}
