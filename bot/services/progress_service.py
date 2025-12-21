from __future__ import annotations

from datetime import date

from bot.storage.repositories import DailyStatsRepository, ProgressRepository


class ProgressService:
    def __init__(self, progress_repository: ProgressRepository, daily_stats_repository: DailyStatsRepository):
        self.progress_repository = progress_repository
        self.daily_stats_repository = daily_stats_repository

    def update_progress(self, user_id: int, level: int, progress: int, attempts: int, correct: int, streak: int) -> None:
        self.progress_repository.save_progress(user_id, level, progress)
        self.daily_stats_repository.update_stats(user_id, date.today().isoformat(), attempts, correct, streak)

    def get_progress(self, user_id: int, level: int) -> int:
        return self.progress_repository.load_progress(user_id, level)

    def get_today_stats(self, user_id: int):
        return self.daily_stats_repository.get_stats(user_id, date.today().isoformat())
