from __future__ import annotations

from typing import Iterable

from bot.services.session_service import SessionService
from bot.storage.repositories import RepositoryProvider


async def handle_start_session(
    repositories: RepositoryProvider,
    session_service: SessionService,
    telegram_id: int,
    level: int,
    deadline_minutes: int,
) -> str:
    user = await repositories.users.get_user(telegram_id)
    if not user:
        return "Спочатку надішліть /start"
    session_id = await session_service.start_session(user_id=user["id"], level=level, deadline_minutes=deadline_minutes)
    items: Iterable[str] = (item.text for item in await session_service.get_items_for_level(level))
    first_item = next(iter(items), None)
    if not first_item:
        return f"Контент рівня {level} відсутній."
    return f"Сесія #{session_id} для рівня {level} запущена. Перше завдання:\n- {first_item}"


async def handle_session_summary(session_service: SessionService, telegram_id: int, repositories: RepositoryProvider) -> str:
    user = await repositories.users.get_user(telegram_id)
    if not user:
        return "Сесія не знайдена. Спершу надішліть /start"
    latest = await session_service.get_latest_session(user["id"])
    if not latest:
        return "Активних сесій немає"
    attempts = latest["attempts"]
    correct = sum(1 for attempt in attempts if attempt["is_correct"])
    return f"Остання сесія: {len(attempts)} спроб, правильних {correct}"
