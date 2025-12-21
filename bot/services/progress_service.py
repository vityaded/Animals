from __future__ import annotations

from datetime import date

from bot.storage.repositories import DailyStatsRepository, ProgressRepository


class ProgressService:
    def __init__(self, progress_repository: ProgressRepository, daily_stats_repository: DailyStatsRepository):
        self.progress_repository = progress_repository
        self.daily_stats_repository = daily_stats_repository

    async def update_progress(self, user_id: int, level: int, progress: int, attempts: int, correct: int, streak: int) -> None:
        await self.progress_repository.save_progress(user_id, level, progress)
        await self.daily_stats_repository.update_stats(user_id, date.today().isoformat(), attempts, correct, streak)

    async def update_after_attempt(self, user_id: int, level: int, is_correct: bool) -> int:
        today = date.today().isoformat()
        current_stats = await self.daily_stats_repository.get_stats(user_id, today)
        streak = current_stats["streak"] if current_stats else 0
        streak = streak + 1 if is_correct else 0
        attempts = 1
        correct = 1 if is_correct else 0
        await self.daily_stats_repository.update_stats(user_id, today, attempts, correct, streak)
        return streak

    async def update_after_session(self, user_id: int, level: int, correct: int, total: int) -> None:
        current_progress = await self.progress_repository.load_progress(user_id, level)
        new_progress = max(current_progress, correct)
        await self.progress_repository.save_progress(user_id, level, new_progress)

    async def get_progress(self, user_id: int, level: int) -> int:
        return await self.progress_repository.load_progress(user_id, level)

    async def get_today_stats(self, user_id: int):
        return await self.daily_stats_repository.get_stats(user_id, date.today().isoformat())
