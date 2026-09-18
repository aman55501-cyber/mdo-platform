"""The proactive half of the evolving loop — draft-only nudges (brief rule 4).

After a run, LIFEOS looks at what it just saw and drafts a short to-do into the
Notion Inbox (Status=New) for each real, actionable gap: an ERP export still owed,
an entity whose file needs a mapping, a counterparty gone silent, an overdue action
awaiting Aman's click, a compliance item due soon. It never sends, signs, or
transacts — it writes an Inbox row Aman approves in one click the next morning.

De-duplicated by a stable fingerprint (db.nudges): the same underlying issue is not
re-filed within WITHIN_DAYS, so the Inbox doesn't fill with repeats every morning.
"""

from __future__ import annotations

from . import db
from .sources import Result
from .sources import notion_client as nc

INBOX_DS = "577583d5-934f-4d26-bda6-4ffb7593eb42"
WITHIN_DAYS = 3


def _by_name(results: list[Result]) -> dict[str, Result]:
    return {r.name: r for r in results}


def build_nudges(results: list[Result]) -> list[dict]:
    """Return nudge candidates {item, note, fingerprint} from a run's results."""
    named = _by_name(results)
    out: list[dict] = []

    def add(item: str, note: str, fp: str):
        out.append({"item": item, "note": note, "fingerprint": fp})

    # ERP exports owed / awaiting a mapping
    erp = named.get("erp_sales")
    if erp and not erp.unreachable and erp.extra:
        for row in erp.extra.get("rows", []):
            entity = row.get("text", "")
            if row.get("gutter") == "OWED":
                add(f"Chase ERP sales export — {entity}", row.get("meta", ""), f"erp_owed:{entity}")
            elif row.get("gutter") == "MAP?":
                add(f"Write column mapping — {entity}", row.get("meta", ""), f"erp_map:{entity}")

    # Counterparties silent > 7 working days
    cp = named.get("deal_room_counterparties")
    if cp and not cp.unreachable and cp.extra:
        for row in cp.extra.get("rows", []):
            party = row.get("text", "")
            add(f"Follow up {party} — silent {row.get('gutter','')}", row.get("meta", ""), f"silent:{party}")

    # Overdue actions still awaiting the click
    act = named.get("deal_room_actions")
    if act and not act.unreachable and act.extra:
        for row in act.extra.get("rows", []):
            if str(row.get("gutter", "")).startswith("+"):  # overdue
                step = row.get("text", "")
                add(f"Overdue, awaiting your click: {step}", row.get("meta", ""), f"overdue_action:{step}")

    # Compliance due soon (critical/warning rows only)
    comp = named.get("compliance")
    if comp and not comp.unreachable and comp.extra:
        for row in comp.extra.get("rows", []):
            if row.get("severity") in ("critical", "warning"):
                ob = row.get("text", "")
                add(f"Compliance due: {ob} — VERIFY with Vimal", row.get("meta", ""), f"compliance:{ob}")

    return out


def file_nudges(results: list[Result]) -> dict:
    """Write new nudges to the Inbox (Status=New). De-duplicated. Best-effort:
    a single failed write doesn't stop the rest. Returns a small report."""
    candidates = build_nudges(results)
    filed = 0
    skipped = 0
    for n in candidates:
        if db.nudge_filed_recently(n["fingerprint"], WITHIN_DAYS):
            skipped += 1
            continue
        props = {
            "Item": nc.title_prop(n["item"]),
            "Status": nc.select_prop("New"),
            "For": nc.select_prop("Aman"),
            "Filed to": nc.select_prop("Life OS"),
            "Note": nc.text_prop((n["note"] or "LIFEOS nudge")[:1900]),
        }
        try:
            nc.create_page(INBOX_DS, props)
            db.record_nudge(n["fingerprint"])
            filed += 1
        except Exception:  # noqa: BLE001 — one failure shouldn't stop the loop
            pass
    return {"candidates": len(candidates), "filed": filed, "skipped": skipped}
