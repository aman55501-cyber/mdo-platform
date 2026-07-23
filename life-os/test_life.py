"""Life OS — scope-enforcement smoke tests.

Exercises the core invariant end-to-end: the share token reaches only /life and
only shared items, filtered server-side; partner adds are forced shared; the
partner can never see or touch a private item nor flip the shared flag; the
share link is owner-only; and nudges are built only from shared items.

Run:  cd life-os && python -m pytest test_life.py -q
(requires httpx for the TestClient)
"""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient

OWNER = "test-owner-token-aaaa"
SHARE = "test-share-token-bbbb"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CFO_API_TOKEN", OWNER)
    monkeypatch.setenv("CFO_SHARE_TOKEN", SHARE)
    monkeypatch.setenv("LIFE_STATE_DIR", str(tmp_path / "state"))
    import life
    importlib.reload(life)           # pick up the fresh LIFE_STATE_DIR
    import agents
    importlib.reload(agents)
    import app as appmod
    importlib.reload(appmod)
    return TestClient(appmod.app)


def h(t):
    return {"X-Life-Token": t}


def test_auth_required(client):
    assert client.get("/life/items").status_code == 401
    assert client.get("/life/items", headers=h("nope")).status_code == 401


def test_owner_sees_all_share_sees_only_shared(client):
    priv = client.post("/life/items", headers=h(OWNER), json={"title": "private"}).json()
    shared = client.post("/life/items", headers=h(OWNER),
                         json={"title": "shared", "shared": True}).json()
    assert priv["shared"] is False and shared["shared"] is True

    owner_items = client.get("/life/items", headers=h(OWNER)).json()
    share_items = client.get("/life/items", headers=h(SHARE)).json()
    assert len(owner_items) == 2
    assert [i["id"] for i in share_items] == [shared["id"]]
    assert all(i["id"] != priv["id"] for i in share_items)  # never on the wire


def test_partner_add_is_forced_shared(client):
    r = client.post("/life/items", headers=h(SHARE),
                    json={"title": "partner", "shared": False})
    assert r.status_code == 201
    assert r.json()["shared"] is True
    assert r.json()["created_by"] == "share"


def test_partner_cannot_touch_private_item(client):
    priv = client.post("/life/items", headers=h(OWNER), json={"title": "private"}).json()
    assert client.patch(f"/life/items/{priv['id']}", headers=h(SHARE),
                        json={"done": True}).status_code == 404
    assert client.delete(f"/life/items/{priv['id']}", headers=h(SHARE)).status_code == 404


def test_partner_cannot_flip_shared_flag(client):
    shared = client.post("/life/items", headers=h(OWNER),
                        json={"title": "shared", "shared": True}).json()
    r = client.patch(f"/life/items/{shared['id']}", headers=h(SHARE),
                     json={"done": True, "shared": False})
    assert r.status_code == 200
    assert r.json()["done"] is True
    assert r.json()["shared"] is True   # flag untouched


def test_owner_flips_shared_flag(client):
    shared = client.post("/life/items", headers=h(OWNER),
                        json={"title": "s", "shared": True}).json()
    r = client.patch(f"/life/items/{shared['id']}", headers=h(OWNER), json={"shared": False})
    assert r.json()["shared"] is False
    assert all(i["id"] != shared["id"] for i in client.get("/life/items", headers=h(SHARE)).json())


def test_share_link_owner_only(client):
    sl = client.get("/life/share-link", headers=h(OWNER))
    assert sl.status_code == 200
    assert sl.json()["url"].endswith(SHARE) and "/life?t=" in sl.json()["url"]
    assert client.get("/life/share-link", headers=h(SHARE)).status_code == 403


def test_console_adapts_to_scope(client):
    gate = client.get("/life")
    assert gate.status_code == 401 and "private" in gate.text.lower()
    assert 'SCOPE = "owner"' in client.get(f"/life?t={OWNER}").text
    assert 'SCOPE = "share"' in client.get(f"/life?t={SHARE}").text


def test_nudges_only_shared(client):
    client.post("/life/items", headers=h(OWNER),
                json={"title": "private overdue", "due": "2019-01-01"})
    client.post("/life/items", headers=h(OWNER),
                json={"title": "shared overdue", "shared": True, "due": "2019-01-01"})
    nd = client.get("/life/nudges", headers=h(SHARE)).json()
    titles = [n["title"] for n in nd["nudges"]]
    assert "shared overdue" in titles
    assert "private overdue" not in titles


def test_distinct_tokens_enforced(client, monkeypatch):
    monkeypatch.setenv("CFO_SHARE_TOKEN", OWNER)  # identical -> refuse
    import life
    importlib.reload(life)
    with pytest.raises(RuntimeError):
        life._life_scope(OWNER)
