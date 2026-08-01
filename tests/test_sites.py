"""Site access over the VPN sidecars — the accuracy and safety rules.

The point of this layer is accurate site data, so the tests are mostly about the ways
it must refuse to be inaccurate: no invented sources, no writes, no silent substitution
when a path is missing, and a dead tunnel surfacing as a finding rather than a gap.

Runs under pytest OR standalone: `python tests/test_sites.py`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite

import mdo_feed
import mdo_sites


def run(coro):
    return asyncio.run(coro)


def _clear():
    for k in ("MDO_SITE_SOURCES", "MDO_SITE_SOURCES_FILE", "HOTEL_PROXY_URL",
              "VEDANTA_PROXY_URL", "HOTEL_PROBE_URL", "VEDANTA_PROBE_URL"):
        os.environ.pop(k, None)
    mdo_feed.clear_actions()


# --- no invented facts -----------------------------------------------------------

def test_no_sources_configured_says_so():
    """With nothing configured it must report a gap, not guess a hostname."""
    _clear()
    out = mdo_sites.read_site("hotel")
    assert out["configured"] is False
    assert out["readings"] == []
    assert "no sources configured" in out["note"]


def test_sources_come_from_env():
    _clear()
    os.environ["MDO_SITE_SOURCES"] = json.dumps([
        {"site": "hotel", "key": "occupancy", "url": "http://10.0.0.5/api/occupancy"},
        {"site": "vedanta", "key": "tally", "url": "http://10.1.0.5/api/tally"},
    ])
    assert len(mdo_sites.sources_for("hotel")) == 1
    assert len(mdo_sites.sources_for("vedanta")) == 1
    assert mdo_sites.sources_for("hotel")[0]["key"] == "occupancy"
    _clear()


def test_malformed_source_config_is_ignored_not_crashed():
    _clear()
    os.environ["MDO_SITE_SOURCES"] = "{not json"
    assert mdo_sites.load_sources() == []
    _clear()


# --- read-only ------------------------------------------------------------------

def test_writes_are_blocked():
    """v1 is read-only against site systems by standing decision."""
    _clear()
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        out = mdo_sites.fetch_through("hotel", "http://10.0.0.5/x", method=method)
        assert out["ok"] is False
        assert "read-only" in out["error"]
    assert mdo_sites.SAFE_METHODS == ("GET",)


def test_unknown_site_is_refused():
    _clear()
    out = mdo_sites.fetch_through("nowhere", "http://10.0.0.5/x")
    assert out["ok"] is False
    assert "unknown site" in out["error"]


# --- proxy wiring ---------------------------------------------------------------

def test_proxy_urls_default_to_the_sidecars():
    _clear()
    assert mdo_sites.proxy_url("hotel") == "http://vpn-hotel:8888"
    assert mdo_sites.proxy_url("vedanta") == "http://vpn-vedanta:8888"


def test_proxy_url_is_overridable_by_env():
    _clear()
    os.environ["HOTEL_PROXY_URL"] = "http://somewhere-else:9999"
    assert mdo_sites.proxy_url("hotel") == "http://somewhere-else:9999"
    _clear()


def test_unreachable_site_reports_the_failure():
    """A failed read must be an explicit error, never an empty success."""
    _clear()
    os.environ["HOTEL_PROXY_URL"] = "http://127.0.0.1:1"  # nothing listening
    out = mdo_sites.fetch_through("hotel", "http://10.0.0.5/api/x", timeout=2)
    assert out["ok"] is False
    assert out["reachable"] is False
    assert "error" in out and out["error"]
    assert "json" not in out and "text" not in out, "no data may be implied on failure"
    _clear()


# --- extraction never substitutes -------------------------------------------------

def test_dig_walks_dicts_and_lists():
    data = {"rooms": {"stats": [{"occupied": 41}]}}
    assert mdo_sites._dig(data, "rooms.stats.0.occupied") == 41


def test_dig_returns_none_for_missing_path():
    assert mdo_sites._dig({"a": 1}, "a.b.c") is None
    assert mdo_sites._dig({"a": 1}, "zzz") is None


def test_missing_json_path_is_an_error_not_a_default():
    """The failure mode that matters: a moved field must not read as zero."""
    _clear()

    captured = {}

    def fake_fetch(site, url, method="GET", timeout=None):
        captured["url"] = url
        return {"ok": True, "status": 200, "site": site, "url": url,
                "json": {"rooms": {"sold": 41}}, "fetched_at": "2026-08-01T10:00:00+05:30"}

    real = mdo_sites.fetch_through
    mdo_sites.fetch_through = fake_fetch
    try:
        out = mdo_sites.read_source({"site": "hotel", "key": "occ",
                                     "url": "http://10.0.0.5/x",
                                     "json_path": "rooms.occupied"})
        assert out["ok"] is False
        assert "not present" in out["error"]
        assert out["value"] is None
    finally:
        mdo_sites.fetch_through = real
    _clear()


def test_present_json_path_is_extracted_with_provenance():
    _clear()

    def fake_fetch(site, url, method="GET", timeout=None):
        return {"ok": True, "status": 200, "site": site, "url": url,
                "json": {"rooms": {"occupied": 41}},
                "fetched_at": "2026-08-01T10:00:00+05:30", "via": "http://vpn-hotel:8888"}

    real = mdo_sites.fetch_through
    mdo_sites.fetch_through = fake_fetch
    try:
        out = mdo_sites.read_source({"site": "hotel", "key": "occ", "label": "Rooms sold",
                                     "url": "http://10.0.0.5/x",
                                     "json_path": "rooms.occupied"})
        assert out["ok"] is True
        assert out["value"] == 41
        # Provenance travels with the number.
        assert out["fetched_at"] and out["via"] and out["site"] == "hotel"
    finally:
        mdo_sites.fetch_through = real
    _clear()


# --- tunnel health → the feed -----------------------------------------------------

def test_tunnel_status_reports_down_when_proxy_dead():
    _clear()
    os.environ["VEDANTA_PROXY_URL"] = "http://127.0.0.1:1"
    st = mdo_sites.tunnel_status("vedanta")
    assert st["up"] is False
    assert "unreachable" in st["detail"]
    _clear()


def test_dead_tunnel_publishes_a_critical_finding():
    """Site data going missing is itself the alert — a dashboard that quietly
    drops a feed is worse than one that says it lost it."""
    _clear()
    os.environ["VEDANTA_PROXY_URL"] = "http://127.0.0.1:1"
    os.environ["MDO_SITE_SOURCES"] = json.dumps(
        [{"site": "vedanta", "key": "tally", "url": "http://10.1.0.5/api/tally"}])

    async def go():
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await mdo_feed.ensure_schema(db)
        published = await mdo_sites.publish_tunnel_alerts(db, mdo_feed)
        assert len(published) == 1
        item = published[0]
        assert item["severity"] == "critical"
        assert item["domain"] == "vwlr"
        assert "site link is down" in item["title"]
        assert item["evidence"], "the finding must carry what it was based on"
        await db.close()

    run(go())
    _clear()


def test_tunnel_with_no_configured_sources_is_not_alerted_on():
    """A tunnel nothing reads through is not yet load-bearing — don't cry wolf."""
    _clear()
    os.environ["HOTEL_PROXY_URL"] = "http://127.0.0.1:1"
    os.environ["VEDANTA_PROXY_URL"] = "http://127.0.0.1:1"

    async def go():
        db = await aiosqlite.connect(":memory:")
        db.row_factory = aiosqlite.Row
        await mdo_feed.ensure_schema(db)
        published = await mdo_sites.publish_tunnel_alerts(db, mdo_feed)
        assert published == []
        await db.close()

    run(go())
    _clear()


def test_both_sites_are_defined():
    assert set(mdo_sites.SITES) == {"hotel", "vedanta"}
    assert mdo_sites.SITES["hotel"]["domain"] == "hotel"
    assert mdo_sites.SITES["vedanta"]["domain"] == "vwlr"


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
                print(f"  ok   {name}")
            except Exception as e:
                failed += 1
                print(f"  FAIL {name}: {type(e).__name__}: {e}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
