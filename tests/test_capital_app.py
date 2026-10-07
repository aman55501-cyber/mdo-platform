"""Capital desk: formatting, PIN gate, auth, and what each page does and does not show."""
from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from starlette.testclient import TestClient

from capital import fmt, pin

UTC = timezone.utc
NOW = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)          # 11:30 IST, Wednesday: market open


class FakeDB:
    """Answers the app's queries by matching a distinctive fragment of the SQL."""

    def __init__(self, **over):
        pull = NOW - timedelta(hours=4)
        self.data = {
            "from wb.desk_freshness": [{"source": "holdings_pull", "last_at": pull}, {"source": "quotes", "last_at": None},
                                       {"source": "bantu_chat", "last_at": NOW - timedelta(hours=273)},
                                       {"source": "bank_balances", "last_at": NOW - timedelta(hours=22)}],
            "order by day_change_pct desc": [{"symbol": "MANYAVAR", "price": Decimal("1402.5"), "day_change_pct": Decimal("0.71"),
                                              "price_source": "holdings-pull", "price_time": pull, "owner_name": "Aditi Investments"}],
            "order by day_change_pct asc": [{"symbol": "NORTHARC", "price": Decimal("98.4"), "day_change_pct": Decimal("-0.32"),
                                             "price_source": "holdings-pull", "price_time": pull, "owner_name": "Aditi Investments"}],
            "from wb.ideas_view": [{"id": 2, "symbol": "VAML", "side": "ADD", "entry": Decimal("250"), "stop": Decimal("230"),
                                    "target": Decimal("300"), "horizon": None, "thesis": "On stale prices. Add ~2% of book",
                                    "status": "proposed", "run_date": date(2026, 9, 18), "age_days": 19, "price": None,
                                    "price_time": None, "price_source": None, "pct_from_entry": None, "held": False}],
            "from wb.calls_view": [{"id": 559, "caller": "Bantu Mausaji", "called_at": NOW - timedelta(days=11), "kind": "call",
                                    "action": "ADD", "symbol_raw": "TGVSL", "symbol": "TGVSL", "entry_low": Decimal("120"),
                                    "entry_high": Decimal("120"), "stop": None, "targets": [], "horizon": None, "status": "open",
                                    "needs_review": False, "unresolved": False, "price": None, "price_time": None,
                                    "price_source": None, "pct_from_entry": None, "held": True}],
            "select distinct portfolio": [{"portfolio": "A1504046"}],
            "from wb.manual_holdings where active": [],
            "from wb.holdings_view order by market_value": [],
            "from wb.actions_view": [],
            "group by 1, 2 order by 1, 2": [{"scope": "company", "line": "holdings", "n": 73, "prov": 73, "amount": Decimal("43593000")},
                                            {"scope": "personal", "line": "cash", "n": 1, "prov": 1, "amount": Decimal("3382210.47")}],
            "from wb.by_bucket": [{"bucket_id": "unbucketed", "amount": Decimal("43593000"), "lines": 73}],
            "from wb.balance_latest": [{"owner_id": "aman", "type": "bank", "institution": "HDFC Bank", "last4": "2484",
                                        "scope": "personal", "as_of": date(2026, 10, 5), "amount": Decimal("3382210.47"),
                                        "status": "provisional", "source": "gmail-alert"}],
            "not exists (select 1 from wb.balances": [{"owner_id": "sudha", "type": "bank", "institution": "HDFC Bank", "last4": "1128"}],
            "from wb.conflicts": [{"subject": "HDFC 2231 and 5555: owner and type unknown"}],
            "select (select count(*) from wb.liabilities)": [{"liab": 0, "assets": 0}],
            "select count(*) n from wb.accounts where active": [{"n": 3}],
            "from wb.source_health": [{"job": "heartbeat", "description": "host heartbeat", "active": True, "last_ran_at": pull,
                                       "last_ok_at": pull, "last_run_ok": True, "age_minutes": 240, "status": "OK"},
                                      {"job": "quote_poll", "description": "intraday quotes", "active": False, "last_ran_at": None,
                                       "last_ok_at": None, "last_run_ok": None, "age_minutes": None, "status": "DEAD"}],
        }
        self.data.update(over)

    def query(self, sql, params=None):
        for frag, rows in self.data.items():
            if frag in sql:
                return [dict(r) for r in rows]
        raise AssertionError(f"unexpected query: {sql[:90]}")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CAPITAL_USER", "aman")
    monkeypatch.setenv("CAPITAL_PASSWORD", "open-sesame")
    monkeypatch.setenv("CAPITAL_PIN", "4821")
    monkeypatch.setenv("CAPITAL_COOKIE_SECRET", "k" * 32)
    from capital import server
    server.app.state.db = FakeDB()
    server.app.state.guard = pin.PinGuard()
    with TestClient(server.app) as c:
        c.headers.update({"Authorization": "Basic " + base64.b64encode(b"aman:open-sesame").decode()})
        yield c


# ---- formatting -----------------------------------------------------------------------------------
def test_indian_formatting():
    assert fmt.inr(43593000) == "₹4.36 Cr"
    assert fmt.inr(3382210.47) == "₹33.82 L"
    assert fmt.inr(3382210.47, False) == "₹33,82,210"
    assert fmt.inr(-1500000) == "−₹15.00 L"
    assert fmt.inr(None) == "—"
    assert fmt.price(486.5) == "486.5" and fmt.price(1402) == "1,402" and fmt.price(120.0) == "120"
    assert fmt.pct(0.714) == "+0.71%" and fmt.pct(-0.32) == "−0.32%"


def test_market_hours_ist():
    wed_1130 = datetime(2026, 10, 7, 11, 30, tzinfo=fmt.IST)
    assert fmt.market_open(wed_1130)
    assert not fmt.market_open(datetime(2026, 10, 7, 7, 45, tzinfo=fmt.IST))     # the pre-market pull
    assert not fmt.market_open(datetime(2026, 10, 10, 11, 0, tzinfo=fmt.IST))    # Saturday


# ---- auth + pin -----------------------------------------------------------------------------------
def test_everything_but_healthz_needs_login(client):
    bare = TestClient(client.app)
    assert bare.get("/healthz").text == "ok"
    for path in ("/", "/holdings", "/networth", "/health"):
        assert bare.get(path).status_code == 401


def test_pin_cookie_roundtrip_and_expiry():
    c = pin.make_cookie("k", now=1000)
    assert pin.cookie_valid(c, "k", now=1001)
    assert not pin.cookie_valid(c, "k", now=1000 + pin.TTL_SECONDS + 1)
    assert not pin.cookie_valid(c, "other-key", now=1001)
    assert not pin.cookie_valid("garbage", "k")


def test_pin_guard_locks_after_repeated_failures():
    g = pin.PinGuard()
    for _ in range(pin.MAX_FAILS):
        assert not g.attempt("0000", "4821", now=100)
    assert g.locked(now=101)
    assert not g.attempt("4821", "4821", now=101)           # correct PIN refused while locked
    assert g.attempt("4821", "4821", now=100 + pin.LOCK_SECONDS + 1)


def test_networth_locked_until_pin(client):
    r = client.get("/networth")
    assert "Net worth is locked" in r.text and "₹" not in r.text
    bad = client.post("/unlock", content=b"pin=0000", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert "not right" in bad.text and "₹" not in bad.text
    ok = client.post("/unlock", content=b"pin=4821", headers={"Content-Type": "application/x-www-form-urlencoded"},
                     follow_redirects=False)
    assert ok.status_code == 303 and pin.COOKIE in ok.headers["set-cookie"]
    client.cookies.set(pin.COOKIE, pin.make_cookie("k" * 32))
    page = client.get("/networth").text
    assert "₹" in page and "partial" in page.lower()


def test_no_pin_configured_stays_locked(client, monkeypatch):
    monkeypatch.delenv("CAPITAL_PIN")
    client.cookies.set(pin.COOKIE, pin.make_cookie("k" * 32))
    assert "No PIN is configured" in client.get("/networth").text


# ---- what the pages say ---------------------------------------------------------------------------
def test_desk_opens_without_any_net_worth_or_rupee_total(client):
    t = client.get("/").text
    assert "Top gainers" in t and "Top losers" in t and "Live trade ideas" in t and "Bantu Mausaji's calls" in t
    assert "Net worth" in t                                  # only as a nav link
    assert "₹" not in t and "Cr" not in t.replace("Crypto", "")


def test_desk_labels_stale_prices_and_dead_bantu_feed(client):
    t = client.get("/").text
    assert "No live quotes right now" in t
    assert "273h old" in t or "11d old" in t
    assert "stale prices" in t                               # the VAML idea was priced on stale data
    assert "Nothing is removed" in t


def test_desk_says_how_much_of_the_book_the_held_check_sees(client):
    t = client.get("/").text
    assert "1 of 4" in t and "Aman (HDFC1)" in t and "Sudha (HDFC2)" in t and "is not marked" in t


def test_empty_ideas_and_calls_are_written_out(client):
    client.app.state.db = FakeDB(**{"from wb.ideas_view": [], "from wb.calls_view": []})
    t = client.get("/").text
    assert "No open trade ideas." in t
    assert "No open calls from Bantu Mausaji." in t


def test_database_failure_is_unreachable_not_a_500(client):
    class Broken:
        def query(self, *a, **k):
            raise RuntimeError("connection refused")
    client.app.state.db = Broken()
    r = client.get("/")
    assert r.status_code == 200 and "UNREACHABLE — database" in r.text


def test_networth_lists_what_it_cannot_see(client):
    client.cookies.set(pin.COOKIE, pin.make_cookie("k" * 32))
    t = client.get("/networth").text
    assert "No balance on record: HDFC Bank ••1128" in t
    assert "Holdings not ingested: Aman (HDFC1)" in t
    assert "No liabilities recorded" in t
    assert "Open question: HDFC 2231 and 5555" in t


def test_health_marks_undeployed_jobs(client):
    t = client.get("/health").text
    assert "not deployed" in t and "heartbeat" in t


def test_responses_are_not_cacheable(client):
    r = client.get("/")
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"]


# ---- graphic bars ----------------------------------------------------------------------------------
def test_range_bar_math_and_refusals():
    r = fmt.range_bar(125, 100, 150, 110)
    assert round(r["now"]) == 50 and round(r["mark"]) == 20 and r["state"] == "inside" and (r["low"], r["high"]) == (100, 150)
    assert fmt.range_bar(90, 100, 150)["state"] == "below_stop" and fmt.range_bar(90, 100, 150)["now"] == 0
    assert fmt.range_bar(160, 100, 150)["state"] == "at_target" and fmt.range_bar(160, 100, 150)["now"] == 100
    assert fmt.range_bar(125, None, 150) is None            # no stop: no invented bar
    assert fmt.range_bar(125, 150, 100) is None             # inverted range
    assert fmt.range_bar(None, 100, 150)["state"] is None   # no price: bar has no pin


def test_movers_have_size_bars_scaled_to_the_biggest_move(client):
    t = client.get("/").text
    assert t.count('role="progressbar"') >= 3               # two movers + coverage
    assert 'aria-valuenow="100"' in t                       # the biggest mover fills its bar
    assert "coverage" in t and 'aria-valuenow="25"' in t        # 1 of 4 demats


def test_idea_without_stop_and_target_gets_no_made_up_bar(client):
    t = client.get("/").text
    assert "No progress bar: needs both a stop and a target." not in t     # VAML has both
    client.app.state.db = FakeDB(**{"from wb.ideas_view": [dict(FakeDB().data["from wb.ideas_view"][0], stop=None)]})
    assert "No progress bar: needs both a stop and a target." in client.get("/").text


def test_idea_with_price_shows_progress_pin(client):
    row = dict(FakeDB().data["from wb.ideas_view"][0], price=Decimal("265"), price_source="angel", price_time=NOW,
               price_time_=None)
    client.app.state.db = FakeDB(**{"from wb.ideas_view": [row]})
    t = client.get("/").text
    assert "nowpin" in t and "tick = entry" in t and "stop 230" in t and "target 300" in t


def test_networth_and_health_progress(client):
    client.cookies.set(pin.COOKIE, pin.make_cookie("k" * 32))
    assert "How much of your money this counts" in client.get("/networth").text
    assert "Deployed jobs healthy" in client.get("/health").text


# ---- held stocks stay visible, marked ---------------------------------------------------------------
def test_held_ideas_and_calls_are_marked_not_removed(client):
    idea = FakeDB().data["from wb.ideas_view"][0]
    client.app.state.db = FakeDB(**{"from wb.ideas_view": [dict(idea, symbol="HELDCO", held=True), dict(idea, id=3, symbol="NEWCO")]})
    t = client.get("/").text
    assert "HELDCO" in t and "NEWCO" in t                       # both listed
    assert t.count('class="chip held"') == 2                     # the held idea and the held call (TGVSL)
    assert "Nothing is removed" in t


# ---- daily login tab ---------------------------------------------------------------------------------
import httpx as _httpx

CFO_ACCOUNTS = {"accounts": [
    {"key": "HDFC1", "label": "Aman (personal)", "broker": "hdfc", "client_code": "4016900", "logged_in": True},
    {"key": "HDFC2", "label": "Sudha", "broker": "hdfc", "client_code": "189737306", "logged_in": False},
    {"key": "HDFC3", "label": "Ashok", "broker": "hdfc", "client_code": "190837559", "logged_in": False},
    {"key": "ANGEL1", "label": "Aditi Investment", "broker": "angel", "client_code": "288924176", "logged_in": True}]}


def _cfo(seen, location="https://developer.hdfcsec.com/oapi/v1/login?api_key=PUB", status=200):
    def handler(req):
        seen.append((req.url.path, req.headers.get("x-cfo-token"), dict(req.url.params)))
        if req.url.path == "/accounts":
            return _httpx.Response(status, json=CFO_ACCOUNTS)
        if req.url.path == "/hdfc/login":
            return _httpx.Response(307, headers={"location": location}) if location else _httpx.Response(500)
        return _httpx.Response(404)
    return _httpx.Client(transport=_httpx.MockTransport(handler))


@pytest.fixture()
def login_client(client, monkeypatch):
    monkeypatch.setenv("CAPITAL_CFO_URL", "http://cfo.test")
    monkeypatch.setenv("CFO_API_TOKEN", "super-secret-cfo-token")
    return client


def test_daily_login_board_counts_progress_and_gives_hdfc_a_button_not_angel(login_client):
    login_client.app.state.cfo_http = _cfo([])
    t = login_client.get("/daily-login").text
    assert "1 of 3" in t and 'aria-valuenow="33"' in t
    assert 'action="/daily-login/start/HDFC2"' in t and 'action="/daily-login/start/HDFC3"' in t
    assert 'action="/daily-login/start/HDFC1"' not in t              # already logged in
    assert "signs in by itself" in t and "ANGEL1/start" not in t
    assert "super-secret-cfo-token" not in t                          # the API token never reaches the page


def test_start_sends_token_in_header_only_and_redirects_to_hdfc(login_client):
    seen = []
    login_client.app.state.cfo_http = _cfo(seen)
    r = login_client.post("/daily-login/start/HDFC2", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://developer.hdfcsec.com/")
    login = [s for s in seen if s[0] == "/hdfc/login"][0]
    assert login[1] == "super-secret-cfo-token" and login[2] == {"key": "HDFC2"}
    assert "super-secret-cfo-token" not in r.headers["location"] and "token=" not in r.headers["location"]


def test_start_refuses_unknown_and_non_hdfc_accounts_without_calling_login(login_client):
    seen = []
    login_client.app.state.cfo_http = _cfo(seen)
    for key in ("ANGEL1", "HDFC9", "../../etc"):
        r = login_client.post(f"/daily-login/start/{key}", follow_redirects=False)
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert "cannot be logged in from here" in r.text
    assert not [s for s in seen if s[0] == "/hdfc/login"]


def test_start_refuses_an_insecure_login_address(login_client):
    login_client.app.state.cfo_http = _cfo([], location="http://evil.example/login")
    r = login_client.post("/daily-login/start/HDFC2", follow_redirects=False)
    assert r.status_code == 200 and "secure HDFC login address" in r.text


def test_login_service_down_is_unreachable_and_claims_nothing(login_client):
    login_client.app.state.cfo_http = _cfo([], status=503)
    t = login_client.get("/daily-login").text
    assert "UNREACHABLE — login service" in t and "logged in</span>" not in t


def test_not_configured_names_the_missing_variables_only(client, monkeypatch):
    monkeypatch.delenv("CAPITAL_CFO_URL", raising=False)
    monkeypatch.delenv("CFO_API_TOKEN", raising=False)
    t = client.get("/daily-login").text
    assert "CAPITAL_CFO_URL and CFO_API_TOKEN" in t


def test_login_tab_is_in_the_nav_and_behind_basic_auth(client):
    assert 'href="/daily-login"' in client.get("/").text
    assert TestClient(client.app).get("/daily-login").status_code == 401
    assert TestClient(client.app).post("/daily-login/start/HDFC1").status_code == 401
