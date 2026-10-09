"""levels-alert — Aman's share buy/sell list: every share every time, 🔴 the moment a level is hit.

Aman, chat 2026-10-09: notify him about ALL shares on the list; ALWAYS show the entire list,
including shares not yet at their level, for both the buy and the sell side.

Runs under pytest OR standalone: `python tests/test_levels.py`. The TestClient part follows
tests/test_singhvi.py: a scratch VEGA_DB_PATH is set before mdo_server is imported.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_cos  # noqa: E402
import mdo_levels as lv  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRI_1045 = datetime(2026, 10, 9, 10, 45, tzinfo=IST)     # market open, no snapshot slot
FRI_0922 = datetime(2026, 10, 9, 9, 22, tzinfo=IST)      # within ±8 of 09:20
FRI_0800 = datetime(2026, 10, 9, 8, 0, tzinfo=IST)       # pre-open
FRI_1531 = datetime(2026, 10, 9, 15, 31, tzinfo=IST)     # just closed
SAT_1045 = datetime(2026, 10, 10, 10, 45, tzinfo=IST)
BOT = {"id": "levels-alert", "provider": "none", "model": "none"}

ROWS = [
    {"ticker": "TCS", "buy_level": 3500, "sell_level": 4200, "active": 1},
    {"ticker": "INFY", "buy_level": 1460, "sell_level": None, "active": 1},        # buy side only
    {"ticker": "RELIANCE", "buy_level": None, "sell_level": 1400, "active": 1},    # sell side only
    {"ticker": "COALINDIA", "buy_level": 390, "sell_level": 430, "active": 1},
    {"ticker": "HDFCBANK", "buy_level": 1760, "sell_level": 1900, "active": 1},    # no ltp
    {"ticker": "SBIN", "buy_level": 800, "sell_level": 900, "active": 0},          # paused: never listed, never hits
]
LTPS = {"TCS": 3612.5, "INFY": 1455.0, "RELIANCE": 1402.0, "COALINDIA": 400.0, "HDFCBANK": None}


# ── pure helpers ──────────────────────────────────────────────────────────────
def test_format_levels_lists_every_share_nearest_first_with_both_sides():
    text = lv.format_levels(ROWS, LTPS, FRI_1045)
    lines = text.splitlines()
    assert lines[0] == "Levels 10:45 IST · 5 shares"          # SBIN is paused, not on the list
    body = lines[1:-1]
    assert len(body) == 5 and "SBIN" not in text               # every active share, exactly once
    # nearest-to-level first: the two hits (0%), then COALINDIA (2.5% to buy), TCS (3.1% to buy), no-ltp last
    assert [ln.split(" ")[0] for ln in body] == ["INFY", "RELIANCE", "COALINDIA", "TCS", "HDFCBANK"]
    assert "INFY ₹1,455 · BUY ≤1,460 (🟢 AT BUY)" in body[0] and "SELL" not in body[0]
    assert "RELIANCE ₹1,402 · SELL ≥1,400 (🔴 AT SELL)" in body[1] and "BUY" not in body[1]
    assert body[3] == "TCS ₹3,612.5 · BUY ≤3,500 (−3.1% away) · SELL ≥4,200 (+16.3% away)"
    assert body[4] == "HDFCBANK ltp n/a · BUY ≤1,760 · SELL ≥1,900"   # no price → no distance, never a guess
    assert lines[-1] == "no level hit today"
    # footer with today's hits; one share → singular header; empty list says how to start
    hits = [{"ticker": "INFY", "side": "buy", "level": 1460, "ltp": 1455, "hit_at": "2026-10-09 10:30:00"}]
    assert lv.format_levels(ROWS, LTPS, FRI_1045, hits).splitlines()[-1] == "hits today: INFY buy ₹1,455 vs ₹1,460 (10:30)"
    one = lv.format_levels(ROWS[:1], {}, FRI_1045)
    assert one.startswith("Levels 10:45 IST · 1 share\nTCS ltp n/a · BUY ≤3,500 · SELL ≥4,200")
    assert "list is empty" in lv.format_levels([], {}, FRI_1045)
    # never truncated: 60 shares → 60 lines
    many = [{"ticker": f"S{i:02d}", "buy_level": 100, "sell_level": 200} for i in range(60)]
    assert len(lv.format_levels(many, {}, FRI_1045).splitlines()) == 62


def test_detect_hits_both_sides_boundaries_and_skips():
    hits = lv.detect_hits(ROWS, LTPS)
    assert hits == [{"ticker": "INFY", "side": "buy", "level": 1460.0, "ltp": 1455.0},
                    {"ticker": "RELIANCE", "side": "sell", "level": 1400.0, "ltp": 1402.0}]
    # equality counts; both sides of one share can hit; paused rows and missing ltps never do
    assert lv.detect_hits([{"ticker": "tcs.ns", "buy_level": 3500, "sell_level": 3500}], {"TCS": 3500}) == [
        {"ticker": "TCS", "side": "buy", "level": 3500.0, "ltp": 3500.0},
        {"ticker": "TCS", "side": "sell", "level": 3500.0, "ltp": 3500.0}]
    assert lv.detect_hits([{"ticker": "SBIN", "buy_level": 800, "active": 0}], {"SBIN": 700}) == []
    assert lv.detect_hits([{"ticker": "SBIN", "buy_level": 800}], {"SBIN": None}) == []
    assert lv.detect_hits([{"ticker": "SBIN", "buy_level": 800}], {}) == []
    assert lv.distance_pct(3612.5, 3500) == -3.11 and lv.distance_pct(None, 3500) is None
    assert lv.fmt_n(3500.0) == "3,500" and lv.fmt_n(152.5) == "152.5" and lv.fmt_n(None) == "n/a"


def test_market_hours_and_snapshot_window():
    assert lv.market_open(FRI_1045) and lv.market_open(datetime(2026, 10, 9, 9, 15, tzinfo=IST))
    assert lv.market_open(datetime(2026, 10, 9, 15, 30, tzinfo=IST))
    assert not lv.market_open(FRI_0800) and not lv.market_open(FRI_1531) and not lv.market_open(SAT_1045)
    assert lv.snapshot_due(FRI_0922) == "09:20"
    assert lv.snapshot_due(datetime(2026, 10, 9, 9, 28, tzinfo=IST)) == "09:20"        # +8 min: in
    assert lv.snapshot_due(datetime(2026, 10, 9, 9, 29, tzinfo=IST)) is None           # +9 min: out
    assert lv.snapshot_due(datetime(2026, 10, 9, 12, 23, tzinfo=IST)) == "12:30"
    assert lv.snapshot_due(datetime(2026, 10, 9, 15, 0, tzinfo=IST)) == "15:05"
    assert lv.snapshot_due(FRI_1045) is None
    # the CoS heartbeat audit understands the bot's cadence (mdo_cos.next_due) and skips the weekend
    cad = "every 15 min 09:15-15:30 IST Mon-Fri"
    last = datetime(2026, 10, 9, 5, 0, tzinfo=mdo_cos.timezone.utc)                   # 10:30 IST Fri
    assert mdo_cos.next_due(cad, last, last) == last + mdo_cos.timedelta(minutes=15)
    assert mdo_cos.is_missed(cad, last, last + mdo_cos.timedelta(minutes=40))
    last_close = datetime(2026, 10, 9, 10, 0, tzinfo=mdo_cos.timezone.utc)            # 15:30 IST Fri
    due = mdo_cos.next_due(cad, last_close, SAT_1045.astimezone(mdo_cos.timezone.utc)).astimezone(IST)
    assert (due.weekday(), due.hour, due.minute) == (0, 9, 15)                        # Monday 09:15
    assert not mdo_cos.is_missed(cad, last_close, SAT_1045.astimezone(mdo_cos.timezone.utc))


def test_fetch_ltp_batches_falls_back_and_never_raises(monkeypatch):
    monkeypatch.delenv("LEVELS_PRICE_SOURCE", raising=False)
    urls: list[str] = []

    def fake_http(url, timeout):
        urls.append(url)
        if "/v7/finance/quote" in url and "TCS.NS" in url:
            return {"quoteResponse": {"result": [{"symbol": "TCS.NS", "regularMarketPrice": 3612.504},
                                                 {"symbol": "INFY.NS", "regularMarketPrice": 0}], "error": None}}
        if "/v8/finance/chart/INFY.NS" in url:
            return {"chart": {"result": [{"meta": {"regularMarketPrice": 1455}}]}}
        if "/v8/finance/chart/XYZ.BO" in url:
            return {"chart": {"result": [{"meta": {"regularMarketPrice": 12.5}}]}}
        return None                                            # 401 / timeout / garbage

    monkeypatch.setattr(lv, "_http_json", fake_http)
    out = lv.fetch_ltp(["tcs", "INFY", "XYZ", "NOPE", ""])
    assert out == {"TCS": 3612.5, "INFY": 1455.0, "XYZ": 12.5, "NOPE": None}
    assert urls[0].startswith(lv.YAHOO_QUOTE.split("?")[0]) and "TCS.NS%2CINFY.NS%2CXYZ.NS%2CNOPE.NS" in urls[0]
    assert any("/v8/finance/chart/INFY.NS" in u for u in urls)            # batch gave 0 → per-symbol retry
    assert any("XYZ.BO" in u for u in urls) and not any("TCS.BO" in u for u in urls)   # .BO only for the missing
    assert lv.fetch_ltp([]) == {}
    # a crashing transport is swallowed; the override env is honoured
    monkeypatch.setattr(lv, "_http_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert lv.fetch_ltp(["TCS"]) == {"TCS": None}
    monkeypatch.setenv("LEVELS_PRICE_SOURCE", "none")
    monkeypatch.setattr(lv, "_http_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch")))
    assert lv.fetch_ltp(["TCS"]) == {"TCS": None}
    monkeypatch.setenv("LEVELS_PRICE_SOURCE", "https://prices.example/ltp?k=1")
    monkeypatch.setattr(lv, "_http_json", lambda url, timeout: urls.append(url) or {"ltps": {"tcs": "3,600.5", "zzz": 1}})
    assert lv.fetch_ltp(["TCS", "INFY"]) == {"TCS": 3600.5, "INFY": None}
    assert urls[-1] == "https://prices.example/ltp?k=1&symbols=TCS%2CINFY"


# ── endpoints through the real app ───────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _wipe(c):
    """The scratch DB is shared by every test module: clear the list, today's hits and the stored ltps."""
    import sqlite3
    for l in c.get("/api/levels").json()["levels"]:
        c.delete(f"/api/levels/{l['ticker']}")
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("DELETE FROM level_hits")
    db.execute("DELETE FROM bot_memory WHERE bot='levels-alert'")
    db.commit(); db.close()


def test_levels_endpoints_upsert_list_snapshot_delete():
    c = _client()
    _wipe(c)
    r = c.post("/api/levels", json={"ticker": "tcs", "buy_level": "3,500", "sell_level": 4200, "note": "IT large cap"})
    assert r.status_code == 200, r.text
    assert r.json()["upserted"] == ["TCS"]
    tcs = {l["ticker"]: l for l in r.json()["levels"]}["TCS"]
    assert (tcs["buy_level"], tcs["sell_level"], tcs["note"], tcs["active"]) == (3500.0, 4200.0, "IT large cap", True)
    assert tcs["ltp"] is None and tcs["buy_distance_pct"] is None and tcs["line"] == "TCS ltp n/a · BUY ≤3,500 · SELL ≥4,200"
    # a list upserts many; an omitted side is kept, a null side is cleared; validation says why
    r = c.post("/api/levels", json=[{"ticker": "INFY", "buy_level": 1460}, {"ticker": "TCS", "sell_level": 4300}])
    assert r.status_code == 200 and r.json()["upserted"] == ["INFY", "TCS"]
    by = {l["ticker"]: l for l in r.json()["levels"]}
    assert by["TCS"]["buy_level"] == 3500.0 and by["TCS"]["sell_level"] == 4300.0 and by["TCS"]["note"] == "IT large cap"
    assert by["INFY"]["sell_level"] is None
    assert c.post("/api/levels", json={"ticker": "INFY", "buy_level": None}).status_code == 400   # would leave no level
    assert c.post("/api/levels", json={"ticker": "", "buy_level": 1}).status_code == 400
    assert c.post("/api/levels", json={"ticker": "TCS", "buy_level": -5}).status_code == 400
    assert c.post("/api/levels", json=[]).status_code == 400
    # the GET shows the last ltps the bot stored, distance both sides, hits today, nearest first
    r = c.post("/api/levels/hits", json={"hits": [{"ticker": "INFY", "side": "buy", "level": 1460, "ltp": 1455}],
                                         "trading_day": "2026-10-09", "ltps": {"TCS": 3612.5, "INFY": 1455},
                                         "as_of": "2026-10-09T10:45:00+05:30"})
    assert r.status_code == 200 and r.json()["new"] == [{"ticker": "INFY", "side": "buy", "level": 1460.0, "ltp": 1455.0}]
    r = c.get("/api/levels").json()
    assert r["ltp_as_of"] == "2026-10-09T10:45:00+05:30" and r["count"] == 2 and r["active"] == 2
    assert [l["ticker"] for l in r["levels"]] == ["INFY", "TCS"]
    tcs = r["levels"][1]
    assert tcs["ltp"] == 3612.5 and tcs["buy_distance_pct"] == -3.11 and tcs["sell_distance_pct"] == 19.03
    assert r["levels"][0]["at_buy"] is True and r["levels"][0]["nearest_pct"] == 0
    assert "market_open" in r
    # a repeat of the same hit the same day is NOT new (once per level per trading day)
    r = c.post("/api/levels/hits", json={"hits": [{"ticker": "INFY", "side": "buy", "level": 1460, "ltp": 1450}],
                                         "trading_day": "2026-10-09", "ltps": {"TCS": 3600, "INFY": 1450},
                                         "as_of": "2026-10-09T11:00:00+05:30"})
    assert r.json()["new"] == [] and len(r.json()["hits_today"]) == 1
    # the snapshot is the same text the bot pushes, with the stored ltps
    snap = c.get("/api/levels/snapshot").json()
    assert snap["count"] == 2 and snap["ltp_as_of"] == "2026-10-09T11:00:00+05:30"
    assert "TCS ₹3,600 · BUY ≤3,500 (−2.8% away) · SELL ≥4,300 (+19.4% away)" in snap["text"]
    assert "INFY ₹1,450 · BUY ≤1,460 (🟢 AT BUY)" in snap["text"]
    # pause keeps the row but drops it from the pushed list (its earlier hit stays in the footer — history is kept)
    assert c.post("/api/levels", json={"ticker": "INFY", "active": False}).json()["levels"][-1]["active"] is False
    paused = c.get("/api/levels/snapshot").json()["text"].splitlines()
    assert paused[0] == "Levels " + paused[0][7:12] + " IST · 1 share" and not any(ln.startswith("INFY ") for ln in paused)
    assert paused[-1].startswith("hits today: INFY buy")
    assert c.delete("/api/levels/infy").json()["deleted"] == "INFY"
    assert c.delete("/api/levels/INFY").status_code == 404
    assert [l["ticker"] for l in c.get("/api/levels").json()["levels"]] == ["TCS"]
    c.delete("/api/levels/TCS")


# ── the bot, end to end through the real endpoints ────────────────────────────
class _Fake:
    """Routes mdo_agent.api() into the app under test and records every report."""

    def __init__(self, client):
        self.client, self.calls, self.reports = client, [], []

    def api(self, path, method="GET", body=None, timeout=30):
        self.calls.append((method, path))
        if path == "/api/agent/report":
            self.reports.append(body)
            return {"stored": True, "report_id": len(self.reports)}
        if path.startswith("/api/levels"):
            r = self.client.post(path, json=body) if method == "POST" else self.client.get(path)
            assert r.status_code == 200, r.text
            return r.json()
        raise AssertionError(f"unexpected call {method} {path}")


def test_run_levels_alert_pushes_red_once_per_day_and_snapshots(monkeypatch):
    c = _client()
    _wipe(c)
    c.post("/api/levels", json=[{"ticker": "TCS", "buy_level": 3500, "sell_level": 4200},
                                {"ticker": "INFY", "buy_level": 1460},
                                {"ticker": "RELIANCE", "sell_level": 1400},
                                {"ticker": "HDFCBANK", "buy_level": 1760, "sell_level": 1900},
                                {"ticker": "SBIN", "buy_level": 800, "active": False}])
    fake = _Fake(c)
    monkeypatch.setattr(ag, "api", fake.api)
    fetched: list[list[str]] = []
    prices = {"TCS": 3612.5, "INFY": 1455.0, "RELIANCE": 1402.0, "HDFCBANK": None}
    monkeypatch.setattr(lv, "fetch_ltp", lambda tickers, timeout=10.0: fetched.append(list(tickers)) or dict(prices))

    # market closed → heartbeat only, nothing fetched
    assert ag.run_levels_alert(BOT, "none", "hourly", now=FRI_0800) == 0
    assert fetched == [] and fake.reports[-1]["heartbeat"] is True and "market closed" in fake.reports[-1]["summary"]
    assert ag.run_levels_alert(BOT, "none", "hourly", now=SAT_1045) == 0
    assert fetched == [] and "market closed" in fake.reports[-1]["summary"]

    # 10:45, two NEW hits → a report with one 🔴 per hit, the FULL list as detail, no snapshot
    assert ag.run_levels_alert(BOT, "none", "hourly", now=FRI_1045) == 0
    assert sorted(fetched[-1]) == ["HDFCBANK", "INFY", "RELIANCE", "TCS"]  # active only, SBIN never fetched
    rep = fake.reports[-1]
    assert not rep.get("heartbeat") and rep["bot"] == "levels-alert" and rep["status"] == "reported"
    assert rep["summary"] == "levels-alert: 4 shares, 2 at level, 2 hits today · ltp n/a: HDFCBANK"
    reds = [f for f in rep["findings"] if f["level"] == "critical"]
    assert [f["title"] for f in reds] == ["LEVEL HIT: INFY buy ₹1,455 vs ₹1,460", "LEVEL HIT: RELIANCE sell ₹1,402 vs ₹1,400"]
    assert rep["title"] == reds[0]["title"]
    for f in reds:                                                          # the entire list rides with every 🔴
        for t in ("TCS", "INFY", "RELIANCE", "HDFCBANK"):
            assert t in f["detail"]
        assert "SBIN" not in f["detail"] and "HDFCBANK ltp n/a" in f["detail"]
        assert "hits today: INFY buy ₹1,455 vs ₹1,460" in f["detail"]
    assert not [f for f in rep["findings"] if f["level"] == "info"]
    assert rep["body"] == reds[0]["detail"]
    hits = c.get("/api/levels").json()["hits_today"]
    assert {(h["ticker"], h["side"]) for h in hits} == {("INFY", "buy"), ("RELIANCE", "sell")}
    assert c.get("/api/levels").json()["ltp_as_of"] == FRI_1045.isoformat()

    # 11:00 same day, same prices → no new 🔴 (once per day); heartbeat still carries the counts
    assert ag.run_levels_alert(BOT, "none", "hourly", now=datetime(2026, 10, 9, 11, 0, tzinfo=IST)) == 0
    assert fake.reports[-1]["heartbeat"] is True
    assert fake.reports[-1]["summary"] == "levels-alert: 4 shares, 2 at level, 2 hits today · ltp n/a: HDFCBANK"

    # 09:22 next trading day: the snapshot slot → info finding with the full list, and the day resets so INFY alerts again
    monday = datetime(2026, 10, 12, 9, 22, tzinfo=IST)
    prices["RELIANCE"] = 1390.0                                               # off its sell level
    assert ag.run_levels_alert(BOT, "none", "hourly", now=monday) == 0
    rep = fake.reports[-1]
    info = [f for f in rep["findings"] if f["level"] == "info"]
    assert len(info) == 1 and info[0]["title"] == "Levels snapshot" and info[0]["detail"].startswith("Levels 09:22 IST · 4 shares")
    assert [f["title"] for f in rep["findings"] if f["level"] == "critical"] == ["LEVEL HIT: INFY buy ₹1,455 vs ₹1,460"]
    assert "RELIANCE ₹1,390 · SELL ≥1,400 (+0.7% away)" in info[0]["detail"]
    # snapshot slot with nothing new → info finding only, titled by the slot
    assert ag.run_levels_alert(BOT, "none", "hourly", now=datetime(2026, 10, 12, 12, 30, tzinfo=IST)) == 0
    rep = fake.reports[-1]
    assert rep["title"] == "Levels snapshot 12:30 IST" and [f["level"] for f in rep["findings"]] == ["info"]

    # every price missing → the heartbeat is a warning (Yahoo blocked), never a guess
    prices.update({k: None for k in prices})
    assert ag.run_levels_alert(BOT, "none", "hourly", now=datetime(2026, 10, 12, 13, 0, tzinfo=IST)) == 0
    assert fake.reports[-1]["status"] == "warning" and "0 at level" in fake.reports[-1]["summary"]
    # empty list → says how to start
    for l in c.get("/api/levels").json()["levels"]:
        c.delete(f"/api/levels/{l['ticker']}")
    assert ag.run_levels_alert(BOT, "none", "hourly", now=FRI_1045) == 0
    assert "0 shares on the list" in fake.reports[-1]["summary"]


def test_levels_alert_is_wired_in_dispatch_fleet_cron_brain_and_env():
    assert ag.CUSTOM_BOTS["levels-alert"] is ag.run_levels_alert
    fleet = yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))
    bot = ag.find_bot(fleet, "levels-alert")
    assert bot["enabled"] is True and bot["runs_on"] == "vps-cron" and bot["provider"] == "none" and bot["model"] == "none"
    assert bot["command"] == "docker compose exec -T backend python mdo_agent.py levels-alert"
    assert bot["cadence"] == "every 15 min 09:15-15:30 IST Mon-Fri" and bot["serves"] == ["capital-rules"]
    assert {"purpose", "thinks", "works", "limits", "minimum_output", "rules"} <= set(bot["charter"])
    rules = " ".join(bot["charter"]["rules"]).lower()
    assert "never suggests execution" in rules and "never books" in rules and "once per level per trading day" in rules
    assert "every share every time" in rules
    # the §8 block is what deploy_vps.sh render_cron installs
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    block = doc[doc.index("# MDO fleet — one line per bot"):]
    block = block[:block.index("```")]
    lines = [ln for ln in block.splitlines() if "mdo_agent.py levels-alert" in ln]
    assert len(lines) == 1 and lines[0].split()[:5] == ["*/15", "3-10", "*", "*", "1-5"]
    assert "self-checks market hours" in lines[0]
    # the chat tools exist and keep the old ones
    import mdo_brain
    names = {t["name"] for t in mdo_brain.TOOLS}
    assert {"set_level", "list_levels", "add_task", "get_agenda", "create_job", "get_fleet"} <= names
    set_level = next(t for t in mdo_brain.TOOLS if t["name"] == "set_level")
    assert set_level["input_schema"]["required"] == ["ticker"]
    assert {"buy_level", "sell_level", "note", "active"} <= set(set_level["input_schema"]["properties"])
    assert "LEVELS_PRICE_SOURCE" in open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()


def test_brain_tools_set_and_list_levels():
    import asyncio
    import mdo_brain
    c = _client()                                   # imports mdo_server → toolbox configured
    _wipe(c)

    async def go():
        import json
        r = json.loads(await mdo_brain.execute_tool("set_level", {"ticker": "zeel", "buy_level": 120, "sell_level": 150, "note": "media"}))
        assert r["upserted"] == ["ZEEL"] and r["levels"][0]["source"] == "cos-chat"
        r = json.loads(await mdo_brain.execute_tool("list_levels", {}))
        assert [l["ticker"] for l in r["levels"]] == ["ZEEL"] and r["levels"][0]["line"] == "ZEEL ltp n/a · BUY ≤120 · SELL ≥150"
        r = json.loads(await mdo_brain.execute_tool("set_level", {"ticker": "ZEEL", "buy_level": None, "sell_level": None}))
        assert "error" in r and "give a buy level" in r["error"]           # tool errors go back to the model, not the user

    asyncio.run(go())
    c.delete("/api/levels/ZEEL")


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
