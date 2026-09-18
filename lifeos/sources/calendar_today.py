"""calendar_today — today's events on the primary calendar, Asia/Kolkata.

Read-only. Credentials from google_auth; missing token -> UNREACHABLE for this panel.
Nil state in words: "no events today".
"""

from __future__ import annotations

from datetime import datetime, time

from . import NIL, OK, Result
from ..config import IST
from .google_auth import calendar_service


def _day_bounds():
    now = datetime.now(IST)
    start = datetime.combine(now.date(), time.min, tzinfo=IST)
    end = datetime.combine(now.date(), time.max, tzinfo=IST)
    return start.isoformat(), end.isoformat()


def _fmt_time(ev: dict) -> str:
    start = ev.get("start", {})
    if "date" in start and "dateTime" not in start:
        return "all day"
    dt = start.get("dateTime", "")
    try:
        return datetime.fromisoformat(dt).astimezone(IST).strftime("%H:%M")
    except (ValueError, TypeError):
        return "—"


def fetch() -> Result:
    service = calendar_service()
    tmin, tmax = _day_bounds()
    resp = service.events().list(
        calendarId="primary", timeMin=tmin, timeMax=tmax,
        singleEvents=True, orderBy="startTime", timeZone="Asia/Kolkata",
    ).execute()
    events = resp.get("items", [])

    rows = []
    for ev in events:
        rows.append(
            {
                "gutter": _fmt_time(ev), "severity": "quiet",
                "text": ev.get("summary", "(no title)"),
                "meta": ev.get("location", "") or "",
            }
        )

    if events:
        summary = f"{len(events)} event(s) today."
        status = OK
    else:
        summary = "No events today."
        status = NIL
    return Result(
        name="calendar",
        status=status,
        summary=summary,
        data={"count": len(events)},
        extra={"rows": rows},
    )
