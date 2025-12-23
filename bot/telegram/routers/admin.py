from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.db.repo import Repo
from bot.services.pet_service import PetService
from bot.services.session_service import SessionService
from bot.services.task_service import TaskService
from bot.services.tts_service import TTSService
from bot.telegram.routers.start import handle_start

router = Router()


@router.message(Command("reset_all"))
async def reset_all(
    message: Message,
    repo: Repo,
    config: Config,
    pet_service: PetService,
    session_service: SessionService,
    task_service: TaskService,
    tts_service: TTSService,
) -> None:
    await repo.delete_user_by_telegram_id(message.from_user.id)
    await message.answer("OK. Database cleared.")
    await handle_start(
        message,
        repo,
        config,
        pet_service,
        session_service,
        task_service,
        tts_service,
    )
