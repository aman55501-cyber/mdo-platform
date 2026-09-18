"""Render one static HTML snapshot from a run's Results.

Phase 0 draws the spine: the heartbeat line (rule 3), a banner if the *previous*
run never finished, and every source's line in words (rule 1 — nil states are
sentences, never blank divs). The five Sales-first tabs land in Phase 3; the
:root token set, dark-mode redefinitions and phone-first shell are established
here so later phases only add panels.
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
        "date": now.strftime("%a %d %b %Y"),
        "time": now.strftime("%H:%M IST"),
        "ok": ok,
        "unreachable": unreachable,
        "total": len(results),
        "trigger": trigger,
        "started": started_at.strftime("%H:%M:%S"),
    }
    template = _env.get_template("console.html")
    return template.render(
        heartbeat=heartbeat,
        results=results,
        previous_incomplete=previous_incomplete,
        version=__version__,
    )
