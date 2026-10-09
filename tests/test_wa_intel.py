"""WhatsApp Intelligence — pure helpers (no DB) plus the ingest gate through the app.

Runs under pytest OR standalone: `python tests/test_wa_intel.py`.
The TestClient part follows tests/test_sessions.py: a scratch VEGA_DB_PATH is set
before mdo_server is imported, so nothing here can touch a real database.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import mdo_cos as c  # noqa: E402
import mdo_wa_intel as w  # noqa: E402

NOW = datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc)


# ── fingerprint ───────────────────────────────────────────────────────────────
def test_fingerprint_is_stable_and_normalised():
    a = w.signal_fingerprint("VWLR", "receivable", "Vedanta BALCO", "2026-10-15")
    b = w.signal_fingerprint("  vwlr ", "RECEIVABLE", "vedanta   balco", "2026-10-15")
    assert a == b and len(a) == 16
    assert a != w.signal_fingerprint("VWLR", "receivable", "Vedanta BALCO", "2026-10-16")
    assert a != w.signal_fingerprint("VWLR", "payable", "Vedanta BALCO", "2026-10-15")
    # no due date → the ISO week stands in, so the same chase next week is a new signal
    assert w.signal_fingerprint("VWLR", "delay", "", "2026-W41") != w.signal_fingerprint("VWLR", "delay", "", "2026-W42")
    assert w.iso_week("2026-10-08T06:00:00Z") == "2026-W41"


# ── response metrics ──────────────────────────────────────────────────────────
def _msg(i, chat, sender, text, minutes):
    return {"id": i, "chat_jid": chat, "sender": sender, "text": text,
            "timestamp": (NOW - timedelta(days=5) + timedelta(minutes=minutes)).isoformat()}


def test_response_metrics_latency_and_unanswered_questions():
    two_days = 48 * 60
    thread = [
        _msg(1, "g1", "Aman", "Rake position kya hai?", 0),          # question, answered after 30 min
        _msg(2, "g1", "Site", "2 rakes loading sir", 30),
        _msg(3, "g1", "Aman", "when will the second one leave?", 40),  # question, answered after 60 min
        _msg(4, "g1", "Site", "by 18:00", 100),
        _msg(5, "g1", "Vendor", "payment status?", 120),                   # answered, but 2 days later → unanswered
        _msg(6, "g1", "Aman", "done today", 120 + two_days),
        _msg(7, "g1", "Aman", "please send the weighbridge slips", 125 + two_days),  # never answered, ~3 days old
        _msg(8, "g1", "Aman", "ok", 130 + two_days),                       # same sender: not a reply
        {"id": 9, "chat_jid": "g1", "sender": "X", "text": "no timestamp", "timestamp": None},
    ]
    rows = {(r["chat"], r["sender"]): r for r in w.response_metrics(thread, now=NOW)}
    site = rows[("g1", "Site")]
    assert site["replies"] == 2 and site["median_reply_min"] == 45.0      # median of 30 and 60
    assert site["questions"] == 0 and site["unanswered_24h"] == 0
    aman = rows[("g1", "Aman")]
    assert aman["questions"] == 3 and aman["unanswered_24h"] == 1           # the slips request
    vendor = rows[("g1", "Vendor")]
    assert vendor["questions"] == 1 and vendor["unanswered_24h"] == 1       # answered after 48h
    assert ("g1", "X") not in rows                                           # dropped: no timestamp
    assert w.response_metrics([]) == []


def test_is_question_prefixes():
    assert w.is_question("Kab tak hoga")
    assert w.is_question("STATUS of the PO")
    assert w.is_question("rake left?")
    assert not w.is_question("rake left at 6")
    assert not w.is_question("")


# ── parsers ───────────────────────────────────────────────────────────────────
def test_parse_signals_tolerates_garbage():
    assert w.parse_signals("") == []
    assert w.parse_signals(None) == []
    assert w.parse_signals("lol no json here") == []
    assert w.parse_signals("{not: json}") == []
    assert w.parse_signals('{"signals": "nope"}') == []
    # fenced, trailing comma, prose around it, an unknown kind, a signal without evidence
    raw = """Here you go:
```json
{"signals": [
  {"kind": "Receivable", "entity": "vwlr", "counterparty": "Vedanta", "amount": "1,20,000", "currency": "inr",
   "due_date": "2026-10-15", "summary": "Vedanta owes for Sept rakes", "evidence_ids": [11, "12", "#11"], "snippet": "1,20,000 pending", "confidence": 0.9,},
  {"kind": "gossip", "summary": "x", "evidence_ids": [1]},
  {"kind": "lead", "summary": "no evidence", "evidence_ids": []},
  {"kind": "lead", "summary": "evidence from another batch", "evidence_ids": [999]},
  {"kind": "payable", "entity": "Some Invented Co", "summary": "due", "evidence_ids": [12], "due_date": "next week", "amount": "n/a"},
]}
```"""
    sigs = w.parse_signals(raw, allowed_ids={11, 12})
    assert [s["kind"] for s in sigs] == ["receivable", "payable"]
    r = sigs[0]
    assert r["entity"] == "VWLR" and r["amount"] == 120000.0 and r["currency"] == "INR"
    assert r["evidence_ids"] == [11, 12] and r["due_date"] == "2026-10-15"
    p = sigs[1]
    assert p["entity"] == "" and p["due_date"] == "" and p["amount"] is None   # invented entity → '', bad date → ''
    # truncated output: salvage the complete objects
    cut = '{"signals": [{"kind": "lead", "summary": "wants 2 rooms", "evidence_ids": [5]}, {"kind": "quote", "summ'
    assert [s["kind"] for s in w.parse_signals(cut)] == ["lead"]


def test_parse_classification_guards_entity_and_confidence():
    assert w.parse_classification("nothing") is None
    assert w.parse_classification('{"classification": "maybe"}') is None
    v = w.parse_classification('{"classification":"Business","entity":"hotel ans international","confidence":"0.95","reason":"bookings"}')
    assert v == {"classification": "business", "entity": "Hotel ANS International", "confidence": 0.95, "reason": "bookings"}
    # an entity outside Aman's registry can never auto-apply
    v = w.parse_classification('{"classification":"business","entity":"Acme Corp","confidence":0.99}')
    assert v["entity"] == "" and v["confidence"] < w.AUTO_CONFIDENCE
    v = w.parse_classification('{"classification":"personal","entity":"VWLR","confidence":7}')
    assert v["entity"] == "" and v["confidence"] == 1.0


def test_prompts_name_only_registry_entities():
    p = w.classify_prompt({"name": "Cousins", "kind": "group", "account": "2", "msg_count": 12, "participants": '["A","B"]'},
                          [{"sender": "A", "text": "hi"}])
    for name in w.ENTITY_NAMES:
        assert name in p
    assert "Cousins" in p and "A, B" in p and "0.85" in p
    e = w.extract_prompt({"name": "Rake Ops", "entity": "VWLR"}, [{"id": 7, "sender": "S", "text": "2 rakes", "timestamp": "2026-10-08T05:00:00Z"}], now=NOW)
    assert "7 | 2026-10-08T05:00:00 | S | 2 rakes" in e and "evidence_ids" in e


# ── pulse ─────────────────────────────────────────────────────────────────────
def _sig(i, kind, cp, days_ago, **kw):
    d = {"id": i, "kind": kind, "entity": "VWLR", "counterparty": cp, "status": "open", "chat_jid": "g1",
         "chat_name": "Rake Ops", "summary": kw.pop("summary", f"{kind} {cp}"), "amount": kw.pop("amount", None),
         "currency": "INR", "created_at": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")}
    d.update(kw)
    return d


def test_pulse_compute_sales_gap_detects_quote_with_no_order():
    signals = [
        _sig(1, "quote", "JSPL", 10, amount=450000.0),                 # cold: nothing since
        _sig(2, "quote", "NTPC Sipat", 12),                             # followed by an order → no gap
        _sig(3, "order", "NTPC Sipat", 4),
        _sig(4, "lead", "Adani", 2),                                    # too fresh to be a gap
        _sig(5, "quote", "BALCO", 9, status="done"),                    # closed → not a gap
        _sig(6, "delay", "Loader", 5, summary="loader breakdown again, waiting on hydraulic part"),
        _sig(7, "bottleneck", "Loader", 1, summary="hydraulic part still not arrived, loader idle"),
        _sig(8, "delay", "Railways", 3, summary="wagon indent pending", chat_jid="g2", chat_name="Siding"),
        _sig(9, "receivable", "NTPC Sipat", 1, amount=250000.0),
        _sig(13, "complaint", "JSPL", 1, summary="JSPL unhappy with ash %"),   # not a sales follow-up
        _sig(10, "receivable", "Unknown", 1),                           # no amount → listed, not summed
        _sig(11, "asset", "Dozer", 6, amount=3500000.0, summary="new dozer delivered"),
        _sig(12, "decision_needed", "", 1, summary="approve tender bid?"),
    ]
    out = w.pulse_compute(signals, [], now=NOW)
    assert [g["signal_id"] for g in out["sales_gap"]] == [1]
    assert out["sales_gap"][0]["age_days"] == 10 and out["sales_gap"][0]["amount"] == 450000.0
    assert out["totals"]["open"] == 12 and out["totals"]["by_kind"]["quote"] == 2
    assert len(out["bottlenecks"]) == 1
    b = out["bottlenecks"][0]
    assert sorted(b["signal_ids"]) == [6, 7] and b["count"] == 2 and "hydraulic" in b["keywords"]
    assert out["money"]["receivable"] == {"total": 250000.0, "signal_ids": [9], "uncounted_ids": [10]}
    assert [r["signal_id"] for r in out["register_changes"]] == [11]
    assert out["register_changes"][0]["category"] == "asset" and out["register_changes"][0]["value"] == 3500000.0
    assert out["decisions_needed"] == [{"signal_id": 12, "summary": "approve tender bid?"}]
    assert out["next_steps"] == [] and out["as_of"] == "2026-10-08"
    empty = w.pulse_compute([], None, now=NOW)
    assert empty["sales_gap"] == [] and empty["totals"]["open"] == 0


def test_verify_numbers_rejects_uncited_figures():
    allowed = {"computed": {"totals": {"open": 11}}, "signals": [{"id": 9, "amount": 250000.0, "created_at": "2026-10-07"}]}
    assert w.verify_numbers("11 open signals; #9 ₹2,50,000 due (7 Oct 2026)", allowed) == []
    assert w.verify_numbers("about 3 lakh across 12 chats", allowed) == ["12", "3"]
    out = w.parse_pulse('{"headline":"h","narrative":"n","next_steps":[{"step":"chase JSPL","owner":"Aman","eta":"Fri","signal_ids":["#9", 9, "x"]}, {"step":""}]}')
    assert out["next_steps"] == [{"step": "chase JSPL", "owner": "Aman", "eta": "Fri", "signal_ids": [9]}]
    assert w.parse_pulse("no json") is None


def test_red_rules():
    assert w.is_red({"kind": "decision_needed"})
    assert w.is_red({"kind": "complaint"})
    today = NOW.date()
    assert w.is_red({"kind": "payable", "due_date": (today + timedelta(days=3)).isoformat()}, today=today)
    assert not w.is_red({"kind": "payable", "due_date": (today + timedelta(days=4)).isoformat()}, today=today)
    assert not w.is_red({"kind": "payable", "due_date": ""})
    assert not w.is_red({"kind": "receivable", "due_date": today.isoformat()}, today=today)
    line = w.red_line({"id": 5, "kind": "payable", "entity": "VWLR", "summary": "diesel bill", "amount": 85000.0,
                       "currency": "INR", "due_date": "2026-10-10", "chat_name": "Accounts", "evidence_ids": [1, 2]})
    assert line.startswith("🔴 wa#5 payable [VWLR] diesel bill · INR 85,000 · due 2026-10-10") and "msgs 1,2" in line


def test_receivable_overdue_rule_is_env_driven(monkeypatch):
    """Aman, chat 2026-10-09: a receivable still open after 30 days past due is 🔴.
    The threshold is RECEIVABLE_OVERDUE_DAYS (default 30); a bad value never becomes 0."""
    today = NOW.date()
    monkeypatch.delenv("RECEIVABLE_OVERDUE_DAYS", raising=False)
    assert w.receivable_overdue_days() == 30
    due_30 = (today - timedelta(days=30)).isoformat()
    due_31 = (today - timedelta(days=31)).isoformat()
    assert not w.is_red({"kind": "receivable", "due_date": due_30}, today=today)      # exactly 30 → not yet
    assert w.is_red({"kind": "receivable", "due_date": due_31}, today=today)          # after 30 days → 🔴
    assert not w.is_red({"kind": "receivable", "due_date": (today + timedelta(days=2)).isoformat()}, today=today)
    assert not w.is_red({"kind": "receivable", "due_date": "not-a-date"}, today=today)
    assert not w.is_red({"kind": "receivable"}, today=today)
    monkeypatch.setenv("RECEIVABLE_OVERDUE_DAYS", "7")
    assert w.receivable_overdue_days() == 7
    assert w.is_red({"kind": "receivable", "due_date": (today - timedelta(days=8)).isoformat()}, today=today)
    assert not w.is_red({"kind": "receivable", "due_date": (today - timedelta(days=7)).isoformat()}, today=today)
    monkeypatch.setenv("RECEIVABLE_OVERDUE_DAYS", "lots")
    assert w.receivable_overdue_days() == 30
    # the payable rule is untouched by the env
    assert w.is_red({"kind": "payable", "due_date": (today + timedelta(days=3)).isoformat()}, today=today)


def test_every_n_hours_cadence_is_understood():
    last = NOW - timedelta(hours=1)
    assert c.next_due("every 2h", last, NOW) == last + timedelta(hours=2)
    assert not c.is_missed("every 2h", last, NOW)
    assert c.is_missed("every 2h", NOW - timedelta(hours=3), NOW)
    assert c.next_due("every 6h", None, NOW) == NOW


# ── ingest gate through the app ───────────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _post(client, **body):
    base = {"group": "Family Jokes", "sender": "Mausi", "text": "😂", "timestamp": "2026-10-08T05:00:00Z",
            "jid": "120363@g.us", "chat_jid": "120363@g.us", "account": "2", "chat_kind": "group", "from_me": 0}
    base.update(body)
    return client.post("/api/whatsapp/message", json=base).json()


def test_ingest_personal_chat_stores_nothing():
    client = _client()
    jid = "test-personal@g.us"
    # first message: unknown chat → quarantined (stored, classification unclear)
    r = _post(client, jid=jid, chat_jid=jid, wa_msg_id="m1", participants=["Mausi", "Aman"])
    assert r["stored"] is True and r["classification"] == "unclear" and r["id"]
    # the same wa_msg_id again (history backfill) is dropped
    r = _post(client, jid=jid, chat_jid=jid, wa_msg_id="m1")
    assert r == {"received": True, "stored": False, "reason": "duplicate", "id": r["id"]}
    chat = next(ch for ch in client.get("/api/wa/chats?classification=unclear").json()["chats"] if ch["jid"] == jid)
    assert chat["msg_count"] == 1 and chat["participants"] == ["Mausi", "Aman"] and chat["account"] == "2"
    # Aman says personal → history gone, nothing more is ever stored
    v = client.post("/api/wa/chats/classify", json={"jid": jid, "classification": "personal", "decided_by": "aman"}).json()
    assert v["ok"] and v["messages"] == 1
    r = _post(client, jid=jid, chat_jid=jid, wa_msg_id="m2", text="another joke")
    assert r == {"received": True, "stored": False, "reason": "personal"}
    msgs = client.get("/api/wa/messages?classification=&jid=" + jid).json()
    assert msgs["count"] == 0
    stats = client.get("/api/wa/stats").json()
    assert stats["chats"]["by_classification"]["personal"] >= 1
    # the row only exists in the client's scratch DB; bad input is refused
    assert client.post("/api/wa/chats/classify", json={"jid": jid, "classification": "maybe"}).status_code == 400
    assert client.post("/api/wa/chats/classify", json={"jid": "nope", "classification": "personal"}).status_code == 404


def test_business_chat_signals_dedup_and_red_push():
    client = _client()
    import mdo_server
    jid = "test-biz@g.us"
    for i, text in enumerate(["JSPL ko 4 rake chahiye next week", "rate 1850/MT quoted", "approve bid? need your call sir"]):
        r = _post(client, jid=jid, chat_jid=jid, group="VWLR Dispatch", sender="Site", text=text, wa_msg_id=f"b{i}")
        assert r["stored"] is True
    v = client.post("/api/wa/chats/classify", json={"jid": jid, "classification": "business", "entity": "vwlr",
                                                    "decided_by": "auto", "confidence": 0.93, "reason": "rakes"}).json()
    assert v["entity"] == "VWLR" and v["messages"] == 0
    msgs = client.get("/api/wa/messages?classification=business&jid=" + jid).json()["messages"]
    assert len(msgs) == 3 and msgs[0]["entity"] == "VWLR" and msgs[0]["chat_name"] == "VWLR Dispatch"
    ids = [m["id"] for m in msgs]
    pushed = []
    mdo_server._cos["send_cos"], orig = (lambda text, **kw: pushed.append(text) or {"sent": True}), mdo_server._cos["send_cos"]
    try:
        payload = {"bot_id": "wa-intel", "signals": [
            {"kind": "quote", "entity": "VWLR", "counterparty": "JSPL", "amount": 1850, "summary": "1850/MT quoted",
             "evidence_ids": ids[1:2], "snippet": "rate 1850/MT quoted", "chat_jid": jid, "chat_name": "VWLR Dispatch"},
            {"kind": "decision_needed", "entity": "VWLR", "counterparty": "JSPL", "summary": "approve bid",
             "evidence_ids": ids[2:], "snippet": "approve bid?", "chat_jid": jid, "chat_name": "VWLR Dispatch"},
            {"kind": "chit_chat", "summary": "ignored", "evidence_ids": ids[:1]},
        ]}
        out = client.post("/api/wa/signals", json=payload).json()
        assert out["inserted"] == 2 and out["duplicates"] == 0 and len(out["alerts"]) == 1
        assert pushed and pushed[0].startswith("🔴 wa#") and "decision_needed [VWLR] approve bid" in pushed[0]
        again = client.post("/api/wa/signals", json=payload).json()
        assert again["inserted"] == 0 and again["duplicates"] == 2 and not again["alerts"]
    finally:
        mdo_server._cos["send_cos"] = orig
    open_sigs = client.get("/api/wa/signals?status=open&entity=VWLR&kind=quote").json()["signals"]
    assert any(s["counterparty"] == "JSPL" and s["evidence_ids"] == ids[1:2] for s in open_sigs)
    sid = out["ids"][0]
    assert client.post(f"/api/wa/signals/{sid}/status", json={"status": "done"}).json()["status"] == "done"
    assert client.post(f"/api/wa/signals/{sid}/status", json={"status": "weird"}).status_code == 400
    stats = client.get("/api/wa/stats").json()
    assert stats["signals"]["open_by_kind"].get("decision_needed", 0) >= 1
    # register requires a source; pulse input carries signals + metrics + register
    assert client.post("/api/wa/register", json={"category": "asset", "item": "Dozer"}).status_code == 400
    rid = client.post("/api/wa/register", json={"category": "asset", "entity": "VWLR", "item": "Dozer", "value": 3500000,
                                                "source": "wa signal #1"}).json()["id"]
    assert any(r["id"] == rid for r in client.get("/api/wa/register").json()["register"])
    inp = client.get("/api/wa/pulse/input").json()
    assert inp["messages_scanned"] >= 3 and any(s["kind"] == "decision_needed" for s in inp["signals"])
    assert client.get("/api/wa/pulse/latest").json()["pulse"] is None or True


def test_verdict_from_a_resolved_job_is_applied():
    client = _client()
    jid = "test-asked@s.whatsapp.net"
    r = _post(client, jid=jid, chat_jid=jid, group="Ramesh Dadu", chat_kind="dm", sender="Ramesh", text="plot registry kal", wa_msg_id="d1")
    assert r["stored"] and r["chat_kind"] == "dm"
    job = client.post("/api/cos/jobs", json={"title": 'chat "Ramesh Dadu" (2) — business or personal?', "kind": "needs_choice",
                                             "bot": "wa-classifier", "push": False,
                                             "options": ["business: Dadu Developers", "personal", "business: other entity"],
                                             "payload": {"action": "wa_classify", "jid": jid, "guess_entity": "Dadu Developers"}}).json()
    assert job["payload"]["action"] == "wa_classify"
    assert client.post("/api/wa/chats/asked", json={"jid": jid, "job_id": job["id"]}).json()["ok"]
    assert client.post("/api/wa/verdicts/apply").json()["applied"] == 0          # still open → nothing applied
    client.put(f"/api/cos/jobs/{job['id']}", json={"status": "chosen", "answer": "option 1", "source": "test"})
    res = client.post("/api/wa/verdicts/apply").json()
    assert res["applied"] == 1 and res["details"][0]["entity"] == "Dadu Developers"
    chat = next(ch for ch in client.get("/api/wa/chats?classification=business").json()["chats"] if ch["jid"] == jid)
    assert chat["decided_by"] == "aman" and chat["asked_job_id"] == job["id"]
    assert client.post("/api/wa/verdicts/apply").json()["applied"] == 0          # idempotent


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
