from __future__ import annotations

from bot.services.content_service import ContentService
from bot.services.progress_service import ProgressService
from bot.storage.repositories import RepositoryProvider


def handle_menu(
    repositories: RepositoryProvider,
    progress_service: ProgressService,
    telegram_id: int,
    content_service: ContentService | None = None,
) -> str:
    user = repositories.users.get_user(telegram_id)
    if not user:
        return "Спочатку надішліть /start"
    progress = progress_service.get_progress(user["id"], level=1)
    stats = progress_service.get_today_stats(user["id"])
    streak = stats["streak"] if stats else 0
    pet_note = ""
    if content_service:
        asset = content_service.resolve_pet_asset("happy")
        if asset.is_placeholder:
            pet_note = f"\n{asset.message}"
        elif asset.path:
            pet_note = f"\nЗображення улюбленця: {asset.path}"

    return f"Ваш прогрес: {progress} балів на рівні 1. Сьогоднішня серія: {streak}{pet_note}"
