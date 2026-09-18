"""Phase 3 — compliance/family sources, tab assignment, and run-overwrite (#7)."""

from __future__ import annotations

import importlib
from datetime import date

import pytest


@pytest.fixture()
def lifeos_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEOS_DB_PATH", str(tmp_path / "p3.db"))
    monkeypatch.setenv("LIFEOS_USER", "a")
    monkeypatch.setenv("LIFEOS_PASSWORD", "b")
    for k in ("NOTION_TOKEN", "SUPABASE_URL", "SUPABASE_KEY", "GOOGLE_CLIENT_ID"):
        monkeypatch.delenv(k, raising=False)
    from lifeos import config as cfg
    from lifeos import db
    importlib.reload(cfg)
    importlib.reload(db)
    db.init_db()
    return db


def _P(props):
    return {"created_time": "2026-09-01T00:00:00Z", "properties": props}


def _title(n, s): return {n: {"title": [{"plain_text": s}]}}
def _sel(n, s): return {n: {"select": {"name": s}}}
def _stat(n, s): return {n: {"status": {"name": s}}}
def _date(n, s): return {n: {"date": {"start": s}}}
def _txt(n, s): return {n: {"rich_text": [{"plain_text": s}]}}


def test_compliance_due_soon_and_verify_flag(monkeypatch):
    from lifeos.sources import notion_ops as no
    pages = [
        _P({**_title("Obligation", "GSTR-3B Aug"), **_stat("Status", "Not started"),
            **_date("Next Due Date", "2026-09-20"), **_sel("Priority", "Critical"),
            **_sel("Category", "GST"), **_txt("Penalty / Consequence if Missed", "₹50/day")}),
        _P({**_title("Obligation", "TDS Q2"), **_stat("Status", "Not started"),
            **_date("Next Due Date", "2026-10-31"), **_sel("Priority", "High")}),
        _P({**_title("Obligation", "Done thing"), **_stat("Status", "Done"),
            **_date("Next Due Date", "2026-09-19")}),
    ]
    monkeypatch.setattr(no.nc, "query_data_source", lambda *a, **k: pages)
    monkeypatch.setattr(no, "_today", lambda: date(2026, 9, 18))

    r = no.fetch_compliance()
    assert r.data["due_21"] == 1        # GSTR within 21d; TDS is 43d (big/High within 60)
    assert r.data["big_60"] == 1
    assert all("VERIFY with Vimal" in row["meta"] for row in r.extra["rows"])  # every row
    assert "penalty" in r.extra["rows"][0]["meta"]


def test_family_recurring_rolls_forward(monkeypatch):
    from lifeos.sources import notion_ops as no
    pages = [
        _P({**_title("Person / Occasion", "Sudha Birthday"), **_sel("Type", "Birthday"),
            **_date("Date", "1968-09-24"), **_sel("Relation", "Immediate family")}),
        _P({**_title("Person / Occasion", "Old anniversary"), **_sel("Type", "Anniversary"),
            **_date("Date", "1990-01-01")}),  # far away this year
    ]
    monkeypatch.setattr(no.nc, "query_data_source", lambda *a, **k: pages)
    monkeypatch.setattr(no, "_today", lambda: date(2026, 9, 18))
    r = no.fetch_family()
    assert r.data["count"] == 1  # birthday in 6 days; anniversary out of window
    assert r.extra["rows"][0]["gutter"] == "6d"


def test_frontier_states_are_blocked_with_words():
    from lifeos.sources import frontier
    for fn in (frontier.fetch_rnd, frontier.fetch_hiring, frontier.fetch_usa,
               frontier.fetch_expansion, frontier.fetch_hotel_pms):
        r = fn()
        assert r.status == "blocked"
        assert r.summary  # never blank
        assert "would fill it" in r.extra["rows"][0]["meta"]


def test_render_assigns_panels_to_tabs():
    from lifeos.render import render_console, TAB_OF
    from lifeos.sources import Result, OK
    from datetime import datetime
    results = [
        Result(name="erp_sales", status="blocked", summary="x", data={"owed": 3}),
        Result(name="tenders", status=OK, summary="y", data={"live": 2}),
        Result(name="deal_room_actions", status=OK, summary="z", data={"awaiting": 4},
               extra={"rows": [{"gutter": "+5d", "severity": "critical", "text": "Sign", "meta": ""}]}),
        Result(name="rnd", status="blocked", summary="r", extra={"rows": []}),
    ]
    html = render_console(results, started_at=datetime(2026, 9, 18, 6, 30),
                          previous_incomplete=False, trigger="scheduled")
    assert TAB_OF["erp_sales"] == "sales" and TAB_OF["rnd"] == "growth"
    # tiles + urgent + tab nav present
    assert "Clicks awaiting you" in html
    assert "Most urgent today" in html and "Sign" in html
    assert 'data-tab="sales"' in html


def test_two_runs_overwrite_cleanly(lifeos_env):
    """#7: run twice — the served snapshot is the second run's; runs table has two."""
    from lifeos.run import execute_run
    execute_run(trigger="manual")
    execute_run(trigger="manual")
    runs = lifeos_env.recent_runs(10)
    assert len(runs) == 2
    # latest snapshot corresponds to the newest run and renders cleanly
    assert lifeos_env.latest_snapshot() is not None
    assert lifeos_env.latest_run()["id"] == runs[0]["id"]
