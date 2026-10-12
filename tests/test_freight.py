"""freight — landed cost to the plant, rail vs road, BID / THIN / SKIP; saved lanes; never an invented rate."""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VEGA_DB_PATH", os.path.join(tempfile.mkdtemp(), "t.db"))

import mdo_freight as fr  # noqa: E402


def test_road_vs_rail_landed_cost_and_the_verdict():
    r = fr.landed_cost({"coal_cost_per_t": 3000, "ceiling_price_per_t": 4200, "tonnage": 10000, "modes": ["road", "rail"],
                        "road_km": 120, "road_rate_per_t_km": 3.0, "rail_rate_per_t": 450, "loading_per_t": 40, "unloading_per_t": 30, "sampling_per_t": 5,
                        "transit_loss_pct": 0.5, "gst_freight_pct": 5})
    road = next(m for m in r["modes"] if m["mode"] == "road")
    rail = next(m for m in r["modes"] if m["mode"] == "rail")
    # road: 3000 + 15 loss + 360 freight + 75 handling + 18 gst = 3468 ; rail: 3000 + 15 + 450 + 75 + 22.5 = 3562.5
    assert road["freight_per_t"] == 360.0 and road["landed_per_t"] == 3468.0
    assert rail["landed_per_t"] == 3562.5 and r["cheapest"] == "road" and r["saving_per_t"] == 94.5 and r["saving_total"] == 945000.0
    assert road["margin_per_t"] == 732.0 and road["margin_pct"] > 17 and r["verdict"].startswith("BID") and r["margin_total"] == 7320000.0


def test_skip_thin_and_gst_credit():
    skip = fr.landed_cost({"coal_cost_per_t": 3000, "ceiling_price_per_t": 3300, "modes": ["road"], "road_rate_per_t": 400})
    assert skip["verdict"].startswith("SKIP") and skip["modes"][0]["margin_per_t"] < 0
    bid = fr.landed_cost({"coal_cost_per_t": 3000, "ceiling_price_per_t": 3550, "modes": ["road"], "road_rate_per_t": 400, "min_margin_pct": 4, "gst_credit": True})
    assert bid["modes"][0]["gst_on_freight_per_t"] == 0.0 and bid["verdict"].startswith("BID")
    t2 = fr.landed_cost({"coal_cost_per_t": 3000, "ceiling_price_per_t": 3450, "modes": ["road"], "road_rate_per_t": 400, "gst_credit": True, "min_margin_pct": 4})
    assert t2["verdict"].startswith("THIN")


def test_missing_rates_are_named_never_guessed_and_illustrative_is_labelled():
    r = fr.landed_cost({"coal_cost_per_t": 3000, "ceiling_price_per_t": 4000})
    assert r["modes"] == [] and any("road_rate_per_t" in m for m in r["missing"]) and any("rail_rate_per_t" in m for m in r["missing"])
    assert "cannot compute yet" in fr.line_for(r, "KMKA to RKM")
    assert fr.landed_cost({"ceiling_price_per_t": 1})["missing"][0].startswith("coal_cost_per_t")
    ill = fr.landed_cost({"coal_cost_per_t": 3000, "ceiling_price_per_t": 4000, "road_km": 100, "illustrative": True})
    assert ill["warning"].startswith("ILLUSTRATIVE") and ill["assumptions"]["road_rate_per_t_km"] == 3.0 and "ILLUSTRATIVE" in fr.line_for(ill)


def test_rail_plus_road_adds_both_legs_and_two_unloadings_and_washing_scales_by_yield():
    r = fr.landed_cost({"coal_cost_per_t": 3000, "modes": ["rail+road"], "road_rate_per_t": 100, "rail_rate_per_t": 500, "rail_siding_per_t": 20, "unloading_per_t": 30, "gst_freight_pct": 5})
    m = r["modes"][0]
    assert m["freight_per_t"] == 620.0 and m["handling_per_t"] == 60.0 and m["landed_per_t"] == 3000 + 620 + 60 + 31
    w = fr.landed_cost({"coal_cost_per_t": 2000, "modes": ["road"], "road_rate_per_t": 0, "washing": {"yield_pct": 80, "wash_cost_per_t_feed": 100, "rejects_value_per_t_feed": 100}})
    assert w["washing"]["cost_per_t_washed"] == 2500.0 and w["modes"][0]["coal_cost_per_t"] == 2500.0
    assert fr.road_freight(10, 3.0, None, 50) == 50 and fr.road_freight(None, None, None, None) is None


def test_saved_lanes_feed_the_endpoint_and_report_their_source(monkeypatch):
    from fastapi.testclient import TestClient
    import mdo_server
    c = TestClient(mdo_server.app)
    assert c.post("/api/freight/lanes", json={"lane": "bad"}).status_code == 400
    ok = c.post("/api/freight/lanes", json={"lane": "VWLR to RKM road", "mode": "road", "rate_per_t": 180, "distance_km": 45, "source": "Ajuni Transport quote", "as_of": "2026-10-12"})
    assert ok.status_code == 200 and ok.json()["saved"]
    c.post("/api/freight/lanes", json={"lane": "KMKA to VWLR rail", "mode": "rail", "rate_per_t": 640, "source": "RR 161010491", "as_of": "2026-10-10"})
    assert {l["lane"] for l in c.get("/api/freight/lanes").json()["lanes"]} >= {"VWLR to RKM road", "KMKA to VWLR rail"}
    r = c.post("/api/freight/landed", json={"coal_cost_per_t": 3200, "ceiling_price_per_t": 4000, "road_lane": "VWLR to RKM road", "rail_lane": "KMKA to VWLR rail"}).json()
    assert {m["mode"] for m in r["modes"]} == {"road", "rail"} and any("Ajuni Transport quote" in n for n in r["lanes_used"])
    wrong = c.post("/api/freight/landed", json={"coal_cost_per_t": 3200, "modes": ["road"], "road_lane": "nope"}).json()
    assert wrong["modes"] == [] and "not a saved road lane" in wrong["lanes_used"][0]
    import sqlite3
    db = sqlite3.connect(os.environ["VEGA_DB_PATH"]); db.execute("DELETE FROM freight_lanes"); db.commit(); db.close()


def test_the_brain_has_the_freight_tools():
    import mdo_brain
    names = {t["name"] for t in mdo_brain.TOOLS}
    assert {"landed_cost", "save_freight_lane"} <= names
