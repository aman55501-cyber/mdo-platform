"""grok memory — two-way memory between the fleet and Grok (mdo_grok_memory.py).

Covers the pure helpers (keys, scrub, build_context), the /api/grok/* endpoints
through the real app (upsert bumps times_seen; the context door's token, audit,
rate limit and app-key exemption) and the two Grok bots writing memory after a
canned Grok reply (x-watch through run(), singhvi through run_singhvi).

Runs under pytest OR standalone: `python tests/test_grok_memory.py`. Follows
tests/test_singhvi.py: a scratch VEGA_DB_PATH is set before mdo_server is imported.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_grok_memory as gm  # noqa: E402
import mdo_wa_intel as wai  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 9, 9, 0, tzinfo=IST)          # Friday
PHONE = "+91 98765 43210"
TOKEN = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4"      # 40 chars, letters+digits, no hyphen
WA_TEXT = "bhai payment kal karenge, 2 lakh pending from JSPL"


def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _agenda():
    return yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))


def _fleet():
    return yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))


# ── keys ──────────────────────────────────────────────────────────────────────
def test_keys_are_normalised_and_stable():
    assert gm.tender_key("SECL/2026/CW-14", "SECL", "whatever") == "id:secl-2026-cw-14"
    assert gm.tender_key("", " SECL ", "Coal Washing at Korba!!") == "secl/coal-washing-at-korba"
    assert gm.tender_key(None, "", "") == "unknown/untitled"
    assert gm.call_key("tatasteel", "buy", NOW.date()) == "TATASTEEL:BUY:2026-10-09"
    assert gm.call_key("TATASTEEL", "BUY", "2026-10-09T08:05:00") == "TATASTEEL:BUY:2026-10-09"
    assert gm.news_key("https://www.Reuters.com/markets/brent-opec/?utm=x#top", "") == "reuters.com/markets/brent-opec"
    assert gm.news_key("", "Brent +4% on OPEC+ cut") == "brent-4-on-opec-cut"
    assert gm.extract_tender_id("SECL NIT No. SECL/2026/CW-14 — coal washing, tender closing 2026-10-20") == "SECL/2026/CW-14"
    assert gm.extract_tender_id("tender closing soon", "Tender ID: GEM/2026/B/551234") == "GEM/2026/B/551234"
    assert gm.extract_tender_id("no id here") == ""
    assert gm.make_key("tender", {"buyer": "NTPC", "title": "RCR at Sipat", "text": "NIT 123/26"}) == "id:123-26"
    assert gm.make_key("call", {"stock": "infy", "action": "sell", "date": "2026-10-09"}) == "INFY:SELL:2026-10-09"
    assert gm.make_key("news", {"url": "https://x.com/SEBI_India/status/1234567890123456789"}) == "x.com/sebi_india/status/1234567890123456789"
    assert gm.extract_url("see https://x.com/a/status/1). more") == "https://x.com/a/status/1"


def test_scrub_removes_phones_and_tokens_but_keeps_urls_and_slugs():
    assert gm.scrub(f"call {PHONE} now") == "call [redacted] now"
    assert gm.scrub(f"key {TOKEN} leaked") == "key [redacted] leaked"
    assert gm.scrub("x.com/jspl/status/1234567890123456789 ok") == "x.com/jspl/status/1234567890123456789 ok"
    assert gm.scrub("brent-4-on-opec-cut-market-negative-for-indian-equities") == "brent-4-on-opec-cut-market-negative-for-indian-equities"
    assert gm.scrub("closes 2026-10-20 EMD 5 lakh") == "closes 2026-10-20 EMD 5 lakh"     # dates are not phones
    assert gm.scrub("a\n b   c", 3) == "a b"


def test_findings_and_calls_map_to_memory_rows():
    f = {"level": "critical", "title": "SECL NIT No. SECL/2026/CW-14 — coal washing at Korba",
         "detail": "New NIT on https://secl-cil.in/tenders/cw-14 ; EMD 5 lakh", "entity": "SECL", "domain": "vwlr"}
    row = gm.finding_to_memory(f, "x-watch", NOW)
    assert row["kind"] == "tender" and row["key"] == "id:secl-2026-cw-14" and row["source"] == "x-watch"
    assert row["url"] == "https://secl-cil.in/tenders/cw-14" and row["entity"] == "SECL" and row["sentiment"] == ""
    n = gm.finding_to_memory({"title": "Brent +4% on OPEC+ cut — market-negative for Indian equities",
                              "detail": "https://www.reuters.com/markets/brent-opec?x=1", "domain": "market"})
    assert n["kind"] == "news" and n["key"] == "reuters.com/markets/brent-opec" and n["sentiment"] == "negative"
    assert gm.finding_to_memory({"detail": "no title"}) is None and gm.finding_to_memory("x") is None
    c = {"stock": "TATASTEEL", "action": "BUY", "entry": 152.5, "stop": 148.0, "target": 160.0,
         "timeframe": "Intraday", "rationale": "breakout", "source_url": "https://x.com/AnilSinghvi_/status/1"}
    m = gm.call_to_memory(c, NOW)
    assert m == {"source": "singhvi", "kind": "call", "key": "TATASTEEL:BUY:2026-10-09", "entity": "TATASTEEL",
                 "text": "BUY TATASTEEL @ 152.5 SL 148 TG 160 Intraday — breakout",
                 "url": "https://x.com/AnilSinghvi_/status/1", "sentiment": "positive"}
    assert gm.call_to_memory({"stock": "X", "action": "HOLD"}) is None


# ── the context pack ──────────────────────────────────────────────────────────
def test_build_context_has_every_section_and_only_confirmed_objectives():
    agenda = _agenda()
    objectives = agenda["objectives"] + agenda["candidates"]           # candidates carry confirmed: false
    kw = gm.keywords_from_fleet(_fleet())
    assert "Brent" in kw["crude"] and "Strait of Hormuz" in kw["crude"] and "SECL" in kw["tender_buyers"]
    memory = [
        {"kind": "tender", "key": "id:secl-2026-cw-14", "entity": "SECL", "text": f"call {PHONE} · {WA_TEXT}"},
        {"kind": "news", "key": "reuters.com/markets/brent-opec", "entity": "", "text": f"token {TOKEN}"},
        {"kind": "fact", "key": "tender247-login-expires-on-password-change", "entity": "", "text": "portal quirk"},
    ]
    tenders = [{"buyer": "NTPC", "notes": "[grok-subscription] RCR at Sipat — NIT NTPC/2026/RCR-7", "url": "", "due_date": "2026-10-30"}]
    calls = [{"ticker": "HDFCBANK", "direction": "SELL"}]
    text = gm.build_context(objectives, wai.ENTITIES, kw, memory, tenders, calls, NOW)

    assert len(text.encode("utf-8")) <= gm.PACK_MAX_BYTES
    for header in ("## Objectives", "## Entities", "## Tender lens", "## Market lens",
                   "## Already known — do not re-report", "## Output format"):
        assert header in text, header
    assert "Fri 09 Oct 2026 09:00 IST" in text
    # objectives: Aman's words, confirmed only — nothing from the candidates list, no amounts added
    live = [o for o in agenda["objectives"] if o.get("confirmed") is True]
    assert len(live) == 5
    for o in live:
        assert f"- {o['id']}: " in text and o["title"][:60] in text
    for c in agenda["candidates"]:
        assert c["title"] not in text and c["id"] not in text
    assert "₹" not in text.split("## Objectives")[1].split("## Entities")[0]
    assert "battery-plant" in text and "[exploratory]" in text
    # entities straight from the register
    for name, _ in wai.ENTITIES:
        assert name in text
    # lenses in Aman's terms
    low = text.lower()
    assert "coal washing" in low and "rcr" in low and "margin first" in low
    assert "never book a loss" in low and ">80%" in text and "crude" in low and "SECL" in text and "JSPL Raigarh" in text
    # already known: memory keys, the pipeline tender, today's queued call
    assert "id:secl-2026-cw-14" in text and "id:ntpc-2026-rcr-7" in text
    assert "HDFCBANK:SELL:2026-10-09" in text and "reuters.com/markets/brent-opec" in text
    assert "tender247-login-expires-on-password-change" in text
    # output format: the Gmail-draft table columns, both tags
    assert "[GROK-TENDER] buyer|title|tender id|category|publish|closing|value|EMD|eligibility|location|URL" in text
    assert "[GROK-SINGHVI] stock|action|entry|stop|target|timeframe|rationale|source" in text
    # forbidden content never reaches the pack: phone, token, WhatsApp text, memory free text
    assert PHONE not in text and "98765" not in text and TOKEN not in text and WA_TEXT not in text
    assert "portal quirk" not in text and "[redacted]" not in text
    # empty inputs still produce a complete, honest pack
    empty = gm.build_context([], [], {}, [], [], [], NOW)
    assert "(none confirmed)" in empty and "tenders: none" in empty and "calls" in empty and len(empty.encode()) <= gm.PACK_MAX_BYTES


def test_build_context_size_cap_holds_under_a_flood():
    memory = [{"kind": "news", "key": f"example.com/very/long/path/number/{i:04d}/" + "x" * 60, "entity": ""} for i in range(500)]
    memory += [{"kind": "tender", "key": f"buyer-{i}/" + "coal-washing-" * 6 + str(i), "entity": "X"} for i in range(200)]
    text = gm.build_context(_agenda()["objectives"], wai.ENTITIES, gm.keywords_from_fleet(_fleet()), memory, [], [], NOW)
    assert len(text.encode("utf-8")) <= gm.PACK_MAX_BYTES
    assert "## Output format" in text and "(+" in text and "more)" in text   # trimmed, never truncated mid-way
    assert text.endswith("Subject line = the tag.\n")


# ── endpoints ─────────────────────────────────────────────────────────────────
def test_memory_upsert_bumps_times_seen_and_filters(monkeypatch):
    client = _client()
    item = {"source": "grok-relay", "kind": "tender", "buyer": "SECL", "title": "Coal washing at Korba",
            "text": "NIT No. SECL/2026/CW-14 coal washing at Korba, closes 2026-10-20",
            "url": "https://secl-cil.in/tenders/cw-14", "entity": "SECL"}
    r = client.post("/api/grok/memory", json=item)
    assert r.status_code == 200 and r.json()["new"] == 1 and r.json()["bumped"] == 0
    mem_id = r.json()["ids"][0]
    row = client.get("/api/grok/memory?kind=tender&entity=SECL").json()["memory"][0]
    assert row["id"] == mem_id and row["key"] == "id:secl-2026-cw-14" and row["times_seen"] == 1 and row["status"] == "open"
    first_seen = row["first_seen"]
    # the same tender again (different source, explicit key) → bumped, first_seen kept
    r2 = client.post("/api/grok/memory", json=[{"source": "x-watch", "kind": "tender", "key": "id:secl-2026-cw-14",
                                                "text": "seen again", "sentiment": "neutral"},
                                               {"source": "singhvi", "kind": "weather", "key": "x", "text": "bad kind"},
                                               {"source": "someone", "kind": "news", "key": "y", "text": "bad source"}])
    assert r2.status_code == 200
    assert r2.json()["new"] == 0 and r2.json()["bumped"] == 1 and r2.json()["skipped"] == {"bad kind": 1, "bad source": 1}
    row = client.get(f"/api/grok/memory?kind=tender").json()["memory"][0]
    assert row["times_seen"] == 2 and row["first_seen"] == first_seen and row["last_seen"] >= first_seen
    assert row["text"] == "seen again" and row["url"] == "https://secl-cil.in/tenders/cw-14" and row["sentiment"] == "neutral"
    assert row["source"] == "x-watch"
    # a single rejected row is a 400, not a silent 200
    assert client.post("/api/grok/memory", json={"kind": "nope", "key": "k"}).status_code == 400
    assert client.post("/api/grok/memory", content=b"not json").status_code == 400
    # news with sentiment; filters by kind, sentiment, since; bad since → 400
    client.post("/api/grok/memory", json={"source": "x-watch", "kind": "news", "url": "https://www.reuters.com/a?b=1",
                                          "text": "Brent +4%", "sentiment": "negative", "entity": "crude"})
    got = client.get("/api/grok/memory?kind=news&sentiment=positive,negative&since=24h").json()
    assert got["count"] == 1 and got["memory"][0]["key"] == "reuters.com/a"
    assert client.get("/api/grok/memory?since=2099-01-01").json()["count"] == 0
    assert client.get("/api/grok/memory?since=yesterday").status_code == 400
    assert client.get("/api/grok/memory?kind=tender,news").json()["count"] == 2
    # status: done drops it from the open view; bad status 400; unknown id 404
    assert client.post(f"/api/grok/memory/{mem_id}/status", json={"status": "done"}).json() == {"id": mem_id, "status": "done"}
    assert all(r["id"] != mem_id for r in client.get("/api/grok/memory?status=open").json()["memory"])
    assert client.get("/api/grok/memory?status=done").json()["memory"][0]["id"] == mem_id
    assert client.post(f"/api/grok/memory/{mem_id}/status", json={"status": "maybe"}).status_code == 400
    assert client.post("/api/grok/memory/999999/status", json={"status": "done"}).status_code == 404
    # phone numbers posted in text never persist in the clear
    r = client.post("/api/grok/memory", json={"source": "grok-relay", "kind": "fact", "key": "contact-x", "text": f"ring {PHONE}"})
    assert "98765" not in client.get("/api/grok/memory?kind=fact").json()["memory"][0]["text"]


def test_context_door_token_audit_rate_limit_and_app_key_exemption(monkeypatch):
    import mdo_server
    client = _client()
    grok = mdo_server._grok
    grok["reset_rate"]()
    grok["invalidate"]()
    # no token configured → 403 for everyone, audited
    monkeypatch.delenv("GROK_CONTEXT_TOKEN", raising=False)
    assert client.get("/api/grok/context?k=anything").status_code == 403
    monkeypatch.setenv("GROK_CONTEXT_TOKEN", "ctx-secret")
    assert client.get("/api/grok/context").status_code == 403
    assert client.get("/api/grok/context?k=wrong").status_code == 403
    assert client.get("/api/grok/context", headers={"X-Grok-Context-Token": "wrong"}).status_code == 403
    # right token, query or header → 200 text/plain, the real pack
    client.post("/api/grok/memory", json={"source": "grok-subscription", "kind": "tender", "key": "id:door-test-2026-1", "text": "t"})
    r = client.get("/api/grok/context?k=ctx-secret")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert r.headers.get("cache-control") == "no-store"
    assert "MDO FLEET CONTEXT PACK" in r.text and "id:door-test-2026-1" in r.text and "[GROK-TENDER]" in r.text
    assert len(r.content) <= gm.PACK_MAX_BYTES
    r2 = client.get("/api/grok/context", headers={"X-Grok-Context-Token": "ctx-secret"})
    assert r2.status_code == 200 and r2.text == r.text
    # every fetch is audited with ip + ok flag
    audit = client.get("/api/grok/context/audit?limit=10").json()["audit"]
    assert audit[0]["ok"] == 1 and audit[0]["note"] == "cached" and audit[0]["ip"]
    assert audit[1]["ok"] == 1 and audit[1]["note"] == "built" and audit[1]["bytes"] == len(r.content)
    assert audit[2]["ok"] == 0 and audit[2]["note"] == "bad or missing token"
    # a write invalidates the cache, so the pack is honest within the 10-minute window
    client.post("/api/grok/memory", json={"source": "grok-relay", "kind": "call", "key": "ACC:BUY:2026-10-09", "text": "c"})
    assert "ACC:BUY:2026-10-09" in client.get("/api/grok/context?k=ctx-secret").text
    # crude rate limit: 60 successful fetches per hour, then 429 (audited)
    grok["reset_rate"]()
    codes = [client.get("/api/grok/context?k=ctx-secret").status_code for _ in range(gm.RATE_LIMIT_PER_HOUR + 1)]
    assert codes[:gm.RATE_LIMIT_PER_HOUR] == [200] * gm.RATE_LIMIT_PER_HOUR and codes[-1] == 429
    assert client.get("/api/grok/context/audit?limit=1").json()["audit"][0]["note"] == "rate limit"
    grok["reset_rate"]()
    # the door is exempt from the app key; everything else under /api/grok needs it
    monkeypatch.setattr(mdo_server, "MDO_AUTH_TOKEN", "app-key")
    assert client.get("/api/grok/context?k=ctx-secret").status_code == 200
    assert client.get("/api/grok/memory").status_code == 401
    assert client.get("/api/grok/context-internal").status_code == 401
    r = client.get("/api/grok/context-internal", headers={"X-MDO-Key": "app-key"})
    assert r.status_code == 200 and r.json()["context"].startswith("MDO FLEET CONTEXT PACK") and r.json()["bytes"] <= gm.PACK_MAX_BYTES
    assert client.get("/api/grok/memory", headers={"X-MDO-Key": "app-key"}).status_code == 200
    # the app key alone never opens the door
    assert client.get("/api/grok/context", headers={"X-MDO-Key": "app-key"}).status_code == 403


# ── the bots write memory ─────────────────────────────────────────────────────
class _Fake:
    """Routes mdo_agent.api() into the app under test for /api/grok/*, cans the
    rest, records heartbeats/reports."""

    def __init__(self, client, canned=None):
        self.client, self.calls, self.reports, self.canned = client, [], [], canned or {}

    def api(self, path, method="GET", body=None, timeout=30):
        self.calls.append((method, path))
        if path == "/api/agent/report":
            self.reports.append(body)
            return {"stored": True, "report_id": 1, "counts": {}}
        if path.startswith("/api/grok/"):
            r = self.client.post(path, json=body) if method == "POST" else self.client.get(path)
            assert r.status_code == 200, r.text
            return r.json()
        if path in self.canned:
            return self.canned[path]
        if path == "/api/feed/publish":
            return {"published": True}
        return {}


XWATCH_REPLY = json.dumps({
    "title": "x-watch 09:00", "summary": "1 coal-washing NIT, 1 crude piece", "body": "",
    "findings": [
        {"level": "critical", "title": "SECL NIT No. SECL/2026/CW-14 — coal washing at Korba, closes 2026-10-20",
         "detail": "New NIT on https://secl-cil.in/tenders/cw-14 ; EMD 5 lakh", "action": "evaluate margin",
         "owner": "Aman", "entity": "SECL", "domain": "vwlr", "eta": "today"},
        {"level": "important", "title": "Brent +4% on OPEC+ cut — market-negative for Indian equities",
         "detail": "Reuters https://www.reuters.com/markets/brent-opec?x=1 — OPEC+ extends cuts", "action": "watch",
         "owner": "Aman", "entity": "Aditi Investments", "domain": "market"},
        {"level": "info", "title": "JSPL Raigarh rake loading normal", "detail": "https://x.com/JSPL/status/1234567890123456789",
         "owner": "site head", "entity": "JSPL", "domain": "vwlr"},
    ]})
CHECKS = {"checks": [{"code": c, "cadence": "hourly", "status": "active", "run_window": "", "title": c, "sources": [],
                      "threshold": "", "owner": "Aman"} for c in ("x_pulse", "tender_watch")]}


def test_x_watch_run_remembers_every_finding_and_reports_memory_count(monkeypatch):
    client = _client()
    fake = _Fake(client, canned={"/api/spend": {"mode": "normal"}, "/api/checks": CHECKS})
    prompts = []
    monkeypatch.setattr(ag, "api", fake.api)
    monkeypatch.setattr(ag, "KEY", "k")
    monkeypatch.setattr(ag, "GROK_KEY", "g")
    monkeypatch.setattr(ag, "wait_for_backend", lambda *a, **k: True)
    monkeypatch.setattr(ag, "ask_grok", lambda prompt, model, bot_id, handles=None: prompts.append(prompt) or XWATCH_REPLY)
    # the bot may be paused in fleet.yaml (Aman pauses bots at will); the test exercises the code path
    _lf = ag.load_fleet
    def _enabled_fleet():
        f = _lf()
        for b in f.get("bots") or []:
            if b.get("id") == "x-watch": b["enabled"] = True
        return f
    monkeypatch.setattr(ag, "load_fleet", _enabled_fleet)
    keys = {"id:secl-2026-cw-14", "reuters.com/markets/brent-opec", "x.com/jspl/status/1234567890123456789"}
    # other tests share this scratch database, so count from where each key stands now
    seen0 = {r["key"]: r["times_seen"] for r in client.get("/api/grok/memory?limit=500").json()["memory"]}

    assert ag.run("x-watch") == 0

    assert len(prompts) == 1 and "Already known" in prompts[0] and "report\nonly NEW items" in prompts[0]
    rows = {r["key"]: r for r in client.get("/api/grok/memory?limit=500").json()["memory"] if r["key"] in keys}
    assert set(rows) == keys and all(r["times_seen"] == seen0.get(k, 0) + 1 for k, r in rows.items())
    t = rows["id:secl-2026-cw-14"]
    assert t["kind"] == "tender" and t["source"] == "x-watch" and t["entity"] == "SECL"
    assert t["url"] == "https://secl-cil.in/tenders/cw-14" and "EMD 5 lakh" in t["text"]
    n = rows["reuters.com/markets/brent-opec"]
    assert n["kind"] == "news" and n["sentiment"] == "negative" and n["url"] == "https://www.reuters.com/markets/brent-opec?x=1"
    assert rows["x.com/jspl/status/1234567890123456789"]["kind"] == "news"
    # the filed report says how much memory it added
    rep = [r for r in fake.reports if not r.get("heartbeat")][-1]
    assert rep["bot"] == "x-watch" and rep["summary"].endswith(" · memory +3") and len(rep["findings"]) == 3
    # the next hour: the same three come back → bumped, not duplicated; the pack now lists them as known
    assert ag.run("x-watch") == 0
    again = {r["key"]: r for r in client.get("/api/grok/memory?limit=500").json()["memory"] if r["key"] in keys}
    assert set(again) == keys and all(r["times_seen"] == seen0.get(k, 0) + 2 for k, r in again.items())
    pack = client.get("/api/grok/context-internal").json()["context"]
    assert "id:secl-2026-cw-14" in pack and "reuters.com/markets/brent-opec" in pack
    # a quiet hour still heartbeats, with memory +0
    monkeypatch.setattr(ag, "ask_grok", lambda *a, **k: '{"findings": [], "summary": "", "title": "", "body": ""}')
    fake.reports.clear()
    assert ag.run("x-watch") == 0
    assert fake.reports[-1]["heartbeat"] is True and fake.reports[-1]["summary"].endswith("nothing crossed a threshold · memory +0")


def test_ask_grok_prepends_the_context_pack_to_instructions(monkeypatch):
    client = _client()
    fake = _Fake(client)
    monkeypatch.setattr(ag, "api", fake.api)
    sent = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        sent["payload"] = json.loads(req.data)
        sent["auth"] = req.get_header("Authorization")
        return _Resp(json.dumps({"output": [{"type": "message", "content": [{"type": "output_text", "text": "{\"calls\": []}"}]}],
                                 "usage": {"input_tokens": 10, "output_tokens": 2}}).encode())

    monkeypatch.setattr(ag.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(ag, "GROK_KEY", "g")
    assert ag.ask_grok("find calls", "grok-4", "singhvi") == '{"calls": []}'
    instr = sent["payload"]["instructions"]
    assert instr.startswith("MDO FLEET CONTEXT PACK") and instr.endswith(ag.GROK_INSTRUCTIONS)
    assert "## Already known — do not re-report" in instr and "[GROK-SINGHVI]" in instr
    assert sent["payload"]["input"] == [{"role": "user", "content": "find calls"}]
    assert ("GET", "/api/grok/context-internal") in fake.calls and ("POST", "/api/spend/record") in fake.calls
    # the backend being down costs the pack, not the run
    monkeypatch.setattr(ag, "api", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert ag.ask_grok("find calls", "grok-4", "singhvi") == '{"calls": []}'
    assert sent["payload"]["instructions"] == ag.GROK_INSTRUCTIONS


def test_singhvi_run_remembers_calls_found(monkeypatch):
    client = _client()
    fake = _Fake(client)
    monkeypatch.setattr(ag, "api", fake.api)
    reply = json.dumps({"calls": [
        {"stock": "ACC", "action": "BUY", "entry": 1900, "stop": 1880, "target": 1950, "rationale": "cement demand",
         "conviction": 90, "source_url": "https://x.com/AnilSinghvi_/status/77"},
        {"stock": "WIPRO", "action": "SELL", "entry": 500, "stop": None, "target": 480, "rationale": "weak",
         "conviction": 95, "source_url": "https://x.com/AnilSinghvi_/status/78"}], "note": "two calls"})
    monkeypatch.setattr(ag, "ask_grok", lambda *a, **k: reply)
    bot = {"id": "singhvi", "provider": "grok", "model": "grok-4", "x_handles": []}
    assert ag.run_singhvi(bot, "grok-4", "daily", now=NOW) == 0
    hb = fake.reports[-1]
    assert hb["status"] == "clean" and " · memory +2" in hb["summary"] and "1 queued as PROPOSALS" in hb["summary"]
    rows = {r["key"]: r for r in client.get("/api/grok/memory?kind=call&limit=500").json()["memory"]}
    acc, wipro = rows["ACC:BUY:2026-10-09"], rows["WIPRO:SELL:2026-10-09"]
    assert acc["sentiment"] == "positive" and acc["url"].endswith("/77") and acc["text"].startswith("BUY ACC @ 1900 SL 1880 TG 1950")
    assert wipro["sentiment"] == "negative" and "SL" not in wipro["text"]          # the missing level is not invented
    assert acc["source"] == "singhvi" and acc["entity"] == "ACC"
    # a failed memory write is reported in the heartbeat, never swallowed
    monkeypatch.setattr(ag, "api", lambda path, method="GET", body=None, timeout=30: (
        fake.reports.append(body) or {} if path == "/api/agent/report" else
        ({"calls": []} if path == "/api/singhvi/today" else (_ for _ in ()).throw(OSError("down")))))
    assert ag.run_singhvi(bot, "grok-4", "daily", now=NOW) == 0
    assert fake.reports[-1]["status"] == "warning" and "memory write failed" in fake.reports[-1]["summary"]


# ── consumers + wiring ───────────────────────────────────────────────────────
def test_consumers_read_grok_memory(monkeypatch):
    client = _client()
    fake = _Fake(client)
    monkeypatch.setattr(ag, "api", fake.api)
    client.post("/api/grok/memory", json={"source": "x-watch", "kind": "news", "key": "example.com/crude-up",
                                          "text": "crude up", "sentiment": "negative", "url": "https://example.com/crude-up"})
    for bot_id in ("daily-brief", "capital-watcher"):
        fake.calls.clear()
        d = ag.gather({"id": bot_id, "checks": [], "cadence": "daily"})
        assert any(k == "example.com/crude-up" for k in (r["key"] for r in d["grok_memory"]))
        assert ("GET", "/api/grok/memory?kind=news&sentiment=positive,negative&since=24h&limit=40") in fake.calls
    assert "grok_memory" not in ag.gather({"id": "ops-hourly", "checks": [], "cadence": "hourly"})


def test_fleet_env_and_server_wiring():
    fleet = _fleet()
    bots = {b["id"]: b for b in fleet["bots"]}
    assert "$MDO_SELF_URL/api/grok/context?k=" in bots["grok-tasks"]["charter"]["works"]
    assert "/api/grok/memory" in bots["grok-relay"]["charter"]["works"]
    assert "/api/grok/context-internal" in bots["x-watch"]["charter"]["works"] and "grok_memory" in bots["x-watch"]["charter"]["works"]
    assert "/api/grok/context-internal" in bots["singhvi"]["charter"]["works"] and "grok_memory" in bots["singhvi"]["charter"]["works"]
    # GROK_CONTEXT_TOKEN sits inside the Chief of Staff block, so deploy_vps.sh step b appends it (empty = 403)
    env = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    block = env.split("# ── Chief of Staff")[1].split("\n# ── ")[0] + "\n"
    assert "\nGROK_CONTEXT_TOKEN=\n" in block and "READ-ONLY" in block
    deploy = open(os.path.join(ROOT, "deploy_vps.sh"), encoding="utf-8").read()
    assert "GROK_CONTEXT_TOKEN" in deploy
    src = open(os.path.join(ROOT, "mdo_server.py"), encoding="utf-8").read()
    assert 'request.url.path == "/api/grok/context"' in src and "mdo_grok_memory.register(app, vdb)" in src
    assert 'await _grok["ensure_schema"](_vdb)' in src
    assert "Already known" in ag.BOT_RULES["x-watch"]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
