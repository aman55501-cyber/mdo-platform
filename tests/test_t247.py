"""Tender247 Participation Insights → competitor tables (mdo_t247). Pure parsers, the mail path, and the questions asked of the data."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import mdo_mail as mm  # noqa: E402
import mdo_t247 as t2  # noqa: E402

TEXT = """Hello Vedanta Washery And Logistic Solutions Private Limited,
New Statistics
New Result | Competitors
10 | 41
Update on Yours Competitors Participation
Bidder Name | Participated Tenders | Awarded New Tenders | Lost New Tenders | Financial Stage | Technical Stage
varma manufacturer | 1 | 1 | 0 | 0 | 0
utility solution | 1 | 0 | 1 | 0 | 0
tulasi enterprises | 1 | 0 | 1 | 0 | 0
Click here to view Competitors (41)
Fresh Results
Result id | Result Brief | Department Name | Stage | Winner Bidder Name | Participants | Contract Value | City/State | Contract Date
18286986 | tender for supply of 1000 mt indonesian steam coal | punjab state co-operative supply and marketing federation limited | AOC | taranjot resources private limited | behl coal fuel private limited,
guru nanak minerals private limited,
taranjot resources private limited | 16,402 | Amritsar, Punjab | 10-10-2026
18280174 | custom bid for services - activities in coal handling plant in cpp-1 | steel authority of india limited | AOC | pritibas sahoo | raj and raj construction,
tulasi enterprises,
utility solution,
pritibas sahoo | 29.94 Lacs | Rourkela, Orissa | 05-10-2026
18042771 | supply of - briquette agrowaste_ 100001213_ rcf - | quantity - 2000 | rashtriya chemicals and fertilizers limited | AOC | varma manufacturer | chandaria industries, varma manufacturer | 46.75 Lacs | Alibagh, Maharashtra | 05-09-2026
18999999 | coal washery operation and maintenance | south eastern coalfields limited | AOC | utility solution | utility solution, tulasi enterprises | 2.5 Cr | Korba, Chhattisgarh | 01-10-2026
Click here to view all
"""


def test_value_parsing():
    assert t2.value_to_cr("29.94 Lacs") == 0.2994 and t2.value_to_cr("2.5 Cr") == 2.5
    assert abs(t2.value_to_cr("16,402") - 0.0016402) < 1e-9 and t2.value_to_cr("") is None and t2.value_to_cr("n/a") is None


def test_results_are_parsed_from_the_right_with_winner_participants_and_value():
    rows = t2.parse_results(TEXT)
    assert [r["result_id"] for r in rows] == ["18286986", "18280174", "18042771", "18999999"]
    a = rows[1]
    assert a["winner"] == "pritibas sahoo" and a["dept"] == "steel authority of india limited" and a["state"] == "Orissa" and a["city"] == "Rourkela"
    assert a["participants"] == ["pritibas sahoo", "raj and raj construction", "tulasi enterprises", "utility solution"] and a["n_participants"] == 4
    assert a["value_cr"] == 0.2994 and a["contract_date"] == "2026-10-05" and a["relevant"] == 1          # coal handling plant
    b = rows[2]
    assert b["brief"] == "supply of - briquette agrowaste_ 100001213_ rcf - quantity - 2000"               # the extra ' | ' cell stays in the brief, not the department
    assert b["dept"] == "rashtriya chemicals and fertilizers limited" and b["relevant"] == 0
    assert rows[3]["relevant"] == 1 and "washery" in rows[3]["keywords"] and rows[0]["relevant"] == 1   # 'steam coal' is coal-related
    long_list = ("18777777 | supply of hire charges of concrete mixer 0.25 to 0.40 cum, hire charges of road roller, " + "tractor with trolley, " * 12
                 + "coal tar drum, garden rake | zilla parishad | AOC | ramu dey | ramu dey, dipankar dam | 10.2 Lacs | Howrah, West Bengal | 08-10-2026")
    assert t2.parse_results("Fresh Results\n" + long_list)[0]["relevant"] == 0                          # 'coal tar' and 'rake' deep in a supply list
    comps = t2.parse_competitors(TEXT)
    assert comps[0] == {"bidder": "varma manufacturer", "participated": 1, "awarded": 1, "lost": 0, "financial": 0, "technical": 0} and len(comps) == 3
    assert t2.headline(TEXT) == {"new_results": 10, "total_competitors": 41}
    assert t2.parse_results("nothing here") == [] and t2.parse_competitors("") == []


def _client():
    from fastapi.testclient import TestClient
    import mdo_server
    return TestClient(mdo_server.app)


def test_ingest_is_idempotent_and_the_intel_answers_who_wins(monkeypatch):
    c = _client()
    c.get("/api/t247/intel")
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("DELETE FROM t247_results"); db.execute("DELETE FROM t247_competitors"); db.commit(); db.close()
    import mdo_server
    import asyncio
    r1 = asyncio.run(mdo_server._t247["ingest"](TEXT, "2026-10-11"))
    r2 = asyncio.run(mdo_server._t247["ingest"](TEXT, "2026-10-11"))
    assert r1["added"] == 4 and r1["competitors"] == 3 and len(r1["relevant_new"]) == 3 and r2["added"] == 0
    got = c.get("/api/t247/results", params={"days": 400, "relevant": 1}).json()
    assert got["count"] == 3 and got["items"][0]["winner"] in ("taranjot resources private limited", "utility solution", "pritibas sahoo")
    intel = c.get("/api/t247/intel", params={"days": 400}).json()
    assert intel["relevant_results"] == 3 and intel["avg_bidders"] == 3.0
    assert {l["winner"] for l in intel["leaders"]} == {"taranjot resources private limited", "pritibas sahoo", "utility solution"}
    assert intel["competitor_snapshot"]["day"] == "2026-10-11" and intel["competitor_snapshot"]["rows"][0]["bidder"] == "varma manufacturer"
    assert ("steel authority of india limited", 1) in [tuple(x) for x in intel["top_departments"]]


def test_mail_path_files_the_tables_not_unknown_buyer_rows(monkeypatch):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import test_mail as tm
    html = "<html><body>" + "".join(f"<p>{ln}</p>" for ln in TEXT.splitlines()[:2]) + "<table>" + "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in ln.split(" | ")) + "</tr>" for ln in TEXT.splitlines()[2:] if " | " in ln) + "</table></body></html>"
    # simpler and exact: carry the text in a <pre>-like paragraph per line so html_to_text returns the same lines
    html = "<html><body>" + "".join(f"<div>{ln}</div>" for ln in TEXT.splitlines()) + "</body></html>"
    msgs = {401: tm._eml("BidsNRFP <admin@bidsnrfp.com>", "(4) New Tender Results : Participation Insights - 11-10-2026", "open in browser",
                         html=html, when=tm.NOW - timedelta(hours=1))}
    c, sent, _, _ = tm._setup(monkeypatch, messages=msgs)
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    db.execute("DELETE FROM t247_results"); db.execute("DELETE FROM vwlr_tender_pipeline WHERE notes LIKE '[bidsnrfp]%'"); db.commit(); db.close()
    r = c.post("/api/mail/run", json={"now": tm.NOW.isoformat()}).json()
    assert r["counts"]["tender-result"] == 1 and r["tenders_posted"] == 0
    assert "Tender247 competitors: +4 results (3 coal/washery/RCR)" in r["line"]
    assert sent.texts == ["Mail: 1 Tender247 competitor-results mail with coal/washery/RCR wins — see Morning › Mail"]
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"])
    assert db.execute("SELECT COUNT(*) FROM t247_results").fetchone()[0] == 4
    assert db.execute("SELECT COUNT(*) FROM vwlr_tender_pipeline WHERE notes LIKE '[bidsnrfp]%'").fetchone()[0] == 0
    db.close()
