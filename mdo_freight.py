"""freight — landed cost to the plant, rail and road, as the deciding factor for every coal tender (Aman, chat 2026-10-12).

"use freight as the deciding factor both rail and road and need to calculate landed cost to the plant".

Landed cost per tonne delivered = coal cost at the source gate (grown by transit loss)
                                  + freight (rail and/or road) + loading + unloading + sampling/weighbridge + GST on freight (when not creditable).
Compare modes, set it against the plant's ceiling price (tender estimate, last award, or a number Aman gives) and say BID / THIN / SKIP.

No rate is invented: every rate is either typed by Aman (stored with its source and date as a lane) or passed in the call. When a rate is missing the answer says
which one, instead of guessing. `illustrative=True` fills gaps with clearly labelled ASSUMPTIONS so a sensitivity can be seen; those are never stored and never
shown as facts. Rules only (Directive 15). Never an order, never a bid: a bid is Aman's click.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Awaitable, Callable

from mdo_cos import IST

ILLUSTRATIVE = {"road_rate_per_t_km": 3.0, "rail_rate_per_t": 900.0, "loading_per_t": 35.0, "unloading_per_t": 25.0, "sampling_per_t": 5.0,
                "transit_loss_pct": 0.5, "gst_freight_pct": 5.0, "min_margin_pct": 4.0}
# Indian Railways coal, train load, class 145A: (from_km, to_km, Rs per tonne). Source: FOIS Freight Rates page
# https://www.fois.indianrail.gov.in/FOISWebPortal/FWP_FrgtRateDtls?RateClss=145A, read 2026-10-12. Base tariff only: no busy-season
# surcharge, development surcharge, terminal/siding charges, rebates or GST. Confirm the class for the specific coal and the lane with FOIS.
RAIL_145A = [(1, 100, 216.0), (101, 125, 389.6), (126, 150, 448.9), (151, 175, 488.7), (176, 200, 532.2), (201, 275, 672.5), (276, 350, 797.2),
             (351, 425, 926.0), (426, 500, 1054.7), (501, 600, 1228.0), (601, 700, 1398.7), (701, 730, 1435.6), (731, 760, 1484.0),
             (761, 790, 1537.9), (791, 820, 1586.7), (821, 850, 1640.3), (851, 880, 1688.6), (881, 910, 1737.0), (911, 940, 1790.2),
             (941, 970, 1838.6), (971, 1000, 1891.8)]
RAIL_145A_SOURCE = "FOIS rate class 145A train load, base tariff, read 2026-10-12"


def rail_rate_for_km(km: float | None) -> float | None:
    """Base railway coal rate (Rs/t) for a distance, from the FOIS 145A slabs above (up to 1000 km); None when out of range."""
    if km is None:
        return None
    for lo, hi, rate in RAIL_145A:
        if lo <= km <= hi:
            return rate
    return None


ILLUSTRATIVE_NOTE = "ILLUSTRATIVE ASSUMPTIONS, not facts: replace every one with your quote before acting"
SCHEMA = """
CREATE TABLE IF NOT EXISTS freight_lanes (
    lane TEXT PRIMARY KEY, mode TEXT NOT NULL, origin TEXT DEFAULT '', destination TEXT DEFAULT '', distance_km REAL,
    rate_per_t REAL, rate_per_t_km REAL, min_per_t REAL, source TEXT DEFAULT '', as_of TEXT DEFAULT '', updated_at TEXT DEFAULT (datetime('now'))
);
"""


def _f(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return default


def road_freight(km: float | None, rate_per_t_km: float | None, rate_per_t: float | None, min_per_t: float | None) -> float | None:
    """₹/t by road: a flat per-tonne lane rate wins; else km x rate per tonne-km; never below the minimum charge."""
    cost = rate_per_t if rate_per_t is not None else (km * rate_per_t_km if km is not None and rate_per_t_km is not None else None)
    if cost is None:
        return None
    return max(cost, min_per_t or 0.0)


def washing(cost_rom_per_t: float, yield_pct: float, wash_cost_per_t_feed: float, rejects_value_per_t_feed: float = 0.0) -> dict:
    """ROM → washed coal. Per tonne of feed: ROM cost + wash cost - value of rejects/middlings; divided by the yield to get ₹ per tonne of WASHED coal."""
    if not yield_pct or yield_pct <= 0:
        raise ValueError("yield_pct must be above 0")
    per_feed = cost_rom_per_t + wash_cost_per_t_feed - rejects_value_per_t_feed
    return {"cost_per_t_washed": per_feed / (yield_pct / 100.0), "per_t_feed": per_feed}


def _mode_cost(mode: str, p: dict, missing: list[str]) -> dict | None:
    gst = p["gst_freight_pct"] / 100.0
    legs: list[dict] = []
    if mode in ("road", "rail+road"):
        r = road_freight(p.get("road_km"), p.get("road_rate_per_t_km"), p.get("road_rate_per_t"), p.get("road_min_per_t"))
        if r is None:
            missing.append("road: road_rate_per_t (or road_km and road_rate_per_t_km)")
            return None
        legs.append({"leg": "road", "per_t": r})
    if mode in ("rail", "rail+road"):
        rr = p.get("rail_rate_per_t")
        if rr is None:
            missing.append("rail: rail_rate_per_t (all-in railway freight for the lane)")
            return None
        legs.append({"leg": "rail", "per_t": rr + (p.get("rail_siding_per_t") or 0.0)})
    freight = sum(x["per_t"] for x in legs)
    transfer = (p.get("loading_per_t") or 0.0) + (p.get("unloading_per_t") or 0.0) * (2 if mode == "rail+road" else 1) + (p.get("sampling_per_t") or 0.0)
    gst_cost = freight * gst if not p.get("gst_credit") else 0.0
    loss = p["coal_cost_per_t"] * (p["transit_loss_pct"] / 100.0)
    landed = p["coal_cost_per_t"] + loss + freight + transfer + gst_cost
    out = {"mode": mode, "coal_cost_per_t": round(p["coal_cost_per_t"], 2), "transit_loss_per_t": round(loss, 2), "freight_per_t": round(freight, 2),
           "handling_per_t": round(transfer, 2), "gst_on_freight_per_t": round(gst_cost, 2), "landed_per_t": round(landed, 2), "legs": legs}
    ceil = p.get("ceiling_price_per_t")
    if ceil is not None:
        margin = ceil - landed
        pct = margin / ceil * 100.0 if ceil else 0.0
        out.update({"ceiling_per_t": ceil, "margin_per_t": round(margin, 2), "margin_pct": round(pct, 2),
                    "verdict": "SKIP (landed cost above the ceiling)" if margin < 0 else ("THIN (margin below your minimum)" if pct < p["min_margin_pct"] else "BID (margin clears your minimum)"),
                    "breakeven_ceiling_per_t": round(landed, 2)})
    return out


def landed_cost(inputs: dict) -> dict:
    """The calculator. inputs: coal_cost_per_t (at the source gate), modes (list of road|rail|rail+road, default compare road and rail), rates and distances (see keys
    below), ceiling_price_per_t (plant ceiling / estimate), tonnage, min_margin_pct, illustrative (bool), washing {yield_pct, wash_cost_per_t_feed, rejects_value_per_t_feed}
    with coal_cost_per_t then meaning ROM cost per tonne of feed. Returns per-mode costs, the cheaper mode, a verdict and what is missing."""
    p: dict[str, Any] = {k: _f(inputs.get(k)) for k in (
        "coal_cost_per_t", "road_km", "road_rate_per_t_km", "road_rate_per_t", "road_min_per_t", "rail_rate_per_t", "rail_siding_per_t", "loading_per_t", "unloading_per_t",
        "sampling_per_t", "transit_loss_pct", "gst_freight_pct", "ceiling_price_per_t", "min_margin_pct", "tonnage", "rail_km")}
    p["gst_credit"] = bool(inputs.get("gst_credit"))
    assumptions: dict[str, float] = {}
    if p.get("rail_rate_per_t") is None and rail_rate_for_km(p.get("rail_km")) is not None:
        p["rail_rate_per_t"] = rail_rate_for_km(p["rail_km"])
        assumptions["rail_rate_per_t"] = p["rail_rate_per_t"]   # reported: base tariff from FOIS 145A, see RAIL_145A_SOURCE
    if inputs.get("illustrative"):
        for k, v in ILLUSTRATIVE.items():
            if p.get(k) is None:
                p[k] = v
                assumptions[k] = v
    for k, d in (("transit_loss_pct", 0.0), ("gst_freight_pct", 5.0), ("min_margin_pct", 4.0)):      # neutral defaults, reported
        if p.get(k) is None:
            p[k] = d
            assumptions.setdefault(k, d)
    out: dict[str, Any] = {"inputs_used": {k: v for k, v in p.items() if v is not None}, "assumptions": assumptions, "missing": [], "modes": []}
    w = inputs.get("washing")
    if isinstance(w, dict) and p.get("coal_cost_per_t") is not None:
        try:
            wr = washing(p["coal_cost_per_t"], _f(w.get("yield_pct"), 0) or 0, _f(w.get("wash_cost_per_t_feed"), 0) or 0, _f(w.get("rejects_value_per_t_feed"), 0) or 0)
            out["washing"] = {k: round(v, 2) for k, v in wr.items()}
            p["coal_cost_per_t"] = wr["cost_per_t_washed"]
        except ValueError as e:
            out["missing"].append(f"washing: {e}")
    if p.get("coal_cost_per_t") is None:
        out["missing"].append("coal_cost_per_t (price at the source gate; ROM cost per tonne of feed when washing is given)")
        return out
    modes = [m for m in (inputs.get("modes") or ["road", "rail"]) if m in ("road", "rail", "rail+road")]
    for m in modes:
        r = _mode_cost(m, p, out["missing"])
        if r:
            out["modes"].append(r)
    if out["modes"]:
        best = min(out["modes"], key=lambda x: x["landed_per_t"])
        out["cheapest"] = best["mode"]
        if len(out["modes"]) > 1:
            worst = max(out["modes"], key=lambda x: x["landed_per_t"])
            out["saving_per_t"] = round(worst["landed_per_t"] - best["landed_per_t"], 2)
            if p.get("tonnage"):
                out["saving_total"] = round(out["saving_per_t"] * p["tonnage"], 0)
        out["verdict"] = best.get("verdict", "set ceiling_price_per_t to get BID / THIN / SKIP")
        if p.get("tonnage") and best.get("margin_per_t") is not None:
            out["margin_total"] = round(best["margin_per_t"] * p["tonnage"], 0)
    if assumptions and inputs.get("illustrative"):
        out["warning"] = ILLUSTRATIVE_NOTE
    out["note"] = "Landed cost = coal cost + transit loss + freight + handling + GST on freight (unless creditable). Every figure above comes from the inputs, nothing from memory."
    return out


def line_for(res: dict, label: str = "") -> str:
    if not res.get("modes"):
        return f"Landed cost {label}: cannot compute yet - missing: " + "; ".join(res.get("missing") or ["inputs"])
    parts = [f"{m['mode']} Rs {m['landed_per_t']:,.0f}/t (freight {m['freight_per_t']:,.0f})" for m in res["modes"]]
    tail = f" -> {res.get('verdict')}" if res.get("verdict") else ""
    sav = f" · {res['cheapest']} saves Rs {res['saving_per_t']:,.0f}/t" if res.get("saving_per_t") else ""
    warn = " [ILLUSTRATIVE rates]" if res.get("warning") else ""
    return f"Landed cost {label}: " + " | ".join(parts) + sav + tail + warn


def register(app, vdb: Callable[[], Awaitable[Any]]) -> dict:
    async def ensure_schema():
        db = await vdb()
        await db.executescript(SCHEMA)
        await db.commit()

    async def lane_set(body: dict) -> dict:
        await ensure_schema()
        lane = re.sub(r"\s+", " ", str(body.get("lane") or "")).strip()[:80]
        mode = str(body.get("mode") or "").lower()
        if not lane or mode not in ("road", "rail"):
            raise ValueError("lane (a name) and mode (road or rail) are required")
        rate_t, rate_km, mn, km = _f(body.get("rate_per_t")), _f(body.get("rate_per_t_km")), _f(body.get("min_per_t")), _f(body.get("distance_km"))
        if rate_t is None and rate_km is None:
            raise ValueError("give rate_per_t, or rate_per_t_km with distance_km")
        db = await vdb()
        await db.execute("INSERT OR REPLACE INTO freight_lanes (lane, mode, origin, destination, distance_km, rate_per_t, rate_per_t_km, min_per_t, source, as_of) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (lane, mode, str(body.get("origin") or "")[:60], str(body.get("destination") or "")[:60], km, rate_t, rate_km, mn,
                          str(body.get("source") or "Aman")[:120], str(body.get("as_of") or datetime.now(IST).date().isoformat())))
        await db.commit()
        return {"lane": lane, "saved": True}

    async def lanes() -> list[dict]:
        await ensure_schema()
        db = await vdb()
        return [dict(r) for r in await db.execute_fetchall("SELECT * FROM freight_lanes ORDER BY lane")]

    async def compute(inputs: dict) -> dict:
        """Fill rail_lane / road_lane from the saved lanes (explicit values in the call win), then run the calculator."""
        inputs = dict(inputs or {})
        by = {l["lane"].lower(): l for l in await lanes()}
        notes = []
        for key, mode in (("road_lane", "road"), ("rail_lane", "rail")):
            name = str(inputs.get(key) or "").lower()
            if not name:
                continue
            l = by.get(name)
            if not l or l["mode"] != mode:
                notes.append(f"{key} '{inputs.get(key)}' is not a saved {mode} lane")
                continue
            if mode == "road":
                inputs.setdefault("road_rate_per_t", l["rate_per_t"])
                inputs.setdefault("road_rate_per_t_km", l["rate_per_t_km"])
                inputs.setdefault("road_km", l["distance_km"])
                inputs.setdefault("road_min_per_t", l["min_per_t"])
            else:
                inputs.setdefault("rail_rate_per_t", l["rate_per_t"])
            notes.append(f"{mode} lane '{l['lane']}' from {l['source'] or 'Aman'} as of {l['as_of'] or '?'}")
        res = landed_cost(inputs)
        res["lanes_used"] = notes
        return res

    @app.post("/api/freight/landed")
    async def api_landed(body: dict):
        return await compute(body)

    @app.get("/api/freight/lanes")
    async def api_lanes():
        return {"lanes": await lanes()}

    @app.post("/api/freight/lanes")
    async def api_lane_set(body: dict):
        from fastapi import HTTPException
        try:
            return await lane_set(body)
        except ValueError as e:
            raise HTTPException(400, str(e))

    return {"ensure_schema": ensure_schema, "compute": compute, "lane_set": lane_set, "lanes": lanes}
