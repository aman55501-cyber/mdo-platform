"""compliance-reminder — statutory calendar as data, 7-day WhatsApp reminders, zero LLM spend.

Aman, chat 2026-10-09: "the compliance due dates are the governmentally fixed dates and i need the reminder at
least a week before." Nothing here touches the network: the WhatsApp send is canned. Follows tests/test_wa_sweep.py:
a scratch VEGA_DB_PATH is set before mdo_server is imported; the endpoint tests wipe the compliance tables (the DB
is shared by every test module).
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("SHARE_MASTER_DATA_DIR", tempfile.mkdtemp())

import pytest  # noqa: E402
import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_compliance as mc  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT = {"id": "compliance-reminder", "provider": "none", "model": "none"}
FOOTER = "Vimal Agrawal & Co (CA) handles filings; your click only for payments"


def _ist(y, m, d, h=8, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=IST)


# ── pure: the calendar ────────────────────────────────────────────────────────
def test_calendar_loads_and_every_row_has_a_source_and_entity_kinds():
    cal = mc.load_calendar()
    assert cal["calendar"] == "IN-FY2026-27" and cal["footer"] == FOOTER
    assert set(cal["entity_kinds"]) == set(mc.KINDS) == {"pvt_ltd", "llp", "partnership", "proprietorship", "individual"}
    rows = cal["items"]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)) >= 24
    for r in rows:
        assert r["source"].strip() and len(r["source"]) > 20, r["id"]            # the rule or section it comes from
        assert r["applies_to"] and set(r["applies_to"]) <= set(mc.KINDS), r["id"]
        assert isinstance(r["extendable"], bool), r["id"]
        assert r.get("group"), r["id"]
        if r["cadence"] == "monthly":
            assert 1 <= int(r["day"]) <= 28
        else:
            assert isinstance(r.get("dates"), list)
            for sp in r["dates"]:
                mm, dd = (int(x) for x in sp["mmdd"].split("-"))
                assert 1 <= mm <= 12 and 1 <= dd <= 31
    # Aman's list, by id and statutory day
    by = {r["id"]: r for r in rows}
    assert by["gstr1"]["day"] == 11 and by["gstr3b"]["day"] == 20 and by["tds-deposit"]["day"] == 7
    assert by["pf-ecr"]["day"] == 15 and by["esi"]["day"] == 15
    assert [d["mmdd"] for d in by["tds-return"]["dates"]] == ["07-31", "10-31", "01-31", "05-31"]
    assert [d["mmdd"] for d in by["advance-tax"]["dates"]] == ["06-15", "09-15", "12-15", "03-15"]
    annual = {"itr-nonaudit": "07-31", "tax-audit-report": "09-30", "itr-audit": "10-31", "itr-tp": "11-30", "gstr9": "12-31",
              "dir3-kyc": "09-30", "aoc-4": "10-29", "mgt-7": "11-28", "dpt-3": "06-30", "llp-11": "05-30", "llp-8": "10-30",
              "adt-1": "10-14", "agm": "09-30"}
    for k, mmdd in annual.items():
        assert by[k]["dates"][0]["mmdd"] == mmdd, k
    assert [d["mmdd"] for d in by["msme-1"]["dates"]] == ["04-30", "10-31"]
    # who each binds
    assert by["aoc-4"]["applies_to"] == ["pvt_ltd"] and by["llp-11"]["applies_to"] == ["llp"] and by["dir3-kyc"]["applies_to"] == ["individual"]
    assert "partnership" in by["itr-nonaudit"]["applies_to"] and "individual" in by["itr-nonaudit"]["applies_to"]
    assert "pvt_ltd" not in by["itr-nonaudit"]["applies_to"] and by["itr-nonaudit"]["requires_not"] == "audit_case"
    assert by["itr-audit"]["always_for"] == ["pvt_ltd"] and by["itr-audit"]["requires"] == "audit_case"
    # extendable only where a notification can move the date; payments never
    for k in ("tds-deposit", "pf-ecr", "esi", "advance-tax"):
        assert by[k]["extendable"] is False and by[k]["payment"] is True, k
    for k in ("gstr1", "gstr3b", "itr-nonaudit", "itr-audit", "aoc-4", "mgt-7", "dir3-kyc", "gstr9", "tds-return"):
        assert by[k]["extendable"] is True, k
    # professional tax: no date on purpose, never a group reminder, says [UNVERIFIED]
    assert by["professional-tax"]["dates"] == [] and by["professional-tax"]["remind_group"] is False
    assert "[UNVERIFIED]" in by["professional-tax"]["source"]
    # a row without a source is refused
    bad = os.path.join(tempfile.mkdtemp(), "bad.json")
    open(bad, "w").write('{"items": [{"id": "x", "item": "X", "cadence": "monthly", "day": 1, "applies_to": ["llp"]}]}')
    with pytest.raises(ValueError):
        mc.load_calendar(bad)


def test_fy_labels_and_period_fill():
    assert mc.fy_start_year(date(2026, 3, 31)) == 2025 and mc.fy_start_year(date(2026, 4, 1)) == 2026
    assert mc.fy_label(2026) == "FY2026-27" and mc.ay_label(2025) == "AY2026-27"
    assert mc.fill("ITR for {fy_prev} ({ay}) in {fy}", date(2026, 7, 31)) == "ITR for FY2025-26 (AY2026-27) in FY2026-27"
    assert mc.fill("{month}", date(2026, 10, 11), date(2026, 9, 1)) == "Sep 2026"
    assert mc.fmt_day(date(2026, 10, 11)) == "Sun 11 Oct" and mc.fmt_day("2027-01-07") == "Thu 07 Jan"
    assert mc.stage_for(0) == "day" and mc.stage_for(1) == "eve" and mc.stage_for(2) == "week" and mc.stage_for(7) == "week"
    assert mc.stage_for(8) is None and mc.stage_for(-1) is None


def test_upcoming_window_math_across_month_and_year_end():
    cal = mc.load_calendar()
    pick = lambda occs: [(o["due"], o["item_id"]) for o in occs]
    # 9 Oct 2026 + 7 → GSTR-1 (11th), ADT-1 (14 Oct), PF + ESI (15th); GSTR-3B (20th) is outside
    occs = mc.expand(cal, date(2026, 10, 9), date(2026, 10, 16))
    assert pick(occs) == [("2026-10-11", "gstr1"), ("2026-10-13", "gstr1-qrmp"), ("2026-10-14", "adt-1"),
                          ("2026-10-15", "pf-ecr"), ("2026-10-15", "esi")]
    assert occs[0]["label"] == "GSTR-1 for Sep 2026" and occs[3]["label"] == "PF ECR + contribution for Sep 2026"
    # year end: GSTR-9 on 31 Dec, then the January TDS deposit for December
    occs = mc.expand(cal, date(2026, 12, 28), date(2027, 1, 7))
    assert pick(occs) == [("2026-12-31", "gstr9"), ("2027-01-07", "tds-deposit")]
    assert occs[0]["label"] == "GSTR-9 (and 9C where turnover > ₹5 cr) for FY2025-26"
    assert occs[1]["label"] == "TDS/TCS deposit for Dec 2026"
    # 7 days exactly: the window end is inclusive, the day after is not
    assert pick(mc.expand(cal, date(2026, 12, 31), date(2027, 1, 7)))[-1] == ("2027-01-07", "tds-deposit")
    assert pick(mc.expand(cal, date(2026, 12, 31), date(2027, 1, 6))) == [("2026-12-31", "gstr9")]
    # FY roll: March TDS has its own 30 April date, TCS for March stays on 7 April; Q4 labels name the previous FY
    occs = mc.expand(cal, date(2027, 4, 1), date(2027, 4, 30))
    labels = {(o["due"], o["label"]) for o in occs}
    assert ("2027-04-07", "TCS deposit for Mar 2027") in labels
    assert ("2027-04-30", "TDS deposit for Mar 2027 (March TDS has its own date)") in labels
    assert ("2027-04-13", "GSTR-1 (QRMP) for Q4 (Jan–Mar) FY2026-27") in labels
    assert ("2027-04-30", "MSME-1 for Oct–Mar (FY2026-27) — dues to MSME suppliers outstanding over 45 days") in labels
    assert [o["label"] for o in occs if o["item_id"] == "tds-deposit"] == ["TCS deposit for Mar 2027", "TDS deposit for Mar 2027 (March TDS has its own date)"]
    # end of a 31-day month → short month: 31 Jan + 7 = 7 Feb catches the Jan TDS deposit; Feb has no 30th problem
    assert pick(mc.expand(cal, date(2027, 1, 31), date(2027, 2, 7))) == [("2027-01-31", "tds-return"), ("2027-02-07", "tds-deposit")]
    # annual rows repeat each year with the FY rolled
    itr = [o for o in mc.expand(cal, date(2026, 4, 1), date(2028, 3, 31)) if o["item_id"] == "itr-nonaudit"]
    assert [(o["due"], o["label"]) for o in itr] == [
        ("2026-07-31", "ITR for FY2025-26 (AY2026-27) — individuals, proprietorships, firms and LLPs not under audit"),
        ("2027-07-31", "ITR for FY2026-27 (AY2027-28) — individuals, proprietorships, firms and LLPs not under audit")]
    # a professional-tax row has no date, so it never appears
    assert not any(o["item_id"] == "professional-tax" for o in mc.expand(cal, date(2026, 4, 1), date(2027, 3, 31)))


def test_targets_group_level_until_entities_then_entity_level():
    cal = mc.load_calendar()
    occs = {o["item_id"]: o for o in mc.expand(cal, date(2026, 10, 1), date(2026, 10, 31))}
    # no entities → the group label; calendar-only rows (QRMP) bind nobody at group level
    assert mc.targets_for(occs["gstr1"], []) == ["all GST-registered entities (monthly filers)"]
    assert mc.targets_for(occs["aoc-4"], []) == ["all private limited companies"]
    assert mc.targets_for(occs["gstr1-qrmp"], []) == []
    ents = [
        {"name": "Alpha Pvt Ltd", "kind": "pvt_ltd", "gst_registered": 1, "tds_deductor": 1, "audit_case": 0, "pf_esi": 1, "gst_qrmp": 0, "active": 1},
        {"name": "Beta LLP", "kind": "llp", "gst_registered": 0, "tds_deductor": 0, "audit_case": 1, "pf_esi": 0, "gst_qrmp": 0, "active": 1},
        {"name": "Gamma Traders", "kind": "proprietorship", "gst_registered": 1, "tds_deductor": 0, "audit_case": 0, "pf_esi": 0, "gst_qrmp": 1, "active": 1},
        {"name": "Old Co", "kind": "pvt_ltd", "gst_registered": 1, "tds_deductor": 1, "audit_case": 0, "pf_esi": 0, "gst_qrmp": 0, "active": 0},
    ]
    assert mc.targets_for(occs["gstr1"], ents) == ["Alpha Pvt Ltd", "Gamma Traders"]          # inactive Old Co is out
    assert mc.targets_for(occs["gstr1-qrmp"], ents) == ["Gamma Traders"]
    assert mc.targets_for(occs["aoc-4"], ents) == ["Alpha Pvt Ltd"]
    assert mc.targets_for(occs["llp-8"], ents) == ["Beta LLP"]
    assert mc.targets_for(occs["tds-return"], ents) == ["Alpha Pvt Ltd"]
    assert mc.targets_for(occs["pf-ecr"], ents) == ["Alpha Pvt Ltd"]
    # ITR: the company always on 31 Oct, the audited LLP too; the non-audit proprietorship is a 31 Jul case
    assert mc.targets_for(occs["itr-audit"], ents) == ["Alpha Pvt Ltd", "Beta LLP"]
    jul = {o["item_id"]: o for o in mc.expand(cal, date(2026, 7, 31), date(2026, 7, 31))}
    assert mc.targets_for(jul["itr-nonaudit"], ents) == ["Gamma Traders"]
    # advance tax binds everyone active
    sep = {o["item_id"]: o for o in mc.expand(cal, date(2026, 9, 15), date(2026, 9, 15))}
    assert mc.targets_for(sep["advance-tax"], ents) == ["Alpha Pvt Ltd", "Beta LLP", "Gamma Traders"]


def test_message_text_grouped_by_date_with_footer():
    cal = mc.load_calendar()
    today = date(2026, 10, 9)
    occs = [dict(o, targets=mc.targets_for(o, [])) for o in mc.expand(cal, today, today + timedelta(days=7))]
    occs = [o for o in occs if o["targets"]]
    assert mc.message_text(occs, today) == (
        "Compliance · due in the next 7 days (Fri 09 Oct – Fri 16 Oct)\n"
        "Sun 11 Oct · GSTR-1 for Sep 2026 — all GST-registered entities (monthly filers)\n"
        "Wed 14 Oct · ADT-1 auditor appointment (15 days after the 30 Sep AGM; appointment years only) — all private limited companies (appointment years only)\n"
        "Thu 15 Oct · PF ECR + contribution for Sep 2026 (payment) — all employers covered by EPF · ESI contribution for Sep 2026 (payment) — all employers covered by ESI\n"
        + FOOTER)
    # entity-level: names instead of the group
    occs2 = [dict(occs[0], targets=["Alpha Pvt Ltd", "Gamma Traders"])]
    assert mc.message_text(occs2, today).splitlines()[1] == "Sun 11 Oct · GSTR-1 for Sep 2026 — Alpha Pvt Ltd, Gamma Traders"
    # the Monday line, empty and not
    monday = date(2026, 10, 12)
    nxt = {"label": "GSTR-3B for Sep 2026", "due": "2026-10-20"}
    assert mc.week_text([], monday, nxt) == "Compliance · this week (Mon 12 Oct – Sun 18 Oct): nothing due · next: GSTR-3B for Sep 2026 on Tue 20 Oct"
    wk = mc.week_text([o for o in occs if o["due"] >= "2026-10-12"], monday, None)
    assert wk.startswith("Compliance · this week (Mon 12 Oct – Sun 18 Oct):\nWed 14 Oct · ADT-1") and wk.endswith(FOOTER)


# ── endpoints through the real app ───────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _wipe():
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("compliance_entities", "compliance_reminders"):
        db.execute(f"DELETE FROM {t}")
    db.commit(); db.close()


class _Sent:
    def __init__(self):
        self.texts, self.ok = [], True

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": self.ok} if self.ok else {"sent": False, "reason": "bridge down"}


def _setup(monkeypatch):
    import mdo_server
    c = _client()
    c.get("/api/compliance/entities")          # opens the DB and creates the tables
    _wipe()
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    return c, sent


def _run(c, mode, now):
    r = c.post("/api/compliance/run", json={"mode": mode, "now": now.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()


def test_calendar_and_upcoming_endpoints(monkeypatch):
    c, _ = _setup(monkeypatch)
    cal = c.get("/api/compliance/calendar").json()
    assert cal["calendar"] == "IN-FY2026-27" and cal["count"] == len(cal["items"]) >= 24 and all(r["source"] for r in cal["items"])
    up = c.get("/api/compliance/upcoming?days=30&now=2026-10-09T08:00:00+05:30").json()
    assert up["entities_loaded"] is False and up["level"] == "group" and up["note"] == "entity list not loaded" and up["footer"] == FOOTER
    assert [(i["due"], i["item_id"]) for i in up["items"]] == [
        ("2026-10-11", "gstr1"), ("2026-10-14", "adt-1"), ("2026-10-15", "pf-ecr"), ("2026-10-15", "esi"), ("2026-10-20", "gstr3b"),
        ("2026-10-29", "aoc-4"), ("2026-10-30", "llp-8"), ("2026-10-31", "tds-return"), ("2026-10-31", "itr-audit"), ("2026-10-31", "msme-1"),
        ("2026-11-07", "tds-deposit")]
    assert up["items"][0]["targets"] == ["all GST-registered entities (monthly filers)"] and up["items"][0]["days_left"] == 2
    assert up["items"][0]["stage"] == "week" and up["items"][4]["stage"] is None and up["items"][0]["reminders"] == []
    assert all(i["source"] for i in up["items"])
    # entity upsert: kinds validated, flags default 0, name is the key (case-insensitive), source kept
    r = c.post("/api/compliance/entities", json={"name": "Alpha Pvt Ltd", "kind": "company"})
    assert r.status_code == 400 and "kind must be one of" in r.json()["detail"]
    r = c.post("/api/compliance/entities", json=[{"name": "Alpha Pvt Ltd", "kind": "pvt_ltd", "gst_registered": True, "tds_deductor": 1,
                                                  "source": "test registry"}, {"name": "Beta LLP", "kind": "llp"}])
    assert r.status_code == 200 and r.json()["upserted"] == ["Alpha Pvt Ltd", "Beta LLP"]
    r = c.post("/api/compliance/entities", json={"name": "alpha pvt ltd", "pf_esi": "yes"})
    ents = {e["name"]: e for e in r.json()["entities"]}
    assert set(ents) == {"Alpha Pvt Ltd", "Beta LLP"}
    assert ents["Alpha Pvt Ltd"]["gst_registered"] is True and ents["Alpha Pvt Ltd"]["pf_esi"] is True and ents["Alpha Pvt Ltd"]["source"] == "test registry"
    assert ents["Beta LLP"]["gst_registered"] is False and ents["Beta LLP"]["active"] is True
    g = c.get("/api/compliance/entities").json()
    assert g["loaded"] is True and g["kinds"] == list(mc.KINDS) and g["note"] == ""
    up = c.get("/api/compliance/upcoming?days=30&now=2026-10-09T08:00:00+05:30").json()
    assert up["entities_loaded"] is True and up["level"] == "entity" and up["entity_count"] == 2
    assert [(i["due"], i["item_id"], i["targets"]) for i in up["items"]] == [
        ("2026-10-11", "gstr1", ["Alpha Pvt Ltd"]), ("2026-10-14", "adt-1", ["Alpha Pvt Ltd"]), ("2026-10-15", "pf-ecr", ["Alpha Pvt Ltd"]),
        ("2026-10-15", "esi", ["Alpha Pvt Ltd"]), ("2026-10-20", "gstr3b", ["Alpha Pvt Ltd"]), ("2026-10-29", "aoc-4", ["Alpha Pvt Ltd"]),
        ("2026-10-30", "llp-8", ["Beta LLP"]), ("2026-10-31", "tds-return", ["Alpha Pvt Ltd"]), ("2026-10-31", "itr-audit", ["Alpha Pvt Ltd"]),
        ("2026-10-31", "msme-1", ["Alpha Pvt Ltd"]), ("2026-11-07", "tds-deposit", ["Alpha Pvt Ltd"])]


def test_daily_run_pushes_one_message_once_per_stage_and_heartbeats_when_empty(monkeypatch):
    c, sent = _setup(monkeypatch)
    # Fri 9 Oct: GSTR-1 in 2 days, ADT-1 in 5, PF/ESI in 6 → one message, four group reminders at stage "week"
    res = _run(c, "daily", _ist(2026, 10, 9))
    assert res["due"] == 4 and res["reminders"] == 4 and res["pushed"] == 1 and res["entities_loaded"] is False
    assert res["line"] == "compliance-reminder: 4 items due in 7 days (4 reminders, 1 message pushed) · entity list not loaded — group level"
    assert len(sent.texts) == 1 and sent.texts[0] == res["text"]
    assert sent.texts[0].splitlines()[0] == "Compliance · due in the next 7 days (Fri 09 Oct – Fri 16 Oct)"
    assert sent.texts[0].splitlines()[1] == "Sun 11 Oct · GSTR-1 for Sep 2026 — all GST-registered entities (monthly filers)"
    assert sent.texts[0].splitlines()[-1] == FOOTER
    rows = c.get("/api/compliance/reminders").json()["reminders"]
    assert len(rows) == 4 and all(r["status"] == "sent" and r["sent_at"] and r["remind_on"] == "2026-10-09" and r["stage"] == "week" for r in rows)
    assert {(r["entity_or_group"], r["item_id"], r["due_date"]) for r in rows} == {
        ("all GST-registered entities (monthly filers)", "gstr1", "2026-10-11"), ("all private limited companies (appointment years only)", "adt-1", "2026-10-14"),
        ("all employers covered by EPF", "pf-ecr", "2026-10-15"), ("all employers covered by ESI", "esi", "2026-10-15")}
    # the same morning again (or a re-run at noon): nothing new → no push, heartbeat still files
    res = _run(c, "daily", _ist(2026, 10, 9, 12))
    assert res["pushed"] == 0 and res["reminders"] == 0 and len(sent.texts) == 1
    assert res["line"].startswith("compliance-reminder: 4 items due in 7 days (all already reminded at this stage, nothing pushed)")
    # Sat 10 Oct: GSTR-1 is tomorrow → the "eve" stage for it, one message listing everything in the window (GSTR-3B 20 Oct is outside)
    res = _run(c, "daily", _ist(2026, 10, 10))
    assert res["reminders"] == 1 and res["pushed"] == 1 and len(sent.texts) == 2
    assert "Sun 11 Oct · GSTR-1 for Sep 2026" in sent.texts[1] and "Sat 17 Oct" in sent.texts[1].splitlines()[0] and "GSTR-3B" not in sent.texts[1]
    # Sun 11 Oct: due day → "day" stage push
    res = _run(c, "daily", _ist(2026, 10, 11))
    assert res["reminders"] == 1 and len(sent.texts) == 3
    stages = {(r["item_id"], r["stage"]) for r in c.get("/api/compliance/reminders").json()["reminders"]}
    assert {("gstr1", "week"), ("gstr1", "eve"), ("gstr1", "day")} <= stages
    # Mon 12 Oct: GSTR-1 gone; nothing new reaches a stage (ADT-1 is in 2 days = still "week", already sent) → no push
    res = _run(c, "daily", _ist(2026, 10, 12))
    assert res["pushed"] == 0 and len(sent.texts) == 3 and res["due"] == 3
    # Tue 13 Oct: ADT-1 is tomorrow (eve) and GSTR-3B 20 Oct is exactly 7 days out (week) → one push, two reminders;
    # mark ADT-1 done → Wed 14 Oct no "day" push for it
    res = _run(c, "daily", _ist(2026, 10, 13))
    assert res["reminders"] == 2 and len(sent.texts) == 4 and "Tue 20 Oct · GSTR-3B for Sep 2026 (payment)" in sent.texts[3]
    rid = [r for r in c.get("/api/compliance/reminders").json()["reminders"] if r["item_id"] == "adt-1" and r["stage"] == "eve"][0]["id"]
    r = c.post(f"/api/compliance/reminders/{rid}/done")
    assert r.status_code == 200 and r.json()["status"] == "done" and r.json()["item_id"] == "adt-1"
    assert all(r["status"] == "done" for r in c.get("/api/compliance/reminders?status=done").json()["reminders"])
    assert c.post("/api/compliance/reminders/999999/done").status_code == 404
    res = _run(c, "daily", _ist(2026, 10, 14))
    assert res["reminders"] == 2 and len(sent.texts) == 5                    # PF + ESI eve: two reminders, still ONE message
    assert "ADT-1" not in sent.texts[4] and "Thu 15 Oct · PF ECR" in sent.texts[4]
    up = c.get("/api/compliance/upcoming?days=30&now=2026-10-14T08:00:00+05:30").json()
    adt = [i for i in up["items"] if i["item_id"] == "adt-1"][0]
    assert adt["done"] is True and adt["done_for"] == ["all private limited companies (appointment years only)"]
    # a bridge that is down: the row stays queued (no sent_at), the run says so, and the next run retries the push
    sent.ok = False
    res = _run(c, "daily", _ist(2026, 10, 15))
    assert res["push_failed"] == 1 and res["pushed"] == 0 and "push NOT delivered" in res["line"]
    queued = [r for r in c.get("/api/compliance/reminders?status=queued").json()["reminders"]]
    assert {(r["item_id"], r["stage"]) for r in queued} == {("pf-ecr", "day"), ("esi", "day")}
    sent.ok = True
    res = _run(c, "daily", _ist(2026, 10, 15, 9))
    assert res["pushed"] == 1 and res["reminders"] == 2 and not c.get("/api/compliance/reminders?status=queued").json()["reminders"]
    # nothing due in 7 days (Sun 29 Nov → Sun 6 Dec; MGT-7 was 28 Nov, December TDS deposit is 7 Dec): no push, the heartbeat names the next item
    n = len(sent.texts)
    res = _run(c, "daily", _ist(2026, 11, 29))
    assert res["due"] == 0 and res["pushed"] == 0 and res["text"] == "" and len(sent.texts) == n
    assert res["line"] == "compliance-reminder: 0 items due in 7 days, next: TDS/TCS deposit for Nov 2026 on Mon 07 Dec · entity list not loaded — group level"
    # a bad mode is refused
    assert c.post("/api/compliance/run", json={"mode": "hourly"}).status_code == 400


def test_entity_level_messages_and_the_weekly_line(monkeypatch):
    c, sent = _setup(monkeypatch)
    c.post("/api/compliance/entities", json=[
        {"name": "Alpha Pvt Ltd", "kind": "pvt_ltd", "gst_registered": 1, "tds_deductor": 1, "pf_esi": 1, "source": "test"},
        {"name": "Gamma Traders", "kind": "proprietorship", "gst_registered": 1, "source": "test"},
        {"name": "Beta LLP", "kind": "llp", "source": "test"}])
    res = _run(c, "daily", _ist(2026, 10, 9))
    assert res["entities_loaded"] is True and "entity list not loaded" not in res["line"]
    assert res["line"] == "compliance-reminder: 4 items due in 7 days (5 reminders, 1 message pushed)"     # GSTR-1 ×2 entities + ADT-1 + PF + ESI
    lines = sent.texts[0].splitlines()
    assert lines[1] == "Sun 11 Oct · GSTR-1 for Sep 2026 — Alpha Pvt Ltd, Gamma Traders"
    assert lines[2].startswith("Wed 14 Oct · ADT-1") and lines[2].endswith("— Alpha Pvt Ltd")
    assert lines[3] == "Thu 15 Oct · PF ECR + contribution for Sep 2026 (payment) — Alpha Pvt Ltd · ESI contribution for Sep 2026 (payment) — Alpha Pvt Ltd"
    rows = c.get("/api/compliance/reminders").json()["reminders"]
    assert sorted(r["entity_or_group"] for r in rows if r["item_id"] == "gstr1") == ["Alpha Pvt Ltd", "Gamma Traders"]
    # "done" for one entity leaves the other's reminders alive
    rid = [r for r in rows if r["item_id"] == "gstr1" and r["entity_or_group"] == "Alpha Pvt Ltd"][0]["id"]
    c.post(f"/api/compliance/reminders/{rid}/done")
    res = _run(c, "daily", _ist(2026, 10, 10))
    assert res["reminders"] == 1 and "Sun 11 Oct · GSTR-1 for Sep 2026 — Gamma Traders" in sent.texts[-1]
    # Monday line, with items; and an empty week names the next item — pushed either way
    res = _run(c, "weekly", _ist(2026, 10, 12, 8, 5))
    assert res["pushed"] == 1 and res["due"] == 3 and res["line"] == "compliance-reminder weekly: 3 items this week (pushed)"
    assert sent.texts[-1].startswith("Compliance · this week (Mon 12 Oct – Sun 18 Oct):\nWed 14 Oct · ADT-1") and sent.texts[-1].endswith(FOOTER)
    res = _run(c, "weekly", _ist(2026, 11, 30, 8, 5))
    assert res["pushed"] == 1 and res["due"] == 0
    assert sent.texts[-1] == "Compliance · this week (Mon 30 Nov – Sun 06 Dec): nothing due · next: TDS/TCS deposit for Nov 2026 on Mon 07 Dec"
    assert res["line"] == "compliance-reminder weekly: 0 items this week (pushed)"


# ── the runner in mdo_agent ───────────────────────────────────────────────────
class _Fake:
    def __init__(self, client):
        self.client, self.reports = client, []

    def api(self, path, method="GET", body=None, timeout=30):
        if path == "/api/agent/report":
            self.reports.append(body)
            return {"stored": True, "report_id": len(self.reports)}
        if path.startswith("/api/compliance/"):
            r = self.client.post(path, json=body) if method == "POST" else self.client.get(path)
            assert r.status_code == 200, r.text
            return r.json()
        raise AssertionError(f"unexpected call {method} {path}")


def test_run_compliance_reminder_heartbeats_every_run_even_when_empty(monkeypatch):
    c, sent = _setup(monkeypatch)
    fake = _Fake(c)
    monkeypatch.setattr(ag, "api", fake.api)
    monkeypatch.setattr(ag, "RUN_ARGS", [])
    # nothing due → no push, heartbeat with "next: …"
    assert ag.run_compliance_reminder(BOT, "none", "daily", now=_ist(2026, 11, 29)) == 0
    hb = fake.reports[-1]
    assert hb["heartbeat"] is True and hb["bot"] == "compliance-reminder" and hb["status"] == "clean" and sent.texts == []
    assert hb["summary"] == "compliance-reminder: 0 items due in 7 days, next: TDS/TCS deposit for Nov 2026 on Mon 07 Dec · entity list not loaded — group level"
    # something due → one push, heartbeat with counts
    assert ag.run_compliance_reminder(BOT, "none", "daily", now=_ist(2026, 10, 9)) == 0
    assert fake.reports[-1]["summary"] == "compliance-reminder: 4 items due in 7 days (4 reminders, 1 message pushed) · entity list not loaded — group level"
    assert len(sent.texts) == 1
    # weekly from argv
    monkeypatch.setattr(ag, "RUN_ARGS", ["weekly"])
    assert ag.run_compliance_reminder(BOT, "none", "daily", now=_ist(2026, 10, 12, 8, 5)) == 0
    assert fake.reports[-1]["summary"] == "compliance-reminder weekly: 3 items this week (pushed) · entity list not loaded — group level"
    # bridge down → warning, never silent
    sent.ok = False
    assert ag.run_compliance_reminder(BOT, "none", "daily", now=_ist(2026, 10, 19, 8, 5), mode="weekly") == 0
    assert fake.reports[-1]["status"] == "warning" and "push NOT delivered" in fake.reports[-1]["summary"]
    # unknown mode
    assert ag.run_compliance_reminder(BOT, "none", "daily", now=_ist(2026, 10, 9), mode="hourly") == 2
    assert fake.reports[-1]["status"] == "error"


def test_compliance_reminder_is_wired_in_dispatch_fleet_cron_brief_and_page():
    assert ag.CUSTOM_BOTS["compliance-reminder"] is ag.run_compliance_reminder
    fleet = yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))
    bot = ag.find_bot(fleet, "compliance-reminder")
    assert bot["enabled"] is True and bot["provider"] == "none" and bot["model"] == "none" and bot["runs_on"] == "vps-cron"
    assert bot["objective"] == "never miss a statutory date; Aman hears a week before"
    assert bot["command"] == "docker compose exec -T backend python mdo_agent.py compliance-reminder"
    assert bot["command_weekly"].endswith("compliance-reminder weekly")
    assert isinstance(bot["heartbeat"], str) and "0 items due in 7 days, next: <item> on <date>" in bot["heartbeat"]
    assert {"purpose", "thinks", "works", "limits", "minimum_output", "rules"} <= set(bot["charter"])
    rules = " ".join(bot["charter"]["rules"]).lower()
    assert "no llm" in rules and "never invents" in rules and "every run reports" in rules and "no questions" in rules
    assert bot["serves"] == [] and "2026-10-09" in bot["notes"]
    # §8 cron block: daily 02:30 UTC, Monday 02:35 UTC
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    block = doc[doc.index("# MDO fleet — one line per bot"):]
    block = block[:block.index("```")]
    lines = [ln.split()[:5] for ln in block.splitlines() if "mdo_agent.py compliance-reminder" in ln]
    assert lines == [["30", "2", "*", "*", "*"], ["35", "2", "*", "*", "1"]]
    weekly = [ln for ln in block.splitlines() if "compliance-reminder weekly" in ln]
    assert len(weekly) == 1 and weekly[0].split()[:5] == ["35", "2", "*", "*", "1"]
    # the brief: questions withdrawn, nothing invented
    brief = open(os.path.join(ROOT, "briefs", "COMPLIANCE_CALENDAR_REVIEW.md"), encoding="utf-8").read()
    assert "## 3. Questions withdrawn" in brief and "withdrawn on Aman's word, 2026-10-09" in brief
    assert "## 3. Questions for Aman" not in brief and "entity list with kinds" in brief and "A15" in brief
    # nothing new in .env.example, the page has the card with a loading state
    env = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    assert "COMPLIANCE" not in env
    page = open(os.path.join(ROOT, "mdo-app", "app", "morning", "page.tsx"), encoding="utf-8").read()
    assert "<ComplianceCard />" in page and "api.complianceCalendar.upcoming(30)" in page and "api.complianceCalendar.done" in page
    assert page.count("Loading…") >= 4 and "entity list not loaded" in page


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
