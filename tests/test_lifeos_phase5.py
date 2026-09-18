"""Phase 5 — broker logins folded into the run (Angel auto, HDFC login-needed)."""

from __future__ import annotations

import pytest


def test_disabled_by_default(monkeypatch):
    from lifeos.sources import broker_logins as bl
    monkeypatch.delenv("LIFEOS_BROKER_LOGINS", raising=False)
    r = bl.fetch()
    assert r.status == "nil"
    assert "not enabled" in r.summary  # never blank


def test_enabled_arms_angel_and_flags_hdfc(monkeypatch):
    from lifeos.sources import broker_logins as bl
    monkeypatch.setenv("LIFEOS_BROKER_LOGINS", "1")
    monkeypatch.setattr(bl, "load_accounts", lambda: [
        ("ANGEL1", "angel", "Aditi Investment"),
        ("HDFC1", "hdfc", "Aman"),
        ("HDFC2", "hdfc", "Sudha"),
    ])
    logged_in = []
    monkeypatch.setattr(bl, "angel_login", lambda key: logged_in.append(key))
    monkeypatch.setattr(bl, "hdfc_armed", lambda key: key == "HDFC1")

    r = bl.fetch()
    assert logged_in == ["ANGEL1"]          # Angel auto-logged-in
    assert r.data["armed"] == 2             # ANGEL1 + HDFC1 (armed today)
    assert r.data["needs_login"] == 1       # HDFC2 needs the phone login
    gutters = {row["text"].split()[0]: row["gutter"] for row in r.extra["rows"]}
    assert gutters["Aditi"] == "ALIVE" and gutters["Sudha"] == "LOGIN"


def test_angel_login_failure_is_isolated(monkeypatch):
    from lifeos.sources import broker_logins as bl
    monkeypatch.setenv("LIFEOS_BROKER_LOGINS", "1")
    monkeypatch.setattr(bl, "load_accounts", lambda: [("ANGEL1", "angel", "Aditi")])

    def boom(key):
        raise RuntimeError("TOTP rejected")
    monkeypatch.setattr(bl, "angel_login", boom)

    r = bl.fetch()
    assert r.data["failed"] == 1
    assert r.extra["rows"][0]["gutter"] == "FAIL"
    assert "TOTP rejected" in r.extra["rows"][0]["meta"]


def test_hdfc_login_nudge_is_daily(monkeypatch):
    from lifeos import nudge
    from lifeos.sources import Result, OK
    results = [Result(name="broker_logins", status=OK, summary="",
                      extra={"rows": [
                          {"gutter": "LOGIN", "severity": "warning", "text": "Aman (HDFC1)", "meta": "HDFC · needs login"},
                          {"gutter": "ALIVE", "severity": "alive", "text": "Aditi (ANGEL1)", "meta": "ok"},
                      ]})]
    cands = nudge.build_nudges(results)
    login_nudges = [c for c in cands if c["fingerprint"].startswith("hdfc_login:")]
    assert len(login_nudges) == 1
    # date-stamped fingerprint so it can recur the next day
    assert login_nudges[0]["fingerprint"].count(":") >= 2
