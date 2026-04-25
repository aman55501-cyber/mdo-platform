"""Declared task scheduler — replace scattered asyncio.sleep loops.

Schedules are declared once at engine startup. Each runs in its own coroutine.
The ScheduleManager runs them all concurrently via a single asyncio task.

Usage:
    scheduler = ScheduleManager()

    scheduler.add(Schedule(
        name="morning_brief",
        fn=engine.send_morning_brief,
        at_times=["08:50"],          # fire at 08:50 IST on weekdays
        weekdays_only=True,
    ))

    scheduler.add(Schedule(
        name="digest",
        fn=alert_router.flush_digest,
        interval_seconds=3600,       # every hour
    ))

    # In engine.run():
    tasks.append(asyncio.create_task(scheduler.run(), name="scheduler"))

A Schedule uses EITHER `at_times` (wall-clock, fires once per day) OR
`interval_seconds` (repeating). Both honour `weekdays_only` and `enabled`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable

from ..utils.logging import get_logger
from ..utils.time import now_ist

log = get_logger("scheduler")

AsyncFn = Callable[[], Awaitable[None]]


@dataclass
class Schedule:
    name: str
    fn: AsyncFn

    # Exactly one of these should be set:
    interval_seconds: int | None = None    # e.g. 3600 for every hour
    at_times: list[str] | None = None      # e.g. ["08:50", "15:30"] (IST, HH:MM)

    weekdays_only: bool = False            # skip Sat/Sun
    enabled: bool = True
    _fired_today: set[str] = field(default_factory=set, repr=False)


class ScheduleManager:
    """Runs all declared schedules concurrently."""

    def __init__(self) -> None:
        self._schedules: list[Schedule] = []
        self._running = False

    def add(self, schedule: Schedule) -> None:
        self._schedules.append(schedule)
        log.info("schedule_registered", name=schedule.name)

    def get(self, name: str) -> Schedule | None:
        return next((s for s in self._schedules if s.name == name), None)

    def enable(self, name: str) -> None:
        s = self.get(name)
        if s:
            s.enabled = True

    def disable(self, name: str) -> None:
        s = self.get(name)
        if s:
            s.enabled = False

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        """Main loop — starts a watcher coroutine for each schedule."""
        self._running = True
        log.info("scheduler_started", count=len(self._schedules))
        tasks = [
            asyncio.create_task(self._run_one(s), name=f"sched_{s.name}")
            for s in self._schedules
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()

    # ── per-schedule loops ──────────────────────────────────────────── #

    async def _run_one(self, s: Schedule) -> None:
        """Drive a single schedule until stopped."""
        while self._running:
            if not s.enabled:
                await asyncio.sleep(30)
                continue

            now = now_ist()

            if s.weekdays_only and now.weekday() >= 5:
                await asyncio.sleep(60)
                continue

            if s.interval_seconds:
                await asyncio.sleep(s.interval_seconds)
                await self._fire(s)

            elif s.at_times:
                next_seconds = _seconds_until_next(now, s.at_times, s._fired_today)
                if next_seconds is None:
                    # All today's times fired — sleep until midnight reset
                    await asyncio.sleep(_seconds_until_midnight(now))
                    s._fired_today.clear()
                    continue
                await asyncio.sleep(next_seconds)
                # Mark this slot fired so we don't double-fire
                slot = _nearest_slot(now_ist(), s.at_times)
                if slot:
                    s._fired_today.add(slot)
                await self._fire(s)

            else:
                log.warning("schedule_no_trigger", name=s.name)
                await asyncio.sleep(3600)

    async def _fire(self, s: Schedule) -> None:
        log.info("schedule_firing", name=s.name)
        try:
            await s.fn()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("schedule_error", name=s.name, error=str(exc))


# ── time helpers ─────────────────────────────────────────────────────── #

def _seconds_until_next(now: datetime, times: list[str], fired: set[str]) -> int | None:
    """Return seconds until the next unfired time slot today, or None if all fired."""
    candidates = []
    for t in times:
        if t in fired:
            continue
        h, m = map(int, t.split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        diff = (target - now).total_seconds()
        if diff > 0:
            candidates.append(diff)
    return int(min(candidates)) if candidates else None


def _nearest_slot(now: datetime, times: list[str]) -> str | None:
    """Return the time slot string closest to (and <= 5s past) now."""
    for t in times:
        h, m = map(int, t.split(":"))
        if now.hour == h and abs(now.minute - m) <= 1:
            return t
    return None


def _seconds_until_midnight(now: datetime) -> int:
    tomorrow = now.replace(hour=0, minute=1, second=0, microsecond=0)
    from datetime import timedelta
    tomorrow += timedelta(days=1)
    return max(60, int((tomorrow - now).total_seconds()))
