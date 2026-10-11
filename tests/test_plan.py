"""daily-plan — morning objectives, evening planned-vs-actual, the faults of the day. Zero LLM; the send is canned.

Aman, chat 2026-10-11: show daily where the fault lay when work that could finish today did not finish today.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_plan as mp  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MON = datetime(2026, 10, 12, 7, 30, tzinfo=IST)
MON_EVE = datetime(2026, 10, 12, 19, 30, tzinfo=IST)
TUE = datetime(2026, 10, 13, 7, 30, tzinfo=IST)


def test_command_grammar():
    assert mp.parse_command("today") == {"cmd": "today"}
    p = mp.parse_command("plan Washery: pour slab C2 @Ramesh; fix shuttering ; ")
    assert p == {"cmd": "plan", "project": "washery", "items": [{"item": "pour slab C2", "owner": "Ramesh"}, {"item": "fix shuttering", "owner": ""}]}
    assert mp.parse_command("done 3,4") == {"cmd": "done", "ids": [3, 4]}
    assert mp.parse_command("done #7") == {"cmd": "done", "ids": [7]}
    m = mp.parse_command("miss 5 material")
    assert m["cmd"] == "miss" and m["ids"] == [5] and m["reason"] == "material" and m["by"] == ""
    assert mp.parse_command("miss 5 manpower by Ramesh")["by"] == "ramesh"
    assert mp.parse_command("miss 5 gremlins")["bad_reason"] == "gremlins"
    assert mp.parse_command("ok 14") is None and mp.parse_command("how is the hotel doing") is None       # left for the job parser / brain
    assert mp.parse_command("plan: nothing") is None


def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


class _Sent:
    def __init__(self):
        self.texts, self.ok = [], True

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": self.ok} if self.ok else {"sent": False, "reason": "bridge down"}


def _setup(monkeypatch):
    import mdo_server
    c = _client()
    c.get("/api/plan/projects")
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("DELETE FROM plan_items"); db.commit(); db.close()
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    return c, sent


def test_morning_plan_evening_actual_and_the_fault_tally(monkeypatch):
    c, sent = _setup(monkeypatch)
    assert {p["key"] for p in c.get("/api/plan/projects").json()["projects"]} >= {"washery", "hotel"}
    r = c.post("/api/plan/items", json={"project": "washery", "date": "2026-10-12",
                                        "items": [{"item": "pour slab C2", "owner": "Ramesh"}, {"item": "erect crusher frame", "owner": "Suresh"}]}).json()
    h = c.post("/api/plan/items", json={"project": "hotel", "date": "2026-10-12", "item": "tile 3rd floor lobby", "owner": "Mohan"}).json()
    assert len(r["ids"]) == 2 and len(h["ids"]) == 1
    assert c.post("/api/plan/items", json={"project": "nope", "item": "x"}).status_code == 400
    a, b = r["ids"]
    t = c.post("/api/plan/run", json={"mode": "morning", "now": MON.isoformat()}).json()
    assert t["status"] == "clean" and t["items"] == 3 and t["carried"] == 0 and t["pushed"] == 1
    assert t["text"].startswith("Good morning · Mon 12 Oct · today's objectives")
    assert "• algo-trading:" in t["text"] and "Project plan for today:" in t["text"] and f"#{a} pour slab C2 @Ramesh" in t["text"]
    # replies by WhatsApp grammar
    ok = c.post("/api/plan/items/%d/close" % a, json={"status": "done"}).json()
    assert ok["ok"] and ok["status"] == "done"
    miss = c.post("/api/plan/items/%d/close" % b, json={"status": "missed", "reason": "material", "fault": "cement vendor"}).json()
    assert miss["reason"] == "material" and miss["fault"] == "cement vendor"
    e = c.post("/api/plan/run", json={"mode": "evening", "now": MON_EVE.isoformat()}).json()
    assert e["done"] == 1 and e["missed"] == 1 and e["open"] == 1
    assert "███░░░░░░░ 1/3 done · 1 missed · 1 not reported" in e["text"]
    assert "Where it stalled: material ×1" in e["text"] and "Not reported: #%d" % h["ids"][0] in e["text"]
    assert e["line"] == "daily-plan evening: 1/3 done, 1 missed, 1 not reported"
    # next morning: the unreported item is closed as missed/unreported and carried over, never dropped
    t2 = c.post("/api/plan/run", json={"mode": "morning", "now": TUE.isoformat()}).json()
    assert t2["carried"] == 1 and "(carried over)" in t2["text"] and "tile 3rd floor lobby" in t2["text"]
    again = c.post("/api/plan/run", json={"mode": "morning", "now": TUE.isoformat()}).json()
    assert again["carried"] == 0                                                   # idempotent: no second carry-over
    f = c.get("/api/plan/faults", params={"days": 7, "now": TUE.isoformat()}).json()
    assert f["missed"] == 2 and dict(map(tuple, f["by_reason"])) == {"material": 1, "other": 1}
    assert dict(map(tuple, f["by_fault"])) == {"cement vendor": 1, "unreported": 1}
    s = c.get("/api/plan/sheet", params={"days": 7, "now": TUE.isoformat()}).json()
    assert s["totals"]["planned"] == 4 and s["totals"]["done"] == 1 and s["totals"]["done_pct"] == 25
    assert s["days"][1]["date"] == "2026-10-12" and s["days"][1]["planned"] == 3


def test_whatsapp_commands_reach_the_plan_before_the_job_parser(monkeypatch):
    c, sent = _setup(monkeypatch)
    sender = "917000512030"
    r = c.post("/api/cos/inbound", json={"from": sender, "text": "plan hotel: fix lobby ceiling @Mohan; paint stairwell", "channel": "baileys"}).json()
    assert r["handled"] and r["reply"].startswith("✔ planned 2 for Hotel ANS — renovation: #")
    ids = [int(x) for x in r["reply"].split("#")[1:] for x in [x.strip(", ")]]
    r = c.post("/api/cos/inbound", json={"from": sender, "text": f"done {ids[0]}", "channel": "baileys"}).json()
    assert r["reply"] == f"✔ done #{ids[0]}"
    r = c.post("/api/cos/inbound", json={"from": sender, "text": f"miss {ids[1]} weather", "channel": "baileys"}).json()
    assert r["reply"].startswith(f"✔ #{ids[1]} missed — weather")
    r = c.post("/api/cos/inbound", json={"from": sender, "text": "miss 999 material", "channel": "baileys"}).json()
    assert "no item #999" in r["reply"]
    r = c.post("/api/cos/inbound", json={"from": sender, "text": "today", "channel": "baileys"}).json()
    assert "✅" in r["reply"] and "❌" in r["reply"]


def test_runner_fleet_and_cron_wiring():
    seen = {}
    old = ag.api
    ag.api = lambda path, method="GET", body=None, timeout=30: seen.update({"path": path, "body": body}) or {"line": "daily-plan morning: 3 items planned, 0 carried over", "status": "clean"}
    beats = []
    oh = ag.heartbeat
    ag.heartbeat = lambda *a: beats.append(a)
    try:
        assert ag.run_daily_plan({"id": "daily-plan"}, "none", "daily", MON, mode="evening") == 0
        assert ag.run_daily_plan({"id": "daily-plan"}, "none", "daily", MON, mode="bogus") == 2
    finally:
        ag.api, ag.heartbeat = old, oh
    assert seen["path"] == "/api/plan/run" and seen["body"]["mode"] == "evening"
    assert beats[0][0] == "daily-plan" and beats[0][2] == "clean" and beats[1][2] == "error"
    bots = {b["id"]: b for b in yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))["bots"]}
    assert bots["daily-plan"]["enabled"] is True and bots["daily-plan"]["provider"] == "none"
    assert "daily-plan" in ag.CUSTOM_BOTS
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    assert "mdo_agent.py daily-plan morning" in doc and "mdo_agent.py daily-plan evening" in doc
    agenda = yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))
    assert set(bots["daily-plan"]["serves"]) <= {o["id"] for o in agenda["objectives"]}
