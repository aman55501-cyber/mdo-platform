"""tenders-direct — public tender listings parsed straight from the buyers' pages, rule-based, zero LLM spend.

Nothing here touches the network: mdo_tenders_direct.fetch_page is replaced by canned HTML per site (one page in
the real layout family of each portal: Drupal views tables for SECL / Coal India, the nested CPP/NIC list table
for eprocure and coalindiatenders, a plain table for NTPC, a script-only page for MSTC), the WhatsApp send is
canned. Follows tests/test_mail.py: a scratch VEGA_DB_PATH is set before mdo_server is imported; the endpoint
tests wipe the tender tables (the DB is shared by every test module).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))
os.environ.setdefault("SHARE_MASTER_DATA_DIR", tempfile.mkdtemp())

import yaml  # noqa: E402

import mdo_agent as ag  # noqa: E402
import mdo_tenders_direct as td  # noqa: E402
from mdo_cos import IST  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT = {"id": "tenders-direct", "provider": "none", "model": "none"}
NOW = datetime(2026, 10, 9, 6, 30, tzinfo=IST)
SITE = {s["key"]: s for s in td.SITES}

# ── canned pages, one per site ───────────────────────────────────────────────
SECL_HTML = """<html><head><script>var x = "<table><tr><td>not a table</td></tr></table>";</script></head><body>
<div class="view-content"><table class="views-table cols-5"><thead><tr>
<th>Tender No.</th><th>Description</th><th>Publish Date</th><th>Closing Date</th><th>Download</th></tr></thead><tbody>
<tr><td>SECL/GM(CMC)/2026/W/41</td><td><a href="/sites/default/files/tenders/w41.pdf">Operation &amp; maintenance of coal washery, 2.5 MTPA, Korba</a></td><td>05-10-2026</td><td>28-10-2026 15:00</td><td><a href="/sites/default/files/tenders/w41.pdf">PDF</a></td></tr>
<tr><td>SECL/GM(CMC)/2026/C/42</td><td>Civil works for colony at Gevra</td><td>06-10-2026</td><td>20-10-2026</td><td><a href="/x/c42.pdf">PDF</a></td></tr>
<tr><td>SECL/GM(CMC)/2026/T/43</td><td>Surface transport of coal from Dipka OCP to Dipka siding, 3 years</td><td>07-10-2026</td><td>15-11-2026</td><td><a href="/x/t43.pdf">PDF</a></td></tr>
</tbody></table></div></body></html>"""

CPP_HTML = """<html><body><table width="100%"><tr><td>
<table id="activeTenders" class="list_table" width="100%">
<tr><td class="list_header">S.No</td><td class="list_header">e-Published Date</td><td class="list_header">Bid Submission Closing Date</td><td class="list_header">Tender Opening Date</td><td class="list_header">Title and Ref.No./Tender ID</td><td class="list_header">Organisation Chain</td></tr>
<tr class="even"><td>1.</td><td>08-Oct-2026 05:30 PM</td><td>29-Oct-2026 03:00 PM</td><td>30-Oct-2026 03:30 PM</td><td><a href="/nicgep/app?component=%24DirectLink&amp;page=FrontEndLatestActiveTenders&amp;service=direct&amp;sp=1">[Hiring of HEMM for overburden removal at Dipka OC] [SECL/DIPKA/2026/OB/17][2026_SECL_123456_1]</a></td><td>Coal India Limited||South Eastern Coalfields Limited||Dipka Area</td></tr>
<tr class="odd"><td>2.</td><td>08-Oct-2026 11:00 AM</td><td>21-Oct-2026 01:00 PM</td><td>22-Oct-2026 01:30 PM</td><td><a href="/nicgep/app?sp=2">[Supply of stationery items] [SECL/HQ/2026/ST/3][2026_SECL_123457_1]</a></td><td>Coal India Limited||South Eastern Coalfields Limited||HQ Bilaspur</td></tr>
<tr class="even"><td>3.</td><td>07-Oct-2026 04:00 PM</td><td>05-Nov-2026 03:00 PM</td><td>06-Nov-2026 03:30 PM</td><td><a href="/nicgep/app?sp=3">[Road cum Rail (RCR) transportation of coal from Kusmunda to Korba siding] [SECL/KUS/2026/RCR/9][2026_SECL_123458_1]</a></td><td>Coal India Limited||South Eastern Coalfields Limited||Kusmunda Area</td></tr>
</table></td></tr></table></body></html>"""

EPROCURE_HTML = CPP_HTML.replace("SECL", "NTPC").replace("South Eastern Coalfields Limited", "NTPC Limited").replace(
    "Coal India Limited||", "Ministry of Power||").replace("/nicgep/", "/eprocure/").replace("Dipka Area", "Lara STPP")

COALINDIA_HTML = """<html><body><table class="table table-striped"><thead><tr>
<th>Tender ID / Reference No.</th><th>Tender Title</th><th>Company</th><th>Publish date</th><th>Closing date</th><th>Estimated Cost</th></tr></thead><tbody>
<tr><td>CIL/MCL/2026/WB/7</td><td><a href="https://www.coalindia.in/tender/cil-mcl-2026-wb-7">Setting up of 10 MTPA coal beneficiation plant on BOM basis at Talcher</a></td><td>MCL</td><td>2026-10-01</td><td>2026-11-20</td><td>Rs. 1,250 Crore</td></tr>
<tr><td>CIL/HQ/2026/IT/2</td><td><a href="https://www.coalindia.in/tender/cil-hq-2026-it-2">Supply of laptops</a></td><td>CIL HQ</td><td>2026-10-03</td><td>2026-10-17</td><td>Rs. 45 Lakh</td></tr>
<tr><td>CIL/WCL/2026/CR/4</td><td><a href="https://www.coalindia.in/tender/cil-wcl-2026-cr-4">Crushing of coal at Umrer OC, 2 years</a></td><td>WCL</td><td>2026-10-04</td><td>2026-10-25</td><td>Rs. 2.4 Cr</td></tr>
</tbody></table></body></html>"""

NTPC_HTML = """<html><body><h2>Current Tenders</h2><table border="1" cellpadding="2"><tr>
<th>Sl</th><th>Tender No</th><th>Tender Description</th><th>Project/Unit</th><th>Due Date</th><th>Estimated Value</th></tr>
<tr><td>1</td><td><a href="tender.php?id=9981">NTPC/LARA/2026/CT/11</a></td><td>Coal transportation by road from Dipka siding to Lara STPP</td><td>Lara</td><td>31/10/2026</td><td>Rs. 12,50,00,000</td></tr>
<tr><td>2</td><td><a href="tender.php?id=9982">NTPC/SIPAT/2026/AMC/5</a></td><td>AMC of air conditioners</td><td>Sipat</td><td>18/10/2026</td><td>Rs. 25,00,000</td></tr>
<tr><td>3</td><td><a href="tender.php?id=9983">NTPC/KORBA/2026/RL/2</a></td><td>Rake loading &amp; wagon cleaning at Korba MGR siding</td><td>Korba</td><td>Nov 2, 2026</td><td>Rs. 90,00,000</td></tr>
</table></body></html>"""

MSTC_HTML = """<html><head><title>MSTC e-Commerce</title></head><body><script>window.location="/auctionhome/coal/home.jsp";</script>
<noscript><table><tr><th>Notice</th><th>Date</th></tr><tr><td>JavaScript required</td><td>-</td></tr></table></noscript>
<div id="app"></div></body></html>"""

PAGES = {
    SITE["secl"]["url"]: SECL_HTML, SITE["secl-etender"]["url"]: CPP_HTML, SITE["coalindia"]["url"]: COALINDIA_HTML,
    SITE["ntpc"]["url"]: NTPC_HTML, SITE["eprocure"]["url"]: EPROCURE_HTML, SITE["mstc"]["url"]: MSTC_HTML,
}


def _fetcher(pages: dict, blocked: dict | None = None):
    calls = []

    def fetch(url, timeout=25):
        calls.append(url)
        if blocked and url in blocked:
            return blocked[url]
        html = pages.get(url)
        if html is None:
            return {"ok": False, "status": 0, "html": "", "reason": "unreachable: [Errno -2] Name or service not known"}
        return {"ok": True, "status": 200, "html": html, "reason": ""}
    fetch.calls = calls
    return fetch


# ── pure: config ─────────────────────────────────────────────────────────────
def test_keywords_floor_and_sites_from_env(monkeypatch):
    for k in ("TENDERS_KEYWORDS", "TENDERS_MIN_VALUE_CR", "TENDERS_SITES_OFF"):
        monkeypatch.delenv(k, raising=False)
    assert td.keywords() == ["washery", "washing", "beneficiation", "RCR", "road cum rail", "coal transportation",
                             "coal loading", "rake loading", "siding", "surface transport", "crushing", "overburden"]
    assert td.min_value_cr() == 0.0
    assert [s["key"] for s in td.sites()] == ["secl", "secl-etender", "coalindia", "ntpc", "eprocure", "mstc"]
    monkeypatch.setenv("TENDERS_KEYWORDS", "washery, RCR ;rcr; ; Coal   Handling Plant")
    assert td.keywords() == ["washery", "RCR", "Coal Handling Plant"]
    monkeypatch.setenv("TENDERS_KEYWORDS", " ; ")
    assert td.keywords()[0] == "washery"                      # an empty list falls back to the default
    monkeypatch.setenv("TENDERS_MIN_VALUE_CR", "2.5")
    assert td.min_value_cr() == 2.5
    monkeypatch.setenv("TENDERS_MIN_VALUE_CR", "ten")
    assert td.min_value_cr() == 0.0
    monkeypatch.setenv("TENDERS_SITES_OFF", "mstc, ntpc")
    assert [s["key"] for s in td.sites()] == ["secl", "secl-etender", "coalindia", "eprocure"]


def test_dates_values_and_keyword_matching():
    assert td.parse_date("29-Oct-2026 03:00 PM") == "2026-10-29" and td.parse_date("31/10/2026") == "2026-10-31"
    assert td.parse_date("2026-11-05") == "2026-11-05" and td.parse_date("Oct 9, 2026") == "2026-10-09"
    assert td.parse_date("9 October 2026") == "2026-10-09" and td.parse_date("05-10-2026") == "2026-10-05"
    assert td.parse_date("none") == "" and td.parse_date("") == "" and td.parse_date("32-13-2026") == ""
    assert td.value_cr("Rs. 12,50,00,000") == 12.5 and td.value_cr("Rs. 45 Lakh") == 0.45 and td.value_cr("1.2 Cr") == 1.2
    assert td.value_cr("Rs. 1,250 Crore") == 1250 and td.value_cr("NA") is None and td.value_cr("1,234") is None
    assert td.value_cr("") is None and td.value_cr("3 million") == 0.3
    assert td.match_keywords("RCR of coal from Kusmunda") == ["RCR"] and td.match_keywords("Orcr crushing") == ["crushing"]
    assert td.match_keywords("Coal Washery O&M") == ["washery"] and td.match_keywords("Road-cum-Rail mode") == ["road cum rail"]
    assert td.match_keywords("Supply of laptops") == [] and td.match_keywords("overburden removal", ["Overburden"]) == ["Overburden"]
    assert td.category_for(["washery"]) == "Coal washing" and td.category_for(["RCR"]) == "RCR"
    assert td.category_for(["siding"]) == "Loading" and td.category_for(["overburden"]) == "Mining services"
    assert td.category_for(["coal transportation", "siding"]) == "Coal transport"
    # the floor: a stated value below it is not matched; an unstated value never disqualifies
    t = {"title": "Coal washery O&M", "org": "SECL", "value_text": "Rs. 90,00,000"}
    assert td.classify(t, floor_cr=0)["matched"] and not td.classify(t, floor_cr=1)["matched"]
    assert td.classify(dict(t, value_text=""), floor_cr=1)["matched"] and td.classify(dict(t, value_text=""), floor_cr=1)["value_cr"] is None
    assert td.classify(t, floor_cr=0)["category"] == "Coal washing" and td.classify({"title": "laptops"}, floor_cr=0)["category"] == ""


# ── pure: the parsers, one canned page per site ──────────────────────────────
def test_parse_secl_drupal_table():
    rows = td.parse_listing(SECL_HTML, SITE["secl"])
    assert [r["tender_id"] for r in rows] == ["SECL/GM(CMC)/2026/W/41", "SECL/GM(CMC)/2026/C/42", "SECL/GM(CMC)/2026/T/43"]
    assert rows[0]["title"] == "Operation & maintenance of coal washery, 2.5 MTPA, Korba" and rows[0]["org"] == "SECL"
    assert rows[0]["published"] == "2026-10-05" and rows[0]["due"] == "2026-10-28"
    assert rows[0]["url"] == "https://www.secl-cil.in/sites/default/files/tenders/w41.pdf"
    assert rows[1]["url"] == "https://www.secl-cil.in/x/c42.pdf"           # a row without a title link keeps the first link it has
    c = [td.classify(r, floor_cr=0) for r in rows]
    assert [x["matched"] for x in c] == [True, False, True] and c[2]["keywords"] == ["siding", "surface transport"]
    assert c[2]["category"] == "Coal transport"


def test_parse_cpp_nested_tables_secl_etender_and_eprocure():
    rows = td.parse_listing(CPP_HTML, SITE["secl-etender"])
    assert [r["tender_id"] for r in rows] == ["2026_SECL_123456_1", "2026_SECL_123457_1", "2026_SECL_123458_1"]
    assert rows[0]["title"] == "Hiring of HEMM for overburden removal at Dipka OC"
    assert rows[0]["org"] == "South Eastern Coalfields Limited / Dipka Area"
    assert rows[0]["published"] == "2026-10-08" and rows[0]["due"] == "2026-10-29"
    assert rows[0]["url"].startswith("https://coalindiatenders.nic.in/nicgep/app?component=%24DirectLink")
    assert rows[2]["title"].startswith("Road cum Rail (RCR) transportation") and rows[2]["due"] == "2026-11-05"
    c = [td.classify(r, floor_cr=0) for r in rows]
    assert [x["matched"] for x in c] == [True, False, True] and c[0]["category"] == "Mining services" and c[2]["category"] == "RCR"
    e = td.parse_listing(EPROCURE_HTML, SITE["eprocure"])
    assert len(e) == 3 and e[0]["source"] == "eprocure" and e[0]["org"] == "NTPC Limited / Lara STPP"
    assert e[0]["url"].startswith("https://eprocure.gov.in/eprocure/app?") and e[0]["tender_id"] == "2026_NTPC_123456_1"


def test_parse_coalindia_ntpc_and_an_empty_js_page():
    rows = td.parse_listing(COALINDIA_HTML, SITE["coalindia"])
    assert [r["tender_id"] for r in rows] == ["CIL/MCL/2026/WB/7", "CIL/HQ/2026/IT/2", "CIL/WCL/2026/CR/4"]
    assert rows[0]["org"] == "Coal India / MCL" and rows[0]["value_text"] == "Rs. 1,250 Crore" and rows[0]["due"] == "2026-11-20"
    assert rows[0]["url"] == "https://www.coalindia.in/tender/cil-mcl-2026-wb-7"
    c = [td.classify(r, floor_cr=0) for r in rows]
    assert [x["matched"] for x in c] == [True, False, True] and c[0]["value_cr"] == 1250 and c[2]["value_cr"] == 2.4
    assert [x["matched"] for x in (td.classify(r, floor_cr=5) for r in rows)] == [True, False, False]
    n = td.parse_listing(NTPC_HTML, SITE["ntpc"])
    assert [r["tender_id"] for r in n] == ["NTPC/LARA/2026/CT/11", "NTPC/SIPAT/2026/AMC/5", "NTPC/KORBA/2026/RL/2"]
    assert n[0]["org"] == "NTPC / Lara" and n[0]["url"] == "https://ntpctender.ntpc.co.in/tender.php?id=9981"
    assert n[0]["due"] == "2026-10-31" and n[2]["due"] == "2026-11-02" and n[2]["title"] == "Rake loading & wagon cleaning at Korba MGR siding"
    assert [td.classify(r, floor_cr=0)["matched"] for r in n] == [True, False, True]
    assert td.parse_listing(MSTC_HTML, SITE["mstc"]) == []            # script-only page: nothing parsed, nothing invented
    assert td.parse_listing("", SITE["mstc"]) == [] and td.parse_listing("<table><tr><td>x</td></tr>", SITE["mstc"]) == []
    # a row without any reference column gets a stable hash id from its url
    h = td.parse_listing("<table><tr><th>Work</th><th>Last date</th></tr><tr><td><a href='/t/1'>Coal washing</a></td><td>01-11-2026</td></tr></table>", SITE["ntpc"])
    assert len(h) == 1 and h[0]["tender_id"].startswith("h:") and h[0]["due"] == "2026-11-01"
    assert td.parse_listing("<table><tr><th>Work</th><th>Last date</th></tr><tr><td><a href='/t/1'>Coal washing</a></td><td>01-11-2026</td></tr></table>", SITE["ntpc"])[0]["tender_id"] == h[0]["tender_id"]


def test_push_text_and_heartbeat_line():
    rows = [{"title": f"Tender {i}", "org": "SECL", "due": f"2026-11-{10 + i:02d}", "url": f"https://x/{i}"} for i in range(12)]
    rows[0]["due"] = ""                                                  # undated goes last
    text = td.push_text(rows)
    lines = text.split("\n")
    assert lines[0] == "Tenders · 12 new:" and len(lines) == 12          # header + 10 + the "more" line
    assert lines[1] == "• Tender 1 — SECL — due 2026-11-11 — https://x/1" and lines[-1] == "… +2 more — see Morning › Tenders"
    assert "due n/a" not in text                                          # the undated one fell outside the 10
    assert td.push_text([{"title": "Coal washery O&M", "org": "", "due": "", "url": ""}]) == "Tenders · 1 new:\n• Coal washery O&M — org n/a — due n/a"
    assert td.heartbeat_line(5, 1, 5, 7, 2, {"mstc": "blocked (HTTP 403 — anti-bot/maintenance)"}, ["ntpc"]) == (
        "tenders-direct: 5 sites ok/1 failed, 5 pages, 7 matched (2 new) · mstc: blocked (HTTP 403 — anti-bot/maintenance)"
        " · 0 rows (layout?): ntpc")
    assert td.heartbeat_line(0, 0, 0, 0, 0) == "tenders-direct: 0 sites ok/0 failed, 0 pages, 0 matched (0 new)"


def test_fetch_page_never_raises(monkeypatch):
    import urllib.error
    import urllib.request

    def raise_http(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", raise_http)
    r = td.fetch_page("https://example.invalid/t")
    assert not r["ok"] and r["status"] == 403 and r["reason"] == "blocked (HTTP 403 — anti-bot/maintenance)"
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: (_ for _ in ()).throw(urllib.error.URLError("timed out")))
    r = td.fetch_page("https://example.invalid/t")
    assert not r["ok"] and r["reason"].startswith("unreachable: ")
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: (_ for _ in ()).throw(TimeoutError()))
    assert td.fetch_page("https://example.invalid/t", timeout=3)["reason"] == "timeout after 3s"


# ── endpoints + the run ──────────────────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def _wipe():
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    for t in ("tenders_direct", "tenders_direct_runs"):
        db.execute(f"DELETE FROM {t}")
    db.execute("DELETE FROM vwlr_tender_pipeline WHERE notes LIKE '[direct:%'")
    db.commit(); db.close()


class _Sent:
    def __init__(self):
        self.texts, self.ok = [], True

    def __call__(self, text, to=None, legacy_send=None):
        self.texts.append(text)
        return {"sent": self.ok} if self.ok else {"sent": False, "reason": "bridge down"}


def _setup(monkeypatch, pages=None, blocked=None):
    import mdo_server
    c = _client()
    c.get("/api/tenders/direct/stats")                 # opens the DB and creates the tables
    _wipe()
    sent = _Sent()
    monkeypatch.setitem(mdo_server._cos, "send_cos", sent)
    for k in ("TENDERS_KEYWORDS", "TENDERS_MIN_VALUE_CR", "TENDERS_SITES_OFF"):
        monkeypatch.delenv(k, raising=False)
    fetch = _fetcher(PAGES if pages is None else pages, blocked)
    monkeypatch.setattr(td, "fetch_page", fetch)
    return c, sent, fetch


def test_run_parses_every_site_pushes_once_posts_the_pipeline_and_heartbeats_zero_next_time(monkeypatch):
    c, sent, fetch = _setup(monkeypatch)
    r = c.post("/api/tenders/direct/run", json={"now": NOW.isoformat()}).json()
    assert len(fetch.calls) == 6 and r["sites_ok"] == 6 and r["sites_failed"] == 0 and r["pages"] == 6
    assert r["rows"] == 15 and r["matched"] == 10 and r["new"] == 10 and r["status"] == "clean"
    assert {k: (v["rows"], v["matched"]) for k, v in r["sites"].items()} == {
        "secl": (3, 2), "secl-etender": (3, 2), "coalindia": (3, 2), "ntpc": (3, 2), "eprocure": (3, 2), "mstc": (0, 0)}
    assert r["line"] == ("tenders-direct: 6 sites ok/0 failed, 6 pages, 10 matched (10 new) · 0 rows (layout?): mstc"
                         " · 1 message pushed · 10 → pipeline")
    # ONE message, due-date order, ≤10 lines, title — org — due — url
    assert r["pushed"] == 1 and len(sent.texts) == 1
    lines = sent.texts[0].split("\n")
    assert lines[0] == "Tenders · 10 new:" and len(lines) == 11
    assert lines[1] == "• Crushing of coal at Umrer OC, 2 years — Coal India / WCL — due 2026-10-25 — https://www.coalindia.in/tender/cil-wcl-2026-cr-4"
    assert lines[2].startswith("• Operation & maintenance of coal washery, 2.5 MTPA, Korba — SECL — due 2026-10-28 — https://www.secl-cil.in/")
    assert lines[-1].startswith("• Setting up of 10 MTPA coal beneficiation plant on BOM basis at Talcher — Coal India / MCL — due 2026-11-20 — ")
    # the pipeline got every new match through the door's body, source direct:<site>, category from the keywords
    pipe = [t for t in c.get("/api/vwlr/pipeline").json()["tenders"] if t["notes"].startswith("[direct:")]
    assert len(pipe) == 10 and r["pipeline_posted"] == 10
    by_url = {t["url"]: t for t in pipe}
    w = by_url["https://www.secl-cil.in/sites/default/files/tenders/w41.pdf"]
    assert w["buyer"] == "SECL" and w["category"] == "Coal washing" and w["due_date"] == "2026-10-28" and w["status"] == "evaluating"
    assert w["notes"] == "[direct:secl] Operation & maintenance of coal washery, 2.5 MTPA, Korba — ref SECL/GM(CMC)/2026/W/41"
    cil = by_url["https://www.coalindia.in/tender/cil-mcl-2026-wb-7"]
    assert cil["notes"].endswith(" — value Rs. 1,250 Crore · ref CIL/MCL/2026/WB/7") and cil["buyer"] == "Coal India / MCL"
    rcr = by_url["https://coalindiatenders.nic.in/nicgep/app?sp=3"]
    assert rcr["category"] == "RCR" and rcr["buyer"] == "South Eastern Coalfields Limited / Kusmunda Area"
    # Morning card: the next 30 days by due date, matched only; the later ones are outside the window
    up = c.get("/api/tenders/direct/upcoming", params={"days": 30, "now": NOW.isoformat()}).json()
    assert up["from"] == NOW.strftime("%Y-%m-%d") and up["count"] == 8
    assert [x["due"] for x in up["items"]] == ["2026-10-25", "2026-10-28", "2026-10-29", "2026-10-29", "2026-10-31", "2026-11-02", "2026-11-05", "2026-11-05"]
    assert all(x["matched"] for x in up["items"]) and up["items"][0]["keywords"] == ["crushing"] and up["undated"] == []
    assert up["state"]["new"] == 10 and up["state"]["sites"]["mstc"]["rows"] == 0 and up["keywords"][0] == "washery"
    assert up["items"][1]["pushed_at"] and up["items"][1]["pipeline_posted"] is True
    assert c.get("/api/tenders/direct/upcoming?days=60").json()["count"] == 10
    # the same pages again: nothing new, nothing pushed, the heartbeat still files
    r2 = c.post("/api/tenders/direct/run", json={"now": (NOW + timedelta(hours=12)).isoformat()}).json()
    assert r2["new"] == 0 and r2["matched"] == 10 and r2["pushed"] == 0 and len(sent.texts) == 1 and r2["text"] == ""
    assert r2["line"] == "tenders-direct: 6 sites ok/0 failed, 6 pages, 10 matched (0 new) · 0 rows (layout?): mstc"
    assert len([t for t in c.get("/api/vwlr/pipeline").json()["tenders"] if t["notes"].startswith("[direct:")]) == 10
    st = c.get("/api/tenders/direct/stats").json()
    assert st["total"] == 15 and st["matched"] == 10 and st["runs"] == 2 and st["by_source"]["secl"] == {
        "label": "SECL tenders", "url": SITE["secl"]["url"], "rows": 3, "matched": 2}
    assert st["state"]["line"] == r2["line"]
    rec = c.get("/api/tenders/direct/recent?days=7&matched=0&source=ntpc").json()
    assert rec["count"] == 1 and rec["items"][0]["title"] == "AMC of air conditioners"
    assert c.get("/api/tenders/direct/recent?source=nope").status_code == 400
    assert c.get("/api/tenders/direct/recent?days=7&matched=1").json()["count"] == 10


def test_site_failures_are_reported_per_site_and_never_crash(monkeypatch):
    blocked = {SITE["eprocure"]["url"]: {"ok": False, "status": 403, "html": "", "reason": "blocked (HTTP 403 — anti-bot/maintenance)"},
               SITE["mstc"]["url"]: {"ok": False, "status": 0, "html": "", "reason": "timeout after 25s"}}
    c, sent, fetch = _setup(monkeypatch, blocked=blocked)
    sent.ok = False
    r = c.post("/api/tenders/direct/run", json={"now": NOW.isoformat()}).json()
    assert r["sites_ok"] == 4 and r["sites_failed"] == 2 and r["pages"] == 4 and r["new"] == 8 and r["status"] == "warning"
    assert r["sites"]["eprocure"] == {"label": "CPP portal (eprocure)", "url": SITE["eprocure"]["url"], "ok": False, "status": 403,
                                      "rows": 0, "matched": 0, "new": 0, "reason": "blocked (HTTP 403 — anti-bot/maintenance)"}
    assert r["line"] == ("tenders-direct: 4 sites ok/2 failed, 4 pages, 8 matched (8 new)"
                         " · eprocure: blocked (HTTP 403 — anti-bot/maintenance) · mstc: timeout after 25s"
                         " · push NOT delivered · 8 → pipeline")
    assert r["push_failed"] == 1 and sent.texts[0].startswith("Tenders · 8 new:")
    assert c.get("/api/tenders/direct/upcoming").json()["items"][0]["pushed_at"] is None
    # a parser that blows up on one site is a per-site note, not a crash
    monkeypatch.setattr(td, "parse_listing", lambda html, site: (_ for _ in ()).throw(ValueError("boom")) if site["key"] == "secl" else [])
    r = c.post("/api/tenders/direct/run", json={"now": NOW.isoformat()}).json()
    assert r["sites"]["secl"]["reason"] == "parse error: ValueError" and r["status"] == "warning"
    # every site down → error status, the line says why
    c2, sent2, _ = _setup(monkeypatch, pages={})
    r = c2.post("/api/tenders/direct/run", json={"now": NOW.isoformat()}).json()
    assert r["status"] == "error" and r["sites_ok"] == 0 and r["sites_failed"] == 6 and sent2.texts == []
    assert r["line"].startswith("tenders-direct: 0 sites ok/6 failed, 0 pages, 0 matched (0 new) · secl: unreachable: ")


def test_keyword_and_floor_env_change_what_matches(monkeypatch):
    c, sent, _ = _setup(monkeypatch)
    monkeypatch.setenv("TENDERS_KEYWORDS", "stationery;laptops")
    monkeypatch.setenv("TENDERS_MIN_VALUE_CR", "0")
    r = c.post("/api/tenders/direct/run", json={"now": NOW.isoformat()}).json()
    assert r["matched"] == 3 and r["new"] == 3 and r["keywords"] == ["stationery", "laptops"]
    assert sorted(t["title"] for t in r["new_matched"]) == ["Supply of laptops", "Supply of stationery items", "Supply of stationery items"]
    _wipe()
    monkeypatch.delenv("TENDERS_KEYWORDS")
    monkeypatch.setenv("TENDERS_MIN_VALUE_CR", "5")
    r = c.post("/api/tenders/direct/run", json={"now": NOW.isoformat()}).json()
    # stated values below ₹5 Cr drop out (crushing 2.4 Cr, rake loading 90 L); unstated values stay
    assert r["matched"] == 8 and r["min_value_cr"] == 5.0
    assert "Crushing of coal at Umrer OC" not in sent.texts[-1] and "Rake loading" not in sent.texts[-1]
    assert "Coal transportation by road from Dipka siding to Lara STPP" in sent.texts[-1]      # 12.5 Cr


def test_run_tenders_direct_heartbeats_every_run(monkeypatch, capsys):
    c, sent, _ = _setup(monkeypatch)
    hb = []
    monkeypatch.setattr(ag, "heartbeat", lambda bot, cad, status, summary, checks=None: hb.append((bot, cad, status, summary)))

    def fake_api(path, method="GET", body=None, timeout=30):
        assert path == "/api/tenders/direct/run" and method == "POST" and timeout >= 300
        r = c.post(path, json=body)
        assert r.status_code == 200
        return r.json()
    monkeypatch.setattr(ag, "api", fake_api)
    monkeypatch.setattr(ag, "RUN_ARGS", [])
    assert ag.run_tenders_direct(BOT, "none", "daily", now=NOW) == 0
    assert hb[-1][0] == "tenders-direct" and hb[-1][2] == "clean"
    assert hb[-1][3].startswith("tenders-direct: 6 sites ok/0 failed, 6 pages, 10 matched (10 new)")
    assert ag.run_tenders_direct(BOT, "none", "daily", now=NOW + timedelta(hours=12)) == 0
    assert hb[-1][3] == "tenders-direct: 6 sites ok/0 failed, 6 pages, 10 matched (0 new) · 0 rows (layout?): mstc"
    out = capsys.readouterr().out
    assert "tenders-direct pushed: Tenders · 10 new:" in out
    assert ag.CUSTOM_BOTS["tenders-direct"] is ag.run_tenders_direct


# ── wiring: fleet.yaml, cron, .env.example, the Morning card ──────────────────
def test_fleet_cron_env_and_morning_card_wiring():
    fleet = yaml.safe_load(open(os.path.join(ROOT, "fleet.yaml"), encoding="utf-8"))
    bot = next(b for b in fleet["bots"] if b["id"] == "tenders-direct")
    assert bot["provider"] == "none" and bot["model"] == "none" and bot["enabled"] is True
    assert bot["cadence"] == "daily 06:30 IST + daily 18:30 IST"
    assert "sites ok" in bot["heartbeat"] and "matched" in bot["heartbeat"] and "blocked" in bot["heartbeat"]
    assert "tenders-washing-rcr" in bot["serves"]
    assert set(bot["serves"]) <= {o["id"] for o in yaml.safe_load(open(os.path.join(ROOT, "agenda.yaml"), encoding="utf-8"))["objectives"]}
    assert any("No LLM" in r for r in bot["charter"]["rules"]) and any("invent" in r.lower() for r in bot["charter"]["rules"])
    doc = open(os.path.join(ROOT, "DEPLOY_HOSTINGER.md"), encoding="utf-8").read()
    block = doc[doc.index("# MDO fleet — one line per bot"):]
    block = block[:block.index("```")]
    lines = [l for l in block.splitlines() if "mdo_agent.py tenders-direct" in l]
    assert len(lines) == 1 and lines[0].startswith("0  1,13 * * *")                 # 06:30 + 18:30 IST
    env = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    assert "\nTENDERS_KEYWORDS=" in env and "\nTENDERS_MIN_VALUE_CR=0\n" in env
    assert env.index("# ── Chief of Staff") < env.index("TENDERS_KEYWORDS=")        # deploy_vps.sh appends from that block
    page_path = os.path.join(ROOT, "mdo-app", "app", "morning", "page.tsx")
    if not os.path.exists(page_path):            # the backend image ships no frontend source; checked in the repo run
        return
    page = open(page_path, encoding="utf-8").read()
    assert "<TendersCard />" in page and "function TendersCard()" in page and "api.tendersDirect.upcoming(30)" in page
    assert "q.isLoading && <div" in page.split("function TendersCard()")[1]     # loading state before any table (Directive 17)
    api_ts = open(os.path.join(ROOT, "mdo-app", "lib", "api.ts"), encoding="utf-8").read()
    assert "/api/tenders/direct/upcoming?days=" in api_ts and "/api/tenders/direct/stats" in api_ts


def test_probe_shows_what_the_server_receives_and_names_a_block(monkeypatch):
    c, _, fetch = _setup(monkeypatch)
    r = c.get("/api/tenders/direct/probe", params={"site": "ntpc", "links": 5}).json()
    assert r["ok"] is True and r["url"] == "https://ntpctender.ntpc.co.in/" and r["bytes"] > 0
    assert r["tables"] and r["tables"][0]["first_rows"] and len(r["links"]) <= 5
    assert c.get("/api/tenders/direct/probe", params={"site": "nope"}).status_code == 404
    monkeypatch.setattr(td, "fetch_page", _fetcher(PAGES, {SITE["coalindia"]["url"]: {"ok": False, "status": 403, "html": "", "reason": "blocked (HTTP 403 — anti-bot/maintenance)"}}))
    r = c.get("/api/tenders/direct/probe", params={"site": "coalindia"}).json()
    assert r["ok"] is False and r["status"] == 403 and "blocked" in r["reason"]
