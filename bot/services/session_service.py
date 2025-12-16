from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from bot.services.content_service import ContentService, LevelItem
from bot.storage.repositories import RepositoryProvider


class SessionService:
    def __init__(self, repositories: RepositoryProvider, content_service: ContentService):
        self.repositories = repositories
        self.content_service = content_service

    def start_session(self, user_id: int, level: int, deadline_minutes: int) -> int:
        due_at = datetime.utcnow() + timedelta(minutes=deadline_minutes)
        session_id = self.repositories.sessions.create_session(user_id, level, due_at)
        progress = self.repositories.progress.load_progress(user_id, level)
        if progress == 0:
            self.repositories.progress.save_progress(user_id, level, progress)
        return session_id

    def record_attempt(
        self,
        session_id: int,
        prompt: str,
        user_answer: str,
        correct_answer: str,
        is_correct: bool,
    ) -> int:
        attempt_id = self.repositories.attempts.log_attempt(
            session_id=session_id,
            question=prompt,
            user_answer=user_answer,
            correct_answer=correct_answer,
            is_correct=is_correct,
        )
        return attempt_id

    def complete_session(self, session_id: int, user_id: int, level: int, correct: int, total: int) -> None:
        status = "passed" if total and correct == total else "done"
        self.repositories.sessions.update_status(session_id, status)
        current_progress = self.repositories.progress.load_progress(user_id, level)
        new_progress = max(current_progress, correct)
        self.repositories.progress.save_progress(user_id, level, new_progress)

    def get_items_for_level(self, level: int) -> list[LevelItem]:
        return self.content_service.get_level_items(level)

    def get_latest_session(self, user_id: int) -> Optional[dict]:
        session = self.repositories.sessions.latest_session(user_id)
        if not session:
            return None
        attempts = self.repositories.attempts.attempts_for_session(session["id"])
        return {"session": session, "attempts": attempts}
