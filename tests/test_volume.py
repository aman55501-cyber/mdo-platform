"""volume-watch — NSE bhavcopy volume/delivery + bulk/block deals for held and watched shares. Zero LLM; no network (fake getter)."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_volume as mv  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 9, 19, 15, tzinfo=IST)          # Friday
HEAD = "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"


def _row(sym, d, prev, close, vol, deliv, high=None):
    return f"{sym}, EQ, {d:%d-%b-%Y}, {prev}, {prev}, {high or max(prev, close)}, {min(prev, close)}, {close}, {close}, {close}, {vol}, 1, 100, {int(vol * deliv / 100)}, {deliv}\n"


def _series(d):
    """TCS: 25 flat sessions at 100k volume, then a -3% day on 3x volume on the last one. INFY: quiet, close near its buy level.
    WIPRO: flat, breakout day on 2x. ZZZ: not watched."""
    last = date(2026, 10, 9)
    txt = HEAD
    n = (last - d).days
    if d == last:
        txt += _row("TCS", d, 3600, 3490, 300000, 55)                  # -3.05% on 3.0x
        txt += _row("INFY", d, 1465, 1458, 40000, 40)                  # 0.4x volume, within 3% of buy 1460
        txt += _row("WIPRO", d, 250, 256, 200000, 60, high=257)        # new high on 2.0x
    else:
        txt += _row("TCS", d, 3600, 3600, 100000, 45)
        txt += _row("INFY", d, 1465, 1465, 100000, 40)
        txt += _row("WIPRO", d, 250, 250, 100000, 40, high=252)
    txt += _row("ZZZ", d, 10, 10, 5, 50)
    return txt


BULK = ("Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price,Remarks\n"
        "09-OCT-2026,TCS,Tata Consultancy,SOME FUND LLP,SELL,2362529,3490.5,-\n"
        "09-OCT-2026,ZZZ,Not Watched,OTHER FUND,BUY,100,10,-\n")
BLOCK = "Date,Symbol,Security Name,Client Name,Buy/Sell,Quantity Traded,Trade Price / Wght. Avg. Price\nNO RECORDS,,,,,,\n"


def test_parsers_and_signals():
    rows = mv.parse_bhav(_series(date(2026, 10, 9)), {"TCS", "INFY"})
    assert {r["symbol"] for r in rows} == {"TCS", "INFY"} and rows[0]["volume"] == 300000 and rows[0]["deliv_per"] == 55
    assert mv.parse_bhav("garbage") == []
    deals = mv.parse_deals(BULK, "bulk")
    assert len(deals) == 2 and deals[0]["side"] == "SELL" and deals[0]["qty"] == 2362529 and deals[0]["day"] == "2026-10-09"
    assert mv.parse_deals(BLOCK, "block") == []                                           # "NO RECORDS" is nothing
    hist = [dict(day=f"d{i}", volume=100000, close=100.0, prev_close=100.0, high=101.0, deliv_per=40.0) for i in range(22)]
    hist.append(dict(day="x", volume=300000, close=96.0, prev_close=100.0, high=100.0, deliv_per=40.0))
    assert [s["kind"] for s in mv.compute_signals(hist)] == ["distribution"]
    hist[-1] = dict(day="x", volume=40000, close=99.0, prev_close=100.0, high=100.0, deliv_per=40.0)
    assert [s["kind"] for s in mv.compute_signals(hist, buy_level=98.0)] == ["quiet-at-buy"]
    hist[-1] = dict(day="x", volume=400000, close=99.0, prev_close=100.0, high=100.0, deliv_per=40.0)
    assert [s["kind"] for s in mv.compute_signals(hist, buy_level=98.0)] == ["heavy-at-buy"]
    hist[-1] = dict(day="x", volume=120000, close=100.4, prev_close=100.0, high=101.0, deliv_per=70.0)
    assert [s["kind"] for s in mv.compute_signals(hist)] == ["accumulation"]
    assert mv.compute_signals(hist[:5]) == []                                               # too little history says nothing


def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


class _Sent:
    def __init__(self):
        self.texts = []

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": True}


def _setup(monkeypatch, *, down=False):
    import mdo_server
    c = _client()
    c.get("/api/volume/latest")
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("market_bhav", "market_deals", "volume_runs", "share_levels", "share_master_holdings"):
        try:
            db.execute(f"DELETE FROM {t}")                     # the scratch DB is shared by every test module
        except sqlite3.OperationalError:
            pass
    db.commit(); db.close()
    for t, b in (("TCS", 3000), ("INFY", 1460), ("WIPRO", None)):
        c.post("/api/levels", json={"ticker": t, "buy_level": b} if b else {"ticker": t, "sell_level": 900})
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    try:
        db.execute("INSERT INTO share_master_holdings (holder, ticker, qty) VALUES ('Aman','TCS',500)")
        db.execute("INSERT INTO share_master_holdings (holder, ticker, qty) VALUES ('Ashok','INFY',200)")
        db.commit()
    finally:
        db.close()
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    calls = []

    def get(url, timeout=25.0):
        calls.append(url)
        if down:
            return None, "HTTP 403"
        if "sec_bhavdata_full_" in url:
            ddmm = url.rsplit("_", 1)[1].split(".")[0]
            d = datetime.strptime(ddmm, "%d%m%Y").date()
            if d > date(2026, 10, 9) or d.weekday() > 4 or d == date(2026, 10, 2):
                return None, "HTTP 404"                                                   # future, weekend, one holiday
            return _series(d), ""
        return (BULK if url.endswith("bulk.csv") else BLOCK), ""
    monkeypatch.setitem(mdo_server._volume["hooks"], "get", get)
    monkeypatch.setitem(mdo_server._volume["hooks"], "fast", True)
    return c, sent, calls


def test_first_run_backfills_pushes_once_and_reports_every_run(monkeypatch):
    c, sent, calls = _setup(monkeypatch)
    r = c.post("/api/volume/run", json={"now": NOW.isoformat()}).json()
    assert r["day"] == "2026-10-09" and r["status"] == "clean" and r["pushed"] == 1
    kinds = sorted((s["symbol"], s["kind"]) for s in r["signals"])
    assert kinds == [("INFY", "quiet-at-buy"), ("TCS", "distribution"), ("WIPRO", "accumulation"), ("WIPRO", "breakout"), ("WIPRO", "strength")]
    assert len(r["deals"]) == 1 and r["deals"][0]["symbol"] == "TCS"                       # the unwatched ZZZ deal is dropped
    assert len(sent.texts) == 1 and sent.texts[0].startswith("Volume · Fri 09 Oct · protect 1 · opportunity 2 · deals 1")
    assert "⚠️ TCS ↓3.1% on 3.0× volume — heavy selling (held:" in sent.texts[0] and "🏦 bulk TCS: SOME FUND LLP sold 23.6 L @ ₹3,490.50" in sent.texts[0]
    assert "(held: Aman 500)" in sent.texts[0] and "🟢 INFY" in sent.texts[0]                 # the holder column is on every line
    assert all("(held:" in ln for ln in sent.texts[0].splitlines()[1:] if ln[:1] in "⚠️📈🚀🟢🟠🧲🏦")
    assert r["line"].startswith("volume-watch: 2026-10-09 · 3 shares watched, 5 signals") and "1 message pushed" in r["line"] and "first run" in r["line"]
    assert sum(1 for u in calls if "sec_bhavdata_full_" in u) <= 25
    # second run, same day: nothing re-pushed, the heartbeat still says so
    r2 = c.post("/api/volume/run", json={"now": NOW.isoformat()}).json()
    assert r2["pushed"] == 0 and len(sent.texts) == 1 and "already pushed today" in r2["line"] and r2["deals"] == []
    h = c.get("/api/volume/symbol/tcs").json()
    assert h["symbol"] == "TCS" and h["rows"][-1]["rvol"] == 3.0 and h["rows"][-1]["volume"] == 300000
    assert c.get("/api/volume/latest").json()["last_run"]["day"] == "2026-10-09"


def test_nse_down_is_reported_not_invented(monkeypatch):
    c, sent, calls = _setup(monkeypatch, down=True)
    r = c.post("/api/volume/run", json={"now": NOW.isoformat()}).json()
    assert r["status"] == "warning" and r["pushed"] == 0 and sent.texts == []
    assert r["line"].startswith("volume-watch: no bhavcopy reachable") and "HTTP 403" in r["line"]
    assert len(calls) <= 4                                                                   # stops after 3 failures, no hammering


def test_runner_fleet_and_cron_wiring():
    seen, beats = {}, []
    old_api, old_hb = ag.api, ag.heartbeat
    ag.api = lambda path, method="GET", body=None, timeout=30: seen.update({"path": path, "timeout": timeout}) or {"line": "volume-watch: 2026-10-09 · 3 shares watched", "status": "clean"}
    ag.heartbeat = lambda *a: beats.append(a)
    try:
        assert ag.run_volume_watch({"id": "volume-watch"}, "none", "daily", NOW) == 0
    finally:
        ag.api, ag.heartbeat = old_api, old_hb
    assert seen["path"] == "/api/volume/run" and seen["timeout"] >= 600 and beats[0][0] == "volume-watch"
    bots = {b["id"]: b for b in yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))["bots"]}
    assert bots["volume-watch"]["enabled"] is True and bots["volume-watch"]["provider"] == "none" and "volume-watch" in ag.CUSTOM_BOTS
    agenda = yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))
    assert set(bots["volume-watch"]["serves"]) <= {o["id"] for o in agenda["objectives"]}
    assert "mdo_agent.py volume-watch" in open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()


def test_round_trip_deals_and_the_selection_keep_the_message_short():
    rt = [dict(day="2026-10-09", kind="bulk", symbol="PCJEWELLER", client="JUMP TRADING", side="BUY", qty=58690000, price=14.59),
          dict(day="2026-10-09", kind="bulk", symbol="PCJEWELLER", client="JUMP TRADING", side="SELL", qty=58690000, price=14.53),
          dict(day="2026-10-09", kind="bulk", symbol="TCS", client="REAL FUND", side="BUY", qty=2000000, price=3490.0)]
    assert [x["client"] for x in mv.net_deals(rt)] == ["REAL FUND"]                       # market-maker round trip is not a position
    held = {"TCS": [{"holder": "Aman", "qty": 5}], "SOLD": [{"holder": "Ashok", "qty": 9}]}
    sigs = [dict(symbol=f"S{i}", kind="quiet-at-buy", rvol=0.5, chg=0, text="x") for i in range(40)]
    sigs += [dict(symbol="TCS", kind="distribution", rvol=3.0, chg=-3, text="↓3.0% on 3.0× volume — heavy selling")]
    sigs += [dict(symbol="NOTMINE", kind="distribution", rvol=9.0, chg=-5, text="x")]       # not held: not a protection alert
    text = mv.push_text("2026-10-09", sigs, rt, held)
    assert text.splitlines()[0] == "Volume · Fri 09 Oct · protect 1 · opportunity 0 · deals 1 (+2 intraday round trips ignored)"
    assert len(text.splitlines()) <= 8 and "TCS" in text.splitlines()[1] and "NOTMINE" not in text
