"""self_check — the one source that exists in Phase 0.

It has no external dependency, so it always answers. Its job is to give the run a
real, non-empty thing to report (so the heartbeat is never "0 OK, 0 unreachable"
during bring-up) and to exercise the whole spine: guarded fetch -> Result ->
run_sources row -> heartbeat -> rendered snapshot. Real sources (Notion, Gmail,
Calendar, Supabase, brokers, ERP exports) land in Phases 1-2 alongside it.
"""

from __future__ import annotations

import platform
import sys

from . import OK, Result
from ..config import db_path


def fetch() -> Result:
    info = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "db": db_path().name,
    }
    return Result(
        name="self_check",
        status=OK,
        summary="LIFEOS spine is alive — run history, heartbeat and render all working.",
        data=info,
    )
