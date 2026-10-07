"""Writer jobs: the call parser on real message shapes, and the quote poller against a mocked broker."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from capital import fmt, scrip
from capital.jobs import parse_calls, quote_poll
from capital.jobs.parse_calls import parse_message, resolve

KSCL = ("FOR 30-45 DAYS \n *ADD : KSCL @ 780-782* \n *(KAVERI SEED CORP LTD)* \n  \n SL - 701 \n  \n Target 795 \n 816 \n 834 \n"
        " 848 \n 865 \n 893 \n 914 \n 945 \n 978 \n  \n Note- Only for Educational purposes")
GLYCOLS = ("FOR 30-45 DAYS  \n *ADD  : INDIA GLYCOLS @ 304-305* \n  \n SL 260 \n  \n Target  \n  \n 310 \n 321 \n 333 \n"
           " 346 \n  \n Note- Only for Educational purposes")


def test_full_call_is_parsed_with_entry_range_stop_targets_and_horizon():
    p = parse_message(KSCL)
    assert (p.action, p.symbol_raw, p.entry_low, p.entry_high, p.stop) == ("ADD", "KSCL", 780, 782, 701)
    assert p.targets[:3] == [795, 816, 834] and len(p.targets) == 9 and p.horizon == "30-45 days"


def test_targets_split_across_blank_lines_and_stop_at_the_disclaimer():
    p = parse_message(GLYCOLS)
    assert p.targets == [310, 321, 333, 346] and p.stop == 260


def test_single_price_call_has_no_invented_stop_or_targets():
    p = parse_message("DARK HORSE \n LOOKING VERY GOOD \n *ADD # TGVSL @ 120.00* \n *(TGV SRAAC LTD)*")
    assert (p.symbol_raw, p.entry_low, p.entry_high, p.stop, p.targets) == ("TGVSL", 120, 120, None, [])


def test_his_own_buys_are_kept_as_declared_and_filler_words_dropped():
    a, b = parse_message("Added Adani power."), parse_message("Added apl apollo more")
    assert (a.kind, a.symbol_raw, a.action) == ("declared", "Adani power", "ADD") and b.symbol_raw == "apl apollo"


@pytest.mark.parametrize("text", ["Added", "", "https://www.facebook.com/share/r/19MfKBNdE5/", "can add me @ 5 pm",
                                  "Motilal initiate coverage on Shriram Piston. Target 6150. Holding all old.",
                                  "Yadi free ho to aa ja beta"])
def test_news_chat_links_and_prose_are_not_calls(text):
    assert parse_message(text) is None


def test_names_resolve_only_to_tickers_we_can_vouch_for():
    known = {"KSCL", "ADANIPOWER"}
    assert resolve("KSCL", known) == "KSCL" and resolve("Adani power", known) == "ADANIPOWER"
    assert resolve("INDIA GLYCOLS", known) is None            # a company name, not a ticker: left unresolved


class WriterDB:
    def __init__(self, messages, known=()):
        self.messages, self.known, self.writes = messages, known, []

    def query(self, sql, params=None):
        if "from public.wa_messages" in sql:
            return self.messages
        return [{"symbol": s} for s in self.known]

    def execute(self, sql, params=None):
        self.writes.append((sql, params))
        return 0


def _msg(i, body):
    return {"id": i, "account": "wa1", "sent_at": datetime(2026, 9, 25, 3, 33, tzinfo=timezone.utc), "body": body}


def test_run_inserts_calls_flags_unresolved_and_always_writes_a_heartbeat():
    db = WriterDB([_msg(541, KSCL), _msg(540, GLYCOLS), _msg(594, "https://x.example/y"), _msg(543, "Added Adani power.")],
                  known=["ADANIPOWER"])
    out = parse_calls.run(db, master={"KSCL": {"token": "1", "symbol": "KSCL-EQ"}})
    assert out["new"] == 3 and out["scanned"] == 4 and out["unresolved"] == 1
    inserts = [p for s, p in db.writes if s.startswith("insert into wb.calls")]
    by_msg = {p[0]: p for p in inserts}
    assert by_msg[541][7] == "KSCL" and by_msg[541][-1] is False        # resolved, full call: no review needed
    assert by_msg[540][7] is None and by_msg[540][-1] is True           # company name: needs review
    assert by_msg[543][5] == "ADD" and by_msg[543][-1] is True          # declared buy: always reviewed
    log = [p for s, p in db.writes if "wb.run_log" in s][-1]          # params: (job, summary); ok is a literal true
    assert log[0] == "bantu_calls" and "3 new call(s)" in log[1] and "1 name(s) not matched" in log[1]


def test_run_with_nothing_new_still_reports():
    db = WriterDB([])
    out = parse_calls.run(db, master={})
    assert out["new"] == 0
    assert any("wb.run_log" in s for s, _ in db.writes)


def test_failure_is_logged_as_failure_then_raised():
    class Boom(WriterDB):
        def query(self, sql, params=None):
            raise RuntimeError("db down")
    db = Boom([])
    with pytest.raises(RuntimeError):
        parse_calls.run(db, master={})
    assert db.writes and db.writes[-1][1][1].startswith("FAILED: RuntimeError")


# ---- quote poller ------------------------------------------------------------------------------------
ENV = {"ANGEL_ADITI_API_KEY": "k", "ANGEL_ADITI_CLIENT_ID": "A1", "ANGEL_ADITI_PIN": "1234", "ANGEL_ADITI_TOTP_SECRET": "JBSWY3DPEHPK3PXP"}


class QuoteDB(WriterDB):
    def query(self, sql, params=None):
        if "from wb.holdings_raw" in sql:
            return [{"symbol": "MANYAVAR", "symboltoken": "1111", "exchange": "NSE", "isin": "INE0"}]
        if "from public.watchlist" in sql:
            return []
        return [{"symbol": "KSCL"}]


def _mock(seen):
    def handler(req: httpx.Request):
        seen.append(req.url.path)
        if req.url.host == "api.ipify.org":
            return httpx.Response(200, text="203.0.113.7")
        if req.url.path == quote_poll.LOGIN_PATH:
            return httpx.Response(200, json={"data": {"jwtToken": "jwt"}})
        body = json.loads(req.content)
        assert body["exchangeTokens"]["NSE"] == ["1111", "2222"]
        return httpx.Response(200, json={"data": {"fetched": [
            {"symbolToken": "1111", "ltp": 1402.5, "close": 1390.0, "exchFeedTime": "07-Oct-2026 11:30:05"},
            {"symbolToken": "2222", "ltp": 790.0, "close": 780.0, "exchFeedTime": "07-Oct-2026 11:30:04"}], "unfetched": []}})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_quote_poll_prices_held_and_idea_symbols_and_touches_only_login_and_quote():
    seen, db = [], QuoteDB([])
    out = quote_poll.run(db, force=True, client=_mock(seen), master={"KSCL": {"token": "2222", "symbol": "KSCL-EQ"}},
                         env=ENV, sleep=lambda s: None)
    assert out == {"priced": 2, "wanted": 2, "unfetched": 0}
    assert set(seen) - {"/"} <= quote_poll.ALLOWED_PATHS | {"/"}
    ups = [p for s, p in db.writes if "wb.quotes" in s]
    assert {u[0] for u in ups} == {"MANYAVAR", "KSCL"} and ups[0][3] == 1390.0
    assert "2 of 2 symbols priced" in db.writes[-1][1][2]


def test_quote_poll_skips_when_the_market_is_closed_but_still_reports():
    db = QuoteDB([])
    out = quote_poll.run(db, now=datetime(2026, 10, 7, 7, 45, tzinfo=fmt.IST), env=ENV)
    assert out == {"skipped": True} and "market closed" in db.writes[-1][1][2]


def test_missing_credentials_are_named_but_never_valued():
    db = QuoteDB([])
    with pytest.raises(Exception) as e:
        quote_poll.run(db, force=True, env={"ANGEL_ADITI_API_KEY": "secret-value"})
    assert "ANGEL_ADITI_CLIENT_ID" in str(e.value) and "secret-value" not in str(e.value)
    assert db.writes[-1][1][1] is False


def test_symbol_master_filters_to_nse_equity_and_normalises(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPITAL_CACHE_DIR", str(tmp_path))
    rows = [{"token": "1", "symbol": "KSCL-EQ", "exch_seg": "NSE"}, {"token": "2", "symbol": "KSCL", "exch_seg": "BSE"},
            {"token": "3", "symbol": "NIFTY26OCTFUT", "exch_seg": "NFO"}]
    m = scrip.load(fetch=lambda: rows)
    assert m == {"KSCL": {"token": "1", "symbol": "KSCL-EQ"}}
