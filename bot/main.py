from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher

from bot.config import get_config
from bot.db.sqlite import init_db
from bot.db.repo import Repo
from bot.logging_setup import setup_logging
from bot.services.asr_service import ASRService
from bot.services.pet_service import PetService
from bot.services.session_service import SessionService
from bot.services.task_service import TaskService
from bot.services.tts_service import TTSService
from bot.telegram.routers import admin, care, learning, pet, start


async def build_dispatcher() -> tuple[Dispatcher, dict]:
    config = get_config()
    setup_logging(config.log_level)
    repo = Repo(config.db_path)
    pet_service = PetService(repo, config)
    session_service = SessionService(repo, config, pet_service)
    task_service = TaskService(config)
    tts_service = TTSService(config)
    asr_service = ASRService(config)

    dp = Dispatcher()
    dp.include_routers(start.router, pet.router, learning.router, care.router, admin.router)

    dp["config"] = config
    dp["repo"] = repo
    dp["pet_service"] = pet_service
    dp["session_service"] = session_service
    dp["task_service"] = task_service
    dp["tts_service"] = tts_service
    dp["asr_service"] = asr_service

    return dp, {
        "config": config,
        "repo": repo,
        "pet_service": pet_service,
        "session_service": session_service,
        "task_service": task_service,
        "tts_service": tts_service,
        "asr_service": asr_service,
    }


async def run_bot() -> None:
    dp, services = await build_dispatcher()
    config = services["config"]
    if not config.bot_token:
        raise RuntimeError("BOT_TOKEN is missing")
    bot = Bot(token=config.bot_token)
    await init_db(config.db_path, "bot/db/schema.sql")
    logging.getLogger(__name__).info(
        "Routers registered: %s", ["start", "pet", "learning", "care", "admin"]
    )
    await dp.start_polling(bot)


async def smoke() -> None:
    await build_dispatcher()
    logging.getLogger(__name__).info(
        "Routers registered: %s", ["start", "pet", "learning", "care", "admin"]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animals Reading bot")
    parser.add_argument("--init-db", action="store_true", help="Initialize the database and exit")
    parser.add_argument("--smoke", action="store_true", help="Run a local smoke check")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = get_config()
    setup_logging(config.log_level)
    Path("var").mkdir(parents=True, exist_ok=True)
    if args.init_db:
        asyncio.run(init_db(config.db_path, "bot/db/schema.sql"))
        return
    if args.smoke:
        asyncio.run(smoke())
        return
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
