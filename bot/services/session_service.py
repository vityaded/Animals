from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from bot.services.content_service import ContentItem, ContentService
from bot.storage.repositories import RepositoryProvider


@dataclass
class SessionState:
    session_id: int
    user_id: int
    level: int
    deck_ids: list[str]
    item_index: int
    total_items: int
    correct_count: int
    reward_stage: int
    mode: str
    blocked: bool
    current_attempts: int

    @classmethod
    def from_row(cls, row) -> "SessionState":
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        deck_ids = []
        if "deck_json" in keys and row["deck_json"]:
            try:
                deck_ids = json.loads(row["deck_json"])
            except Exception:
                deck_ids = []
        return cls(
            session_id=row["session_id"],
            user_id=row["user_id"],
            level=row["level"],
            deck_ids=deck_ids,
            item_index=row["item_index"],
            total_items=row["total_items"],
            correct_count=row["correct_count"] if "correct_count" in keys else 0,
            reward_stage=row["reward_stage"] if "reward_stage" in keys else 0,
            mode=row["mode"] if "mode" in keys else "normal",
            blocked=bool(row["blocked"]),
            current_attempts=row["current_attempts"] if "current_attempts" in keys else 0,
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
        passed_ids = await self.repositories.item_progress.list_passed(user_id, level)
        deck_ids = self.content_service.build_deck(user_id, level, size=10, passed_ids=passed_ids)
        total_items = len(deck_ids)
        await self.repositories.session_state.create_state(
            session_id=session_id,
            user_id=user_id,
            level=level,
            deck_json=json.dumps(deck_ids, ensure_ascii=False),
            total_items=total_items,
            item_index=0,
            blocked=0,
            correct_count=0,
            reward_stage=0,
            mode="normal",
            current_attempts=0,
        )
        return session_id

    async def start_resurrection(self, user_id: int, level: int = 1, deadline_minutes: int = 180) -> int:
        """Start a special session where the user must get 20 correct answers in a row to revive a dead pet."""
        due_at = datetime.now(timezone.utc) + timedelta(minutes=deadline_minutes)
        session_id = await self.repositories.sessions.create_session(user_id, level, due_at)
        await self.repositories.sessions.update_status(session_id, "active")
        # A long-running session; we cycle tasks until the pet is revived.
        total_items = 1_000_000
        deck_ids = [item.id for item in self.content_service.list_items(level)]
        await self.repositories.session_state.create_state(
            session_id=session_id,
            user_id=user_id,
            level=level,
            deck_json=json.dumps(deck_ids, ensure_ascii=False),
            total_items=total_items,
            item_index=0,
            blocked=0,
            correct_count=0,
            reward_stage=0,
            mode="resurrect",
            current_attempts=0,
        )
        return session_id

    async def get_active_session(self, user_id: int) -> Optional[SessionState]:
        row = await self.repositories.session_state.get_active_state_for_user(user_id)
        return SessionState.from_row(row) if row else None

    async def get_current_item(self, level: int, deck_ids: list[str], item_index: int) -> ContentItem:
        if not deck_ids:
            items = self.content_service.list_items(level)
            if not items:
                raise IndexError("No items for this level")
            return items[item_index % len(items)]
        content_id = deck_ids[item_index % len(deck_ids)]
        return self.content_service.get_item(level, content_id)

    async def advance_item(self, session_id: int) -> None:
        state_row = await self.repositories.session_state.get_state(session_id)
        if not state_row:
            return
        next_index = state_row["item_index"] + 1
        await self.repositories.session_state.update_index(session_id, next_index)
        await self.repositories.session_state.update_attempts(session_id, 0)

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
        user_id: int,
        content_id: str,
        expected_text: str,
        transcript: str,
        similarity: int,
        is_first_try: bool,
        is_correct: bool,
    ) -> int:
        return await self.repositories.attempts.log_attempt(
            session_id=session_id,
            user_id=user_id,
            content_id=content_id,
            expected_text=expected_text,
            transcript=transcript,
            similarity=similarity,
            is_first_try=is_first_try,
            is_correct=is_correct,
            question=expected_text,
            user_answer=transcript,
            correct_answer=expected_text,
        )

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

    async def get_items_for_level(self, level: int) -> list[ContentItem]:
        return self.content_service.get_level_items(level)
