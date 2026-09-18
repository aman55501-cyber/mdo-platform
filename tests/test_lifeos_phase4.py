"""Phase 4 — ask bar (capture + model), Notion publish, /ask route gating."""

from __future__ import annotations

import base64
import importlib

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEOS_DB_PATH", str(tmp_path / "p4.db"))
    monkeypatch.setenv("LIFEOS_USER", "aman")
    monkeypatch.setenv("LIFEOS_PASSWORD", "pw")
    from lifeos import config as cfg
    from lifeos import db
    importlib.reload(cfg)
    importlib.reload(db)
    db.init_db()
    return db


# ── capture parsing ───────────────────────────────────────────────────────────
def test_parse_capture():
    from lifeos import ask
    assert ask.parse_capture("capture: call NTPC Monday") == ("capture", "call NTPC Monday")
    assert ask.parse_capture("remind: GST due 20th") == ("remind", "GST due 20th")
    assert ask.parse_capture("Remind me: site visit") == ("remind", "site visit")
    assert ask.parse_capture("what is my occupancy?") is None


def test_write_capture_builds_new_inbox_row(monkeypatch):
    from lifeos import ask
    captured = {}
    def fake_create(ds, props):
        captured["ds"] = ds
        captured["props"] = props
        return {"id": "x"}
    monkeypatch.setattr(ask.nc, "create_page", fake_create)
    msg = ask.write_capture("capture", "call NTPC Monday")
    assert captured["ds"] == ask.INBOX_DS
    assert captured["props"]["Status"] == {"select": {"name": "New"}}
    assert captured["props"]["Item"]["title"][0]["text"]["content"] == "call NTPC Monday"
    assert "Inbox" in msg


def test_stream_answer_offline_without_key(monkeypatch):
    from lifeos import ask
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = "".join(ask.stream_answer("hi"))
    assert "ANTHROPIC_API_KEY not set" in out


def test_state_context_from_run(env):
    from lifeos.run import execute_run
    from lifeos import ask
    execute_run(trigger="manual")
    ctx = ask.build_state_context()
    assert "Run #" in ctx and "Sources:" in ctx


# ── publish ───────────────────────────────────────────────────────────────────
def test_publish_rewrites_today_and_appends_archive(monkeypatch):
    from lifeos import publish
    from lifeos.sources import Result, OK
    calls = {"deleted": 0, "appended": []}
    monkeypatch.setattr(publish.nc, "list_children", lambda pid: [{"id": "b1"}, {"id": "b2"}])
    monkeypatch.setattr(publish.nc, "delete_block", lambda bid: calls.__setitem__("deleted", calls["deleted"] + 1))
    monkeypatch.setattr(publish.nc, "append_children", lambda pid, children: calls["appended"].append((pid, len(children))))
    results = [Result(name="erp_sales", status="blocked", summary="3 owed"),
               Result(name="tenders", status=OK, summary="pipeline ok")]
    out = publish.publish(results, ok=1, unreachable=0)
    assert out["today"] == "today: rewritten"
    assert out["archive"] == "archive: appended"
    assert calls["deleted"] == 2                       # cleared existing blocks
    # today append includes heading + heartbeat + 2 source lines; archive appends 1
    assert calls["appended"][0][1] == 4 and calls["appended"][1][1] == 1


# ── /ask route ────────────────────────────────────────────────────────────────
def _client(monkeypatch):
    from starlette.testclient import TestClient
    from lifeos.server import app
    return TestClient(app)


def test_ask_route_is_gated(env, monkeypatch):
    c = _client(monkeypatch)
    with c:
        assert c.post("/ask", json={"q": "hi"}).status_code == 401


def test_ask_route_capture_and_model(env, monkeypatch):
    from lifeos import ask
    monkeypatch.setattr(ask.nc, "create_page", lambda ds, props: {"id": "x"})
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = _client(monkeypatch)
    auth = {"Authorization": "Basic " + base64.b64encode(b"aman:pw").decode()}
    with c:
        r = c.post("/ask", json={"q": "capture: call NTPC"}, headers=auth)
        assert r.status_code == 200 and r.json()["captured"] is True
        r2 = c.post("/ask", json={"q": "what is due today?"}, headers=auth)
        assert "ANTHROPIC_API_KEY not set" in r2.text  # streamed offline message
