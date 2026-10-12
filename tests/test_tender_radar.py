"""tender-radar — classification of real titles from the Tender247 Missed Opportunities export, reminder stages sent once, WhatsApp commands."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import yaml  # noqa: E402

import mdo_tender_radar as tr  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = date(2026, 10, 12)


def test_classify_titles_from_the_export():
    c = tr.classify("loading, transportation ( rcr mode) & handling of coal from ccl mines to designated railway siding for apc", "National Thermal Power Corporation Limited", "Chhattisgarh")
    assert c["tier"] == "A" and c["family"] == "RCR / siding" and c["preferred_state"]
    assert tr.classify("supply of - domestic coal for ntpc (q3) - | quantity - 5000")["family"] == "Coal supply"
    assert tr.classify("auction sale of coal middlings gcv 2200-2500")["tier"] == "A"
    assert tr.classify("coal washery operation and beneficiation of non coking coal")["family"] == "Washery / beneficiation"
    assert tr.classify("coal loading and crushing at siding")["tier"] == "A"
    b = tr.classify("hiring of dumpers for ob removal and coal extraction at ocp")
    assert b["tier"] == "B" and b["family"] == "Mining services"
    assert tr.classify("strenghtning of coal transportation road from shivdanga ssi unit to colliery gate")["tier"] == "X"     # civil road work
    assert tr.classify("construction of coal transport road near siding")["tier"] == "A"                                      # siding keeps it in
    assert tr.classify("supply of hire charges of concrete mixer")["tier"] == "X"
    assert tr.classify("purchase of office furniture")["tier"] == "X"
    assert tr.classify("coal transport", "Godavari Commodities")["competitors"] == ["Godavari Commodities"]


def test_stages_and_commands():
    assert tr.stage_for("A", 7) == "T-7" and tr.stage_for("A", 3) == "T-3" and tr.stage_for("A", 2) is None and tr.stage_for("B", 7) is None
    assert tr.stage_for("B", 0) == "T-0" and tr.stage_for("A", -1) is None and tr.stage_for("A", None) is None
    assert tr.parse_command("bid 42") == ("bid", 42) and tr.parse_command("Skip #7") == ("skip", 7) and tr.parse_command("tenders") == ("tenders", None)
    assert tr.parse_command("bid") is None and tr.parse_command("hello") is None


class _Sent:
    def __init__(self):
        self.texts = []

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": True}


def test_run_sends_each_stage_once_flags_undecided_and_the_commands_mark_rows(monkeypatch):
    from fastapi.testclient import TestClient
    import mdo_server
    c = TestClient(mdo_server.app)
    c.get("/api/health/public")
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("DELETE FROM vwlr_tender_pipeline")
    rows = [("National Thermal Power Corporation Limited", "RCR", "2026-10-15", "evaluating", "[tender247] loading, transportation (rcr mode) of coal to siding"),   # T-3, A
            ("Central Coalfields Limited", "Other", "2026-10-12", "evaluating", "[tender247] coal supply (steam coal) quantity 5000"),                               # T-0, A
            ("South Eastern Coalfields Limited", "Other", "2026-10-11", "evaluating", "[tender247] coal handling and crushing at siding"),                           # closed yesterday, undecided
            ("Zilla Parishad", "Other", "2026-10-13", "evaluating", "[tender247] supply of hire charges of concrete mixer"),                                       # X
            ("Western Coalfields Limited", "Other", "2026-10-19", "evaluating", "[tender247] coal supply washed coal 20000 mt")]                                     # T-7, A
    for b, cat, due, st, notes in rows:
        db.execute("INSERT INTO vwlr_tender_pipeline (buyer,category,due_date,status,notes,created_at) VALUES (?,?,?,?,?,?)", (b, cat, due, st, notes, "2026-10-12 06:00:00"))
    db.commit(); db.close()
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    r = c.post("/api/tender-radar/run", json={"now": "2026-10-12T08:00:00+05:30"}).json()
    assert r["open_a"] == 3 and r["reminders"] == 3 and r["closed_undecided"] == 1 and r["new_today"] == 3 and r["status"] == "clean"
    assert "closes TODAY" in sent.texts[0] and "closes in 3 days" in sent.texts[0] and "closes in 7 days" in sent.texts[0] and "Closed yesterday with no decision" in sent.texts[0]
    assert "concrete" not in sent.texts[0] and r["line"].startswith("tender-radar: 3 A and 0 B tenders open · 3 reminders sent")
    again = c.post("/api/tender-radar/run", json={"now": "2026-10-12T14:00:00+05:30"}).json()
    assert again["reminders"] == 0 and "due: none" in again["line"]                                                  # every stage once, still reports
    nxt = c.post("/api/tender-radar/run", json={"now": "2026-10-15T08:00:00+05:30"}).json()                          # three days later: the first row is now T-0
    assert nxt["reminders"] >= 1
    o = c.get("/api/tender-radar/open").json()
    assert o["count"] >= 1 and all(t["tier"] in ("A", "B") for t in o["tenders"])
    # WhatsApp commands claimed by the hook
    import asyncio
    hook = mdo_server._radar["handle_text"]
    assert "Open tenders" in asyncio.run(hook("91", "tenders"))
    tid = o["tenders"][0]["id"]
    assert "marked bidding" in asyncio.run(hook("91", f"bid {tid}")) and "No tender #99999" in asyncio.run(hook("91", "skip 99999"))
    assert asyncio.run(hook("91", "good morning")) is None
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"]); db.execute("DELETE FROM vwlr_tender_pipeline"); db.execute("DELETE FROM tender_reminders"); db.commit(); db.close()


def test_fleet_cron_and_runner_exist(monkeypatch):
    import mdo_agent as ag
    bots = {b["id"]: b for b in yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))["bots"]}
    assert bots["tender-radar"]["enabled"] is True and bots["tender-radar"]["provider"] == "none" and "tender-radar" in ag.CUSTOM_BOTS
    assert "mdo_agent.py tender-radar" in open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    beats = []
    monkeypatch.setattr(ag, "api", lambda path, method="GET", body=None, timeout=30: {"line": "tender-radar: 0 A and 0 B tenders open · 0 reminders due: none", "status": "clean"})
    monkeypatch.setattr(ag, "heartbeat", lambda *a, **k: beats.append(a))
    assert ag.run_tender_radar({"id": "tender-radar"}, "none", "daily", now=datetime(2026, 10, 12, 8, 0, tzinfo=IST)) == 0
    assert beats[0][0] == "tender-radar" and "tenders open" in beats[0][3]
