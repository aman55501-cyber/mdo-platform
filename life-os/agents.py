"""Life OS agents — lifted out of handoff/business-os/agents.py.

Only `_life_agent` belongs to this project; the trading/business agents stayed
behind in the console it was extracted from. This agent reads the SHARED slice
of the store (never private items) and surfaces due / overdue items as nudges
for phone alerts and the morning digest, so the home board doesn't slip either.

Reconstructed from the DESIGN_EXPORT handoff: the original agents.py was not
carried across. It reuses the same scoped store as the API, so it can never
build a nudge out of a private item.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional

from life import LifeScope, _visible, _load


@dataclass(frozen=True)
class Nudge:
    item_id: str
    kind: str
    title: str
    due: str
    status: str          # "overdue" | "due_today" | "due_soon"
    amount: Optional[float] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "title": self.title,
            "due": self.due,
            "status": self.status,
            "amount": self.amount,
        }


def _parse_due(raw: Any) -> Optional[date]:
    """Accept an ISO date or datetime; return a date, or None if unparseable."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _classify(due: date, today: date, soon_days: int) -> Optional[str]:
    delta = (due - today).days
    if delta < 0:
        return "overdue"
    if delta == 0:
        return "due_today"
    if delta <= soon_days:
        return "due_soon"
    return None


def _life_agent(today: Optional[date] = None, *, soon_days: int = 2) -> dict[str, Any]:
    """Scan SHARED, not-done items for anything due / overdue and return a
    digest. `today` is injectable for testing. Operates strictly on the share
    scope's visible set, so private items are structurally excluded.
    """
    today = today or datetime.now(timezone.utc).date()
    # Reuse the same server-side filter the API uses — shared items only.
    shared = _visible(_load(), LifeScope("share"))

    nudges: list[Nudge] = []
    for it in shared:
        if it.get("done"):
            continue
        due = _parse_due(it.get("due"))
        if due is None:
            continue
        status = _classify(due, today, soon_days)
        if status is None:
            continue
        nudges.append(Nudge(
            item_id=it["id"],
            kind=it.get("kind", "task"),
            title=it.get("title", ""),
            due=it["due"],
            status=status,
            amount=it.get("amount"),
        ))

    order = {"overdue": 0, "due_today": 1, "due_soon": 2}
    nudges.sort(key=lambda n: (order[n.status], n.due))

    overdue = [n for n in nudges if n.status == "overdue"]
    due_today = [n for n in nudges if n.status == "due_today"]
    due_soon = [n for n in nudges if n.status == "due_soon"]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {
            "overdue": len(overdue),
            "due_today": len(due_today),
            "due_soon": len(due_soon),
        },
        "nudges": [n.as_dict() for n in nudges],
        "digest_line": _digest_line(len(overdue), len(due_today), len(due_soon)),
    }


def _digest_line(overdue: int, due_today: int, due_soon: int) -> str:
    """One-line summary for the morning digest / a phone alert."""
    if not (overdue or due_today or due_soon):
        return "Home board is clear — nothing shared is due."
    bits = []
    if overdue:
        bits.append(f"{overdue} overdue")
    if due_today:
        bits.append(f"{due_today} due today")
    if due_soon:
        bits.append(f"{due_soon} due soon")
    return "Shared: " + ", ".join(bits) + "."
