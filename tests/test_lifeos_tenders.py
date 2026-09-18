"""tenders source — the deadline pathology must be detected, never reported as a
real number. Verified against the shape of the live table (no network in the test).
"""

from __future__ import annotations

from lifeos.sources import tenders


def test_deadline_pathology_detected():
    # 9 of 10 rows have deadline == scan date -> unreliable.
    rows = [{"deadline": f"2026-09-1{i}T00:00:00Z", "created_at": f"2026-09-1{i}T09:00:00Z"} for i in range(9)]
    rows.append({"deadline": "2026-12-01T00:00:00Z", "created_at": "2026-09-01T09:00:00Z"})
    unreliable, frac = tenders.deadline_is_unreliable(rows)
    assert unreliable is True
    assert 0.85 <= frac <= 0.95


def test_deadline_reliable_when_dates_differ():
    rows = [{"deadline": "2026-12-01T00:00:00Z", "created_at": f"2026-09-0{i}T09:00:00Z"} for i in range(1, 9)]
    unreliable, frac = tenders.deadline_is_unreliable(rows)
    assert unreliable is False
    assert frac == 0.0


def test_no_deadlines_treated_unreliable():
    unreliable, frac = tenders.deadline_is_unreliable([{"created_at": "2026-09-01T00:00:00Z"}])
    assert unreliable is True and frac == 1.0


def test_fetch_reports_funnel_not_fake_deadline(monkeypatch):
    canned = (
        [{"title": "Coal washery civil work", "authority": "SECL||Hasdeo", "status": "accepted",
          "relevance_score": 8, "value_inr": None,
          "deadline": "2026-09-17T00:00:00Z", "created_at": "2026-09-17T09:00:00Z"}]
        + [{"title": f"Rejected job {i}", "authority": "MCL||LKP", "status": "rejected",
            "relevance_score": 0, "value_inr": None,
            "deadline": f"2026-09-17T00:00:00Z", "created_at": "2026-09-17T09:00:00Z"} for i in range(20)]
        + [{"title": "Rake siding tender", "authority": "IRCON||Raipur", "status": "pending",
            "relevance_score": 5, "value_inr": None,
            "deadline": "2026-09-16T00:00:00Z", "created_at": "2026-09-16T09:00:00Z"} for _ in range(3)]
    )
    monkeypatch.setattr(tenders, "_creds", lambda: ("https://x.supabase.co", "k"))
    monkeypatch.setattr(tenders, "_fetch_recent", lambda url, key: canned)

    r = tenders.fetch()
    assert "DEADLINE FIELD UNRELIABLE" in r.summary
    assert "closing within" not in r.summary.lower()  # never the fabricated count form
    assert r.data["by_status"]["accepted"] == 1
    assert r.data["by_status"]["pending"] == 3
    assert r.data["deadline_unreliable"] is True
    # accepted sorts above pending, gutter tags correct
    assert r.extra["rows"][0]["gutter"] == "ACC"
