"""erp_sales — the Sales-first surface, fed by per-entity ERP exports.

Sales for the other entities is the majority focus, and today most of it is unfed,
so this source is built to be loud about absence:

  OWED   no export file for the entity yet -> "owed by <who>" (a real, named gap)
  MAP?   a file arrived but no column mapping exists yet -> lists the headers so a
         mapping can be written in seconds (we never guess the columns)
  LIVE   file + mapping -> totals per report (pipeline / invoiced / receivables)

One Result carries a row per entity so the whole sales picture is visible at once;
the heartbeat summary counts fed vs owed. Files land in a per-entity drop folder
(LIFEOS_ERP_DIR/<slug>/), which a Google Drive sync populates from the
"LIFEOS Sales Exports" folder — see lifeos/ingest/drive.py.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import BLOCKED, OK, Result
from ..ingest import apply_mapping, load_mapping, read_table, to_number
from ..ingest.entities import ENTITIES


def _drop_root() -> Path:
    override = os.environ.get("LIFEOS_ERP_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data" / "erp_drop"


def _mappings_dir() -> Path | None:
    override = os.environ.get("LIFEOS_MAPPINGS_DIR", "").strip()
    return Path(override) if override else None


def _entity_files(root: Path, slug: str) -> list[Path]:
    d = root / slug
    if not d.is_dir():
        return []
    files = [p for p in d.iterdir() if p.suffix.lower() in (".csv", ".xlsx", ".xlsm")]
    # newest first
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _fmt_inr(x: float) -> str:
    if x >= 1e7:
        return f"₹{x/1e7:.2f} Cr"
    if x >= 1e5:
        return f"₹{x/1e5:.2f} L"
    return f"₹{x:,.0f}"


def _entity_row(root: Path, entity) -> dict:
    files = _entity_files(root, entity.slug)
    if not files:
        return {
            "gutter": "OWED", "severity": "warning", "text": entity.label,
            "meta": f"no export yet — owed by {entity.owed_by}", "_state": "owed",
        }

    mapping = load_mapping(entity.slug, _mappings_dir())
    newest = files[0]
    if not mapping:
        table = read_table(newest)
        headers = ", ".join(table.headers[:8]) + ("…" if len(table.headers) > 8 else "")
        return {
            "gutter": "MAP?", "severity": "warning", "text": entity.label,
            "meta": f"received {newest.name} ({len(table.rows)} rows) — mapping needed; headers: {headers}",
            "_state": "mapping_needed",
        }

    # Live: total each report kind across the entity's files.
    totals: dict[str, float] = {}
    for f in files:
        table = read_table(f)
        rows = apply_mapping(table, mapping)
        field = "outstanding" if table.report == "receivables" else "amount"
        total = sum(to_number(r.get(field) or r.get("gross") or r.get("amount")) for r in rows)
        totals[table.report] = totals.get(table.report, 0.0) + total
    parts = []
    for kind in ("pipeline", "invoiced", "receivables"):
        if kind in totals:
            parts.append(f"{kind} {_fmt_inr(totals[kind])}")
    return {
        "gutter": "LIVE", "severity": "alive", "text": entity.label,
        "meta": " · ".join(parts) or "file mapped, 0 rows", "_state": "live",
    }


def fetch() -> Result:
    root = _drop_root()
    rows = [_entity_row(root, e) for e in ENTITIES]

    fed = sum(1 for r in rows if r["_state"] == "live")
    owed = sum(1 for r in rows if r["_state"] == "owed")
    mapping_needed = sum(1 for r in rows if r["_state"] == "mapping_needed")
    for r in rows:
        r.pop("_state", None)

    total = len(ENTITIES)
    bits = [f"{fed} of {total} entities fed"]
    if mapping_needed:
        bits.append(f"{mapping_needed} awaiting a column mapping")
    if owed:
        bits.append(f"{owed} still owed an export")
    summary = ". ".join(bits) + "."

    # Blocked (not OK) while nothing is fed — the majority-focus surface says so
    # plainly rather than showing an empty or fake number.
    status = OK if fed else BLOCKED
    return Result(
        name="erp_sales",
        status=status,
        summary=summary,
        data={"fed": fed, "owed": owed, "mapping_needed": mapping_needed, "total": total},
        reason="" if fed else "no ERP sales exports ingested yet",
        extra={"rows": rows},
    )
