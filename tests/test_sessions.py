"""Broker-session freshness — the silent failure that makes the feed lie.

HDFC logins need browser 2FA and expire daily. When they lapse, nothing errors: the app
renders, the briefing generates, and the capital numbers are simply absent. A calm-looking
screen with no capital in it is worse than a broken one, so the absence must itself be a
finding.

Runs under pytest OR standalone: `python tests/test_sessions.py`.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the server at a scratch DB before importing it.
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

from fastapi.testclient import TestClient  # noqa: E402

import mdo_server  # noqa: E402

client = TestClient(mdo_server.app)


def _patch_cfo(responses: dict):
    """Swap the Shares CFO bridge for canned answers, keyed by path."""
    original = mdo_server._cfo_get

    def fake(path, timeout=25):
        for prefix, payload in responses.items():
            if path.startswith(prefix):
                return payload
        return {"error": "unstubbed path " + path}

    mdo_server._cfo_get = fake
    return original


def _restore(original):
    mdo_server._cfo_get = original


def _clear_feed():
    """Each test starts from an empty feed so cooldowns don't leak between them.

    Also re-binds the real action handlers: the feed's action registry is
    process-global, and the feed-core tests clear it to install their own stubs.

    Written synchronously against the file rather than through the app's connection:
    TestClient owns its own event loop, and borrowing it here is more trouble than a
    three-line sqlite3 call.
    """
    mdo_server.register_feed_actions()
    import sqlite3
    con = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    con.execute("DELETE FROM feed_items")
    con.execute("DELETE FROM feed_audit")
    con.commit()
    con.close()


def test_logged_out_account_becomes_a_finding():
    """The case that bit today: login run yesterday, tokens now expired."""
    client.get("/api/feed")  # ensure schema exists
    _clear_feed()
    original = _patch_cfo({
        "/accounts": {"accounts": [
            {"key": "HDFC1", "label": "Aman (HDFC)", "logged_in": False},
            {"key": "HDFC2", "label": "Sudha (HDFC)", "logged_in": False},
            {"key": "ANGEL1", "label": "Aditi (Angel)", "logged_in": True},
        ]},
        "/portfolio": {"error": "not authenticated"},
    })
    try:
        out = client.post("/api/feed/check-sessions").json()
        assert out["published"] >= 1
        item = out["items"][0]
        assert item["severity"] == "important"
        assert item["domain"] == "capital"
        assert "2 of 3" in item["title"]
        # It must draft the fix, not just complain.
        assert item["action_type"] == "add_task"
        assert "hdfc_login" in item["body"]
        # And it must name which accounts, so he knows what to re-run.
        assert "Aman (HDFC)" in item["body"] and "Sudha (HDFC)" in item["body"]
    finally:
        _restore(original)


def test_all_logged_in_publishes_nothing():
    """Silence is the healthy state — no finding when every session is live."""
    client.get("/api/feed")
    _clear_feed()
    original = _patch_cfo({
        "/accounts": {"accounts": [
            {"key": "HDFC1", "label": "Aman (HDFC)", "logged_in": True},
            {"key": "ANGEL1", "label": "Aditi (Angel)", "logged_in": True},
        ]},
        "/portfolio": {"error": "skip"},
    })
    try:
        out = client.post("/api/feed/check-sessions").json()
        assert out["published"] == 0
        assert len(out["accounts"]) == 2
        assert all(a["logged_in"] for a in out["accounts"])
    finally:
        _restore(original)


def test_bridge_down_is_critical_not_important():
    """No bridge at all is worse than an expired login — every number is gone."""
    client.get("/api/feed")
    _clear_feed()
    original = _patch_cfo({"/": {"error": "Connection refused"}})
    try:
        out = client.post("/api/feed/check-sessions").json()
        assert out["published"] >= 1
        item = out["items"][0]
        assert item["severity"] == "critical"
        assert "unreachable" in item["title"]
        assert item["evidence"], "the finding must carry what it saw"
    finally:
        _restore(original)


def test_repeat_check_does_not_re_alert():
    """The agent runs hourly; an expired login must interrupt once, not every hour."""
    client.get("/api/feed")
    _clear_feed()
    original = _patch_cfo({
        "/accounts": {"accounts": [{"key": "HDFC1", "label": "Aman", "logged_in": False}]},
        "/portfolio": {"error": "not authenticated"},
    })
    try:
        first = client.post("/api/feed/check-sessions").json()
        second = client.post("/api/feed/check-sessions").json()
        assert first["published"] == 1
        assert second["published"] == 0, "cooldown must suppress the repeat"
    finally:
        _restore(original)


def test_stale_snapshot_is_caught_even_when_logins_look_fine():
    """Authenticated but not refreshing — the subtler version of the same lie."""
    client.get("/api/feed")
    _clear_feed()
    original = _patch_cfo({
        "/accounts": {"accounts": [{"key": "HDFC1", "label": "Aman", "logged_in": True}]},
        "/portfolio": {"net_worth": 8578000, "as_of": "2026-07-20T10:00:00+00:00"},
        "/exposure": {},
        "/positions/live": {},
    })
    try:
        out = client.post("/api/feed/check-sessions").json()
        titles = [i["title"] for i in out["items"]]
        assert any("snapshot is" in t for t in titles), titles
    finally:
        _restore(original)


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"  ok   {name}")
            except Exception as e:
                failed += 1
                print(f"  FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
