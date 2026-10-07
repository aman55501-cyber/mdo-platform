"""Turn a caller's WhatsApp messages into tracked calls (wb.calls). Rule-based; nothing is guessed.

His calls follow a pattern, e.g.
    FOR 30-45 DAYS / *ADD : KSCL @ 780-782* / SL - 701 / Target 795 / 816 / 834 ...
    *ADD # TGVSL @ 120.00*
and he also states his own buys ("Added Adani power."), kept as kind='declared'.
Everything else (news links, chat, broker notes) is ignored and stays in the chat. One call per message: if a
message holds more than one, the first is kept and the run summary says how many were skipped.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .. import scrip
from ..config import optional
from ..db import DB

CALLER = "Bantu Mausaji"
JOB = "bantu_calls"

# The action word must be capitals, as he writes it, so prose like "can add me @ 5" never matches.
_CALL = re.compile(r"\b(ADD|BUY|SELL|TRIM|EXIT)\b\s*[:#\-]*\s*\*?\s*([A-Za-z0-9][A-Za-z0-9 &.\-]{1,40}?)\s*\*?\s*@\s*"
                   r"(\d+(?:\.\d+)?)(?:\s*(?:[-–]|to)\s*(\d+(?:\.\d+)?))?")
_SL = re.compile(r"\b(?:SL|S\.L\.|STOP[\s\-]*LOSS)\b\s*[:\-#]*\s*(\d+(?:\.\d+)?)", re.I)
_TARGET = re.compile(r"\btargets?\b", re.I)
_HORIZON = re.compile(r"\b(\d+\s*(?:[-–]|to)\s*\d+|\d+)\s*(day|week|month)s?\b", re.I)
_DECLARED = re.compile(r"^\s*\*?(Added|Bought|Sold|Exited)\s+(.{2,40}?)[.\s*]*$", re.I)
_FILLER = {"more", "again", "today", "also", "some", "little", "bit"}
_DECL_ACTION = {"added": "ADD", "bought": "ADD", "sold": "EXIT", "exited": "EXIT"}


@dataclass
class Parsed:
    action: str
    symbol_raw: str
    kind: str = "call"
    entry_low: float | None = None
    entry_high: float | None = None
    stop: float | None = None
    targets: list[float] = field(default_factory=list)
    horizon: str | None = None
    confidence: float = 0.9
    extra_calls: int = 0


def _targets(body: str) -> list[float]:
    m = _TARGET.search(body)
    if not m:
        return []
    out: list[float] = []
    lines = body[m.end():].splitlines()
    for i, line in enumerate(lines):
        text = line.strip().strip("*")
        if not text:
            continue
        if re.search(r"[A-Za-z]", text):          # first line with words ends the list
            break
        out += [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
        if len(out) >= 12:
            break
    return out[:12]


_TO = re.compile(r"\s*(?:to|–)\s*", re.I)


def _horizon_text(m) -> str:
    """'3 to 6' + 'month' -> '3-6 months'."""
    return f"{_TO.sub('-', m.group(1)).replace(' ', '')} {m.group(2).lower()}s"


def parse_message(body: str) -> Parsed | None:
    body = body or ""
    calls = list(_CALL.finditer(body))
    if calls:
        m = calls[0]
        low = float(m.group(3))
        high = float(m.group(4)) if m.group(4) else low
        sl = _SL.search(body)
        hz = _HORIZON.search(body)
        return Parsed(action=m.group(1), symbol_raw=m.group(2).strip(" *-"), entry_low=min(low, high), entry_high=max(low, high),
                      stop=float(sl.group(1)) if sl else None, targets=_targets(body),
                      horizon=_horizon_text(hz) if hz else None,
                      confidence=0.9, extra_calls=len(calls) - 1)
    if len(body) <= 80:
        d = _DECLARED.match(body.strip())
        if d:
            words = d.group(2).strip().split()
            while words and words[-1].lower().strip(".,;:!*") in _FILLER:
                words.pop()
            name = " ".join(words).strip(" .*")
            if len(name) >= 2:
                return Parsed(action=_DECL_ACTION[d.group(1).lower()], symbol_raw=name, kind="declared", confidence=0.6)
    return None


def resolve(symbol_raw: str, known: set[str]) -> str | None:
    n = scrip.norm(symbol_raw)
    return n if n in known else None


def known_symbols(db, master: dict) -> set[str]:
    """Tickers we can vouch for: what you hold, watch, or were pitched, plus the exchange's own list."""
    rows = db.query("select symbol from wb.holdings_raw union select wb.norm_symbol(symbol) from public.watchlist "
                    "union select wb.norm_symbol(symbol) from public.desk_ideas")
    return {r["symbol"] for r in rows if r["symbol"]} | set(master)


_INSERT = ("insert into wb.calls (source_msg_id, wa_account, caller, called_at, kind, action, symbol_raw, symbol, entry_low, "
           "entry_high, stop, targets, horizon, extractor, confidence, needs_review) "
           "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::numeric[],%s,'rule',%s,%s) on conflict (source_msg_id) do nothing")

_BOOKED = ("update wb.calls c set status='booked', reviewed_at=now(), outcome=jsonb_build_object('hit','first_target',"
           "'price',pn.price,'at',pn.price_time) from wb.price_now pn where pn.symbol=c.symbol and c.status in ('open','watching') "
           "and c.action in ('ADD','BUY') and cardinality(c.targets)>0 and pn.price_source<>'holdings-pull' "
           "and pn.price_time > now()-interval '30 minutes' and pn.price >= (select min(t) from unnest(c.targets) t)")
_STOPPED = ("update wb.calls c set status='stopped', reviewed_at=now(), outcome=jsonb_build_object('hit','stop',"
            "'price',pn.price,'at',pn.price_time) from wb.price_now pn where pn.symbol=c.symbol and c.status in ('open','watching') "
            "and c.action in ('ADD','BUY') and c.stop is not null and pn.price_source<>'holdings-pull' "
            "and pn.price_time > now()-interval '30 minutes' and pn.price <= c.stop")


def run(db: DB, *, master: dict | None = None, note: str | None = None, lookback_days: int = 45) -> dict:
    """Parse new messages, track outcomes on LIVE quotes only, and write the heartbeat row."""
    try:
        if master is None:
            master, note = scrip.load_or_empty()
        known = known_symbols(db, master)
        msgs = db.query("select id, account, sent_at, body from public.wa_messages where chat_name = %s and not from_me "
                        "and sent_at > now() - make_interval(days => %s) and id not in (select source_msg_id from wb.calls) "
                        "order by sent_at", (optional("CAPITAL_CALLER_CHAT", CALLER), lookback_days))
        new = skipped_multi = unresolved = 0
        for m in msgs:
            p = parse_message(m["body"])
            if not p:
                continue
            sym = resolve(p.symbol_raw, known)
            review = sym is None or p.confidence < 0.8 or (p.kind == "call" and p.entry_low is None)
            db.execute(_INSERT, (m["id"], m["account"], CALLER, m["sent_at"], p.kind, p.action, p.symbol_raw, sym, p.entry_low,
                                 p.entry_high, p.stop, p.targets, p.horizon, p.confidence, review))
            new += 1
            unresolved += sym is None
            skipped_multi += p.extra_calls
        rematched = 0
        for r in db.query("select id, symbol_raw, confidence, entry_low from wb.calls where symbol is null"):
            sym = resolve(r["symbol_raw"], known)
            if sym:
                review = float(r["confidence"] or 0) < 0.8 or r["entry_low"] is None
                db.execute("update wb.calls set symbol = %s, needs_review = %s where id = %s", (sym, review, r["id"]))
                rematched += 1
        booked = db.execute(_BOOKED)
        stopped = db.execute(_STOPPED)
        summary = (f"{new} new call(s) from {len(msgs)} unparsed message(s); {unresolved} name(s) not matched to a ticker; "
                   f"{rematched} earlier name(s) now matched; {booked} booked, {stopped} stopped on live quotes"
                   + (f"; {skipped_multi} extra call(s) in multi-call messages skipped" if skipped_multi else "")
                   + (f"; {note}" if note else ""))
        db.execute("insert into wb.run_log (job, ok, summary) values (%s, true, %s)", (JOB, summary))
        return {"new": new, "scanned": len(msgs), "unresolved": unresolved, "booked": booked, "stopped": stopped, "summary": summary}
    except Exception as exc:
        try:
            db.execute("insert into wb.run_log (job, ok, summary) values (%s, false, %s)", (JOB, f"FAILED: {type(exc).__name__}"))
        finally:
            raise


if __name__ == "__main__":  # pragma: no cover
    print(run(DB(readonly=False))["summary"], file=sys.stderr)
