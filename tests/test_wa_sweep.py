"""wa-sweep — Aman's eyes on the Mausaji chat and the site groups, rule-based, zero LLM spend.

Aman, chat 2026-10-09. Nothing here touches the network: Yahoo, the NSE list, the NSE option chain and
the WhatsApp send are canned. Follows tests/test_levels.py: a scratch VEGA_DB_PATH is set before
mdo_server is imported; the endpoint tests wipe the WhatsApp tables they use (the DB is shared by every
test module).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("SHARE_MASTER_DATA_DIR", tempfile.mkdtemp())

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_option_levels as ol  # noqa: E402
import mdo_wa_sweep as ws  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRI_1045 = datetime(2026, 10, 9, 10, 45, tzinfo=IST)
FRI_0800 = datetime(2026, 10, 9, 8, 0, tzinfo=IST)
BOT = {"id": "wa-sweep", "provider": "none", "model": "none"}
MAUSAJI_JID = "919800000001@s.whatsapp.net"
WASHERY_JID = "120363111@g.us"
RAKE_JID = "120363222@g.us"
CORE_JID = "120363333@g.us"
FAMILY_JID = "120363444@g.us"
TRANSPORT_JID = "120363555@g.us"
VEDANTA_JID = "919800000002@s.whatsapp.net"

LEVELS = [{"ticker": "TCS", "note": "Tata Consultancy Services · Mausaji (call) · zone 3450 - 3500"},
          {"ticker": "ADVENTHTL", "note": "Advent Hotels International · Mausaji (mention)"},
          {"ticker": "RELIANCE", "note": ""}]
INDEX = ws.ticker_index(LEVELS, {"ETERNAL", "INFY", "IDEA", "TATACOMM"})
CHAIN = {"records": {"expiryDates": ["29-Dec-2026"], "data": [
    {"strikePrice": 24500, "expiryDate": "29-Dec-2026", "CE": {"lastPrice": 60.0}, "PE": {"lastPrice": 700.0}},
    {"strikePrice": 25000, "expiryDate": "29-Dec-2026", "CE": {"lastPrice": 27.5}, "PE": {"lastPrice": 905.2}},
    {"strikePrice": 25000, "expiryDate": "30-Oct-2026", "CE": {"lastPrice": 3.1}},
]}}


# ── pure: which chats ─────────────────────────────────────────────────────────
def test_chat_matching_explicit_list_regex_and_mausaji(monkeypatch):
    for k in ("WA_SWEEP_CHATS", "WA_SWEEP_GROUPS", "MAUSAJI_CHAT", "WA_SWEEP_IDLE_HOURS"):
        monkeypatch.delenv(k, raising=False)
    assert ws.watch_chats() == ["Bantu Mausaji", "Vedanta Daily Report", "Washery Civil Update", "Ans Management",
                                "VWLR Indent Planning", "Core Group"]
    assert ws.groups_regex().pattern == ws.GROUPS_REGEX_DEFAULT and ws.idle_hours() == 1.0
    # Aman's six chats: the Mausaji one is the shares chat, the rest are ops — any kind, exact or contained
    assert ws.chat_mode("Bantu Mausaji", "dm") == "mausaji" and ws.chat_mode("bantu mausaji 🙏", "group") == "mausaji"
    for name in ("Vedanta Daily Report", "washery civil update", "Ans Management", "VWLR Indent Planning", "Core Group (VWLR)"):
        assert ws.chat_mode(name, "dm") == "ops", name
    # the regex is an extra matcher for GROUPS only; a DM never matches by regex; "ans" matches inside words (documented)
    assert ws.chat_mode("Siding Loading Team", "group") == "ops" and ws.chat_mode("Siding Loading Team", "dm") is None
    assert ws.chat_mode("Transport Bills", "group") == "ops"
    assert ws.chat_mode("Family Jokes", "group") is None and ws.chat_mode("", "group") is None
    # env overrides: the list, the regex (a broken one falls back), the chat name, the idle hours
    monkeypatch.setenv("WA_SWEEP_CHATS", "Core Group; ;core group;Night Shift")
    assert ws.watch_chats() == ["Core Group", "Night Shift"]
    monkeypatch.setenv("WA_SWEEP_GROUPS", "(unclosed")
    assert ws.groups_regex().pattern == ws.GROUPS_REGEX_DEFAULT
    monkeypatch.setenv("WA_SWEEP_GROUPS", "^hotel ans$")
    assert ws.chat_mode("Hotel ANS", "group") == "ops" and ws.chat_mode("Washery Ops", "group") is None
    monkeypatch.setenv("MAUSAJI_CHAT", "Mausaji Shares")
    assert ws.chat_mode("Bantu Mausaji", "dm") is None and ws.chat_mode("mausaji shares", "dm") == "mausaji"
    monkeypatch.setenv("WA_SWEEP_IDLE_HOURS", "2.5")
    assert ws.idle_hours() == 2.5
    monkeypatch.setenv("WA_SWEEP_IDLE_HOURS", "zero")
    assert ws.idle_hours() == 1.0


# ── pure: Mausaji rules ───────────────────────────────────────────────────────
def test_mausaji_tickers_calls_and_what_is_about_a_share():
    assert INDEX["listed"] == {"TCS", "ADVENTHTL", "RELIANCE"} and INDEX["words"]["advent"] == "ADVENTHTL"
    assert INDEX["words"]["consultancy"] == "TCS" and "tata" not in INDEX["words"]            # 4 letters: too short
    assert ws.find_tickers("TCS lelo 3500 ke aas paas, target 3900, SL 3350", INDEX) == ["TCS"]
    assert ws.find_tickers("Reliance hold karo. Eternal mat lena abhi.", INDEX) == ["RELIANCE", "ETERNAL"]
    assert ws.find_tickers("advent me entry lo", INDEX) == ["ADVENTHTL"]                     # company word from the note
    assert ws.find_tickers("idea nahi hai, market gir raha hai", INDEX) == []                 # stop words never match
    assert ws.find_tickers("tcs.ns 3500", INDEX) == ["TCS"] and ws.find_tickers("", INDEX) == []
    assert ws.find_tickers("tatacomm", None) == []                                            # no index → nothing known
    c = ws.parse_call("TCS lelo 3500 ke aas paas, target 3900, SL 3350, 3 mahine")
    assert c == {"action": "buy", "buy": 3500.0, "sell": None, "target": 3900.0, "sl": 3350.0}
    assert ws.parse_call("3,450 pe tcs lelo")["buy"] == 3450.0
    assert ws.parse_call("infy bech do 1500") == {"action": "sell", "buy": None, "sell": 1500.0, "target": None, "sl": None}
    assert ws.parse_call("Reliance hold karo")["action"] == "hold" and ws.parse_call("Zomato mat lena abhi")["action"] == "avoid"
    assert ws.parse_call("Eternal target 300 sl 240")["target"] == 300.0 and ws.parse_call("stop loss 240")["sl"] == 240.0
    assert ws.parse_call("good morning")["action"] is None
    a = ws.analyse_mausaji("TCS lelo 3500 ke aas paas, target 3900", INDEX)
    assert a["kind"] == "call" and a["tickers"] == ["TCS"] and a["call"]["target"] == 3900.0
    assert ws.analyse_mausaji("Reliance results acche aaye", INDEX)["kind"] == "mention"
    assert ws.analyse_mausaji("lelo 120 pe, achha hai", INDEX) == {"tickers": [], "call": ws.parse_call("lelo 120 pe, achha hai"), "kind": "call"}
    assert ws.analyse_mausaji("market gir raha hai", INDEX) is None
    assert ws.analyse_mausaji("hold karo sab", INDEX) is None                                  # a call word without a number or a share
    assert ws.call_text(c) == "read: buy 3,500 · target 3,900 · SL 3,350" and ws.call_text(None) == ""
    assert ws.call_text({"action": "sell", "sell": 1500}) == "read: sell 1,500"


# ── pure: ops rules ───────────────────────────────────────────────────────────
def test_bottleneck_words_hindi_roman_and_english():
    assert ws.find_bottleneck("diesel nahi aaya, loader band hai") == ["band", "nahi aaya", "no diesel"]
    assert ws.find_bottleneck("rake nahi aaya aaj") == ["nahi aaya", "rake nahi"]
    assert ws.find_bottleneck("guest complaint room 204 AC kharab") == ["kharab", "guest complaint"]
    assert ws.find_bottleneck("payment pending 3 din se") == ["pending", "payment"]
    assert ws.find_bottleneck("Loading late ho rahi hai, wagon 42 abhi tak nahi") == ["late", "wagon"]
    assert ws.find_bottleneck("demurrage lagega, urgent") == ["urgent", "demurrage"]
    assert ws.find_bottleneck("breakdown at crusher, machine ruk gayi") == ["ruka", "breakdown"]
    assert ws.find_bottleneck("strike ho sakti hai, labour problem") == ["problem", "strike"]
    assert ws.find_bottleneck("cancelled trip, penalty lagi") == ["penalty", "cancel"]
    assert ws.find_bottleneck("diesel 500L filled") == ["diesel"]                              # the plain word counts (Aman's list)
    for clean in ("sab theek hai", "dispatch 12 trucks done", "good morning", "husband aa gaye", "later", "issued"):
        assert ws.find_bottleneck(clean) == [], clean


# ── pure: time, silence, lines ────────────────────────────────────────────────
def test_business_hours_silence_episodes_and_age():
    bh = ws.business_hours_between
    assert bh(datetime(2026, 10, 8, 19, 0, tzinfo=IST), FRI_1045) == 3.75       # 19:00–20:00 + 08:00–10:45
    assert bh(datetime(2026, 10, 9, 9, 30, tzinfo=IST), FRI_1045) == 1.25
    assert bh(datetime(2026, 10, 9, 10, 30, tzinfo=IST), FRI_1045) == 0.25
    assert bh(datetime(2026, 10, 8, 21, 0, tzinfo=IST), datetime(2026, 10, 9, 7, 0, tzinfo=IST)) == 0.0   # night does not count
    assert bh(None, FRI_1045) == 0.0 and bh(FRI_1045, FRI_0800) == 0.0
    chats = [{"chat_jid": "a", "last_at": "2026-10-09T09:30:00+05:30", "silence_since": ""},                  # 1.25h → silent
             {"chat_jid": "b", "last_at": "2026-10-09T10:30:00+05:30", "silence_since": ""},                  # 0.25h → fine
             {"chat_jid": "c", "last_at": "2026-10-09T07:00:00+05:30", "silence_since": "2026-10-09T01:30:00+00:00"},  # same episode, flagged
             {"chat_jid": "d", "last_at": None}]
    out = ws.silent_chats(chats, FRI_1045, 1.0)
    assert [c["chat_jid"] for c in out] == ["a"] and out[0]["silent_hours"] == 1.25
    assert [c["chat_jid"] for c in ws.silent_chats(chats, FRI_1045, 0.2)] == ["a", "b"]
    assert ws.age_text("2026-10-09T10:33:00+05:30", FRI_1045) == "12 min ago"
    assert ws.age_text("2026-10-09T10:44:40+05:30", FRI_1045) == "just now"
    assert ws.age_text("2026-10-09T07:40:00+05:30", FRI_1045) == "3h 05m ago"
    assert ws.age_text("2026-10-07T10:00:00+05:30", FRI_1045) == "2d ago" and ws.age_text("", FRI_1045) == "time n/a"
    assert ws.quote("  a   b " * 60).endswith("…") and len(ws.quote("x" * 300)) == 200


def test_lines_aman_reads():
    flag = {"tickers": ["TCS"], "sender": "Bantu Mausaji", "text": "TCS lelo 3500 ke aas paas, target 3900, SL 3350",
            "call": ws.parse_call("TCS lelo 3500 ke aas paas, target 3900, SL 3350")}
    lvl = {"TCS": {"ticker": "TCS", "buy_level": 3500, "sell_level": 4200, "best_entry": 3450}}
    line = ws.format_mausaji_line(flag, {"TCS": 3612.5}, lvl, {"TCS": [{"holder": "Aman", "qty": 500}, {"holder": "Aditi", "qty": 100}]}, "10:32 IST")
    assert line == ('TCS · Bantu Mausaji: "TCS lelo 3500 ke aas paas, target 3900, SL 3350" · read: buy 3,500 · target 3,900 · SL 3,350'
                    ' · ₹3,612.5 (10:32 IST) · list: BUY ≤3,500 (best 3,450) (−3.1% away) · SELL ≥4,200 (+16.3% away)'
                    ' · HELD BY Aman 500, Aditi 100 · research only')
    # Directive 18 on every line: nobody / holdings n/a; no price → "price n/a"; not on the list said so
    assert ws.format_mausaji_line(flag, {}, {}, {}, "") == (
        'TCS · Bantu Mausaji: "TCS lelo 3500 ke aas paas, target 3900, SL 3350" · read: buy 3,500 · target 3,900 · SL 3,350'
        ' · price n/a · not on list · HELD BY nobody · research only')
    assert "HELD BY holdings n/a" in ws.format_mausaji_line(flag, {}, {}, None)
    two = ws.format_mausaji_line({"tickers": ["TCS", "INFY"], "text": "TCS aur Infy dono acche", "call": ws.parse_call("x")},
                                 {"TCS": 3612.5, "INFY": None}, lvl, {})
    assert two.startswith('TCS, INFY · Mausaji: "TCS aur Infy dono acche" · TCS ₹3,612.5 · list: BUY ≤3,500')
    assert "INFY price n/a · not on list · HELD BY nobody · research only" in two
    none = ws.format_mausaji_line({"tickers": [], "text": "lelo 120 pe", "call": ws.parse_call("lelo 120 pe")}, {}, {}, {})
    assert none == 'share? · Mausaji: "lelo 120 pe" · read: buy 120 · price n/a (no ticker named) · not on list · HELD BY n/a · research only'
    ops = {"chat_name": "Washery Civil Update", "sender": "Ramesh", "text": "diesel nahi aaya, loader band hai",
           "msg_at": "2026-10-09T10:33:00+05:30", "kind": "bottleneck", "detail": {"words": ["band", "nahi aaya", "no diesel"]}}
    assert ws.format_ops_line(ops, FRI_1045) == '🔴 Washery Civil Update · Ramesh · "diesel nahi aaya, loader band hai" [band, nahi aaya, no diesel] · 12 min ago'
    sil = {"chat_name": "Core Group", "kind": "silence", "msg_at": "2026-10-09T07:40:00+05:30", "detail": {"silent_hours": 2.75}}
    assert ws.format_ops_line(sil, FRI_1045) == "🔕 Core Group · silent 2.75h in 08:00–20:00 IST · last message 07:40 (3h 05m ago)"
    batch = ws.format_batch([f"line {i}" for i in range(12)])
    assert batch.splitlines()[0] == "wa-sweep · 12 more flags (chats pushed in the last 30 min):" and batch.endswith("+2 more on the Morning page")
    assert ws.heartbeat_line("ops", 0, 0, 0, 0) == "wa-sweep ops: 0 chats swept, 0 new msgs, 0 flags (0 pushed)"
    # the first ops run names the matched chats so Aman can correct the set; with none it names what was seen
    watch, rx = ws.watch_chats(ws.WATCH_CHATS_DEFAULT), ws.groups_regex(ws.GROUPS_REGEX_DEFAULT)
    ann = ws.announcement_text([], False, ["Family Jokes", "Transport Bills"], watch, rx, "Bantu Mausaji")
    assert ann == ('wa-sweep · watching 0 ops chats — none match yet; group chats seen: Family Jokes, Transport Bills'
                   ' · Mausaji chat "Bantu Mausaji": not seen yet · list: Vedanta Daily Report; Washery Civil Update; Ans Management;'
                   ' VWLR Indent Planning; Core Group · regex: /washery|siding|hotel|ans|vwlr|rake|plant|site|loader|dispatch/i'
                   ' · to change: WA_SWEEP_CHATS / WA_SWEEP_GROUPS in .env')
    assert ws.announcement_text([], False, [], watch, rx, "Bantu Mausaji").startswith(
        "wa-sweep · watching 0 ops chats — none match yet; no group chats received from the bridges yet · ")
    assert ws.announcement_text([{"chat_name": "Core Group"}, {"chat_name": "Washery Civil Update"}], True, [], watch, rx, "Bantu Mausaji").startswith(
        'wa-sweep · watching 2 ops chats: Core Group, Washery Civil Update · Mausaji chat "Bantu Mausaji": found · ')
    day = ws.daily_summary_text(FRI_1045.date(), {"runs": 27, "new_msgs": 311, "flags": 9, "pushed": 7, "open": 2,
                                                   "flags_by_kind": {"call": 2, "bottleneck": 6, "silence": 1}},
                                [{"chat_name": "Core Group"}], True, "Bantu Mausaji")
    assert day == ('wa-sweep · Fri 09 Oct · 27 runs · 311 new msgs · 9 flags (2 calls, 6 bottlenecks, 1 silence) · 7 pushed · 2 open'
                   ' · watching 1 ops chat: Core Group · Mausaji chat "Bantu Mausaji": found · to change: WA_SWEEP_CHATS / WA_SWEEP_GROUPS in .env')


# ── pure: the option watcher ──────────────────────────────────────────────────
def test_option_instrument_chain_parse_and_crossing_rule():
    p = ol.parse_instrument("NIFTY 29-Dec-26 25000 CE")
    assert p == {"instrument": "NIFTY 29-Dec-26 25000 CE", "symbol": "NIFTY", "expiry": "29-Dec-2026", "strike": 25000.0, "opt_type": "CE"}
    assert ol.parse_instrument("nifty 29-dec-2026 25000.0 pe")["instrument"] == "NIFTY 29-Dec-26 25000 PE"
    assert ol.parse_instrument("BANKNIFTY 7-Jan-27 52500 CE")["expiry"] == "07-Jan-2027"
    assert ol.parse_instrument("NIFTY 25000 CE") is None and ol.parse_instrument("NIFTY 31-Feb-26 25000 CE") is None
    assert ol.price_from_chain(CHAIN, "29-Dec-2026", 25000, "CE") == 27.5
    assert ol.price_from_chain(CHAIN, "29-Dec-2026", 25000, "PE") == 905.2
    assert ol.price_from_chain(CHAIN, "30-Oct-2026", 25000, "CE") == 3.1
    assert ol.price_from_chain(CHAIN, "29-Dec-2026", 26000, "CE") is None                    # strike not in the chain
    assert ol.price_from_chain(None, "29-Dec-2026", 25000, "CE") is None and ol.price_from_chain({"records": {}}, "x", 1, "CE") is None
    assert ol.price_from_chain({"records": {"data": [{"strikePrice": 25000, "expiryDate": "29-Dec-2026", "CE": {"lastPrice": 0}}]}}, "29-Dec-2026", 25000, "CE") is None
    row = {"instrument": "NIFTY 29-Dec-26 25000 CE", "alert_below": 30, "alert_above": None, "held": "AA 29,250", "last_state": "", "last_alerted_at": None}
    t0 = FRI_1045
    assert ol.should_alert(row, 42.0, t0) == (False, "inside")
    assert ol.should_alert(row, 27.5, t0) == (True, "below")                                  # the crossing
    row.update(last_state="below", last_alerted_at=t0.isoformat())
    assert ol.should_alert(row, 26.0, t0 + timedelta(minutes=15)) == (False, "below")        # still below, too soon
    assert ol.should_alert(row, 26.0, t0 + timedelta(minutes=60)) == (True, "below")         # repeat at most hourly
    assert ol.should_alert(row, 31.0, t0 + timedelta(minutes=20)) == (False, "inside")       # back inside: quiet
    row.update(last_state="inside")
    assert ol.should_alert(row, 29.9, t0 + timedelta(minutes=25)) == (True, "below")         # a new crossing pushes again
    assert ol.should_alert(row, None, t0) == (False, "")                                      # no price → never a push
    above = {"instrument": "X 29-Dec-26 100 PE", "alert_below": None, "alert_above": 50, "held": "", "last_state": ""}
    assert ol.should_alert(above, 51, t0) == (True, "above") and ol.alert_text(above, 51, "above") == "X 29-Dec-26 100 PE at 51 — above your 50 alert. Held: nobody. Research only."
    assert ol.alert_text(row, 27.5, "below") == "NIFTY 29-Dec-26 25000 CE at 27.5 — below your 30 alert. Held: AA 29,250. Research only."


# ── endpoints through the real app ───────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _wipe(c):
    """The scratch DB is shared by every test module: clear the WhatsApp store, the sweep tables and the lists."""
    for l in c.get("/api/levels").json()["levels"]:
        c.delete(f"/api/levels/{l['ticker']}")
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("whatsapp_messages", "wa_chats", "wa_sweep_state", "wa_sweep_flags", "wa_sweep_runs", "option_levels",
              "share_master_holdings", "portfolio_snapshot"):
        db.execute(f"DELETE FROM {t}")
    db.commit(); db.close()


class _Sent:
    """Captures what send_cos would put on WhatsApp; `ok=False` plays a bridge that is down."""

    def __init__(self):
        self.texts, self.ok = [], True

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": self.ok} if self.ok else {"sent": False, "reason": "bridge down"}


def _post(c, jid, group, text, ts, sender="Someone", kind="group", account="1", from_me=0, wa_msg_id=None):
    body = {"group": group, "sender": sender, "text": text, "timestamp": ts, "jid": jid, "chat_jid": jid,
            "account": account, "chat_kind": kind, "from_me": from_me, "wa_msg_id": wa_msg_id or f"{jid}-{ts}-{text[:12]}"}
    r = c.post("/api/whatsapp/message", json=body)
    assert r.status_code == 200 and r.json().get("stored"), r.text
    return r.json()["id"]


def _ist(h, m, day=9):
    return datetime(2026, 10, day, h, m, tzinfo=IST).isoformat()


def _setup(monkeypatch):
    import mdo_server
    c = _client()
    _wipe(c)
    for k in ("WA_SWEEP_CHATS", "WA_SWEEP_GROUPS", "MAUSAJI_CHAT", "WA_SWEEP_IDLE_HOURS"):
        monkeypatch.delenv(k, raising=False)
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    prices = {"TCS": 3612.5, "RELIANCE": 1402.0, "ETERNAL": None}
    mdo_server._wa_sweep["set_fetch_ltp"](lambda tickers, timeout=10.0: {t: prices.get(t) for t in tickers})
    mdo_server._wa_sweep["set_nse_symbols"](lambda: {"ETERNAL", "INFY", "TATACOMM", "RELIANCE"})
    mdo_server._options["set_fetch_chain"](lambda sym: CHAIN)
    return c, sent, prices


def test_mausaji_run_pushes_every_share_message_once_with_price_level_and_holder(monkeypatch):
    c, sent, prices = _setup(monkeypatch)
    c.post("/api/levels", json=[{"ticker": "TCS", "buy_level": 3500, "sell_level": 4200, "best_entry": 3450,
                                 "note": "Tata Consultancy Services · Mausaji (call)"}])
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("INSERT INTO share_master_holdings (holder, ticker, qty) VALUES ('Aditi', 'TCS', 100)")
    db.commit(); db.close()
    _post(c, MAUSAJI_JID, "Bantu Mausaji", "Good morning", _ist(9, 50), "Bantu Mausaji", kind="dm")
    _post(c, MAUSAJI_JID, "Bantu Mausaji", "TCS lelo 3500 ke aas paas, target 3900, SL 3350", _ist(10, 5), "Bantu Mausaji", kind="dm")
    _post(c, MAUSAJI_JID, "Bantu Mausaji", "Reliance results acche aaye, hold", _ist(10, 20), "Bantu Mausaji", kind="dm")
    _post(c, MAUSAJI_JID, "Bantu Mausaji", "Eternal 240 pe lelo", _ist(10, 30), "Bantu Mausaji", kind="dm")
    last_id = _post(c, MAUSAJI_JID, "Bantu Mausaji", "ok TCS dekh raha hoon", _ist(10, 31), "Aman", kind="dm", from_me=1)   # Aman's own words: never flagged
    _post(c, WASHERY_JID, "Washery Civil Update", "diesel nahi aaya", _ist(10, 35), "Ramesh")                       # an ops chat: not this mode
    r = c.post("/api/wa/sweep/run", json={"mode": "mausaji", "now": FRI_1045.isoformat()})
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["chats"], res["new_msgs"], res["flags"], res["pushed"], res["push_failed"]) == (1, 4, 3, 3, 0)
    assert res["line"] == "wa-sweep mausaji: 1 chats swept, 4 new msgs, 3 flags (3 pushed)"
    assert sent.texts == res["pushes"] and len(sent.texts) == 3
    assert sent.texts[0] == ('TCS · Bantu Mausaji: "TCS lelo 3500 ke aas paas, target 3900, SL 3350" · read: buy 3,500 · target 3,900 · SL 3,350'
                             ' · ₹3,612.5 (' + sent.texts[0].split("₹3,612.5 (")[1].split(")")[0] + ') · list: BUY ≤3,500 (best 3,450) (−3.1% away)'
                             ' · SELL ≥4,200 (+16.3% away) · HELD BY Aditi 100 · research only')
    assert re.search(r"₹3,612\.5 \(\d\d:\d\d IST\)", sent.texts[0])
    assert sent.texts[1].startswith('RELIANCE · Bantu Mausaji: "Reliance results acche aaye, hold" · read: hold · ₹1,402 (')
    assert sent.texts[1].endswith(" · not on list · HELD BY nobody · research only")
    assert sent.texts[2] == 'ETERNAL · Bantu Mausaji: "Eternal 240 pe lelo" · read: buy 240 · price n/a · not on list · HELD BY nobody · research only'
    kinds = [(f["kind"], f["ticker"]) for f in res["flag_rows"]]
    assert kinds == [("call", "TCS"), ("call", "RELIANCE"), ("call", "ETERNAL")]          # "hold" is a call too
    # the watermark advanced: the same run again finds nothing new and pushes nothing (no duplicate pushes)
    r = c.post("/api/wa/sweep/run", json={"mode": "mausaji", "now": (FRI_1045 + timedelta(minutes=15)).isoformat()}).json()
    assert (r["chats"], r["new_msgs"], r["flags"], r["pushed"]) == (1, 0, 0, 0) and len(sent.texts) == 3
    assert r["line"] == "wa-sweep mausaji: 1 chats swept, 0 new msgs, 0 flags (0 pushed)"
    chats = c.get("/api/wa/sweep/chats").json()
    assert chats["count"] == 2 and chats["mausaji_found"] is True                   # + the washery group (ops), Mausaji listed first
    assert [ch["mode"] for ch in chats["chats"]] == ["mausaji", "ops"]
    assert chats["chats"][0]["watermark"] == last_id and chats["chats"][0]["priority"] == "normal"
    # a new message → one more line; the bridge down → the flag stays open and unpushed, the run says so
    _post(c, MAUSAJI_JID, "Bantu Mausaji", "TCS 3450 aa gaya, lelo", _ist(11, 2), "Bantu Mausaji", kind="dm")
    sent.ok = False
    r = c.post("/api/wa/sweep/run", json={"mode": "mausaji", "now": (FRI_1045 + timedelta(minutes=30)).isoformat()}).json()
    assert (r["new_msgs"], r["flags"], r["pushed"], r["push_failed"]) == (1, 1, 0, 1)
    sent.ok = True
    # the flags endpoint: open ones newest first; ack closes one; an unknown id is a 404
    fl = c.get("/api/wa/sweep/flags").json()
    assert fl["open"] == 4 and [f["ticker"] for f in fl["flags"]] == ["TCS", "ETERNAL", "RELIANCE", "TCS"]
    assert fl["flags"][0]["pushed_at"] is None and fl["flags"][1]["pushed_at"]
    assert fl["flags"][0]["detail"]["call"]["buy"] == 3450.0
    assert c.post(f"/api/wa/sweep/flags/{fl['flags'][0]['id']}/ack").json() == {"ok": True, "id": fl["flags"][0]["id"], "status": "ack"}
    assert c.get("/api/wa/sweep/flags").json()["open"] == 3 and c.get("/api/wa/sweep/flags?status=ack").json()["count"] == 1
    assert c.post("/api/wa/sweep/flags/999999/ack").status_code == 404
    # no Mausaji chat seen → the run says so and still reports zeros
    monkeypatch.setenv("MAUSAJI_CHAT", "Some Other Uncle")
    r = c.post("/api/wa/sweep/run", json={"mode": "mausaji", "now": FRI_1045.isoformat()}).json()
    assert r["line"] == "wa-sweep mausaji: 0 chats swept, 0 new msgs, 0 flags (0 pushed)" and r["note"] == 'no chat matches "Some Other Uncle" yet'
    assert c.post("/api/wa/sweep/run", json={"mode": "nope"}).status_code == 400


def test_ops_run_bottlenecks_thirty_minute_rule_silence_and_announcement(monkeypatch):
    c, sent, _ = _setup(monkeypatch)
    now = FRI_1045
    _post(c, FAMILY_JID, "Family Jokes", "lol band bajegi", _ist(10, 30), "Mausi")                       # not watched
    _post(c, WASHERY_JID, "Washery Civil Update", "slab casting done", _ist(9, 40), "Ramesh")
    _post(c, WASHERY_JID, "Washery Civil Update", "diesel nahi aaya, loader band hai", _ist(10, 33), "Ramesh")
    _post(c, WASHERY_JID, "Washery Civil Update", "diesel nahi aaya, loader band hai", _ist(10, 33), "Ramesh", account="2")  # phone 2 stores it again
    _post(c, RAKE_JID, "VWLR Rake Loading", "wagon 42 placed, loading late ho rahi hai", _ist(10, 40), "Suresh")  # regex match
    _post(c, CORE_JID, "Core Group", "plan for the week attached", _ist(7, 40), "Aman", from_me=1)          # silent since 07:40
    _post(c, VEDANTA_JID, "Vedanta Daily Report", "report: 1,240 MT dispatched", _ist(10, 10), "Vedanta", kind="dm")
    _post(c, TRANSPORT_JID, "Transport Bills", "bill payment done", _ist(10, 41), "Accounts")          # "ans" inside Transport: documented noise
    r = c.post("/api/wa/sweep/run", json={"mode": "ops", "now": now.isoformat()})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["chats"] == 5 and res["new_msgs"] == 6 and res["flags"] == 4 and res["silence"] == 1
    # the very first ops run announces the matched chats (pushed first), then one push per chat + the silence
    assert sent.texts[0] == res["announcement"] == (
        'wa-sweep · watching 5 ops chats: Core Group, Transport Bills, Vedanta Daily Report, VWLR Rake Loading, Washery Civil Update'
        ' · Mausaji chat "Bantu Mausaji": not seen yet · list: Vedanta Daily Report; Washery Civil Update; Ans Management;'
        ' VWLR Indent Planning; Core Group · regex: /washery|siding|hotel|ans|vwlr|rake|plant|site|loader|dispatch/i'
        ' · to change: WA_SWEEP_CHATS / WA_SWEEP_GROUPS in .env')
    assert res["pushed"] == 5 and res["line"] == "wa-sweep ops: 5 chats swept, 6 new msgs, 4 flags (5 pushed)"
    assert sent.texts[1] == "🔕 Core Group · silent 2.75h in 08:00–20:00 IST · last message 07:40 (3h 05m ago)"
    assert '🔴 Washery Civil Update · Ramesh · "diesel nahi aaya, loader band hai" [band, nahi aaya, no diesel] · 12 min ago' in sent.texts
    assert '🔴 VWLR Rake Loading · Suresh · "wagon 42 placed, loading late ho rahi hai" [late, wagon] · 5 min ago' in sent.texts
    assert '🔴 Transport Bills · Accounts · "bill payment done" [payment] · 4 min ago' in sent.texts
    assert sum("diesel nahi aaya" in t for t in sent.texts) == 1                      # phone 2's copy: no second flag, no second push
    # 10 min later: a new bottleneck in a chat pushed within 30 min goes into ONE batched message; silence not repeated
    _post(c, WASHERY_JID, "Washery Civil Update", "crusher breakdown, 2 hours stuck", _ist(10, 50), "Ramesh")
    _post(c, RAKE_JID, "VWLR Rake Loading", "rake nahi aaya abhi tak", _ist(10, 52), "Suresh")
    n = len(sent.texts)
    res = c.post("/api/wa/sweep/run", json={"mode": "ops", "now": (now + timedelta(minutes=10)).isoformat()}).json()
    assert (res["new_msgs"], res["flags"], res["pushed"], res["silence"]) == (2, 2, 1, 0) and "announcement" not in res
    assert sent.texts[n] == ("wa-sweep · 2 more flags (chats pushed in the last 30 min):\n"
                             '🔴 VWLR Rake Loading · Suresh · "rake nahi aaya abhi tak" [nahi aaya, rake nahi] · 3 min ago\n'
                             '🔴 Washery Civil Update · Ramesh · "crusher breakdown, 2 hours stuck" [breakdown, stuck] · 5 min ago')
    # 40 min after that: the chat is quiet again → pushed at once, on its own
    _post(c, WASHERY_JID, "Washery Civil Update", "payment pending contractor ka", _ist(11, 30), "Ramesh")
    res = c.post("/api/wa/sweep/run", json={"mode": "ops", "now": (now + timedelta(minutes=50)).isoformat()}).json()
    assert (res["flags"], res["pushed"], res["silence"]) == (2, 2, 1)                 # + Vedanta DM quiet since 10:10
    assert sent.texts[-1] == '🔴 Washery Civil Update · Ramesh · "payment pending contractor ka" [pending, payment] · 5 min ago'
    assert sent.texts[-2].startswith("🔕 Vedanta Daily Report · silent 1.42h")
    # silence: one flag per episode — a new message ends it, the next long gap flags again
    res = c.post("/api/wa/sweep/run", json={"mode": "ops", "now": (now + timedelta(hours=2)).isoformat()}).json()
    assert res["silence"] == 3 and not any(t.startswith("🔕 Core Group") for t in sent.texts[n:])   # the others fell silent; Core Group not twice
    _post(c, CORE_JID, "Core Group", "noted", _ist(12, 50), "Vimal")
    res = c.post("/api/wa/sweep/run", json={"mode": "ops", "now": datetime(2026, 10, 9, 13, 0, tzinfo=IST).isoformat()}).json()
    assert res["silence"] == 0                                                         # 10 min quiet is fine
    res = c.post("/api/wa/sweep/run", json={"mode": "ops", "now": datetime(2026, 10, 9, 14, 0, tzinfo=IST).isoformat()}).json()
    assert res["silence"] == 1 and sent.texts[-1] == "🔕 Core Group · silent 1.17h in 08:00–20:00 IST · last message 12:50 (1h 10m ago)"
    # the other watched chats went quiet too by now: each flagged once, never twice
    silences = [f for f in c.get("/api/wa/sweep/flags?kind=silence&status=").json()["flags"]]
    assert len(silences) == len({(f["chat_jid"], f["msg_at"]) for f in silences})
    # chats endpoint: modes, priorities (settable, shown), last message time; a bad priority or jid is refused
    chats = c.get("/api/wa/sweep/chats").json()
    assert {ch["name"]: ch["mode"] for ch in chats["chats"]} == {
        "Core Group": "ops", "Transport Bills": "ops", "Vedanta Daily Report": "ops", "VWLR Rake Loading": "ops", "Washery Civil Update": "ops"}
    assert chats["groups_seen"] == ["Core Group", "Family Jokes", "Transport Bills", "VWLR Rake Loading", "Washery Civil Update"]
    assert chats["idle_hours"] == 1.0 and chats["groups_regex"] == ws.GROUPS_REGEX_DEFAULT
    assert c.post(f"/api/wa/sweep/chats/{WASHERY_JID}/priority", json={"priority": "high"}).json()["priority"] == "high"
    assert next(ch for ch in c.get("/api/wa/sweep/chats").json()["chats"] if ch["jid"] == WASHERY_JID)["priority"] == "high"
    assert c.post(f"/api/wa/sweep/chats/{WASHERY_JID}/priority", json={"priority": "urgent"}).status_code == 400
    assert c.post("/api/wa/sweep/chats/nope@g.us/priority", json={"priority": "low"}).status_code == 404
    # the daily line adds the day up and lists the chats so Aman can correct the set
    res = c.post("/api/wa/sweep/run", json={"mode": "daily", "now": datetime(2026, 10, 9, 21, 0, tzinfo=IST).isoformat()}).json()
    assert res["pushed"] == 1 and sent.texts[-1] == res["text"]
    assert res["text"].startswith("wa-sweep · Fri 09 Oct · 6 runs · 10 new msgs · ")
    assert "Core Group, Transport Bills, Vedanta Daily Report, VWLR Rake Loading, Washery Civil Update" in res["text"]
    assert res["totals"]["flags_by_kind"] == {"bottleneck": 6, "silence": 6} and res["totals"]["pushed"] == len(sent.texts) - 1
    assert c.get("/api/wa/sweep/summary?day=2026-10-09").json()["runs"] == 6


def test_option_levels_endpoints_seed_and_once_per_crossing(monkeypatch):
    c, sent, _ = _setup(monkeypatch)
    seed = json.load(open(os.path.join(ROOT, "data", "option_levels_import_2026-10-09.json"), encoding="utf-8"))
    r = c.post("/api/levels/options", json=seed["options"])                           # the importer POSTs this list
    assert r.status_code == 200, r.text
    assert r.json()["upserted"] == ["NIFTY 29-Dec-26 25000 CE"]
    row = c.get("/api/levels/options").json()["options"][0]
    assert (row["symbol"], row["expiry"], row["strike"], row["opt_type"], row["alert_below"], row["alert_above"], row["held"]) == (
        "NIFTY", "29-Dec-2026", 25000.0, "CE", 30.0, None, "AA 29,250")
    assert "AA account holds 29,250" in row["note"] and row["active"] is True
    assert c.post("/api/levels/options", json={"instrument": "NIFTY 25000 CE", "alert_below": 30}).status_code == 400
    assert c.post("/api/levels/options", json={"instrument": "NIFTY 29-Dec-26 25000 CE", "alert_below": None, "alert_above": None}).status_code == 400
    # the check through the canned NSE chain: 27.5 < 30 → one push with the exact text
    t0 = FRI_1045
    r = c.post("/api/levels/options/check", json={"now": t0.isoformat()}).json()
    assert r["checked"] == 1 and r["prices"] == {"NIFTY 29-Dec-26 25000 CE": 27.5} and r["unavailable"] == []
    assert r["pushed"] == ["NIFTY 29-Dec-26 25000 CE at 27.5 — below your 30 alert. Held: AA 29,250. Research only."] == sent.texts
    assert r["line"] == "option NIFTY 29-Dec-26 25000 CE ₹27.5 (below 30, pushed)"
    # still below 15 min later → no repeat; 60 min later → one repeat; back inside → quiet; a new crossing → push
    for minutes, ltp, pushes in ((15, 27.0, 0), (60, 26.0, 1), (80, 31.0, 0), (95, 29.5, 1), (100, 29.0, 0)):
        r = c.post("/api/levels/options/check", json={"now": (t0 + timedelta(minutes=minutes)).isoformat(),
                                                      "ltps": {"NIFTY 29-Dec-26 25000 CE": ltp}}).json()
        assert len(r["pushed"]) == pushes, (minutes, ltp, r)
    assert len(sent.texts) == 3
    st = c.get("/api/levels/options").json()["options"][0]
    assert st["last_ltp"] == 29.0 and st["last_state"] == "below" and st["last_alerted_at"].startswith((t0 + timedelta(minutes=95)).astimezone(ol.timezone.utc).strftime("%Y-%m-%dT%H:%M"))
    # NSE unreachable → "option price unavailable", nothing invented, nothing pushed
    import mdo_server
    mdo_server._options["set_fetch_chain"](lambda sym: None)
    r = c.post("/api/levels/options/check", json={"now": (t0 + timedelta(minutes=120)).isoformat()}).json()
    assert r["unavailable"] == ["NIFTY 29-Dec-26 25000 CE"] and r["line"] == "option price unavailable" and r["pushed"] == []
    mdo_server._options["set_fetch_chain"](lambda sym: CHAIN)
    assert c.delete("/api/levels/options/NIFTY%2029-Dec-26%2025000%20CE").json()["deleted"] == "NIFTY 29-Dec-26 25000 CE"
    assert c.post("/api/levels/options/check", json={}).json()["line"] == "no option levels set"
    # the seed file is applied once at startup (no manual VPS step); a deleted row stays deleted; force re-applies
    import asyncio
    assert asyncio.run(mdo_server._options["seed"]())["reason"] == "already applied"
    assert c.get("/api/levels/options").json()["options"] == []
    assert asyncio.run(mdo_server._options["seed"](force=True)) == {"seeded": 1, "file": "option_levels_import_2026-10-09.json"}
    assert c.get("/api/levels/options").json()["options"][0]["instrument"] == "NIFTY 29-Dec-26 25000 CE"
    assert ol.fetch_option_chain.__doc__ and ol.fetch_option_chain("NIFTY", timeout=0.01) is None   # never raises
    # a list is one call: the shares importer handles both keys
    src = open(os.path.join(ROOT, "tools", "import_levels.py"), encoding="utf-8").read()
    assert '/api/levels/options' in src and 'doc.get("options")' in src


# ── the bot, end to end through the real endpoints ────────────────────────────
class _Fake:
    def __init__(self, client):
        self.client, self.reports = client, []

    def api(self, path, method="GET", body=None, timeout=30):
        if path == "/api/agent/report":
            self.reports.append(body)
            return {"stored": True, "report_id": len(self.reports)}
        if path.startswith(("/api/wa/sweep", "/api/levels/options")):
            r = self.client.post(path, json=body) if method == "POST" else self.client.get(path)
            assert r.status_code == 200, r.text
            return r.json()
        raise AssertionError(f"unexpected call {method} {path}")


def test_run_wa_sweep_heartbeats_every_mode_even_when_zero(monkeypatch):
    c, sent, _ = _setup(monkeypatch)
    fake = _Fake(c)
    monkeypatch.setattr(ag, "api", fake.api)
    monkeypatch.setattr(ag, "RUN_ARGS", ["mausaji"])
    # nothing matched, market closed → the heartbeat still files with every count at zero
    assert ag.run_wa_sweep(BOT, "none", "hourly", now=FRI_0800) == 0
    hb = fake.reports[-1]
    assert hb["heartbeat"] is True and hb["bot"] == "wa-sweep" and hb["status"] == "clean"
    assert hb["summary"] == 'wa-sweep mausaji: 0 chats swept, 0 new msgs, 0 flags (0 pushed) · options: market closed · no chat matches "Bantu Mausaji" yet'
    # ops with no chats: the announcement goes out once (first run), the heartbeat says 0/0/0 (1 pushed)
    monkeypatch.setattr(ag, "RUN_ARGS", [])
    assert ag.run_wa_sweep(BOT, "none", "hourly", now=FRI_1045, mode="ops") == 0
    assert fake.reports[-1]["summary"] == ("wa-sweep ops: 0 chats swept, 0 new msgs, 0 flags (1 pushed)"
                                           " · no ops chat matches WA_SWEEP_CHATS / WA_SWEEP_GROUPS yet")
    assert sent.texts[-1].startswith("wa-sweep · watching 0 ops chats — none match yet; no group chats received from the bridges yet · ")
    assert ag.run_wa_sweep(BOT, "none", "hourly", now=FRI_1045) == 0                   # no argv → ops
    assert fake.reports[-1]["summary"] == "wa-sweep ops: 0 chats swept, 0 new msgs, 0 flags (0 pushed) · no ops chat matches WA_SWEEP_CHATS / WA_SWEEP_GROUPS yet"
    # market hours: the option check rides on the mausaji run; unavailable → warning, nothing invented
    c.post("/api/levels/options", json={"instrument": "NIFTY 29-Dec-26 25000 CE", "alert_below": 30, "held": "AA 29,250"})
    assert ag.run_wa_sweep(BOT, "none", "hourly", now=FRI_1045, mode="mausaji") == 0
    assert fake.reports[-1]["status"] == "clean" and " · option NIFTY 29-Dec-26 25000 CE ₹27.5 (below 30, pushed)" in fake.reports[-1]["summary"]
    import mdo_server
    mdo_server._options["set_fetch_chain"](lambda sym: None)
    assert ag.run_wa_sweep(BOT, "none", "hourly", now=FRI_1045 + timedelta(minutes=15), mode="mausaji") == 0
    assert fake.reports[-1]["status"] == "warning" and fake.reports[-1]["summary"].endswith(" · option price unavailable · no chat matches \"Bantu Mausaji\" yet")
    mdo_server._options["set_fetch_chain"](lambda sym: CHAIN)
    # a bridge that is down → warning with the count of pushes not delivered
    _post(c, MAUSAJI_JID, "Bantu Mausaji", "TCS lelo 3500", _ist(10, 50), "Bantu Mausaji", kind="dm")
    c.post("/api/levels", json={"ticker": "TCS", "buy_level": 3500})
    sent.ok = False
    assert ag.run_wa_sweep(BOT, "none", "hourly", now=FRI_1045 + timedelta(minutes=30), mode="mausaji") == 0
    assert fake.reports[-1]["status"] == "warning" and "1 flags (0 pushed)" in fake.reports[-1]["summary"]
    assert "1 push(es) NOT delivered" in fake.reports[-1]["summary"]
    sent.ok = True
    assert ag.run_wa_sweep(BOT, "none", "hourly", now=FRI_1045, mode="daily") == 0
    assert fake.reports[-1]["summary"].startswith("wa-sweep daily: 1 chats swept, 0 new msgs, 0 flags (1 pushed)")
    assert ag.run_wa_sweep(BOT, "none", "hourly", now=FRI_1045, mode="weekly") == 2
    assert fake.reports[-1]["status"] == "error"


def test_wa_sweep_is_wired_in_dispatch_fleet_cron_env_and_docs():
    assert ag.CUSTOM_BOTS["wa-sweep"] is ag.run_wa_sweep
    fleet = yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))
    ids = [b["id"] for b in fleet["bots"]]
    assert "classifier" not in ids and "wa-classifier" in ids                  # the dead library entry is gone (Aman 2026-10-09)
    bot = ag.find_bot(fleet, "wa-sweep")
    assert bot["enabled"] is True and bot["provider"] == "none" and bot["model"] == "none" and bot["runs_on"] == "vps-cron"
    assert bot["objective"] == "Aman's eyes on Mausaji and site groups"
    assert bot["command"] == "docker compose exec -T backend python mdo_agent.py wa-sweep ops"
    assert bot["command_mausaji"].endswith("wa-sweep mausaji") and bot["command_daily"].endswith("wa-sweep daily")
    assert bot["cadence"].startswith("every 15 min 09:00-15:45 IST Mon-Fri")
    assert isinstance(bot["heartbeat"], str) and "wa-sweep <mode>: C chats swept, N new msgs, F flags (K pushed)" in bot["heartbeat"]
    assert {"purpose", "thinks", "works", "limits", "minimum_output", "rules"} <= set(bot["charter"])
    rules = " ".join(bot["charter"]["rules"]).lower()
    assert "research only" in rules and "no llm" in rules and "holder on every share line" in rules
    assert set(bot["serves"]) <= {o["id"] for o in yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))["objectives"]}
    # the §8 block is what deploy_vps.sh render_cron installs: three lines, UTC
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    block = doc[doc.index("# MDO fleet — one line per bot"):]
    block = block[:block.index("```")]
    lines = {ln.split("mdo_agent.py wa-sweep ")[1].split()[0]: ln.split()[:5] for ln in block.splitlines() if "mdo_agent.py wa-sweep " in ln}
    assert lines == {"mausaji": ["*/15", "3-10", "*", "*", "1-5"], "ops": ["*/30", "2-16", "*", "*", "*"], "daily": ["30", "15", "*", "*", "*"]}
    env = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    for key in ("WA_SWEEP_CHATS=Bantu Mausaji;Vedanta Daily Report;Washery Civil Update;Ans Management;VWLR Indent Planning;Core Group",
                "WA_SWEEP_GROUPS=washery|siding|hotel|ans|vwlr|rake|plant|site|loader|dispatch", "WA_SWEEP_IDLE_HOURS=1", "MAUSAJI_CHAT="):
        assert key in env, key
    walk = open(os.path.join(ROOT, "briefs", "PLATFORM_WALKTHROUGH.md"), encoding="utf-8").read()
    assert "| classifier | library |" not in walk and "`classifier`" not in walk and "wa-classifier" in walk
    page = open(os.path.join(ROOT, "mdo-app", "app", "morning", "page.tsx"), encoding="utf-8").read()
    assert "<WaSweepCard />" in page and "api.waSweep.ack" in page and "Loading…" in page


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
