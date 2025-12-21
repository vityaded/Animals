from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bot.config import Config
from bot.handlers import menu, session, start
from bot.scheduler.scheduler import ReminderScheduler
from bot.services.content_service import ContentService
from bot.services.health_service import HealthService
from bot.services.progress_service import ProgressService
from bot.services.session_service import SessionService
from bot.services.speech_service import SpeechService
from bot.storage.repositories import Database, RepositoryProvider

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s")

    config = Config.from_env()
    schema_path = Path(__file__).parent / "storage" / "schema.sql"
    database = Database(config.db_path, schema_path)
    database.ensure_schema()

    repositories = RepositoryProvider(database)
    content_service = ContentService(Path("content/levels"))
    session_service = SessionService(repositories, content_service)
    progress_service = ProgressService(repositories.progress, repositories.daily_stats)
    health_service = HealthService(repositories.health, repositories.revive)
    speech_service = SpeechService(config.whisper_model)

    async def on_reminder(label: str, when) -> None:
        logger.info("Нагадування про сесію %s о %s", label, when.isoformat())

    async def on_deadline(label: str, when) -> None:
        logger.warning("Дедлайн сесії %s о %s", label, when.isoformat())

    scheduler = ReminderScheduler(
        session_times=config.session_times,
        reminder_minutes_before=config.reminder_minutes_before,
        deadline_minutes_after=config.deadline_minutes_after,
        on_reminder=on_reminder,
        on_deadline=on_deadline,
    )
    await scheduler.start()

    logger.info("Бот готовий. Запускаємо тестові хендлери...")
    # Демонстраційні виклики бізнес-логіки
    logger.info(
        start.handle_start(repositories, health_service, telegram_id=123, username="demo"),
    )
    logger.info(menu.handle_menu(repositories, progress_service, telegram_id=123, content_service=content_service))
    logger.info(
        session.handle_start_session(
            repositories,
            session_service,
            telegram_id=123,
            level=1,
            deadline_minutes=config.deadline_minutes_after,
        )
    )

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
