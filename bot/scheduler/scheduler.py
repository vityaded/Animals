from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

ReminderCallback = Callable[[str, datetime], Awaitable[None]]
DeadlineCallback = Callable[[str, datetime], Awaitable[None]]


@dataclass
class ScheduledEvent:
    name: str
    when: datetime
    kind: str  # reminder | deadline


class ReminderScheduler:
    def __init__(
        self,
        session_times: Iterable[str],
        reminder_minutes_before: int,
        deadline_minutes_after: int,
        on_reminder: Optional[ReminderCallback] = None,
        on_deadline: Optional[DeadlineCallback] = None,
    ):
        self.session_times = list(session_times)
        self.reminder_delta = timedelta(minutes=reminder_minutes_before)
        self.deadline_delta = timedelta(minutes=deadline_minutes_after)
        self.on_reminder = on_reminder or self._log_event
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
            now = datetime.now()
            next_event = self._next_event(now)
            if next_event is None:
                await asyncio.sleep(60)
                continue
            sleep_seconds = max(0, (next_event.when - now).total_seconds())
            await asyncio.sleep(sleep_seconds)
            if next_event.kind == "reminder":
                await self.on_reminder(next_event.name, next_event.when)
            else:
                await self.on_deadline(next_event.name, next_event.when)

    def _next_event(self, now: datetime) -> Optional[ScheduledEvent]:
        events: list[ScheduledEvent] = []
        for time_str in self.session_times:
            hour, minute = map(int, time_str.split(":"))
            session_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if session_dt <= now:
                session_dt += timedelta(days=1)
            reminder_time = session_dt - self.reminder_delta
            deadline_time = session_dt + self.deadline_delta
            events.append(ScheduledEvent(name=time_str, when=reminder_time, kind="reminder"))
            events.append(ScheduledEvent(name=time_str, when=deadline_time, kind="deadline"))
        if not events:
            return None
        return min(events, key=lambda e: e.when)

    async def _log_event(self, session_label: str, when: datetime) -> None:
        logger.info("Scheduler event %s at %s", session_label, when.isoformat())
