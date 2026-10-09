"""Calendar feed — GET /api/calendar.ics?token=<CALENDAR_TOKEN>: compliance due dates, position expiries, the option
alert note and the Las Vegas trip dates as one iCalendar feed. Token required; computed on request; zero LLM spend.

Follows tests/test_compliance.py: a scratch VEGA_DB_PATH before mdo_server is imported; the endpoint test wipes the
tables it fills (the DB is shared by every test module).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("SHARE_MASTER_DATA_DIR", tempfile.mkdtemp())

import mdo_calendar as mc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── pure ──────────────────────────────────────────────────────────────────────
def test_escape_fold_and_uid():
    assert mc.ics_escape("a,b;c\\d\nnew") == "a\\,b\\;c\\\\d\\nnew"
    long = "SUMMARY:" + "x" * 200
    folded = mc.fold(long)
    assert all(len(l.encode("utf-8")) <= 75 for l in folded.split("\r\n")) and folded.replace("\r\n ", "") == long
    assert mc.fold("short") == "short"
    uni = "SUMMARY:" + "₹" * 60                                                   # multi-byte: never split inside a character
    assert "".join(mc.fold(uni).split("\r\n ")) == uni
    assert mc.uid_for("a", 1) == mc.uid_for("a", 1) != mc.uid_for("a", 2) and mc.uid_for("x").endswith("@mdo.amanagrawal")


def test_event_builders():
    comp = mc.compliance_events([
        {"item_id": "gstr3b", "label": "GSTR-3B Sep 2026", "due": "2026-10-20", "targets": ["all GST-registered entities"],
         "source": "Rule 61(1) CGST Rules", "payment": True, "extendable": True},
        {"item_id": "adt1", "label": "ADT-1", "due": "2026-10-14", "targets": ["ANS Pvt Ltd", "VWLR LLP"], "source": "s.139 CA 2013"},
        {"item_id": "bad", "label": "", "due": "2026-10-14", "targets": []},
    ])
    assert [e["summary"] for e in comp] == ["GSTR-3B Sep 2026 — all GST-registered entities", "ADT-1 — ANS Pvt Ltd, VWLR LLP"]
    assert comp[0]["alarms"] == ("-P7D", "-P1D") and comp[0]["start"] == date(2026, 10, 20) and comp[0]["end"] == date(2026, 10, 21)
    assert "Payment — your click" in comp[0]["description"] and "Rule 61(1)" in comp[0]["description"]
    pos = mc.position_expiry_events([
        {"account": "Aman", "instrument": "NIFTY 29-Dec-26 25000 CE", "expiry": "2026-12-29", "side": "BUY", "qty": 75, "product": "OVERNIGHT"},
        {"account": "Aman", "instrument": "NIFTY 29-Dec-26 25000 CE", "expiry": "2026-12-29", "side": "SELL", "qty": 75, "product": "MTF"},
        {"account": "Aman", "instrument": "POLYCAB", "expiry": None},
    ])
    assert len(pos) == 1 and pos[0]["summary"] == "Expiry: NIFTY 29-Dec-26 25000 CE (Aman)" and pos[0]["start"] == date(2026, 12, 29)
    opt = mc.option_alert_events([{"instrument": "NIFTY 29-Dec-26 25000 CE", "expiry": "29-Dec-2026", "alert_below": 30.0, "alert_above": None,
                                   "held": "AA 29,250", "note": "research only", "active": 1},
                                  {"instrument": "OLD", "expiry": "29-Dec-2026", "alert_below": 1, "active": 0}])
    assert len(opt) == 1 and opt[0]["summary"] == "Note: option alert NIFTY 29-Dec-26 25000 CE (below 30)" and "held: AA 29,250" in opt[0]["description"]
    assert mc._expiry_date("29-Dec-26") == date(2026, 12, 29) and mc._expiry_date("2026-12-29") == date(2026, 12, 29) and mc._expiry_date("x") is None


def test_trip_dates_come_from_the_brief_only():
    text = open(os.path.join(ROOT, "briefs", "TRIP_LAS_VEGAS_2026-11.md"), encoding="utf-8").read()
    assert mc.trip_dates_from_brief(text) == (date(2026, 11, 10), date(2026, 11, 12))
    assert mc.trip_dates_from_brief("# nothing dated\n10–12 Nov 2026 in the body only") is None
    evs = mc.trip_events()
    assert len(evs) == 1 and evs[0]["summary"] == "Las Vegas trip (provisional)"
    assert evs[0]["start"] == date(2026, 11, 10) and evs[0]["end"] == date(2026, 11, 13)      # DTEND exclusive
    assert "₹" not in evs[0]["description"] and "booking.com" not in evs[0]["description"].lower()   # dates only
    assert mc.trip_events("/nonexistent/brief.md") == []


def test_build_ics_is_valid():
    ics = mc.build_ics(mc.compliance_events([{"item_id": "a", "label": "ADT-1, filing; x", "due": "2026-10-14", "targets": ["G"], "source": "s"}])
                       + mc.trip_events(), datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:") and ics.endswith("END:VCALENDAR\r\n")
    assert "\n" not in ics.replace("\r\n", "") and ics.count("BEGIN:VEVENT") == ics.count("END:VEVENT") == 2
    ev = ics.split("BEGIN:VEVENT")[1]
    assert "UID:" in ev and "DTSTAMP:20261009T120000Z" in ev and "DTSTART;VALUE=DATE:20261014" in ev and "DTEND;VALUE=DATE:20261015" in ev
    assert "SUMMARY:ADT-1\\, filing\\; x — G" in ev and ev.count("BEGIN:VALARM") == 2 and "TRIGGER:-P7D" in ev and "TRIGGER:-P1D" in ev
    assert "X-WR-TIMEZONE:Asia/Kolkata" in ics
    assert mc.token_ok("abc", "abc") and not mc.token_ok("", "abc") and not mc.token_ok("abc", "") and not mc.token_ok("abd", "abc")


# ── endpoint through the real app ─────────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def test_feed_endpoint_token_and_content(monkeypatch):
    import mdo_server
    c = _client()
    c.get("/api/corp-actions/tickers")          # opens the DB and creates every table
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("share_master_positions", "compliance_entities", "compliance_reminders"):
        db.execute(f"DELETE FROM {t}")
    db.execute("INSERT INTO share_master_positions (account, instrument, side, qty, avg, ltp, pl, product, as_of) VALUES "
               "('Aman','NIFTY 29-Dec-26 25000 CE','BUY',75,100,110,750,'OVERNIGHT','2026-10-09')")
    db.execute("INSERT OR IGNORE INTO option_levels (instrument, symbol, expiry, strike, opt_type, alert_below, held, active) VALUES "
               "('NIFTY 29-Dec-26 25000 CE','NIFTY','29-Dec-2026',25000,'CE',30,'AA 29,250',1)")
    db.commit(); db.close()
    # the door: empty token = closed for everyone; wrong or missing = 401; the app key is NOT accepted in its place
    monkeypatch.setenv("CALENDAR_TOKEN", "")
    assert c.get("/api/calendar.ics?token=x").status_code == 403
    monkeypatch.setenv("CALENDAR_TOKEN", "cal-token-123")
    monkeypatch.setattr(mdo_server, "MDO_AUTH_TOKEN", "app-secret-key")
    assert c.get("/api/calendar.ics").status_code == 401
    assert c.get("/api/calendar.ics?token=wrong").status_code == 401
    assert c.get("/api/calendar.ics?key=app-secret-key").status_code == 401
    r = c.get("/api/calendar.ics?token=cal-token-123")                       # no X-MDO-Key: the middleware exempts the path
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    ics = r.text
    assert ics.startswith("BEGIN:VCALENDAR") and "END:VCALENDAR" in ics and ics.count("BEGIN:VEVENT") >= 4
    for ev in ics.split("BEGIN:VEVENT")[1:]:
        assert "UID:" in ev and "DTSTART;VALUE=DATE:" in ev and "SUMMARY:" in ev and "END:VEVENT" in ev
    unfolded = ics.replace("\r\n ", "")
    assert "SUMMARY:Expiry: NIFTY 29-Dec-26 25000 CE (Aman)" in unfolded
    assert "SUMMARY:Note: option alert NIFTY 29-Dec-26 25000 CE (below 30)" in unfolded
    assert "SUMMARY:Las Vegas trip (provisional)" in unfolded and "DTSTART;VALUE=DATE:20261110" in unfolded and "DTEND;VALUE=DATE:20261113" in unfolded
    assert "GSTR-3B" in unfolded and " — all GST-registered entities" in unfolded      # group level until entities load
    assert "TRIGGER:-P7D" in unfolded and "TRIGGER:-P1D" in unfolded
    assert "cal-token-123" not in ics and "app-secret-key" not in ics
    assert c.get("/api/calendar.ics", headers={"X-Calendar-Token": "cal-token-123"}).status_code == 200
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"]); db.execute("DELETE FROM share_master_positions"); db.commit(); db.close()


def test_calendar_wiring_env_deploy_and_doc():
    srv = open(os.path.join(ROOT, "mdo_server.py"), encoding="utf-8").read()
    assert 'request.url.path == "/api/calendar.ics"' in srv.split("async def _require_key")[1].split("supplied = (")[0]
    env = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    assert "\nCALENDAR_TOKEN=\n" in env
    assert env.index("# ── Chief of Staff") < env.index("CALENDAR_TOKEN=") < env.index("# ── Vault")   # deploy_vps.sh appends from that block
    dep = open(os.path.join(ROOT, "deploy_vps.sh"), encoding="utf-8").read()
    assert 'read_env_value CALENDAR_TOKEN' in dep and "openssl rand -hex 24" in dep and "calendar_feed_url" in dep
    assert " calendar feed : $(calendar_feed_url)" in dep                      # the summary line Aman copies into Google Calendar
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    sec = doc.split("Calendar on your phone")[1].split("\n## ")[0]
    assert "Other calendars" in sec and "From URL" in sec and "/api/calendar.ics?token=" in sec and "deploy_vps.sh" in sec
