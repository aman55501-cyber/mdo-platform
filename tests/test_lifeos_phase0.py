"""Phase 0 acceptance tests for LIFEOS.

Focus on the two criteria this phase must prove:
  #3 — the run must prove it ran; silent death is visible in the runs table.
  #6 — no secrets in code (checked by a grep in CI / by hand; here we assert the
       config layer only reads os.environ and fails loudly when a secret is absent).

Plus the spine: a run produces a snapshot, the heartbeat counts sources, and a
source that raises degrades to UNREACHABLE without aborting the run.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def lifeos_env(tmp_path, monkeypatch):
    """Point LIFEOS at a throwaway DB and set the auth gate."""
    monkeypatch.setenv("LIFEOS_DB_PATH", str(tmp_path / "lifeos_test.db"))
    monkeypatch.setenv("LIFEOS_USER", "aman")
    monkeypatch.setenv("LIFEOS_PASSWORD", "correct horse battery staple")
    # Reload config + db so db_path() picks up the temp path for this test.
    from lifeos import config as cfg
    from lifeos import db
    importlib.reload(cfg)
    importlib.reload(db)
    db.init_db()
    return db


# ── #6: fails-loud config, no default credential values ───────────────────────
def test_require_raises_when_missing(monkeypatch):
    from lifeos import config
    monkeypatch.delenv("LIFEOS_TESTKEY", raising=False)
    with pytest.raises(config.ConfigError):
        config.require("LIFEOS_TESTKEY")


def test_require_returns_value(monkeypatch):
    from lifeos import config
    monkeypatch.setenv("LIFEOS_TESTKEY", "value")
    assert config.require("LIFEOS_TESTKEY") == "value"


def test_auth_credentials_fail_loud(monkeypatch):
    from lifeos import config
    monkeypatch.delenv("LIFEOS_USER", raising=False)
    monkeypatch.delenv("LIFEOS_PASSWORD", raising=False)
    with pytest.raises(config.ConfigError):
        config.auth_credentials()


# ── #3: silent death is visible ───────────────────────────────────────────────
def test_started_run_without_finish_is_visible(lifeos_env):
    db = lifeos_env
    run_id = db.start_run("manual")
    # Simulate a process death: we never call finish_run.
    incomplete = db.previous_incomplete_run()
    assert incomplete is not None
    assert incomplete["id"] == run_id
    assert incomplete["finished_at"] is None


def test_finished_run_is_not_flagged_incomplete(lifeos_env):
    db = lifeos_env
    run_id = db.start_run("manual")
    db.finish_run(run_id, sources_ok=1, sources_unreachable=0, note="done")
    assert db.previous_incomplete_run() is None


def test_next_run_after_silent_death_shows_banner(lifeos_env):
    """Regression: a run that died mid-way must make the NEXT run's page say so.
    The current run's own row is unfinished at render time and must not mask it."""
    from lifeos.run import execute_run

    lifeos_env.start_run("scheduled")  # died: started, never finished
    execute_run(trigger="manual")      # the next morning's run
    html = lifeos_env.latest_snapshot()
    assert "Previous run did not complete" in html


# ── the spine: a run publishes and counts ─────────────────────────────────────
def test_execute_run_publishes_snapshot(lifeos_env):
    from lifeos.run import execute_run
    summary = execute_run(trigger="manual")
    assert summary["total"] >= 1
    assert summary["sources_ok"] >= 1
    html = lifeos_env.latest_snapshot()
    assert html is not None
    assert "LIFE" in html and "OK" in html  # heartbeat rendered


def test_failing_source_degrades_not_aborts(lifeos_env, monkeypatch):
    """A source that raises must become UNREACHABLE and the run must still finish."""
    from lifeos import run as run_mod
    from lifeos.sources import Result, UNREACHABLE

    def boom() -> Result:
        raise RuntimeError("simulated Notion outage")

    monkeypatch.setattr(run_mod, "SOURCES", [("self_check", run_mod.self_check.fetch), ("boom", boom)])
    summary = run_mod.execute_run(trigger="manual")
    assert summary["total"] == 2
    assert summary["sources_unreachable"] == 1
    assert summary["sources_ok"] == 1  # the run completed and published
    html = lifeos_env.latest_snapshot()
    assert "UNREACHABLE" in html and "boom" in html


# ── auth gate ─────────────────────────────────────────────────────────────────
def test_auth_check_accepts_and_rejects(lifeos_env):
    import base64
    from lifeos.auth import _check

    good = "Basic " + base64.b64encode(b"aman:correct horse battery staple").decode()
    bad = "Basic " + base64.b64encode(b"aman:wrong").decode()
    assert _check(good) is True
    assert _check(bad) is False
    assert _check(None) is False
    assert _check("Bearer xyz") is False
