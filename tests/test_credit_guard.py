"""credit-guard — plan window + fleet API cap → one policy, one line per state change, zero LLM.

Aman, chat 2026-10-10: "one major bot that you must focus on is a bot that manages that we dont run out of
credits" and "effectively change models whenever required". The WhatsApp send is canned; the DB is the shared
scratch DB, so the guard's tables are wiped first.
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
import mdo_cos  # noqa: E402
import mdo_credit_guard as cg  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=IST)


class _Sent:
    def __init__(self):
        self.texts = []

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": True}


def _setup(monkeypatch):
    from fastapi.testclient import TestClient
    import mdo_server
    c = TestClient(mdo_server.app)
    c.get("/api/credits")                               # creates the tables
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("credit_plan_readings", "credit_guard_alerts", "credit_guard_runs", "spend_ledger"):
        db.execute(f"DELETE FROM {t}")
    db.commit(); db.close()
    monkeypatch.delenv("SPEND_CAP_INR_MONTH", raising=False)
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    return c, sent


def test_pace_mode_switches_to_economy_before_90_percent():
    assert mdo_cos.pace_mode(450, 10000, NOW) == ("normal", "")                          # day 10, on pace for ~₹1,500
    mode, why = mdo_cos.pace_mode(4000, 10000, NOW)                                         # 40% gone by day 10
    assert mode == "economy" and why.startswith("on pace for ₹") and "of ₹10,000" in why
    assert mdo_cos.pace_mode(9100, 10000, NOW) == ("economy", "≥90% of cap")
    assert mdo_cos.pace_mode(10000, 10000, NOW) == ("paused", "cap reached")
    assert mdo_cos.pace_mode(1000, 10000, datetime(2026, 10, 2, 9, 0, tzinfo=IST)) == ("normal", "")   # too early to project
    assert mdo_cos.pace_mode(5000, None, NOW) == ("normal", "")


def test_plan_state_reads_status_overage_staleness_and_reset():
    fresh = {"at": NOW.isoformat(), "status": "allowed", "resets_at": int((NOW + timedelta(hours=2)).timestamp()), "overage": 0}
    assert cg.plan_state(fresh, NOW) == "ok"
    assert cg.plan_state({**fresh, "status": "allowed_warning"}, NOW) == "tight"
    assert cg.plan_state({**fresh, "status": "rejected"}, NOW) == "blocked"
    assert cg.plan_state({**fresh, "overage": 1}, NOW) == "overage"
    assert cg.plan_state(None, NOW) == "unknown"
    assert cg.plan_state({**fresh, "at": (NOW - timedelta(hours=7)).isoformat()}, NOW) == "unknown"     # stale
    assert cg.plan_state({**fresh, "resets_at": int((NOW - timedelta(minutes=1)).timestamp())}, NOW) == "unknown"   # window reset


def test_reading_posted_from_a_session_drives_the_policy_and_alerts_once_per_window(monkeypatch):
    c, sent = _setup(monkeypatch)
    resets = int((NOW + timedelta(hours=3)).timestamp())
    # the dict exactly as get_session returns it
    r = c.post("/api/credits/plan", json={"rate_limit_info": {"isUsingOverage": False, "rateLimitType": "five_hour",
                                                              "resetsAt": resets, "status": "allowed"},
                                          "session": "CoS-2", "now": NOW.isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["plan_state"] in ("ok", "unknown")       # GET uses the wall clock; the run below pins NOW
    run = c.post("/api/credits/run", json={"now": NOW.isoformat()}).json()
    assert run["plan_state"] == "ok" and run["pushed"] == 0 and sent.texts == []
    assert run["policy"]["workers"] == "yes" and run["policy"]["models"] == {"read": "haiku", "build": "sonnet", "cos": "opus"}
    assert run["line"].startswith("credit-guard: credits fine · plan: ok · resets 15:00 IST · overage no · API ₹0 (no cap set)")

    c.post("/api/credits/plan", json={"status": "allowed_warning", "resetsAt": resets, "now": NOW.isoformat()})
    run = c.post("/api/credits/run", json={"now": NOW.isoformat()}).json()
    assert run["plan_state"] == "tight" and run["pushed"] == 1 and run["status"] == "warning"
    assert run["policy"]["workers"] == "no" and run["policy"]["max_workers"] == 0 and run["policy"]["models"]["build"] == "haiku"
    assert sent.texts == ["🔴 Claude plan near its limit — resets 15:00 IST. Workers stopped; reads on Haiku, CoS on Sonnet until reset."]
    again = c.post("/api/credits/run", json={"now": (NOW + timedelta(minutes=30)).isoformat()}).json()
    assert again["pushed"] == 0 and len(sent.texts) == 1                                    # same window: never repeated

    assert c.post("/api/credits/plan", json={"status": "maybe"}).status_code == 400


def test_api_spend_on_pace_switches_every_bot_and_says_so_once(monkeypatch):
    c, sent = _setup(monkeypatch)
    monkeypatch.setenv("SPEND_CAP_INR_MONTH", "100")
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("INSERT INTO spend_ledger (bot,model,input_tokens,output_tokens,cache_read_tokens,cost_inr) "
               "VALUES ('capital-watcher','claude-opus-5-5',1,1,0,95)")
    db.commit(); db.close()
    spend = c.get("/api/spend").json()
    assert spend["mode"] == "economy" and spend["mode_reason"] and spend["forecast_inr"] >= 95
    run = c.post("/api/credits/run", json={"now": NOW.isoformat()}).json()
    assert "credits TIGHT" in run["line"] and "top capital-watcher opus ₹95" in run["line"]
    assert any(t.startswith("🟡 Fleet API") for t in sent.texts)
    n = len(sent.texts)
    c.post("/api/credits/run", json={"now": NOW.isoformat()})
    assert len(sent.texts) == n


def test_agent_runner_files_the_heartbeat_every_run(monkeypatch):
    calls, beats = [], []
    monkeypatch.setattr(ag, "api", lambda path, method="GET", body=None, timeout=30: calls.append((path, method)) or
                        {"line": "credit-guard: credits fine · plan: no live reading · API ₹0 (no cap set)", "status": "clean"})
    monkeypatch.setattr(ag, "heartbeat", lambda *a, **k: beats.append(a))
    assert ag.run_credit_guard({"id": "credit-guard"}, "none", "hourly", now=NOW) == 0
    assert calls == [("/api/credits/run", "POST")] and beats[0][0] == "credit-guard" and "credits fine" in beats[0][3]


def test_fleet_entry_and_cron_line_exist():
    bots = {b["id"]: b for b in yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))["bots"]}
    b = bots["credit-guard"]
    assert b["enabled"] is True and b["provider"] == "none" and b["runs_on"] == "vps-cron"
    assert "credit-guard" in ag.CUSTOM_BOTS
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    assert "mdo_agent.py credit-guard" in doc
