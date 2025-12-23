from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from bot.services.content_service import ContentService, LevelItem
from bot.storage.repositories import RepositoryProvider


@dataclass
class SessionState:
    session_id: int
    user_id: int
    level: int
    item_index: int
    total_items: int
    correct_count: int
    reward_stage: int
    mode: str
    blocked: bool

    @classmethod
    def from_row(cls, row) -> "SessionState":
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        return cls(
            session_id=row["session_id"],
            user_id=row["user_id"],
            level=row["level"],
            item_index=row["item_index"],
            total_items=row["total_items"],
            correct_count=row["correct_count"] if "correct_count" in keys else 0,
            reward_stage=row["reward_stage"] if "reward_stage" in keys else 0,
            mode=row["mode"] if "mode" in keys else "normal",
            blocked=bool(row["blocked"]),
        )


class SessionService:
    def __init__(self, repositories: RepositoryProvider, content_service: ContentService):
        self.repositories = repositories
        self.content_service = content_service

    async def start_session(self, user_id: int, level: int, deadline_minutes: int) -> int:
        due_at = datetime.now(timezone.utc) + timedelta(minutes=deadline_minutes)
        session_id = await self.repositories.sessions.create_session(user_id, level, due_at)
        await self.repositories.sessions.update_status(session_id, "active")
        progress = await self.repositories.progress.load_progress(user_id, level)
        if progress == 0:
            await self.repositories.progress.save_progress(user_id, level, progress)
        total_items = min(10, len(self.content_service.get_level_items(level)))
        await self.repositories.session_state.create_state(
            session_id=session_id,
            user_id=user_id,
            level=level,
            total_items=total_items,
            item_index=0,
            blocked=0,
            correct_count=0,
            reward_stage=0,
            mode="normal",
        )
        return session_id

    async def start_resurrection(self, user_id: int, level: int = 1, deadline_minutes: int = 180) -> int:
        """Start a special session where the user must get 20 correct answers in a row to revive a dead pet."""
        due_at = datetime.now(timezone.utc) + timedelta(minutes=deadline_minutes)
        session_id = await self.repositories.sessions.create_session(user_id, level, due_at)
        await self.repositories.sessions.update_status(session_id, "active")
        # A long-running session; we cycle tasks until the pet is revived.
        total_items = 1_000_000
        await self.repositories.session_state.create_state(
            session_id=session_id,
            user_id=user_id,
            level=level,
            total_items=total_items,
            item_index=0,
            blocked=0,
            correct_count=0,
            reward_stage=0,
            mode="resurrect",
        )
        return session_id

    async def get_active_session(self, user_id: int) -> Optional[SessionState]:
        row = await self.repositories.session_state.get_active_state_for_user(user_id)
        return SessionState.from_row(row) if row else None

    async def get_current_item(self, level: int, item_index: int) -> LevelItem:
        items = self.content_service.get_level_items(level)
        if not items:
            raise IndexError("No items for this level")
        # For resurrection mode we may advance beyond the end; cycle.
        return items[item_index % len(items)]

    async def advance_item(self, session_id: int) -> None:
        state_row = await self.repositories.session_state.get_state(session_id)
        if not state_row:
            return
        next_index = state_row["item_index"] + 1
        await self.repositories.session_state.update_index(session_id, next_index)

    async def finish_if_needed(self, session_id: int, user_id: int, level: int) -> bool:
        state_row = await self.repositories.session_state.get_state(session_id)
        if not state_row:
            return True
        if state_row["item_index"] < state_row["total_items"]:
            return False
        total, correct = await self.repositories.attempts.count_for_session(session_id)
        await self.complete_session(session_id, user_id, level, correct, total)
        await self.repositories.session_state.delete_state(session_id)
        return True

    async def record_attempt(
        self,
        session_id: int,
        prompt: str,
        user_answer: str,
        correct_answer: str,
        is_correct: bool,
    ) -> int:
        attempt_id = await self.repositories.attempts.log_attempt(
            session_id=session_id,
            question=prompt,
            user_answer=user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
        )
        return attempt_id

    async def complete_session(self, session_id: int, user_id: int, level: int, correct: int, total: int) -> None:
        status = "passed" if total and correct == total else "done"
        await self.repositories.sessions.update_status(session_id, status)
        current_progress = await self.repositories.progress.load_progress(user_id, level)
        new_progress = max(current_progress, correct)
        await self.repositories.progress.save_progress(user_id, level, new_progress)

    async def get_latest_session(self, user_id: int) -> Optional[dict]:
        session = await self.repositories.sessions.latest_session(user_id)
        if not session:
            return None
        attempts = await self.repositories.attempts.attempts_for_session(session["id"])
        return {"session": session, "attempts": attempts}

    async def block_session(self, session_id: int) -> None:
        await self.repositories.session_state.set_blocked(session_id, 1)
        await self.repositories.sessions.update_status(session_id, "blocked")

    async def revive_session(self, session_id: int) -> None:
        await self.repositories.session_state.set_blocked(session_id, 0)
        await self.repositories.sessions.update_status(session_id, "active")

    async def get_items_for_level(self, level: int) -> list[LevelItem]:
        return self.content_service.get_level_items(level)
