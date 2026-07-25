"""Core safety + correctness tests — the pure functions where the review's P0/P1s lived.

Runs under pytest (the project's runner) OR standalone: `python tests/test_core.py`.
Kept dependency-light and file-isolated so it can run in CI or on the box.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Make `shares_cfo` importable when run standalone (pytest handles this via rootdir).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- guardrails: the safety gate -------------------------------------------------
def _order(**kw):
    from shares_cfo.execution.models import OrderRequest
    base = dict(creds_key="ANGEL1", exchange="NFO", symbol="NIFTY24500CE", token="1",
                side="BUY", quantity=75, price=120, stop_loss=90, target=200,
                underlying="NIFTY", lot_size=75)
    base.update(kw)
    return OrderRequest(**base)


def _cfg(**kw):
    from shares_cfo.config import TradingConfig
    base = dict(enabled=True, max_orders_per_day=10, max_risk_per_trade=5000,
                fno_enabled=True, fno_allowed_underlyings=("NIFTY",),
                max_lots_per_order=5, max_premium_per_order=20000)
    base.update(kw)
    return TradingConfig(**base)


def _blocks(order, cfg, day_pnl=0.0, kill=False):
    from shares_cfo.execution import guardrails as g
    try:
        g.check(order, cfg, 0, day_pnl, kill)
        return None
    except g.GuardrailError as e:
        return str(e)


def test_fno_lot_multiple_enforced():
    assert _blocks(_order(quantity=100), _cfg()) and "multiple" in _blocks(_order(quantity=100), _cfg())


def test_fno_lots_cap():
    assert "lots" in _blocks(_order(quantity=450), _cfg())  # 6 lots > cap 5


def test_fno_premium_cap():
    # 3 lots (225) * 100 premium = 22500 > 20000; keep risk under its cap
    assert "Premium" in _blocks(_order(quantity=225, price=100, stop_loss=98), _cfg())


def test_fno_switch_off_blocks():
    assert "F&O" in _blocks(_order(), _cfg(fno_enabled=False))


def test_kill_switch_blocks():
    assert "Kill" in _blocks(_order(), _cfg(), kill=True)


def test_daily_loss_halt_triggers():
    assert "halt" in _blocks(_order(), _cfg(daily_loss_halt=2500), day_pnl=-3000).lower()


def test_daily_loss_unknown_fails_closed():
    # P&L None + a halt set MUST refuse (fail closed), not pass
    assert "verify" in _blocks(_order(), _cfg(daily_loss_halt=2500), day_pnl=None).lower()


def test_no_halt_unknown_pnl_ok():
    assert _blocks(_order(), _cfg(daily_loss_halt=0), day_pnl=None) is None


def test_fno_good_order_passes():
    assert _blocks(_order(), _cfg()) is None


# --- reconciliation matchers -----------------------------------------------------
def test_order_match_no_false_substring():
    from shares_cfo import reconcile_live as R
    assert R._order_matches({"symbol": "BIOCON28JUL26FUT"}, None, "IOC FUT 28-JUL-26") is False
    assert R._order_matches({"symbol": "IOC28JUL26FUT"}, None, "IOC FUT 28-JUL-26") is True
    assert R._order_matches({"symbol": "X", "symboltoken": "999"}, "999", "ANYTHING") is True


def test_match_orders_buckets():
    from shares_cfo import reconcile_live as R
    sent = [
        {"ts": "t1", "order": {"symbol": "NIFTYCE", "side": "BUY", "quantity": 75,
                               "creds_key": "ANGEL1", "stop_loss": 90},
         "result": {"account": "ANGEL1", "orderid": "A1", "stop_loss_orderid": "A1SL"}},
        {"ts": "t2", "order": {"symbol": "BN", "side": "BUY", "quantity": 35,
                               "creds_key": "ANGEL1", "stop_loss": 100},
         "result": {"account": "ANGEL1", "orderid": "A2", "stop_loss_error": "RMS"}},
        {"ts": "t3", "order": {"symbol": "INFY", "side": "BUY", "quantity": 1, "stop_loss": 0},
         "result": {"account": "HDFC1", "orderid": "H9"}},
    ]
    book = [
        {"orderid": "A1", "status": "complete", "symbol": "NIFTYCE", "symboltoken": "1"},
        {"orderid": "A1SL", "status": "trigger pending", "trigger": 90, "symboltoken": "1"},
        {"orderid": "A2", "status": "rejected", "reason": "margin"},
    ]
    m = R.match_orders(sent, book)
    assert len(m["matched"]) == 1 and len(m["rejected"]) == 1
    assert len(m["unaccounted"]) == 1 and len(m["sl_issues"]) == 1


def test_naked_positions():
    from shares_cfo import reconcile_live as R
    book = [{"orderid": "A1SL", "status": "trigger pending", "side": "SELL",
             "trigger": 90, "symboltoken": "111", "creds_key": "ANGEL1"}]
    pos = [
        {"creds_key": "HDFC2", "account": "Sudha", "ticker": "VEDL FUT 28-JUL-26",
         "token": "999", "quantity": 1150, "kind": "future"},
        {"creds_key": "ANGEL1", "account": "Aditi", "ticker": "NIFTY24500CE",
         "token": "111", "quantity": 75, "kind": "option"},
    ]
    naked = R.naked_positions(pos, book)
    assert len(naked) == 1 and naked[0]["symbol"].startswith("VEDL")


# --- fundamentals D/E ------------------------------------------------------------
def test_de_source_units():
    from shares_cfo.analysis.fundamentals import _norm_de
    assert _norm_de(6.0, as_ratio=True) == 6.0     # Screener ratio: leveraged NBFC stays leveraged
    assert _norm_de(72.5) == 0.725                 # yfinance percent -> ratio


# --- server pure helpers ---------------------------------------------------------
def test_avg_plausible():
    from shares_cfo.server import _avg_plausible
    assert _avg_plausible("future", 11.6, 265.1) is False   # VEDL bad basis
    assert _avg_plausible("future", 265, 270) is True
    assert _avg_plausible("option", 5, 50) is True          # options exempt


def test_buildup_deadband():
    from shares_cfo.server import _buildup
    assert _buildup(0.3, 0.5) == "Flat"            # <1.5% OI drift
    assert _buildup(0.3, 5.0) == "Long buildup"
    assert _buildup(-0.3, 5.0) == "Short buildup"


# --- kill-switch persistence + proposal TTL + orders counter ---------------------
def test_kill_switch_persists(tmp_path=None):
    import shares_cfo.execution.engine as E
    d = Path(tmp_path or tempfile.mkdtemp())
    E._KILL_FILE = d / "kill.on"
    assert E._kill_engaged() is False
    E.engage_kill()
    assert E._kill_engaged() is True               # a fresh process re-reads the file
    E.release_kill()
    assert E._kill_engaged() is False


def test_orders_today_daily_roll(tmp_path=None):
    import shares_cfo.execution.engine as E
    d = Path(tmp_path or tempfile.mkdtemp())
    E._ORDERS_FILE = d / "orders.json"
    assert E._orders_today() == 0
    E._bump_orders(); E._bump_orders()
    assert E._orders_today() == 2                  # persisted, survives a "restart"
    # a stale (yesterday) file reads as 0 today
    E._ORDERS_FILE.write_text('{"date":"1999-01-01","count":9}')
    assert E._orders_today() == 0


# --- tips (advisor calls) --------------------------------------------------------
def test_tips_defaults_and_state():
    from shares_cfo import tips
    assert tips.suggest_stop(100, "BUY", 4.0) == 96.0
    assert tips.ladder(100, 3, 5.0) == [100.0, 95.0, 90.0]
    st = tips.state({"kind": "trade", "buy": 85, "target": 150, "stop": 81.6, "side": "BUY"}, 82.1)
    assert st["actionable"] is True and "entry" in st["state"]
    st2 = tips.state({"kind": "trade", "buy": 85, "target": 150, "stop": 81.6, "side": "BUY"}, 80.0)
    assert st2.get("alert") is True                # below stop -> alert


# --- screener LLM column mapper --------------------------------------------------
_CANDS = {
    "pe": ["Price to Earning", "P/E"],
    "roe": ["Return on equity", "ROE %"],
    "industry": ["Industry", "Sub-Industry"],
}


def test_screener_static_map_and_no_llm_when_complete():
    from shares_cfo.analysis import screener_map as sm

    def boom(prompt, timeout):
        raise AssertionError("LLM must not be called when static maps everything")

    headers = ["Name", "P/E", "Return on equity", "Industry"]
    m = sm.resolve(headers, _CANDS, call_fn=boom)     # all present -> pure static, no call
    assert m == {"pe": "P/E", "roe": "Return on equity", "industry": "Industry"}


def test_screener_llm_fills_gap():
    from shares_cfo.analysis import screener_map as sm
    headers = ["Name", "P/E", "Return on Equity (%)"]  # roe header static can't match
    calls = {"n": 0}

    def fake(prompt, timeout):
        calls["n"] += 1
        assert "roe" in prompt and "Return on Equity (%)" in prompt  # only the gap is asked
        return '{"roe": "Return on Equity (%)"}'

    m = sm.resolve(headers, _CANDS, call_fn=fake)
    assert m["pe"] == "P/E" and m["roe"] == "Return on Equity (%)" and calls["n"] == 1


def test_screener_rejects_hallucinated_header():
    from shares_cfo.analysis import screener_map as sm
    headers = ["Name", "P/E"]

    def liar(prompt, timeout):
        return '{"roe": "Column That Does Not Exist", "industry": "Also Fake"}'

    m = sm.resolve(headers, _CANDS, call_fn=liar)
    assert m == {"pe": "P/E"}                          # invented headers dropped, not trusted


def test_screener_mapping_cached(tmp_path=None):
    from shares_cfo.analysis import screener_map as sm
    d = Path(tmp_path or tempfile.mkdtemp())
    headers = ["Name", "P/E", "Return on Equity (%)"]

    m1 = sm.resolve(headers, _CANDS, cache_dir=d, call_fn=lambda p, t: '{"roe": "Return on Equity (%)"}')
    assert m1["roe"] == "Return on Equity (%)"

    def boom(prompt, timeout):
        raise AssertionError("second resolve must hit the cache, not the LLM")

    m2 = sm.resolve(headers, _CANDS, cache_dir=d, call_fn=boom)
    assert m2 == m1


def test_screener_text_field_passthrough():
    from shares_cfo.analysis import fundamentals as fun
    mapping = {"industry": "Industry", "pe": "P/E", "de": "Debt to equity"}
    row = {"Industry": "Auto Ancillary", "P/E": "12.5", "Debt to equity": "0.8"}
    fields = fun._map_row(row, mapping)
    assert fields["industry"] == "Auto Ancillary"     # text passed through, not float-parsed
    assert fields["pe"] == 12.5
    assert fields["de"] == 0.8                         # screener D/E stays a ratio


# --- sub-sector grouping (sector tile -> industries) -----------------------------
def test_subsector_split_and_unclassified():
    # mirrors holdings_grouped._summarise/_group(subkey) shape without the web layer
    def summarise(name, rows):
        value = sum(s["value"] for s in rows)
        return {"name": name, "value": value, "count": len(rows),
                "stocks": sorted(rows, key=lambda x: -x["value"])}

    def group(stocks, key, subkey=None):
        buckets = {}
        for s in stocks:
            buckets.setdefault(s[key], []).append(s)
        out = []
        for name, rows in buckets.items():
            entry = summarise(name, rows)
            if subkey:
                subs = {}
                for s in rows:
                    subs.setdefault(s.get(subkey) or "Unclassified", []).append(s)
                entry["sub_sectors"] = sorted((summarise(sn, sr) for sn, sr in subs.items()),
                                              key=lambda g: -g["value"])
            out.append(entry)
        return out

    stocks = [
        {"symbol": "BOSCHLTD", "sector": "AUTO", "industry": "Auto Ancillary", "value": 300},
        {"symbol": "MOTHERSON", "sector": "AUTO", "industry": "Auto Ancillary", "value": 200},
        {"symbol": "TVSMOTOR", "sector": "AUTO", "industry": "2-Wheelers", "value": 500},
        {"symbol": "XYZ", "sector": "AUTO", "industry": None, "value": 50},
    ]
    auto = group(stocks, "sector", subkey="industry")[0]
    subs = {s["name"]: s for s in auto["sub_sectors"]}
    assert auto["value"] == 1050 and len(auto["sub_sectors"]) == 3
    assert subs["2-Wheelers"]["value"] == 500                 # sorted first (largest)
    assert subs["Auto Ancillary"]["value"] == 500 and subs["Auto Ancillary"]["count"] == 2
    assert "Unclassified" in subs and subs["Unclassified"]["value"] == 50


# --- universe: merge all exports + index + search/screen -------------------------
def _write_universe(d: Path):
    (d / "a_old.csv").write_text(
        "Name,NSE Code,P/E,Industry\n"
        "Reliance Industries,RELIANCE,25,Refineries\n"
        "Tata Consultancy,TCS,30,IT Services\n", encoding="utf-8")
    (d / "b_new.csv").write_text(
        "Name,NSE Code,P/E,Industry\n"
        "Reliance Industries,RELIANCE,20,Refineries\n"
        "Infosys,INFY,22,IT Services\n", encoding="utf-8")
    import os
    os.utime(d / "a_old.csv", (1000, 1000))
    os.utime(d / "b_new.csv", (2000, 2000))   # newer -> wins on conflict


def _universe_env(tmp_path=None):
    from shares_cfo.analysis import fundamentals as F, universe as U
    d = Path(tmp_path or tempfile.mkdtemp())
    _write_universe(d)
    F.SCREENER_DIR = d
    U.INDEX_CACHE = d / ".universe_index.json"
    U._MEMO = {"fp": None, "index": None}
    return F, U, d


def test_universe_merge_newest_wins():
    _, U, _ = _universe_env()
    idx = U.get_index()
    assert set(idx.keys()) == {"RELIANCE", "TCS", "INFY"}       # merged across both files
    assert U.record("RELIANCE")["fields"]["pe"] == 20.0         # newer file overrides


def test_universe_search_ranked():
    _, U, _ = _universe_env()
    hits = U.search("INF")
    assert hits and hits[0]["code"] == "INFY"
    assert U.search("RELIANCE")[0]["code"] == "RELIANCE"       # exact code first


def test_universe_screen_numeric_and_text():
    _, U, _ = _universe_env()
    cheap = U.screen({"pe": {"max": 23}})
    assert cheap["count"] == 2 and {r["code"] for r in cheap["results"]} == {"RELIANCE", "INFY"}
    it = U.screen({"industry": "IT"})
    assert {r["code"] for r in it["results"]} == {"TCS", "INFY"}


def test_universe_index_cached_and_rebuilds():
    _, U, d = _universe_env()
    U.get_index()
    assert (d / ".universe_index.json").exists()               # persisted
    # a new file changes the fingerprint -> rebuild picks it up
    (d / "c.csv").write_text("Name,NSE Code,P/E\nWipro,WIPRO,18\n", encoding="utf-8")
    import os
    os.utime(d / "c.csv", (3000, 3000))
    assert "WIPRO" in U.get_index()


# --- order model segment awareness ----------------------------------------------
def test_order_segment_awareness():
    o = _order(quantity=150)                        # 2 lots
    assert o.is_fno and o.is_option and o.segment == "FNO"
    assert o.lots() == 2.0
    assert o.premium_outlay() == 150 * 120          # BUY option


# --- standalone runner (works without pytest) ------------------------------------
if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
