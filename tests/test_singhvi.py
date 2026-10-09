"""singhvi bot — Anil Singhvi's morning calls become Morning Setup PROPOSALS, never trades.

Aman, chat 2026-10-09: trade suggestions only at >80% conviction, with the reasoning and
the invalidation level; nothing executes without his click. Also covers the wa-intel
receivable-overdue sweep (RECEIVABLE_OVERDUE_DAYS, default 30) that landed in the same change.

Runs under pytest OR standalone: `python tests/test_singhvi.py`. The TestClient part follows
tests/test_sessions.py: a scratch VEGA_DB_PATH is set before mdo_server is imported.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRIDAY = datetime(2026, 10, 9, 8, 5, tzinfo=IST)
SATURDAY = datetime(2026, 10, 10, 8, 5, tzinfo=IST)
BOT = {"id": "singhvi", "provider": "grok", "model": "grok-4", "x_handles": []}

CANNED_GROK = """Here is what I found today.
```json
{"calls": [
  {"stock": "tatasteel", "action": "buy", "entry": 152.5, "stop": 148, "target": 160,
   "timeframe": "Intraday", "rationale": "breakout above 150 on volume", "conviction": 88,
   "source_url": "https://x.com/AnilSinghvi_/status/1", "quote": "Tata Steel buy above 152, SL 148, TG 160"},
  {"stock": "HDFCBANK", "action": "SELL", "entry": 1700, "stop": 1720, "target": 1660,
   "rationale": "weak close yesterday", "conviction": 0.9,
   "source_url": "https://www.zeebiz.com/markets/x", "quote": "HDFC Bank sell below 1700"},
  {"stock": "INFY", "action": "BUY", "entry": 1500, "stop": 1480, "target": 1540,
   "rationale": "IT bounce", "conviction": 80, "source_url": "https://x.com/AnilSinghvi_/status/2"},
  {"stock": "RELIANCE", "action": "BUY", "entry": 2900, "stop": null, "target": 2980,
   "rationale": "crude up", "conviction": 95, "source_url": "https://x.com/AnilSinghvi_/status/3"},
  {"stock": "SBIN", "action": "BUY", "entry": 800, "stop": 790, "target": 820,
   "rationale": "PSU bank strength", "conviction": 92, "source_url": ""},
  "garbage", {"action": "BUY"}
],
 "note": "searched @AnilSinghvi_ and zeebiz.com; 5 calls in the 08:00 show"}
```"""


# ── pure helpers ──────────────────────────────────────────────────────────────
def test_parse_singhvi_calls_normalises_and_tolerates_garbage():
    assert ag.parse_singhvi_calls("") == {"calls": [], "note": ""}
    assert ag.parse_singhvi_calls(None) == {"calls": [], "note": ""}
    assert ag.parse_singhvi_calls("no json at all") == {"calls": [], "note": ""}
    assert ag.parse_singhvi_calls('{"calls": "nope"}') == {"calls": [], "note": ""}
    out = ag.parse_singhvi_calls(CANNED_GROK)
    assert out["note"].startswith("searched @AnilSinghvi_")
    calls = out["calls"]
    assert len(calls) == 6                                   # the bare string is dropped, the empty dict kept
    tata, hdfc = calls[0], calls[1]
    assert tata["stock"] == "TATASTEEL" and tata["action"] == "BUY"
    assert (tata["entry"], tata["stop"], tata["target"]) == (152.5, 148.0, 160.0)
    assert tata["conviction"] == 88 and hdfc["conviction"] == 90          # 0.9 → 90%
    assert hdfc["action"] == "SELL" and hdfc["timeframe"] == "Intraday"   # default timeframe
    assert calls[3]["stop"] is None and calls[5]["stock"] == ""
    # a bare list is accepted too
    assert ag.parse_singhvi_calls('[{"ticker": "acc", "direction": "long", "entry_price": "1,900"}]')["calls"][0] == {
        "stock": "ACC", "action": "BUY", "entry": 1900.0, "stop": None, "target": None, "timeframe": "Intraday",
        "rationale": "", "conviction": None, "source_url": "", "quote": ""}


def test_gate_demands_levels_reasoning_source_and_conviction_over_80():
    good = {"stock": "X", "action": "BUY", "entry": 10.0, "stop": 9.0, "target": 12.0,
            "rationale": "why", "source_url": "https://x.com/p", "conviction": 81}
    assert ag.singhvi_call_gate(good) == ""
    assert ag.singhvi_call_gate({**good, "conviction": 80}) == "conviction ≤80%"      # strictly greater
    assert ag.singhvi_call_gate({**good, "conviction": None}) == "conviction ≤80%"
    assert ag.singhvi_call_gate({**good, "stop": None}) == "missing entry/stop/target"  # no invalidation level
    assert ag.singhvi_call_gate({**good, "target": 0}) == "missing entry/stop/target"
    assert ag.singhvi_call_gate({**good, "rationale": ""}) == "no rationale"
    assert ag.singhvi_call_gate({**good, "source_url": "see tv"}) == "no source URL"
    assert ag.singhvi_call_gate({**good, "action": "HOLD"}) == "no action"
    assert ag.singhvi_call_gate({**good, "stock": ""}) == "no stock"
    assert ag.SINGHVI_MIN_CONVICTION == 80


# ── end to end through the real queue endpoints ──────────────────────────────
class _Fake:
    """Routes mdo_agent.api() into the app under test and records every call,
    so the test can prove which endpoints the bot touched (and did not)."""

    def __init__(self, client, canned=None):
        self.client, self.calls, self.reports, self.canned = client, [], [], canned or {}

    def api(self, path, method="GET", body=None, timeout=30):
        self.calls.append((method, path))
        if path == "/api/agent/report":
            self.reports.append(body)
            return {"stored": True}
        if path in self.canned:
            return self.canned[path]
        if path.startswith(("/api/singhvi/", "/api/grok/")):
            r = self.client.post(path, json=body) if method == "POST" else self.client.get(path)
            assert r.status_code == 200, r.text
            return r.json()
        raise AssertionError(f"unexpected call {method} {path}")


def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def test_run_singhvi_queues_only_qualifying_calls_as_pending_proposals(monkeypatch):
    client = _client()
    fake = _Fake(client)
    grok_prompts = []
    monkeypatch.setattr(ag, "api", fake.api)
    monkeypatch.setattr(ag, "ask_grok", lambda prompt, model, bot_id, handles=None: grok_prompts.append(prompt) or CANNED_GROK)
    before = {c["id"] for c in client.get("/api/singhvi/today").json()["calls"]}

    assert ag.run_singhvi(BOT, "grok-4", "daily", now=FRIDAY) == 0

    assert len(grok_prompts) == 1 and "Anil Singhvi" in grok_prompts[0] and "09 October 2026" in grok_prompts[0]
    rows = [c for c in client.get("/api/singhvi/today").json()["calls"] if c["id"] not in before]
    by_ticker = {r["ticker"]: r for r in rows}
    assert set(by_ticker) == {"TATASTEEL", "HDFCBANK"}        # INFY=80 (not >80), RELIANCE no stop, SBIN no URL
    tata = by_ticker["TATASTEEL"]
    assert tata["status"] == "pending" and tata["direction"] == "BUY" and tata["source"] == ag.SINGHVI_SOURCE
    assert (tata["entry_price"], tata["stop_loss"], tata["target_price"]) == (152.5, 148.0, 160.0)
    assert "breakout above 150" in tata["notes"] and "conviction 88%" in tata["notes"]
    assert "invalidation (stop) 148" in tata["notes"] and "https://x.com/AnilSinghvi_/status/1" in tata["notes"]
    assert tata["raw_text"].startswith("Tata Steel buy above 152")
    assert by_ticker["HDFCBANK"]["direction"] == "SELL" and by_ticker["HDFCBANK"]["executed_at"] is None
    # proposals only: nothing approved, nothing executed, trading_signals untouched
    assert all(not p.endswith(("/approve", "/reject", "/execute")) for _, p in fake.calls)
    assert all("trading" not in p and "order" not in p for _, p in fake.calls)
    assert client.get("/api/trading/signals").status_code in (200, 404)
    # the heartbeat says what happened, including what was NOT queued and why
    assert len(fake.reports) == 1
    hb = fake.reports[0]
    assert hb["heartbeat"] is True and hb["bot"] == "singhvi" and hb["status"] == "clean"
    assert hb["summary"].startswith("singhvi: 6 call(s) found · 2 queued as PROPOSALS (>80% conviction, status pending — nothing executed)")
    assert "BUY TATASTEEL @152.5 SL 148 TG 160" in hb["summary"]
    assert "conviction ≤80%" in hb["summary"] and "missing entry/stop/target" in hb["summary"] and "no source URL" in hb["summary"]
    assert "searched @AnilSinghvi_" in hb["summary"]

    # a second run the same morning does not duplicate the queue
    fake.reports.clear()
    assert ag.run_singhvi(BOT, "grok-4", "daily", now=FRIDAY) == 0
    again = [c for c in client.get("/api/singhvi/today").json()["calls"] if c["id"] not in before]
    assert len(again) == 2
    assert "0 queued as PROPOSALS" in fake.reports[0]["summary"] and "2 already in today's queue" in fake.reports[0]["summary"]


def test_run_singhvi_heartbeats_when_nothing_found_or_weekend(monkeypatch):
    fake = _Fake(None, canned={"/api/singhvi/today": {"calls": []}})
    monkeypatch.setattr(ag, "api", fake.api)
    monkeypatch.setattr(ag, "ask_grok", lambda *a, **k: '{"calls": [], "note": "no calls posted yet"}')
    assert ag.run_singhvi(BOT, "grok-4", "daily", now=FRIDAY) == 0
    assert fake.reports[-1]["status"] == "clean"
    assert fake.reports[-1]["summary"].startswith("singhvi: 0 call(s) found · 0 queued as PROPOSALS")
    assert "no calls posted yet" in fake.reports[-1]["summary"]
    assert not any(p == "/api/singhvi/calls" for _, p in fake.calls)
    # weekend: no search, still a heartbeat
    fake.calls.clear()
    monkeypatch.setattr(ag, "ask_grok", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not search on a weekend")))
    assert ag.run_singhvi(BOT, "grok-4", "daily", now=SATURDAY) == 0
    assert fake.calls == [("POST", "/api/agent/report")] and "weekend" in fake.reports[-1]["summary"]
    # the queue being unreadable is reported, never fatal
    fake.calls.clear()
    monkeypatch.setattr(ag, "ask_grok", lambda *a, **k: "")
    fake.canned.clear()
    monkeypatch.setattr(fake, "api", lambda path, method="GET", body=None, timeout=30: (
        fake.reports.append(body) or {} if path == "/api/agent/report" else (_ for _ in ()).throw(OSError("down"))))
    monkeypatch.setattr(ag, "api", fake.api)
    assert ag.run_singhvi(BOT, "grok-4", "daily", now=FRIDAY) == 0
    assert fake.reports[-1]["status"] == "warning" and "today's queue unreadable" in fake.reports[-1]["summary"]


def test_singhvi_is_wired_in_dispatch_fleet_agenda_and_cron():
    assert ag.CUSTOM_BOTS["singhvi"] is ag.run_singhvi and ag.CUSTOM_BOTS["wa-intel"] is ag.run_wa_intel
    fleet = yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))
    bot = ag.find_bot(fleet, "singhvi")
    assert bot["enabled"] is True and bot["runs_on"] == "vps-cron" and bot["provider"] == "grok"
    assert bot["command"] == "docker compose exec -T backend python mdo_agent.py singhvi"
    assert bot["cadence"] == "weekdays 08:05 IST" and bot["model"] == "grok-4" and "capital-rules" in bot["serves"]
    assert {"purpose", "thinks", "works", "limits", "minimum_output", "rules"} <= set(bot["charter"])
    hotel = ag.find_bot(fleet, "hotel-daily")
    assert hotel["cadence"] == "daily 20:00 IST" and "hotel_daily" not in hotel["checks"]
    assert "hotel_daily" not in ag.find_bot(fleet, "daily-brief")["checks"]
    # the §8 block is what deploy_vps.sh render_cron installs
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    block = doc[doc.index("# MDO fleet — one line per bot"):]
    block = block[:block.index("```")]
    lines = [ln for ln in block.splitlines() if "mdo_agent.py singhvi" in ln]
    assert len(lines) == 1 and lines[0].split()[:5] == ["35", "2", "*", "*", "1-5"]
    hotel_lines = [ln for ln in block.splitlines() if "mdo_agent.py hotel-daily" in ln]
    assert len(hotel_lines) == 1 and hotel_lines[0].split()[:5] == ["30", "14", "*", "*", "*"]   # 20:00 IST
    agenda = yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))
    live = {o["id"]: o for o in agenda["objectives"] if o.get("confirmed") is True}
    assert {"vwlr-dispatch", "tenders-washing-rcr", "hotel-renovation-contract", "capital-rules", "battery-plant"} <= set(live)
    assert all(o["source"] == "Aman, chat 2026-10-09" for o in live.values())
    assert len(agenda["candidates"]) == 8                      # nothing removed
    # every objective a bot serves exists in the agenda
    known = set(live) | {"all"}
    for b in fleet["bots"]:
        for obj in b.get("serves") or []:
            assert obj in known, (b["id"], obj)


# ── wa-intel receivable sweep ─────────────────────────────────────────────────
def test_receivable_sweep_files_one_red_per_overdue_receivable(monkeypatch):
    monkeypatch.delenv("RECEIVABLE_OVERDUE_DAYS", raising=False)
    today = FRIDAY.date()
    sigs = [
        {"id": 7, "kind": "receivable", "entity": "VWLR", "counterparty": "JSPL", "amount": 1850000.0, "currency": "INR",
         "due_date": (today - timedelta(days=45)).isoformat(), "summary": "Sept bill pending", "evidence_ids": [11, 12],
         "chat_name": "VWLR Accounts", "owner": ""},
        {"id": 8, "kind": "receivable", "entity": "VWLR", "counterparty": "BALCO", "amount": None,
         "due_date": (today - timedelta(days=10)).isoformat(), "summary": "recent", "evidence_ids": [13]},
        {"id": 9, "kind": "receivable", "entity": "Dadu Developers", "counterparty": "Buyer", "amount": 500000.0,
         "due_date": "", "summary": "no due date", "evidence_ids": [14]},
    ]
    fake = _Fake(None, canned={"/api/wa/signals?status=open&kind=receivable&limit=500": {"signals": sigs}})
    monkeypatch.setattr(ag, "api", fake.api)
    n, note = ag.sweep_overdue_receivables("wa-intel", "hourly", today=today)
    assert n == 1 and note == "1 receivable(s) overdue >30d → 🔴"
    assert len(fake.reports) == 1
    rep = fake.reports[0]
    assert rep["bot"] == "wa-intel" and rep["status"] == "reported" and not rep.get("heartbeat")
    f = rep["findings"][0]
    assert f["level"] == "critical" and f["owner"] == "Aman" and f["entity"] == "VWLR"
    assert f["title"] == "receivable overdue >30d: JSPL [VWLR] · INR 1,850,000 · wa#7"   # stable → alerts once
    assert "45 days past due" in f["detail"] and "RECEIVABLE_OVERDUE_DAYS=30" in f["detail"] and "msgs 11,12" in f["detail"]
    # nothing overdue → no report at all; a failed read → a note, never an exception
    fake.reports.clear()
    fake.canned["/api/wa/signals?status=open&kind=receivable&limit=500"] = {"signals": sigs[1:]}
    assert ag.sweep_overdue_receivables(today=today) == (0, "") and fake.reports == []
    fake.canned.clear()
    monkeypatch.setattr(ag, "api", lambda *a, **k: (_ for _ in ()).throw(OSError("backend down")))
    n, note = ag.sweep_overdue_receivables(today=today)
    assert n == 0 and note.startswith("receivable sweep failed")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
