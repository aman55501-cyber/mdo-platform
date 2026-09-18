"""Phase 1 acceptance — the first real sources (Notion Deal Room), fault-isolated.

Panel logic is tested against canned Notion page objects (no network). The
fault-isolation criterion (#1) is proven at the unit level: when the Notion client
raises, the source degrades to UNREACHABLE and the run still completes and publishes.
"""

from __future__ import annotations

import importlib
from datetime import date

import pytest


@pytest.fixture()
def lifeos_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFEOS_DB_PATH", str(tmp_path / "p1.db"))
    monkeypatch.setenv("LIFEOS_USER", "aman")
    monkeypatch.setenv("LIFEOS_PASSWORD", "pw")
    from lifeos import config as cfg
    from lifeos import db
    importlib.reload(cfg)
    importlib.reload(db)
    db.init_db()
    return db


def _page(props: dict, created="2026-09-01T00:00:00.000Z") -> dict:
    return {"created_time": created, "properties": props}


def _title(name, s):
    return {name: {"title": [{"plain_text": s}]}}


def _sel(name, s):
    return {name: {"select": {"name": s}}}


def _date(name, s):
    return {name: {"date": {"start": s}}}


def _chk(name, b):
    return {name: {"checkbox": b}}


def _txt(name, s):
    return {name: {"rich_text": [{"plain_text": s}]}}


FIXED_TODAY = date(2026, 9, 18)


def test_actions_awaiting_clicks_and_overdue(monkeypatch):
    from lifeos.sources import deal_room as dr

    pages = [
        _page({**_title("Step", "Sign term sheet"), **_sel("Status", "In progress"),
               **_date("Due", "2026-09-10"), **_chk("My click", False),
               **_sel("Owner", "Aman"), **_sel("Phase", "3 Terms")}),
        _page({**_title("Step", "Board note"), **_sel("Status", "Done"),
               **_date("Due", "2026-09-05"), **_chk("My click", False)}),
        _page({**_title("Step", "Call lawyer"), **_sel("Status", "Waiting on other side"),
               **_date("Due", "2026-09-25"), **_chk("My click", False)}),
        _page({**_title("Step", "Wire advance"), **_sel("Status", "In progress"),
               **_date("Due", "2026-09-18"), **_chk("My click", True)}),
    ]
    monkeypatch.setattr(dr.nc, "query_data_source", lambda *_a, **_k: pages)
    monkeypatch.setattr(dr, "_today", lambda: FIXED_TODAY)

    r = dr.fetch_actions()
    assert r.status in ("ok", "nil")
    # Done row excluded; checked-click row excluded -> 2 awaiting.
    rows = r.extra["rows"]
    assert [row["text"] for row in rows] == ["Sign term sheet", "Call lawyer"]
    # Most overdue first, with correct gutter + severity.
    assert rows[0]["gutter"] == "+8d" and rows[0]["severity"] == "critical"
    assert rows[1]["gutter"] == "-7d" and rows[1]["severity"] == "quiet"
    assert r.data["overdue"] == 1


def test_counterparties_silent_detection(monkeypatch):
    from lifeos.sources import deal_room as dr

    pages = [
        _page({**_title("Party", "Marriott"), **_sel("Stage", "Replied"),
               **_date("Last touch", "2026-09-01"), **_txt("Next action", "Send teaser v2")}),
        _page({**_title("Party", "Radisson"), **_sel("Stage", "Term sheet"),
               **_date("Last touch", "2026-09-17")}),
        _page({**_title("Party", "Ginger"), **_sel("Stage", "Dropped"),
               **_date("Last touch", "2026-01-01")}),
    ]
    monkeypatch.setattr(dr.nc, "query_data_source", lambda *_a, **_k: pages)
    monkeypatch.setattr(dr, "_today", lambda: FIXED_TODAY)

    r = dr.fetch_counterparties()
    assert r.data["live"] == 2          # Dropped excluded
    assert r.data["silent"] == 1        # only Marriott is silent >7 working days
    assert r.extra["rows"][0]["text"] == "Marriott"
    assert "Dropped: 1" in r.summary    # stage line still reports the dropped one


def test_missing_token_degrades_to_unreachable_and_run_completes(lifeos_env, monkeypatch):
    """#1 at unit level: no NOTION_TOKEN -> Notion panels UNREACHABLE, run still finishes."""
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    from lifeos.run import execute_run

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    summary = execute_run(trigger="manual")
    # The two Notion panels are UNREACHABLE; self_check ok and erp_sales blocked/owed
    # both count as "reporting"; the run still published regardless of how many
    # sources are unreachable.
    assert summary["sources_unreachable"] >= 2
    assert summary["sources_ok"] >= 1
    html = lifeos_env.latest_snapshot()
    assert "UNREACHABLE" in html and "deal_room_actions" in html
    assert "NOTION_TOKEN not set" in html
