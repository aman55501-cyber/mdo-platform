"""corp-actions — NSE announcements + corporate actions for every held/watched ticker, one push of NEW rows with the
holder column, heartbeat every run, "NSE unavailable" when NSE is down. Zero LLM spend; canned NSE JSON only.

Follows tests/test_compliance.py: a scratch VEGA_DB_PATH before mdo_server is imported; the endpoint tests wipe the
tables they fill (the DB is shared by every test module). The NSE fetch is a hook (make_fetcher) the tests replace.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("SHARE_MASTER_DATA_DIR", tempfile.mkdtemp())

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_corp_actions as ca  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── canned NSE JSON (the live shapes, trimmed) ────────────────────────────────
ANN_TCS = [
    {"symbol": "TCS", "desc": "Board Meeting Intimation", "an_dt": "08-Oct-2026 17:32:11",
     "attchmntText": "Board meeting on 09-Oct-2026 to consider the financial results for the quarter ended 30-Sep-2026 and an interim dividend",
     "attchmntFile": "https://nsearchives.nseindia.com/corporate/TCS_08102026173211.pdf", "sm_name": "Tata Consultancy Services Limited"},
    {"symbol": "TCS", "desc": "Financial Results", "an_dt": "09-Oct-2026 16:05:00", "attchmntText": "Unaudited financial results for the quarter ended 30-Sep-2026",
     "attchmntFile": "https://nsearchives.nseindia.com/corporate/TCS_09102026160500.pdf", "sm_name": "Tata Consultancy Services Limited"},
    {"symbol": "TCS", "desc": "Updates", "an_dt": "01-Jul-2026 10:00:00", "attchmntText": "Old update — outside the 30-day window", "attchmntFile": ""},
]
ACT_TCS = [
    {"symbol": "TCS", "series": "EQ", "subject": "Interim Dividend - Rs 11 Per Share", "exDate": "20-Oct-2026", "recDate": "20-Oct-2026",
     "bcStartDate": "-", "bcEndDate": "-", "caBroadcastDate": "09-Oct-2026 16:10:00", "comp": "Tata Consultancy Services Limited", "isin": "INE467B01029"},
]
ANN_INFY = [{"symbol": "INFY", "desc": "Buyback", "dt": "07-Oct-2026 09:00:00", "attchmntText": "Buyback of equity shares — record date 25-Oct-2026",
             "attchmntFile": "https://nsearchives.nseindia.com/corporate/INFY_x.pdf", "sm_name": "Infosys Limited"}]
ACT_RELIANCE = [{"symbol": "RELIANCE", "subject": "Annual General Meeting", "exDate": "-", "recDate": "15-Oct-2026", "caBroadcastDate": "05-Oct-2026 12:00:00", "comp": "Reliance Industries"}]
CANNED = {("announcements", "TCS"): ANN_TCS, ("actions", "TCS"): ACT_TCS, ("announcements", "INFY"): ANN_INFY,
          ("actions", "INFY"): [], ("announcements", "RELIANCE"): {"data": []}, ("actions", "RELIANCE"): ACT_RELIANCE}
NOW = datetime(2026, 10, 9, 18, 30, tzinfo=IST)


# ── pure ──────────────────────────────────────────────────────────────────────
def test_dates_and_kinds():
    assert ca.parse_nse_date("07-Oct-2026") == "2026-10-07" and ca.parse_nse_date("-") == "" and ca.parse_nse_date("2026-10-07") == "2026-10-07"
    assert ca.parse_nse_date("31-Feb-2026") == "" and ca.parse_nse_date("garbage") == ""
    assert ca.parse_nse_datetime("09-Oct-2026 17:32:11") == "2026-10-09T17:32:11" and ca.parse_nse_datetime("09-Oct-2026") == "2026-10-09T00:00:00"
    assert ca.parse_nse_datetime("") == ""
    assert ca.classify("Interim Dividend - Rs 11 Per Share") == "dividend"
    assert ca.classify("Unaudited financial results", "Financial Results") == "results"
    assert ca.classify("Buyback of equity shares") == "buyback" and ca.classify("Bonus 1:1") == "bonus" and ca.classify("Sub-division of shares") == "split"
    assert ca.classify("Rights issue") == "rights" and ca.classify("Annual General Meeting") == "agm" and ca.classify("Postal ballot / e-voting") == "agm"
    assert ca.classify("Board meeting on 09-Oct", "Board Meeting Intimation") == "board_meeting"
    assert ca.classify("Record date for something") == "record_date" and ca.classify("Press release") == "other"
    assert ca.classify("Board meeting to consider an interim dividend") == "dividend"      # the dividend outranks the meeting


def test_rows_from_canned_json():
    rows = ca.rows_from_announcements("TCS", ANN_TCS)
    assert [(r["kind"], r["announced_at"]) for r in rows] == [("dividend", "2026-10-08T17:32:11"), ("results", "2026-10-09T16:05:00"), ("other", "2026-07-01T10:00:00")]
    assert rows[0]["subject"].startswith("Board Meeting Intimation: Board meeting on 09-Oct-2026") and rows[0]["url"].endswith(".pdf")
    assert rows[0]["source"] == "announcement" and rows[0]["company"] == "Tata Consultancy Services Limited" and rows[0]["ex_date"] == ""
    acts = ca.rows_from_actions("TCS", ACT_TCS)
    assert acts == [{"ticker": "TCS", "kind": "dividend", "subject": "Interim Dividend - Rs 11 Per Share", "ex_date": "2026-10-20", "record_date": "2026-10-20",
                     "announced_at": "2026-10-09T16:10:00", "url": "https://www.nseindia.com/get-quotes/equity?symbol=TCS", "source": "action",
                     "company": "Tata Consultancy Services Limited"}]
    assert ca.rows_from_actions("RELIANCE", ACT_RELIANCE)[0]["record_date"] == "2026-10-15" and ca.rows_from_actions("RELIANCE", ACT_RELIANCE)[0]["ex_date"] == ""
    assert ca.rows_from_announcements("X", None) == [] and ca.rows_from_actions("X", {"data": None}) == [] and ca.rows_from_announcements("X", [1, "x"]) == []


def test_push_text_and_heartbeat_line():
    held = {"TCS": [{"holder": "Ashok", "qty": 3000}, {"holder": "Aman", "qty": 500}], "INFY": []}
    r = ca.rows_from_actions("TCS", ACT_TCS)[0]
    assert ca.line_for(r, held["TCS"]) == "TCS · dividend · 20 Oct · held: Ashok 3,000, Aman 500"
    a = ca.rows_from_announcements("INFY", ANN_INFY)[0]
    assert ca.line_for(a, held.get("INFY")) == "INFY · buyback · 07 Oct · held: nobody"              # Directive 18: nobody, never blank
    assert ca.line_for(a, None) == "INFY · buyback · 07 Oct · held: nobody"
    text = ca.push_text([r, a], held, date(2026, 10, 9))
    assert text == "Corporate actions · 2 new (09 Oct)\nINFY · buyback · 07 Oct · held: nobody\nTCS · dividend · 20 Oct · held: Ashok 3,000, Aman 500"
    many = [{**r, "ticker": f"T{i:03d}", "ex_date": f"2026-10-{10 + i % 20:02d}"} for i in range(40)]
    text = ca.push_text(many, {}, date(2026, 10, 9))
    lines = text.split("\n")
    assert len(lines) == 27 and lines[0] == "Corporate actions · 40 new (09 Oct)" and lines[-1] == "+15 more on the dashboard"
    assert lines[1].startswith("T000 · dividend · 10 Oct") and lines[2].startswith("T020 · dividend · 10 Oct")         # nearest date first
    assert ca.heartbeat_line(120, [r, a, {**r, "kind": "results"}], True) == "corp-actions: 120 tickers checked, 3 new (1 results, 1 dividends, 1 other) — NSE ok"
    assert ca.heartbeat_line(3, [], False, 3) == "corp-actions: 3 tickers checked, 0 new (0 results, 0 dividends, 0 other) — NSE unavailable (3 of 3 tickers unanswered)"


def test_fetcher_cookie_dance_and_rate_limit(monkeypatch):
    """One cookie dance, then the JSON; never two requests inside a second; a failure returns (None, reason)."""
    calls, sleeps, clock = [], [], {"t": 100.0}

    class _Resp:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1): return self.body

    class _Opener:
        def open(self, req, timeout=None):
            calls.append(req.full_url)
            assert req.get_header("User-agent", "").startswith("Mozilla/5.0")
            if req.full_url.endswith("symbol=BAD"):
                raise OSError("HTTP 403")
            return _Resp(b"<html>" if req.full_url == ca.NSE_HOME else b'[{"symbol":"TCS","subject":"x","exDate":"20-Oct-2026","caBroadcastDate":"09-Oct-2026 16:10:00"}]')

    monkeypatch.setattr(ca.urllib.request, "build_opener", lambda *a: _Opener())
    fetch = ca.make_fetcher(sleep=lambda s: sleeps.append(round(s, 3)) or clock.__setitem__("t", clock["t"] + s), clock=lambda: clock["t"])
    data, err = fetch("actions", "TCS")
    assert err == "" and data[0]["symbol"] == "TCS"
    assert calls == [ca.NSE_HOME, ca.NSE_ACTIONS.format(symbol="TCS")]            # dance first, then the JSON
    assert sleeps == [1.0]                                                        # the JSON waited the full second after the dance
    data, err = fetch("announcements", "TCS")
    assert calls[-1] == ca.NSE_ANNOUNCEMENTS.format(symbol="TCS") and len(calls) == 3 and sleeps == [1.0, 1.0]   # opener reused, 1 s gap
    data, err = fetch("actions", "BAD")
    assert data is None and err.startswith("OSError") and "403" in err
    data, err = fetch("actions", "TCS")
    assert err == "" and calls[-2] == ca.NSE_HOME                                 # a failure drops the cookie: dance again


# ── endpoints through the real app ───────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _wipe():
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("corp_actions", "corp_actions_runs", "share_master_holdings", "share_levels", "portfolio_snapshot"):
        db.execute(f"DELETE FROM {t}")
    db.commit(); db.close()


def _seed_holdings():
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for holder, ticker, qty, ok in (("Ashok", "TCS", 3000, 1), ("Aman", "TCS", 500, 1), ("Aman", "INFY", 100, 1), ("Ashok", "DIATEA", 30000, 0)):
        db.execute("INSERT INTO share_master_holdings (holder, ticker, hdfc_code, qty, ticker_verified, source) VALUES (?,?,?,?,?,'hdfc-csv')",
                   (holder, ticker, ticker + "EQ", qty, ok))
    db.execute("INSERT INTO share_levels (ticker, buy_level, sell_level) VALUES ('RELIANCE', 1300, 1600)")
    db.commit(); db.close()


class _Sent:
    def __init__(self):
        self.texts, self.ok = [], True

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": self.ok} if self.ok else {"sent": False, "reason": "bridge down"}


def _setup(monkeypatch, canned=CANNED):
    import mdo_server
    c = _client()
    c.get("/api/corp-actions/tickers")           # opens the DB and creates the tables
    _wipe()
    _seed_holdings()
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    asked: list[tuple[str, str]] = []

    def make_fetcher():
        def fetch(kind, sym):
            asked.append((kind, sym))
            if canned is None:
                return None, "URLError: NSE timed out"
            return canned.get((kind, sym), []), ""
        return fetch
    monkeypatch.setitem(mdo_server._corp["hooks"], "make_fetcher", make_fetcher)
    return c, sent, asked


def test_run_pushes_new_rows_only_with_holder_column(monkeypatch):
    c, sent, asked = _setup(monkeypatch)
    assert c.get("/api/corp-actions/tickers").json() == {"tickers": ["INFY", "RELIANCE", "TCS"], "count": 3}   # held (verified) + watched; DIATEA skipped
    r = c.post("/api/corp-actions/run", json={"now": NOW.isoformat()}).json()
    assert (r["tickers"], r["checked"], r["new"], r["failed"], r["nse_ok"], r["pushed"], r["status"]) == (3, 3, 5, 0, True, 1, "clean")
    assert sorted(asked) == sorted([(k, s) for s in ("INFY", "RELIANCE", "TCS") for k in ("announcements", "actions")])
    assert r["line"] == "corp-actions: 3 tickers checked, 5 new (1 results, 2 dividends, 2 other) — NSE ok"
    assert sent.texts == [r["text"]]
    assert r["text"].split("\n") == [
        "Corporate actions · 5 new (09 Oct)",
        "INFY · buyback · 07 Oct · held: Aman 100",
        "TCS · dividend · 08 Oct · held: Ashok 3,000, Aman 500",
        "TCS · results · 09 Oct · held: Ashok 3,000, Aman 500",
        "RELIANCE · agm · 15 Oct · held: nobody",
        "TCS · dividend · 20 Oct · held: Ashok 3,000, Aman 500",
    ]
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    rows = db.execute("SELECT ticker, subject, announced_at, pushed_at FROM corp_actions ORDER BY id").fetchall()
    assert len(rows) == 5 and all(x[3] for x in rows) and not any("Old update" in x[1] for x in rows)   # 30-day cutoff: the July row not stored
    runs = db.execute("SELECT tickers, new, failed, nse_ok, pushed, line FROM corp_actions_runs").fetchall()
    db.close()
    assert runs == [(3, 5, 0, 1, 1, r["line"])]
    # second run, same NSE answers: nothing new, nothing pushed, heartbeat still says so
    r2 = c.post("/api/corp-actions/run", json={"now": NOW.isoformat()}).json()
    assert (r2["new"], r2["pushed"], r2["text"]) == (0, 0, "") and len(sent.texts) == 1
    assert r2["line"] == "corp-actions: 3 tickers checked, 0 new (0 results, 0 dividends, 0 other) — NSE ok"
    # the dashboard: next 14 days by ex/record date, holder column on every row
    up = c.get(f"/api/corp-actions/upcoming?days=14&now={NOW.isoformat()}").json()
    assert [(i["ticker"], i["date"], i["held_text"]) for i in up["items"]] == [("RELIANCE", "2026-10-15", "nobody"), ("TCS", "2026-10-20", "Ashok 3,000, Aman 500")]
    assert up["last_run"]["line"] == r2["line"] and up["tickers_watched"] == 3 and up["today"] == "2026-10-09"
    rec = c.get("/api/corp-actions/recent?days=400").json()
    assert len(rec["items"]) == 5 and rec["items"][0]["announced_at"] >= rec["items"][-1]["announced_at"]
    # a push that fails is said in the line and the row stays unpushed for the record
    sent.ok = False
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"]); db.execute("DELETE FROM corp_actions WHERE ticker='INFY'"); db.commit(); db.close()
    r3 = c.post("/api/corp-actions/run", json={"now": NOW.isoformat()}).json()
    assert r3["new"] == 1 and r3["pushed"] == 0 and r3["push_failed"] == 1 and r3["status"] == "warning" and r3["line"].endswith("— NSE ok · push NOT delivered")
    _wipe()


def test_run_when_nse_is_down_invents_nothing(monkeypatch):
    c, sent, asked = _setup(monkeypatch, canned=None)
    r = c.post("/api/corp-actions/run", json={"now": NOW.isoformat()}).json()
    assert r["nse_ok"] is False and r["new"] == 0 and r["pushed"] == 0 and r["status"] == "warning" and sent.texts == []
    assert r["line"] == "corp-actions: 3 tickers checked, 0 new (0 results, 0 dividends, 0 other) — NSE unavailable (3 of 3 tickers unanswered)"
    assert len(asked) == 6                                                     # stopped after UNAVAILABLE_AFTER tickers, no hammering
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    assert db.execute("SELECT COUNT(*) FROM corp_actions").fetchone()[0] == 0
    assert db.execute("SELECT nse_ok, failed FROM corp_actions_runs").fetchall() == [(0, 3)]
    db.close()
    up = c.get(f"/api/corp-actions/upcoming?days=14&now={NOW.isoformat()}").json()
    assert up["items"] == [] and up["last_run"]["nse_ok"] == 0
    _wipe()


def test_agent_runner_files_the_heartbeat(monkeypatch):
    seen = {}
    monkeypatch.setattr(ag, "api", lambda path, method="GET", body=None, timeout=30: seen.update({"path": path, "body": body, "timeout": timeout}) or
                        {"line": "corp-actions: 3 tickers checked, 0 new (0 results, 0 dividends, 0 other) — NSE unavailable (3 of 3 tickers unanswered)",
                         "status": "warning", "new": 0, "tickers": 3})
    beats = []
    monkeypatch.setattr(ag, "heartbeat", lambda *a: beats.append(a))
    assert ag.CUSTOM_BOTS["corp-actions"] is ag.run_corp_actions
    assert ag.run_corp_actions({"id": "corp-actions"}, "none", "daily", NOW) == 0
    assert seen["path"] == "/api/corp-actions/run" and seen["body"] == {"now": NOW.isoformat()} and seen["timeout"] >= 1200
    assert beats == [("corp-actions", "daily", "warning", "corp-actions: 3 tickers checked, 0 new (0 results, 0 dividends, 0 other) — NSE unavailable (3 of 3 tickers unanswered)")]


# ── wiring: fleet.yaml, cron, the Morning card ────────────────────────────────
def test_fleet_cron_and_morning_card_wiring():
    fleet = yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))
    bot = next(b for b in fleet["bots"] if b["id"] == "corp-actions")
    assert bot["provider"] == "none" and bot["model"] == "none" and bot["enabled"] is True and bot["cadence"] == "daily 18:30 IST"
    assert "NSE ok" in bot["heartbeat"] and "NSE unavailable" in bot["heartbeat"] and "T tickers checked, N new (R results, D dividends, O other)" in bot["heartbeat"]
    assert set(bot["serves"]) <= {o["id"] for o in yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))["objectives"]}
    rules = " ".join(bot["charter"]["rules"])
    assert "Holder on every share line" in rules and "No LLM" in rules and "request per second" in rules.lower()
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    block = doc[doc.index("# MDO fleet — one line per bot"):]
    block = block[:block.index("```")]
    lines = [l for l in block.splitlines() if "mdo_agent.py corp-actions" in l]
    assert len(lines) == 1 and lines[0].split()[:5] == ["0", "13", "*", "*", "*"]      # 18:30 IST daily, in UTC
    page_path = os.path.join(ROOT, "mdo-app", "app", "morning", "page.tsx")
    if not os.path.exists(page_path):            # the backend image ships no frontend source; checked in the repo run
        return
    page = open(page_path, encoding="utf-8").read()
    assert "<CorpActionsCard />" in page and "function CorpActionsCard()" in page and "api.corpActions.upcoming(14)" in page
    assert "q.isLoading && <div" in page.split("function CorpActionsCard()")[1]      # loading state before any table (Directive 17)
    assert "held_text" in page.split("function CorpActionsCard()")[1]                 # the holder column
    api_ts = open(os.path.join(ROOT, "mdo-app", "lib", "api.ts"), encoding="utf-8").read()
    assert "/api/corp-actions/upcoming?days=" in api_ts
