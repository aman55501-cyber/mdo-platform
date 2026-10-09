"""Unit tests for the Chief of Staff helpers (no network, no database)."""
from datetime import datetime, timedelta, timezone

import mdo_cos as c


def test_cost_inr_uses_price_table(monkeypatch):
    monkeypatch.setenv("USD_INR", "80")
    # Sonnet 5.5: $2 in / $10 out per 1M
    assert c.cost_inr("claude-sonnet-5-5", 1_000_000, 0) == 160.0
    assert c.cost_inr("claude-sonnet-5-5", 0, 100_000) == 80.0
    # cache reads are 10% of input price
    assert c.cost_inr("claude-sonnet-5-5", 1_000_000, 0, cache_read_tokens=1_000_000) == 16.0


def test_unknown_model_is_never_free():
    assert c.cost_inr("some-new-model", 1_000_000, 0) > 0


def test_budget_mode_thresholds():
    assert c.budget_mode(0, None) == "normal"
    assert c.budget_mode(8999, 10000) == "normal"
    assert c.budget_mode(9000, 10000) == "economy"
    assert c.budget_mode(10000, 10000) == "paused"
    assert c.budget_mode(99999, 10000) == "paused"


def test_parse_reply_ack_nack_choice():
    assert c.parse_reply("ok 14") == {"kind": "ack", "job": 14, "option": None}
    assert c.parse_reply("OK #14") == {"kind": "ack", "job": 14, "option": None}
    assert c.parse_reply("buy 3") == {"kind": "ack", "job": 3, "option": None}
    assert c.parse_reply("no 14") == {"kind": "nack", "job": 14, "option": None}
    assert c.parse_reply("skip 7") == {"kind": "nack", "job": 7, "option": None}
    assert c.parse_reply("14:2") == {"kind": "choice", "job": 14, "option": 2}
    assert c.parse_reply("2") == {"kind": "choice", "job": None, "option": 2}


def test_parse_reply_free_text_goes_to_brain():
    assert c.parse_reply("what is the rake position today?") is None
    assert c.parse_reply("ok, let's discuss tomorrow") is None
    assert c.parse_reply("") is None


def test_next_due_hourly():
    now = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)
    last = now - timedelta(minutes=30)
    assert c.next_due("hourly", last, now) == last + timedelta(hours=1)
    assert not c.is_missed("hourly", last, now)
    assert c.is_missed("hourly", now - timedelta(hours=2), now)


def test_next_due_hourly_market_window_skips_weekend():
    # Saturday 10:00 IST → next due is Monday 09:00 IST
    sat = datetime(2026, 10, 10, 4, 30, tzinfo=timezone.utc)  # 10:00 IST
    due = c.next_due("hourly 09:00-15:30 IST Mon-Fri", sat - timedelta(hours=1), sat)
    assert due.astimezone(c.IST).weekday() == 0
    assert due.astimezone(c.IST).hour == 9
    # last run Friday 15:35 IST (the final slot) → nothing is due until Monday
    assert not c.is_missed("hourly 09:00-15:30 IST Mon-Fri", sat - timedelta(hours=18, minutes=25), sat)
    # last run Friday 14:00 IST → the 15:00 slot was missed
    assert c.is_missed("hourly 09:00-15:30 IST Mon-Fri", sat - timedelta(hours=20), sat)


def test_next_due_daily_and_weekly():
    now = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)  # 07:30 IST Wednesday
    due = c.next_due("daily 06:57 IST", None, now)
    assert due.astimezone(c.IST).strftime("%H:%M") == "06:57"
    # ran this morning → next is tomorrow
    ran = now - timedelta(minutes=30)
    assert c.next_due("daily 06:57 IST", ran, now).astimezone(c.IST).day == 8
    # weekly Sunday 03:00
    due_w = c.next_due("weekly Sun 03:00 IST", None, now).astimezone(c.IST)
    assert due_w.weekday() == 6 and due_w.hour == 3
    assert c.next_due("on demand", None, now) is None
    assert c.next_due("daily 06:30 IST + on demand", None, now) is not None


def test_job_lines_carry_reply_and_eta():
    assert c.job_line({"id": 14, "title": "Send draft to Vimal", "kind": "needs_click", "eta": "today"}) == \
        '🖐 #14 Send draft to Vimal · ETA today — reply "ok 14" / "no 14"'
    line = c.job_line({"id": 9, "title": "Two readings", "kind": "needs_choice", "options": ["A", "B"]})
    assert "(1) A" in line and "(2) B" in line and "9:1" in line and "9:2" in line
    assert c.job_line({"id": 3, "title": "CA draft ready", "kind": "done"}) == "✅ #3 CA draft ready"
    assert c.job_line({"id": 5, "title": "₹300/mo buys X", "kind": "proposal"}).startswith("💡 #5")


def test_rollup_line_never_blank():
    now = datetime(2026, 10, 7, 1, 0, tzinfo=timezone.utc)
    line = c.rollup_line(now, 0, 0, 0, 11, 11, 0, [], 0, 10000, [])
    assert "Fleet: 11/11 reported · all alive" in line
    assert "nothing needs you" in line
    line2 = c.rollup_line(now, 2, 1, 0, 10, 11, 3, [14, 17], 812.5, None, ["ops-hourly"])
    assert "ops-hourly dead" in line2 and "#14, #17" in line2 and "no cap set" in line2


def test_safe_vault_path_confines(tmp_path):
    root = str(tmp_path)
    assert c.safe_vault_path(root, "memory/entity-registry.md") == str(tmp_path / "memory" / "entity-registry.md")
    assert c.safe_vault_path(root, "finance/Family_Finance_Master.xlsx").endswith("Family_Finance_Master.xlsx")
    assert c.safe_vault_path(root, "../etc/passwd") is None
    assert c.safe_vault_path(root, "memory/../../x") is None
    assert c.safe_vault_path(root, "/memory/x.md") is not None          # leading slash tolerated
    assert c.safe_vault_path(root, "other/x.md") is None                 # unknown area
    assert c.safe_vault_path(root, "memory/.env") is None                # hidden files never
    assert c.safe_vault_path(root, "") is None


def test_next_due_weekdays_skips_weekend():
    sat = datetime(2026, 10, 10, 4, 30, tzinfo=timezone.utc)   # Saturday 10:00 IST
    due = c.next_due("weekdays 08:05 IST", sat - timedelta(days=1), sat).astimezone(c.IST)
    assert due.weekday() == 0 and due.strftime("%H:%M") == "08:05"
    assert not c.is_missed("weekdays 08:05 IST", sat - timedelta(days=1), sat)
