"""Public watchdog door — GET /api/health/public: no key, ok/age/bridges only, 503 when the fleet is stale.

The one alarm that fires when the fleet itself is dead (UptimeRobot keyword monitor, DEPLOY_HOSTINGER.md §8a).
Follows tests/test_compliance.py: a scratch VEGA_DB_PATH before mdo_server is imported; the endpoint tests wipe
cos_runs (the DB is shared by every test module).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("SHARE_MASTER_DATA_DIR", tempfile.mkdtemp())

import mdo_health as mh  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── pure ──────────────────────────────────────────────────────────────────────
def test_heartbeat_age_and_verdict():
    now = datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc)
    assert mh.parse_stamp(None) is None and mh.parse_stamp("garbage") is None
    assert mh.parse_stamp("2026-10-09 12:50:00") == datetime(2026, 10, 9, 12, 50, tzinfo=timezone.utc)   # sqlite datetime('now') is UTC
    assert mh.parse_stamp("2026-10-09T18:20:00+05:30") == datetime(2026, 10, 9, 12, 50, tzinfo=timezone.utc)
    assert mh.heartbeat_age_min("2026-10-09 12:50:00", now) == 10
    assert mh.heartbeat_age_min("2026-10-09 13:05:00", now) == 0                 # clock skew never goes negative
    assert mh.heartbeat_age_min(None, now) is None
    assert mh.verdict(10, True) == (True, "")
    assert mh.verdict(44, True) == (True, "")
    assert mh.verdict(45, True) == (False, "last fleet heartbeat 45 min ago (limit 45)")
    assert mh.verdict(None, True) == (False, "no fleet heartbeat on record")
    assert mh.verdict(1, False, "OperationalError") == (False, "database not answering: OperationalError")
    assert mh.MAX_HEARTBEAT_AGE_MIN == 45 and mh.PUBLIC_PATH == "/api/health/public"


def test_bridge_state_never_raises(monkeypatch):
    assert mh.bridge_state("") == "down"
    monkeypatch.setattr(mh.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
    assert mh.bridge_state("http://whatsapp:3001") == "down"


# ── endpoint through the real app ─────────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _runs(rows: list[tuple[str, str]]):
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("DELETE FROM cos_runs")
    for bot, stamp in rows:
        db.execute("INSERT INTO cos_runs (bot, cadence, status, summary, created_at) VALUES (?,?,?,?,?)", (bot, "daily", "clean", "x", stamp))
    db.commit(); db.close()


def test_public_health_no_key_fresh_stale_and_no_secrets(monkeypatch):
    import mdo_server
    c = _client()
    c.get("/api/corp-actions/tickers")                     # opens the DB, creates every table
    monkeypatch.setattr(mdo_server, "MDO_AUTH_TOKEN", "app-secret-key")
    monkeypatch.setenv("WA_BRIDGE_URL", "http://whatsapp:3001")
    monkeypatch.setenv("WA_BRIDGE2_URL", "http://whatsapp2:3001")
    monkeypatch.setitem(mdo_server._health["hooks"], "bridge_state", lambda url: "connected" if "whatsapp:" in url else "down")
    assert c.get("/api/status").status_code == 401        # the lock is on …
    # … and the watchdog door is open without a key
    _runs([("deploy", (datetime.now(timezone.utc) - timedelta(minutes=7)).strftime("%Y-%m-%d %H:%M:%S")),
           ("levels-alert", (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"))])
    r = c.get("/api/health/public")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"ok", "last_heartbeat_age_min", "bridges"}
    assert body["ok"] is True and 6 <= body["last_heartbeat_age_min"] <= 8        # the NEWEST heartbeat counts
    assert body["bridges"] == {"wa1": "connected", "wa2": "down"}
    assert "app-secret-key" not in r.text and "deploy" not in r.text and "levels-alert" not in r.text
    assert r.headers.get("cache-control") == "no-store"
    # stale: the newest heartbeat is 46 min old → 503 with the reason, still no key needed
    _runs([("deploy", (datetime.now(timezone.utc) - timedelta(minutes=46)).strftime("%Y-%m-%d %H:%M:%S"))])
    r = c.get("/api/health/public")
    assert r.status_code == 503 and r.json()["ok"] is False and r.json()["reason"].startswith("last fleet heartbeat 46 min ago")
    assert set(r.json()) == {"ok", "last_heartbeat_age_min", "bridges", "reason"}
    # nothing on record → 503; bridges down does not fail a fresh fleet
    _runs([])
    assert c.get("/api/health/public").status_code == 503 and c.get("/api/health/public").json()["reason"] == "no fleet heartbeat on record"
    monkeypatch.setitem(mdo_server._health["hooks"], "bridge_state", lambda url: "down")
    _runs([("deploy", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))])
    r = c.get("/api/health/public")
    assert r.status_code == 200 and r.json()["bridges"] == {"wa1": "down", "wa2": "down"}
    monkeypatch.delenv("WA_BRIDGE_URL"); monkeypatch.delenv("WA_BRIDGE2_URL")
    assert c.get("/api/health/public").json()["bridges"] == {"wa1": "down", "wa2": "down"}   # unset = down, never a crash
    _runs([])


def test_watchdog_wiring_caddy_middleware_and_doc():
    srv = open(os.path.join(ROOT, "mdo_server.py"), encoding="utf-8").read()
    mw = srv.split("async def _require_key")[1].split("supplied = (")[0]
    assert 'request.url.path == "/api/health/public"' in mw                     # exempt from the app key
    caddy = open(os.path.join(ROOT, "Caddyfile"), encoding="utf-8").read()
    assert "handle /api/* {" in caddy and "reverse_proxy backend:8501" in caddy.split("handle /api/* {")[1].split("}")[0]
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    sec = doc.split("External watchdog")[1].split("\n## ")[0]
    assert "UptimeRobot" in sec and "https://amanagrawal.cloud/api/health/public" in sec
    assert '"ok":true' in sec and "5 minutes" in sec and "aman.55501@gmail.com" in sec and "45 minutes" in sec
    assert "+91" not in sec                                                     # no phone number in the doc
