from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.scheduler.scheduler import ReminderScheduler


def test_next_event_selects_soonest_deadline_same_day() -> None:
    """Pick the closest deadline on the same day when sessions are in the future."""
    tz = ZoneInfo("UTC")
    scheduler = ReminderScheduler(["09:00", "18:00"], deadline_minutes_after=30, timezone=tz)
    now = datetime(2024, 1, 1, 8, 0, tzinfo=tz)

    next_event = scheduler._next_event(now)

    assert next_event is not None
    assert next_event.name == "09:00"
    assert next_event.when == datetime(2024, 1, 1, 9, 30, tzinfo=tz)


def test_next_event_rolls_over_to_next_day() -> None:
    """Move the next deadline to the following day once today's session passed."""
    tz = ZoneInfo("UTC")
    scheduler = ReminderScheduler(["09:00"], deadline_minutes_after=15, timezone=tz)
    now = datetime(2024, 1, 1, 10, 0, tzinfo=tz)

    next_event = scheduler._next_event(now)

    assert next_event is not None
    assert next_event.when == datetime(2024, 1, 2, 9, 15, tzinfo=tz)


def test_next_event_returns_none_for_empty_schedule() -> None:
    """Return None when no session times are configured."""
    tz = ZoneInfo("UTC")
    scheduler = ReminderScheduler([], deadline_minutes_after=10, timezone=tz)
    now = datetime(2024, 1, 1, 10, 0, tzinfo=tz)

    assert scheduler._next_event(now) is None


@pytest.mark.asyncio
async def test_run_invokes_deadline_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invoke the deadline callback at the computed time without real sleeping."""
    tz = ZoneInfo("UTC")
    now = datetime(2024, 1, 1, 8, 0, tzinfo=tz)
    events: list[tuple[str, datetime]] = []

    async def on_deadline(name: str, when: datetime) -> None:
        events.append((name, when))
        raise asyncio.CancelledError

    scheduler = ReminderScheduler(["09:00"], deadline_minutes_after=0, timezone=tz, on_deadline=on_deadline)

    class _FakeNow(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return now if tz is None else now.astimezone(tz)

    async def _fake_sleep(seconds: float) -> None:
        return None

    import bot.scheduler.scheduler as scheduler_module

    monkeypatch.setattr(scheduler_module, "datetime", _FakeNow)
    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await scheduler._run()

    assert events == [("09:00", datetime(2024, 1, 1, 9, 0, tzinfo=tz))]
