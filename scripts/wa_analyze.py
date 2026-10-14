#!/usr/bin/env python3
"""Aggregate analysis of the WhatsApp groups captured by the MDO bridge.

Run where MDO_BASE_URL and MDO_AUTH_TOKEN are set (VPS or a routine):
    python3 scripts/wa_analyze.py > WA_ANALYSIS.md

Reads /api/whatsapp/groups, /messages, /extractions. Prints counts and signals only;
no message text is copied out. Stdlib only. A failure prints a finding and exits 1 (never silent).
"""
import json, os, re, sys, urllib.request, urllib.parse
from collections import Counter
from datetime import datetime, timezone

BASE = os.environ.get("MDO_BASE_URL", "").rstrip("/")
KEY = os.environ.get("MDO_AUTH_TOKEN", "")

# role -> keywords that suggest a need for that professional
ROLES = {
    "Civil QC engineer": r"\b(pour|pcc|rcc|cube|slab|shuttering|centering|footing|column|beam|bar|rebar|cement|steel|curing|plaster|brick|excavation|foundation|bridge|road|culvert)\b",
    "Accounts / finance controller": r"\b(payment|paid|invoice|bill|gst|tds|bank|cheque|neft|rtgs|ledger|advance|voucher|receipt|challan|ra bill|outstanding)\b",
    "Logistics / dispatch controller": r"\b(rake|dispatch|loader|weighbridge|w/?b|truck|mt|tonnes?|siding|placement|demurrage|wagon|rr)\b",
    "Equipment / maintenance engineer": r"\b(breakdown|repair|spare|machine|motor|belt|crusher|hydra|jcb|loader|service|hmr|diesel|alternator)\b",
    "Procurement / stores": r"\b(purchase|po|quotation|rate|stock|store|vendor|supplier|indent|material)\b",
    "Legal / compliance": r"\b(notice|court|hearing|roc|mca|licen[cs]e|consent|pollution|cte|cto|inspection|fir|penalty|renewal)\b",
    "HR / site admin": r"\b(salary|attendance|leave|labou?r|contractor|pf|esic|bocw|insurance|accident|safety)\b",
    "Hotel operations manager": r"\b(room|occupancy|guest|booking|checkout|check-in|housekeeping|dsr|night report|revpar)\b",
}


def get(path, **q):
    url = f"{BASE}{path}" + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={"X-MDO-Key": KEY} if KEY else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def parse_ts(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:26] if "." in s else s[:19], fmt).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    try:
        return datetime.fromtimestamp(float(s), tz=timezone.utc)
    except Exception:
        return None


def analyse(group, msgs, ext):
    n = len(msgs)
    texts = [m.get("text") or "" for m in msgs]
    media = sum(1 for t in texts if t.strip() == "[media]")
    senders = Counter((m.get("sender") or "?") for m in msgs)
    stamps = sorted(t for t in (parse_ts(str(m.get("timestamp", ""))) for m in msgs) if t)
    days = len({t.date() for t in stamps})
    gap = max(((b - a).total_seconds() / 86400 for a, b in zip(stamps, stamps[1:])), default=0)
    last = (datetime.now(timezone.utc) - stamps[-1]).total_seconds() / 86400 if stamps else None
    blob = "\n".join(texts).lower()
    scores = {r: len(re.findall(rx, blob)) for r, rx in ROLES.items()}
    docs = Counter(e.get("doc_type", "other") for e in ext)
    return dict(group=group, n=n, media=media, senders=senders, days=days, gap=gap, last=last, scores=scores, docs=docs)


def main():
    if not BASE:
        print("FINDING: MDO_BASE_URL not set. Nothing analysed.")
        return 1
    try:
        groups = get("/api/whatsapp/groups")["groups"]
    except Exception as e:
        print(f"FINDING: cannot reach {BASE}/api/whatsapp/groups: {e}")
        return 1
    rows = []
    for g in groups:
        name = g["group_name"]
        msgs = get("/api/whatsapp/messages", group=name, limit=2000)["messages"]
        ext = get("/api/whatsapp/extractions", group=name, limit=200)["extractions"]
        rows.append(analyse(name, msgs, ext))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"# WhatsApp group analysis {today} (aggregate only, no message text)\n")
    print(f"{len(rows)} groups. Window = last <=2000 messages per group.\n")
    print("| Group | Msgs | Media % | Active days | Longest silence (d) | Last msg (d ago) | Top senders | Photo types |")
    print("|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: -r["n"]):
        pct = f"{100 * r['media'] / r['n']:.0f}" if r["n"] else "0"
        top = ", ".join(f"{s[:14]}({c})" for s, c in r["senders"].most_common(3))
        docs = ", ".join(f"{d}:{c}" for d, c in r["docs"].most_common(3)) or "-"
        last = f"{r['last']:.1f}" if r["last"] is not None else "?"
        print(f"| {r['group'][:40]} | {r['n']} | {pct} | {r['days']} | {r['gap']:.1f} | {last} | {top} | {docs} |")
    print("\n## Where each virtual professional is indicated (keyword hits per group, higher = more traffic of that kind)\n")
    for role in ROLES:
        ranked = sorted(rows, key=lambda r: -r["scores"][role])[:3]
        hits = sum(r["scores"][role] for r in rows)
        line = "; ".join(f"{r['group'][:30]} ({r['scores'][role]})" for r in ranked if r["scores"][role])
        print(f"- **{role}**: {hits} hits. {line or 'no signal'}")
    silent = [r["group"] for r in rows if r["last"] is not None and r["last"] > 2]
    print(f"\nGROUPS SILENT >2 DAYS: {', '.join(silent) if silent else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
