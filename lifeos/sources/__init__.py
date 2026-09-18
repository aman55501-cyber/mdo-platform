"""Sources — each one is fault-isolated (brief rule 2).

A source is a function that returns a ``Result``. It must never raise to the caller:
``guarded`` wraps the fetch in try/except and converts any exception into a
``Result`` with status UNREACHABLE and the reason attached, so one dead source can
never abort the run. The run continues and still publishes.

Status vocabulary (also used by the runs table and the page's severity stripes):
  OK          the source answered and has content
  NIL         the source answered and is legitimately empty ("0 overdue") — still
              reported in words, never a blank div (rule 1)
  BLOCKED     a known-missing input we are waiting on (e.g. an ERP export not yet
              delivered) — rendered as an explicit blocked state naming who owes it
  UNREACHABLE the source raised or a credential is missing — rendered as
              "UNREACHABLE — <source> — <reason>"
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

OK = "ok"
NIL = "nil"
BLOCKED = "blocked"
UNREACHABLE = "unreachable"

# statuses that count as "the source is reporting" for the heartbeat OK tally
_HEALTHY = {OK, NIL, BLOCKED}


@dataclass
class Result:
    """The outcome of one source fetch. ``data`` is whatever the panel needs; the
    render layer decides how to draw it. ``summary`` is the one-line nil/ok/blocked
    sentence so no panel is ever empty."""

    name: str
    status: str = OK
    summary: str = ""
    data: Any = None
    reason: str = ""  # only meaningful when status == UNREACHABLE / BLOCKED
    ms: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return self.status in _HEALTHY

    @property
    def unreachable(self) -> bool:
        return self.status == UNREACHABLE


def guarded(name: str, fetch: Callable[[], Result]) -> Result:
    """Run ``fetch`` and guarantee a Result. Any exception becomes UNREACHABLE with
    a compact reason (never a stack trace to the user, but the reason is specific
    enough to act on). Timing is always recorded."""
    start = time.monotonic()
    try:
        result = fetch()
        if not isinstance(result, Result):  # defensive: a source must return a Result
            raise TypeError(f"source '{name}' returned {type(result).__name__}, not Result")
        result.name = result.name or name
    except Exception as exc:  # noqa: BLE001 — fault isolation is the point
        reason = f"{type(exc).__name__}: {exc}".strip().replace("\n", " ")
        # One concise operator line by default; full trace only with LIFEOS_DEBUG=1
        # (so a handful of expected UNREACHABLE sources don't flood the logs).
        if os.environ.get("LIFEOS_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
            traceback.print_exc()
        else:
            print(f"[lifeos] source '{name}' unreachable: {reason[:200]}", file=sys.stderr)
        result = Result(
            name=name,
            status=UNREACHABLE,
            summary=f"UNREACHABLE — {name} — {reason[:200]}",
            reason=reason[:200],
        )
    result.ms = int((time.monotonic() - start) * 1000)
    return result
