"""Phase 4b — proactive nudges: built from results, filed once, de-duplicated."""

from __future__ import annotations

import importlib

import pytest

from lifeos.sources import Result, OK, BLOCKED, UNREACHABLE


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEOS_DB_PATH", str(tmp_path / "p4b.db"))
    monkeypatch.setenv("LIFEOS_USER", "a")
    monkeypatch.setenv("LIFEOS_PASSWORD", "b")
    from lifeos import config as cfg
    from lifeos import db
    importlib.reload(cfg)
    importlib.reload(db)
    db.init_db()
    return db


def _sample_results():
    return [
        Result(name="erp_sales", status=BLOCKED, summary="",
               extra={"rows": [
                   {"gutter": "OWED", "severity": "warning", "text": "Rukmani Infrastructure", "meta": "owed by site ERP"},
                   {"gutter": "MAP?", "severity": "warning", "text": "VWLR", "meta": "headers: A,B"},
                   {"gutter": "LIVE", "severity": "alive", "text": "Dadu Developers", "meta": "pipeline ₹1 Cr"},
               ]}),
        Result(name="deal_room_counterparties", status=OK, summary="",
               extra={"rows": [{"gutter": "12wd", "severity": "warning", "text": "Marriott", "meta": "Replied"}]}),
        Result(name="deal_room_actions", status=OK, summary="",
               extra={"rows": [
                   {"gutter": "+5d", "severity": "critical", "text": "Sign term sheet", "meta": ""},
                   {"gutter": "-3d", "severity": "quiet", "text": "Future action", "meta": ""},
               ]}),
        Result(name="compliance", status=OK, summary="",
               extra={"rows": [
                   {"gutter": "today", "severity": "critical", "text": "GSTR-3B", "meta": "VERIFY with Vimal"},
                   {"gutter": "40d", "severity": "quiet", "text": "Far compliance", "meta": ""},
               ]}),
        Result(name="tenders", status=UNREACHABLE, reason="no key"),  # ignored
    ]


def test_build_nudges_picks_real_gaps():
    from lifeos import nudge
    cands = nudge.build_nudges(_sample_results())
    fps = {c["fingerprint"] for c in cands}
    assert "erp_owed:Rukmani Infrastructure" in fps
    assert "erp_map:VWLR" in fps
    assert "silent:Marriott" in fps
    assert "overdue_action:Sign term sheet" in fps
    assert "compliance:GSTR-3B" in fps
    # LIVE entity, future action, and low-severity compliance are NOT nudged
    assert not any(c["fingerprint"].startswith("erp_owed:Dadu") for c in cands)
    assert "overdue_action:Future action" not in fps
    assert "compliance:Far compliance" not in fps


def test_file_nudges_dedupes(env, monkeypatch):
    from lifeos import nudge
    written = []
    monkeypatch.setattr(nudge.nc, "create_page", lambda ds, props: written.append(props) or {"id": "x"})

    first = nudge.file_nudges(_sample_results())
    assert first["filed"] == 5 and first["skipped"] == 0
    assert len(written) == 5
    # every filed row is Status=New, For=Aman (draft, user approves)
    assert all(p["Status"] == {"select": {"name": "New"}} for p in written)

    # second run within the window files nothing new
    second = nudge.file_nudges(_sample_results())
    assert second["filed"] == 0 and second["skipped"] == 5
    assert len(written) == 5  # no new writes


def test_scheduled_run_files_nudges_but_manual_does_not(env, monkeypatch):
    """Manual runs must not write to the Inbox; only the scheduled morning run does."""
    import lifeos.run as run
    from lifeos import nudge
    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setattr(nudge.nc, "create_page", lambda ds, props: {"id": "x"})
    # publish is best-effort and will fail without a real token; stub it out
    monkeypatch.setattr("lifeos.publish.publish", lambda *a, **k: {"today": "x", "archive": "y"})

    calls = {"n": 0}
    monkeypatch.setattr(nudge, "file_nudges", lambda results: calls.__setitem__("n", calls["n"] + 1) or {"candidates": 0, "filed": 0, "skipped": 0})

    run.execute_run(trigger="manual")
    assert calls["n"] == 0          # manual: no nudges filed
    run.execute_run(trigger="scheduled")
    assert calls["n"] == 1          # scheduled: nudges filed once
