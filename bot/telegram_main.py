from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher

from bot.config import Config
from bot.scheduler.scheduler import ReminderScheduler
from bot.services.content_service import ContentService
from bot.services.health_service import HealthService
from bot.services.progress_service import ProgressService
from bot.services.session_service import SessionService
from bot.services.task_presenter import TaskPresenter
from bot.services.speech_service import SpeechService
from bot.services.tts_service import TTSService
from bot.services.pet_service import PetService
from bot.storage.repositories import Database, RepositoryProvider
from bot.telegram import AppContext
from bot.paths import project_path, resolve_project_path
from bot.telegram.routers.menu import setup_menu_router
from bot.telegram.routers.session import setup_session_router
from bot.telegram.routers.start import setup_start_router
from bot.telegram.routers.voice import setup_voice_router
from bot.telegram.routers.pet import setup_pet_router

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s")
    config = Config.from_env()
    schema_path = Path(__file__).parent / "storage" / "schema.sql"
    database = Database(config.db_path, schema_path)
    await database.ensure_schema()

    repositories = RepositoryProvider.build(database)
    content_service = ContentService(project_path("content/levels"))
    session_service = SessionService(repositories, content_service)
    progress_service = ProgressService(repositories.progress, repositories.daily_stats)
    health_service = HealthService(repositories.health, repositories.revive)
    speech_service = SpeechService(config.whisper_model)
    tts_service = TTSService()
    task_presenter = TaskPresenter(project_path("assets"), tts_service)
    pet_service = PetService(
        repo=repositories.pets,
        assets_root=resolve_project_path(config.pets_assets_root),
        timezone_name=str(config.timezone),
    )

    ctx = AppContext(
        repositories=repositories,
        content_service=content_service,
        session_service=session_service,
        progress_service=progress_service,
        health_service=health_service,
        pet_service=pet_service,
        speech_service=speech_service,
        tts_service=tts_service,
        task_presenter=task_presenter,
        timezone=str(config.timezone),
        admin_ids=config.admin_telegram_ids,
    )

    bot = Bot(token=config.telegram_token)
    dp = Dispatcher()
    dp.include_router(setup_start_router(ctx))
    dp.include_router(setup_pet_router(ctx))
    dp.include_router(setup_menu_router(ctx))
    dp.include_router(setup_session_router(ctx))
    dp.include_router(setup_voice_router(ctx))

    async def on_deadline(label: str, when) -> None:
        now = when
        active_sessions = await repositories.sessions.get_active_sessions(now)
        for session in active_sessions:
            state = await repositories.session_state.get_state(session["id"])
            if not state:
                continue
            await repositories.sessions.update_status(session["id"], "blocked")
            await repositories.session_state.set_blocked(session["id"], 1)
            user = await repositories.users.get_user_by_id(session["user_id"])
            if user:
                try:
                    await bot.send_message(user["telegram_id"], f"Дедлайн сесії {label} минув. Сесію заблоковано.")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to send deadline message to %s: %s", user["telegram_id"], exc)

    scheduler = ReminderScheduler(
        session_times=config.session_times,
        deadline_minutes_after=config.deadline_minutes_after,
        timezone=config.timezone,
        on_deadline=on_deadline,
    )
    await scheduler.start()

    logger.info("Запуск Telegram polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
