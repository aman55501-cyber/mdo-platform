"""/api/today — the phone page's one JSON. Read-only aggregation; the plan buttons use the existing /api/plan endpoints."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import mdo_today as mt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_pending_table_is_parsed_from_the_real_file():
    md = open(os.path.join(ROOT, "AMAN_PENDING.md"), encoding="utf-8").read()
    rows = mt.parse_pending(md)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)) >= 10 and "A27" in ids and all(r["item"] for r in rows)
    assert mt.parse_pending("| # | Item |\n|---|---|\n| A1 | x | y | z |\nnot a row") == [{"id": "A1", "item": "x", "why": "y", "since": "z"}]
    assert mt.parse_pending("") == []


def test_today_endpoint_shape_and_plan_roundtrip(monkeypatch):
    from fastapi.testclient import TestClient
    import mdo_server
    c = TestClient(mdo_server.app)
    c.get("/api/plan/projects")
    r = c.get("/api/today")
    assert r.status_code == 200
    d = r.json()
    for k in ("as_of", "date", "reasons", "plan", "objectives", "pending", "system", "tenders", "volume", "competitors", "credits"):
        assert k in d, k
    assert "material" in d["reasons"] and any(o.startswith("• algo-trading:") for o in d["objectives"])
    assert d["pending"] and d["pending"][0]["id"].startswith("A")
    # what the phone buttons do: add an item for today, close it as done, see it counted
    before = d["plan"]["total"]
    new = c.post("/api/plan/items", json={"project": "hotel", "date": d["date"], "items": [{"item": "phone test item", "owner": "Aman"}]}).json()
    c.post(f"/api/plan/items/{new['ids'][0]}/close", json={"status": "done"})
    d2 = c.get("/api/today").json()
    assert d2["plan"]["total"] == before + 1 and d2["plan"]["done"] >= 1
    assert any(i["item"] == "phone test item" and i["status"] == "done" for i in d2["plan"]["items"])


def test_phone_app_files_exist():
    path = os.path.join(ROOT, "mdo-app", "public", "manifest.webmanifest")
    if not os.path.exists(path):          # the backend image ships no frontend source; checked in the repo run
        return
    man = open(path, encoding="utf-8").read()
    assert '"start_url": "/today"' in man and '"display": "standalone"' in man
    for sz in ("192", "512"):
        assert os.path.getsize(os.path.join(ROOT, "mdo-app", "public", "icons", f"icon-{sz}.png")) > 500


def test_notes_roundtrip_and_the_brain_has_the_tools():
    from fastapi.testclient import TestClient
    import mdo_server
    import mdo_brain
    c = TestClient(mdo_server.app)
    n = c.post("/api/notes", json={"title": "Curcumin US buyers", "body": "SupplySide Global 26-30 Oct (source: wholefoodsmagazine.com)", "tags": "curcumin,usa"}).json()
    assert n["id"] >= 1
    got = c.get("/api/notes", params={"q": "curcumin"}).json()["notes"]
    assert got and got[0]["title"] == "Curcumin US buyers" and "SupplySide" in c.get(f"/api/notes/{n['id']}").json()["body"]
    assert c.post("/api/notes", json={"title": "", "body": "x"}).status_code == 400
    names = {t["name"] for t in mdo_brain.TOOLS}
    assert {"save_note", "list_notes", "get_note"} <= names
    assert "web_search" in open(os.path.join(ROOT, "mdo_brain.py"), encoding="utf-8").read()
