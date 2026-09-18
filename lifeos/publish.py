"""Publish the run to Notion — the console's second home (brief rule 3).

  Today page          rewritten each run with the heartbeat + headline lines, so the
                      console exists in Notion too and neither copy can die quietly.
  Daily Briefs Archive one appended line per run.

Both are best-effort and fault-isolated: if NOTION_TOKEN is absent or a write fails,
publish returns a status string and the run continues (it never blocks publishing the
HTML snapshot). These are the only page writes LIFEOS makes; they don't transact.
"""

from __future__ import annotations

from datetime import datetime

from .config import IST
from .sources import Result
from .sources import notion_client as nc

TODAY_PAGE = "3c4f1a9b6dc281778879c7bfe2a3fbc0"
ARCHIVE_PAGE = "354f1a9b6dc281f98ccfca01c93066ab"


def _brief_lines(results: list[Result], ok: int, unreachable: int) -> list[str]:
    now = datetime.now(IST)
    lines = [f"{now:%a %d %b %Y · %H:%M IST} — {ok} OK, {unreachable} unreachable"]
    for r in results:
        # one concise line per source: its summary, or the UNREACHABLE reason
        text = r.summary if r.status != "unreachable" else f"UNREACHABLE — {r.reason}"
        lines.append(f"{r.name}: {text}")
    return lines


def publish_today(results: list[Result], ok: int, unreachable: int) -> str:
    """Rewrite the Today page: clear its blocks, then write the current brief."""
    try:
        existing = nc.list_children(TODAY_PAGE)
        for b in existing:
            try:
                nc.delete_block(b["id"])
            except Exception:  # noqa: BLE001 — one stubborn block shouldn't abort
                pass
        blocks = [nc.heading_block("LIFEOS — today")]
        blocks += [nc.paragraph_block(line) for line in _brief_lines(results, ok, unreachable)]
        nc.append_children(TODAY_PAGE, blocks)
        return "today: rewritten"
    except Exception as exc:  # noqa: BLE001
        return f"today: FAILED — {type(exc).__name__}: {exc}"


def append_archive(ok: int, unreachable: int) -> str:
    """Append exactly one line to the Daily Briefs Archive."""
    now = datetime.now(IST)
    line = f"{now:%Y-%m-%d %H:%M IST} — {ok} OK, {unreachable} unreachable"
    try:
        nc.append_children(ARCHIVE_PAGE, [nc.paragraph_block(line)])
        return "archive: appended"
    except Exception as exc:  # noqa: BLE001
        return f"archive: FAILED — {type(exc).__name__}: {exc}"


def publish(results: list[Result], ok: int, unreachable: int) -> dict:
    """Best-effort publish to both pages. Returns a small status dict for the run."""
    return {"today": publish_today(results, ok, unreachable),
            "archive": append_archive(ok, unreachable)}
