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
    assert len(ids) == len(set(ids)) >= 10 and "A30" in ids and "A12" not in ids and all(r["item"] for r in rows)
    assert mt.parse_pending("| # | Item |\n|---|---|\n| A1 | x | y | z |\nnot a row") == [{"id": "A1", "item": "x", "why": "y", "since": "z"}]
    assert mt.parse_pending("| A2 | WITHDRAWN by Aman | y | z |\n| A3 | ANSWERED 2026 | y | z |") == []     # closed rows are not "waiting on you"
    assert mt.parse_pending("") == []


def test_today_endpoint_shape_and_plan_roundtrip(monkeypatch):
    from fastapi.testclient import TestClient
    import mdo_server
    c = TestClient(mdo_server.app)
    c.get("/api/plan/projects")
    r = c.get("/api/today")
    assert r.status_code == 200
    d = r.json()
    for k in ("as_of", "date", "reasons", "plan", "objectives", "pending", "system", "tenders", "volume", "competitors", "credits", "logins"):
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


def test_logins_card_lists_accounts_and_the_login_link(monkeypatch):
    from fastapi.testclient import TestClient
    import mdo_server
    monkeypatch.setattr(mdo_server, "_cfo_get", lambda path, timeout=25: {"accounts": [
        {"key": "HDFC1", "label": "Aman", "broker": "hdfc", "logged_in": True, "client_code": "x"},
        {"key": "ANGEL1", "label": "Aditi", "broker": "angel", "logged_in": False, "client_code": "y"}]})
    monkeypatch.setattr(mdo_server, "CFO_TOKEN", "tok")
    d = TestClient(mdo_server.app).get("/api/today").json()["logins"]
    assert [(a["key"], a["logged_in"]) for a in d["accounts"]] == [("HDFC1", True), ("ANGEL1", False)] and "client_code" not in d["accounts"][0]
    assert d["login_url"] == "/accounts" and "tok" not in str(d) and d["error"] == ""


def test_broker_accounts_page_endpoints_never_return_or_log_a_key(monkeypatch, capsys):
    from fastapi.testclient import TestClient
    import mdo_server
    sent = {}
    monkeypatch.setattr(mdo_server, "_cfo_get", lambda path, timeout=25: {"accounts": [
        {"key": "HDFC1", "label": "Aman", "broker": "hdfc", "client_code": "C1", "logged_in": False, "needs_setup": True, "source": "env", "secret": "x"}]})

    def fake_post(path, body, timeout=40):
        sent["path"], sent["body"] = path, body
        return 200, {"connected": True, "account": body["creds_key"], "broker": "hdfc", "stored_fields": ["api_key"], "next": "Now log in."}
    monkeypatch.setattr(mdo_server, "_cfo_post", fake_post)
    monkeypatch.setattr(mdo_server, "CFO_TOKEN", "cfo-tok")
    c = TestClient(mdo_server.app)
    a = c.get("/api/broker/accounts").json()
    assert a["accounts"][0]["key"] == "HDFC1" and "secret" not in a["accounts"][0]
    r = c.post("/api/broker/accounts/add", json={"account": "hdfc2", "api_key": "KEY123", "api_secret": "SEC456", "client_code": "ZZ", "junk": "no"})
    assert r.status_code == 200 and r.json() == {"connected": True, "account": "HDFC2", "broker": "hdfc", "next": "Now log in."}
    assert sent["path"] == "/accounts/add" and sent["body"] == {"creds_key": "HDFC2", "api_key": "KEY123", "api_secret": "SEC456", "client_code": "ZZ"}
    assert "KEY123" not in r.text and "SEC456" not in r.text and "KEY123" not in capsys.readouterr().out
    assert c.post("/api/broker/accounts/add", json={"account": "ZERODHA1", "api_key": "k"}).status_code == 400
    u = c.get("/api/broker/hdfc-login-url?key=HDFC2").json()["url"]
    assert u.endswith("/hdfc/login?key=HDFC2&token=cfo-tok") and c.get("/api/broker/hdfc-login-url?key=ANGEL1").status_code == 400
    monkeypatch.setattr(mdo_server, "_cfo_post", lambda *a, **k: (400, {"detail": "HDFC needs both API key and API secret."}))
    bad = c.post("/api/broker/accounts/add", json={"account": "HDFC3", "api_key": "k"})
    assert bad.status_code == 400 and "HDFC needs both" in bad.text


def test_accounts_page_files_exist():
    p = os.path.join(ROOT, "mdo-app", "app", "accounts", "page.tsx")
    if not os.path.exists(p):                      # the backend image ships no frontend; checked in the repo run
        return
    src = open(p, encoding="utf-8").read()
    assert 'type={f.secret ? "password" : "text"}' in src and "aria-label" in src and "Cowork" in src
    assert "/api/broker/accounts/add" in src and "setVals({})" in src                 # the keys are cleared after sending


def test_hdfc_login_without_keys_is_a_clear_message_not_a_500():
    import inspect
    from shares_cfo import server
    src = inspect.getsource(server.hdfc_login)
    assert "_ConfigError" in src and "409" in src
