"""Phase 2c — Gmail sweep, Calendar, and the self-referential task-health source."""

from __future__ import annotations

from datetime import datetime, timedelta

from lifeos.config import IST


# ── Gmail ─────────────────────────────────────────────────────────────────────
class _Exec:
    def __init__(self, val):
        self.val = val

    def execute(self):
        return self.val


class _Messages:
    _DATA = {
        "m1": {"payload": {"headers": [{"name": "From", "value": "gm@hotelans.in"},
                                        {"name": "Subject", "value": "Occupancy update"}]}},
        "m2": {"payload": {"headers": [{"name": "From", "value": "vimal500321@gmail.com"},
                                        {"name": "Subject", "value": "GST filing due"}]}},
        "t1": {"payload": {"headers": [{"name": "Subject",
                                        "value": "10  New Tender/s, 17-Sep-26 - Tender247"}]}},
    }

    def list(self, userId, q, maxResults):
        if "bidsnrfp" in q:
            return _Exec({"messages": [{"id": "t1"}]})
        return _Exec({"messages": [{"id": "m1"}, {"id": "m2"}]})

    def get(self, userId, id, format, metadataHeaders):
        return _Exec(self._DATA[id])


class _Users:
    def messages(self):
        return _Messages()


class _Gmail:
    def users(self):
        return _Users()


def test_parse_tender_count():
    from lifeos.sources import gmail_mail as gm
    assert gm.parse_tender_count("10  New Tender/s, 17-Sep-26 - Tender247") == 10
    assert gm.parse_tender_count("17 New Tenders today") == 17
    assert gm.parse_tender_count("no numbers here") is None


def test_gmail_fetch_counts_and_tender247(monkeypatch):
    from lifeos.sources import gmail_mail as gm
    monkeypatch.setattr(gm, "gmail_service", lambda: _Gmail())
    r = gm.fetch()
    assert r.data["key_senders"] == 2
    assert r.data["tender247_announced"] == 10
    assert "2 mail(s) from key senders" in r.summary
    assert "announced 10 new tenders" in r.summary


# ── Calendar ──────────────────────────────────────────────────────────────────
class _Events:
    def list(self, **kwargs):
        return _Exec({"items": [
            {"summary": "Marriott call", "start": {"dateTime": "2026-09-18T11:00:00+05:30"}},
            {"summary": "Site inspection", "start": {"date": "2026-09-18"}},
        ]})


class _Cal:
    def events(self):
        return _Events()


def test_calendar_fetch(monkeypatch):
    from lifeos.sources import calendar_today as cal
    monkeypatch.setattr(cal, "calendar_service", lambda: _Cal())
    r = cal.fetch()
    assert r.data["count"] == 2
    assert r.extra["rows"][0]["gutter"] == "11:00"
    assert r.extra["rows"][1]["gutter"] == "all day"


# ── task_health ───────────────────────────────────────────────────────────────
def _row(**kw):
    base = {"id": 1, "started_at": None, "finished_at": None,
            "sources_ok": None, "sources_unreachable": None}
    base.update(kw)
    return base


def test_task_health_classify_states():
    from lifeos.sources import task_health as th
    now = datetime.now(IST)

    # ALIVE: a recent completed run (excluding the current in-flight row)
    runs = [_row(id=3, finished_at=None),  # current in-flight
            _row(id=2, finished_at=(now - timedelta(hours=1)).isoformat(),
                 sources_ok=5, sources_unreachable=1)]
    assert th._classify(runs)[0] == "ALIVE"

    # SUSPECT: a prior run started and never finished
    runs = [_row(id=3, finished_at=None),
            _row(id=2, finished_at=None, started_at="2026-09-17T06:30:00+05:30")]
    assert th._classify(runs)[0] == "SUSPECT"

    # SILENT: last completed run is too old for a daily schedule
    runs = [_row(id=2, finished_at=(now - timedelta(hours=40)).isoformat(),
                 sources_ok=5, sources_unreachable=0)]
    assert th._classify(runs)[0] == "SILENT"

    # SUSPECT blind: last run had every source unreachable
    runs = [_row(id=2, finished_at=(now - timedelta(hours=1)).isoformat(),
                 sources_ok=0, sources_unreachable=6)]
    assert th._classify(runs)[0] == "SUSPECT"

    # UNVERIFIABLE: nothing on record
    assert th._classify([])[0] == "UNVERIFIABLE"
