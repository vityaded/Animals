from __future__ import annotations

from bot.services.health_service import HealthService
from bot.storage.repositories import RepositoryProvider


def handle_start(repositories: RepositoryProvider, health_service: HealthService, telegram_id: int, username: str | None = None) -> str:
    user_id = repositories.users.upsert_user(telegram_id, username)
    health_service.gain_heart(user_id)
    return "Вітаємо в мовному тренажері! Оберіть рівень та розпочніть першу сесію."
