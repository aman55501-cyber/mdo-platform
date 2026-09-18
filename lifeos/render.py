"""Render one static HTML snapshot from a run's Results.

Groups sources into Sales-first tabs (Home · Sales · Operations · Growth), computes
the Home number tiles and the single most-urgent item, and draws the heartbeat and
the "previous run did not complete" banner. Nil/blocked/unreachable states are all
rendered in words (rules 1-3). The token set, dark-mode redefinitions and phone-first
shell live in templates/console.html.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import __version__
from .config import IST
from .sources import Result

_TEMPLATES = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)

# Which tab each source renders on. A source missing here falls into Operations.
TAB_OF = {
    "deal_room_actions": "home", "calendar": "home", "family": "home",
    "erp_sales": "sales", "tenders": "sales", "hotel_ans_pms": "sales",
    "deal_room_counterparties": "operations", "compliance": "operations",
    "mail": "operations", "task_health": "operations",
    "rnd": "growth", "hiring": "growth", "expansion": "growth", "usa": "growth",
}
TABS = [("home", "Home"), ("sales", "Sales"), ("operations", "Operations"), ("growth", "Growth")]

_SEV_RANK = {"critical": 3, "warning": 2, "alive": 1, "quiet": 0}


def _by_name(results: list[Result]) -> dict[str, Result]:
    return {r.name: r for r in results}


def _tile(results: dict, name: str, key: str, label: str, *, critical_if_gt0=False) -> dict:
    r = results.get(name)
    if r is None or r.unreachable or not isinstance(r.data, dict) or key not in r.data:
        return {"value": "—", "label": label, "severity": "quiet", "note": "unreachable" if (r and r.unreachable) else "no data"}
    value = r.data.get(key, 0)
    sev = "quiet"
    if isinstance(value, (int, float)) and value > 0:
        sev = "warning" if critical_if_gt0 else "quiet"
        if critical_if_gt0:
            sev = "critical"
    return {"value": value, "label": label, "severity": sev, "note": ""}


def _home_tiles(results: dict) -> list[dict]:
    return [
        _tile(results, "deal_room_actions", "awaiting", "Clicks awaiting you", critical_if_gt0=True),
        _tile(results, "compliance", "due_21", "Compliance ≤21d", critical_if_gt0=True),
        _tile(results, "erp_sales", "owed", "Entities owed export"),
        _tile(results, "tenders", "live", "Tenders live"),
    ]


def _most_urgent(results: dict) -> dict | None:
    """The single most urgent actionable row across actions and compliance."""
    candidates: list[tuple[int, dict, str]] = []
    for name, source_label in (("deal_room_actions", "Deal Room"), ("compliance", "Compliance")):
        r = results.get(name)
        if r and not r.unreachable and r.extra and r.extra.get("rows"):
            row = r.extra["rows"][0]
            candidates.append((_SEV_RANK.get(row.get("severity", "quiet"), 0), row, source_label))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    rank, row, source_label = candidates[0]
    if rank == 0:  # nothing actually urgent
        return None
    return {"gutter": row.get("gutter", ""), "severity": row.get("severity", "quiet"),
            "text": row.get("text", ""), "meta": row.get("meta", ""), "source": source_label}


def render_console(
    results: list[Result],
    *,
    started_at: datetime,
    previous_incomplete: bool,
    trigger: str,
) -> str:
    ok = sum(1 for r in results if r.healthy)
    unreachable = sum(1 for r in results if r.unreachable)
    now = datetime.now(IST)
    heartbeat = {
        "date": now.strftime("%a %d %b %Y"), "time": now.strftime("%H:%M IST"),
        "ok": ok, "unreachable": unreachable, "total": len(results),
        "trigger": trigger, "started": started_at.strftime("%H:%M:%S"),
    }

    named = _by_name(results)
    # panels per tab, preserving the run's source order within each tab
    tab_panels: dict[str, list[Result]] = {tid: [] for tid, _ in TABS}
    for r in results:
        tab_panels.get(TAB_OF.get(r.name, "operations"), tab_panels["operations"]).append(r)
    tabs = [{"id": tid, "label": label, "panels": tab_panels[tid]} for tid, label in TABS]

    template = _env.get_template("console.html")
    return template.render(
        heartbeat=heartbeat,
        tabs=tabs,
        tiles=_home_tiles(named),
        urgent=_most_urgent(named),
        previous_incomplete=previous_incomplete,
        version=__version__,
    )
