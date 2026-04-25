"""Vedanta CRM bridge — read-only access to vedanta_crm.db for the VEGA bot.

Reads directly from SQLite (no SQLAlchemy dependency in VEGA).
DB path: C:/Users/Owner/Desktop/MASTER/misc/vedanta/vedanta_crm.db
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_DB_PATH = os.environ.get(
    "VEDANTA_DB_PATH",
    # Primary: inside vega/data/ (deployed + Railway)
    os.path.join(os.path.dirname(__file__), "..", "data", "vedanta_crm.db"),
)


def _conn() -> sqlite3.Connection:
    path = os.path.abspath(_DB_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Vedanta DB not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

# Public alias used by server.py for write operations
def _get_conn() -> sqlite3.Connection:
    return _conn()


# ------------------------------------------------------------------ #
#  Leads                                                               #
# ------------------------------------------------------------------ #

@dataclass
class Lead:
    id: int
    company: str
    contact_person: str
    phone: str
    location: str
    distance_km: float
    potential_volume: str
    status: str
    priority: str
    tender_score: int
    next_followup: str | None
    notes: str | None


def get_leads(priority: str | None = None, limit: int = 20) -> list[Lead]:
    """Return leads, optionally filtered by priority (High/Medium/Low)."""
    with _conn() as conn:
        if priority:
            rows = conn.execute(
                "SELECT * FROM leads WHERE priority = ? ORDER BY tender_score DESC LIMIT ?",
                (priority, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM leads ORDER BY tender_score DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_lead(r) for r in rows]


def get_lead_detail(company_partial: str) -> Lead | None:
    """Find a lead by partial company name (case-insensitive)."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE LOWER(company) LIKE ? LIMIT 1",
            (f"%{company_partial.lower()}%",),
        ).fetchone()
    return _row_to_lead(row) if row else None


def get_followups_today() -> list[Lead]:
    """Leads with next_followup = today or overdue."""
    today = datetime.now().date().isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM leads WHERE date(next_followup) <= ? ORDER BY priority DESC",
            (today,),
        ).fetchall()
    return [_row_to_lead(r) for r in rows]


def _row_to_lead(r: sqlite3.Row) -> Lead:
    return Lead(
        id=r["id"],
        company=r["company"] or "",
        contact_person=r["contact_person"] or "",
        phone=r["phone"] or "",
        location=r["location"] or "",
        distance_km=r["distance_from_vwlr"] or 0.0,
        potential_volume=r["potential_volume"] or "",
        status=r["status"] or "",
        priority=r["priority"] or "",
        tender_score=r["tender_score"] or 0,
        next_followup=str(r["next_followup"])[:10] if r["next_followup"] else None,
        notes=r["notes"],
    )


# ------------------------------------------------------------------ #
#  Competitors                                                         #
# ------------------------------------------------------------------ #

@dataclass
class Competitor:
    id: int
    name: str
    type: str
    locations: str
    pricing: str
    threat_level: str
    strengths: str
    weaknesses: str
    recent_activity: str


def get_competitors(threat_level: str | None = None, limit: int = 33) -> list[Competitor]:
    with _conn() as conn:
        if threat_level:
            rows = conn.execute(
                "SELECT * FROM competitors WHERE threat_level = ? ORDER BY name LIMIT ?",
                (threat_level.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM competitors ORDER BY "
                "CASE threat_level WHEN 'VERY HIGH' THEN 1 WHEN 'HIGH' THEN 2 "
                "WHEN 'MEDIUM' THEN 3 ELSE 4 END LIMIT ?",
                (limit,),
            ).fetchall()
    return [_row_to_competitor(r) for r in rows]


def get_competitor_detail(name_partial: str) -> Competitor | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM competitors WHERE LOWER(name) LIKE ? LIMIT 1",
            (f"%{name_partial.lower()}%",),
        ).fetchone()
    return _row_to_competitor(row) if row else None


def _row_to_competitor(r: sqlite3.Row) -> Competitor:
    return Competitor(
        id=r["id"],
        name=r["name"] or "",
        type=r["type"] or "",
        locations=r["locations"] or "",
        pricing=r["pricing"] or "",
        threat_level=r["threat_level"] or "",
        strengths=r["strengths"] or "",
        weaknesses=r["weaknesses"] or "",
        recent_activity=r["recent_activity"] or "",
    )


# ------------------------------------------------------------------ #
#  Tenders                                                             #
# ------------------------------------------------------------------ #

@dataclass
class TenderActivity:
    id: int
    buyer: str
    volume_mt: float
    route: str
    status: str
    closing_date: str | None
    our_bid: float | None
    result: str | None


def get_tenders(buyer: str | None = None, hot_only: bool = False, limit: int = 20) -> list[TenderActivity]:
    """Return tender activities. hot_only = closing within 7 days."""
    clauses = []
    params: list[Any] = []
    if buyer:
        clauses.append("LOWER(buyer) LIKE ?")
        params.append(f"%{buyer.lower()}%")
    if hot_only:
        clauses.append("date(closing_date) <= date('now', '+7 days') AND date(closing_date) >= date('now')")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM tender_activities {where} ORDER BY closing_date ASC LIMIT ?",
            params,
        ).fetchall()
    return [_row_to_tender(r) for r in rows]


def _row_to_tender(r: sqlite3.Row) -> TenderActivity:
    return TenderActivity(
        id=r["id"],
        buyer=r["buyer"] if "buyer" in r.keys() else "",
        volume_mt=r["volume_mt"] if "volume_mt" in r.keys() else 0.0,
        route=r["route"] if "route" in r.keys() else "",
        status=r["status"] if "status" in r.keys() else "",
        closing_date=str(r["closing_date"])[:10] if r["closing_date"] else None,
        our_bid=r["our_bid"] if "our_bid" in r.keys() else None,
        result=r["result"] if "result" in r.keys() else None,
    )


# ------------------------------------------------------------------ #
#  Bid optimizer (local formula — no Grok call)                        #
# ------------------------------------------------------------------ #

# FOIS rates ₹/MT by destination
_FOIS_RATES: dict[str, float] = {
    "sipat":    850.0,
    "raigarh":  120.0,
    "bhilai":  1200.0,
    "nagpur":  1400.0,
    "raipur":   300.0,
    "korba":    180.0,
    "bilaspur": 250.0,
    "bokaro":  1600.0,
    "jamshedpur": 1800.0,
}

# Typical buyer discount bands (% below our ask) based on volume
_VOLUME_DISCOUNT: list[tuple[float, float]] = [
    (0,     5_000,  0.0),
    (5_000, 20_000, 1.5),
    (20_000, 50_000, 3.0),
    (50_000, float("inf"), 4.5),
]


def calculate_bid(buyer: str, volume_mt: float, route: str, gate_price: float) -> dict:
    """Return bid recommendation dict.

    Args:
        buyer: buyer name (for discount logic)
        volume_mt: volume in metric tons
        route: destination key (e.g. 'sipat', 'bhilai')
        gate_price: current washery gate price ₹/MT
    """
    fois = _FOIS_RATES.get(route.lower(), 500.0)
    discount = 0.0
    for lo, hi, pct in _VOLUME_DISCOUNT:
        if lo <= volume_mt < hi:
            discount = pct
            break

    landed = gate_price + fois
    suggested_bid = round(landed * (1 - discount / 100), 2)
    margin_pct = round((suggested_bid - landed) / suggested_bid * 100, 1)

    return {
        "buyer": buyer,
        "volume_mt": volume_mt,
        "route": route,
        "gate_price": gate_price,
        "fois_freight": fois,
        "landed_cost": round(landed, 2),
        "volume_discount_pct": discount,
        "suggested_bid": suggested_bid,
        "margin_pct": margin_pct,
        "total_revenue": round(suggested_bid * volume_mt, 0),
        "total_margin": round((suggested_bid - landed) * volume_mt, 0),
    }
