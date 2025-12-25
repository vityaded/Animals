from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DeadlineCallback = Callable[[str, datetime], Awaitable[None]]


@dataclass
class ScheduledEvent:
    name: str
    when: datetime


class ReminderScheduler:
    def __init__(
        self,
        session_times: Iterable[str],
        deadline_minutes_after: int,
        timezone: ZoneInfo,
        on_deadline: Optional[DeadlineCallback] = None,
    ):
        self.session_times = list(session_times)
        self.deadline_delta = timedelta(minutes=deadline_minutes_after)
        self.timezone = timezone
        self.on_deadline = on_deadline or self._log_event
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            now = datetime.now(tz=self.timezone)
            next_event = self._next_event(now)
            if next_event is None:
                await asyncio.sleep(60)
                continue
            sleep_seconds = max(0, (next_event.when - now).total_seconds())
            await asyncio.sleep(sleep_seconds)
            await self.on_deadline(next_event.name, next_event.when)

    def _next_event(self, now: datetime) -> Optional[ScheduledEvent]:
        events: list[ScheduledEvent] = []
        for time_str in self.session_times:
            hour, minute = map(int, time_str.split(":"))
            session_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if session_dt <= now:
                session_dt += timedelta(days=1)
            deadline_time = session_dt + self.deadline_delta
            events.append(ScheduledEvent(name=time_str, when=deadline_time))
        if not events:
            return None
        return min(events, key=lambda e: e.when)

    async def _log_event(self, session_label: str, when: datetime) -> None:
        logger.info("Scheduler event %s at %s", session_label, when.isoformat())
