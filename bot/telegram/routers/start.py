from __future__ import annotations

from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.db.repo import Repo
from bot.services.pet_service import PetService
from bot.services.session_service import SessionService
from bot.services.task_service import TaskService
from bot.services.tts_service import TTSService
from bot.telegram.keyboards import difficulty_keyboard, main_menu_keyboard, pet_picker_keyboard
from bot.telegram.routers import learning

router = Router()

AVAILABLE_PETS = ["panda", "dog", "dinosaur", "fox"]


def _available_pet_types(assets_root: str) -> list[str]:
    types = []
    for pet in AVAILABLE_PETS:
        if (Path(assets_root) / pet).exists():
            types.append(pet)
    return types


async def handle_start(
    message: Message,
    repo: Repo,
    config: Config,
    pet_service: PetService,
    session_service: SessionService,
    task_service: TaskService,
    tts_service: TTSService,
) -> None:
    user = await repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await repo.create_user(message.from_user.id)
    if not user.get("pet_type"):
        await message.answer(
            "Привіт! Обери тваринку:",
            reply_markup=pet_picker_keyboard(_available_pet_types(config.assets_root)),
        )
        return
    await learning.start_or_continue(
        message,
        user,
        repo,
        config,
        pet_service,
        session_service,
        task_service,
        tts_service,
    )


@router.message(Command("start"))
async def start_command(
    message: Message,
    repo: Repo,
    config: Config,
    pet_service: PetService,
    session_service: SessionService,
    task_service: TaskService,
    tts_service: TTSService,
) -> None:
    await message.answer("Готові вчитись?", reply_markup=main_menu_keyboard())
    await handle_start(
        message,
        repo,
        config,
        pet_service,
        session_service,
        task_service,
        tts_service,
    )


@router.message(F.text == "Рівень")
async def level_message(message: Message) -> None:
    await message.answer("Обери рівень:", reply_markup=difficulty_keyboard())


@router.message(F.text.in_(["1️⃣ Слова", "2️⃣ Фрази", "3️⃣ Речення"]))
async def select_level(
    message: Message,
    repo: Repo,
    config: Config,
    pet_service: PetService,
    session_service: SessionService,
    task_service: TaskService,
    tts_service: TTSService,
) -> None:
    mapping = {"1️⃣ Слова": 1, "2️⃣ Фрази": 2, "3️⃣ Речення": 3}
    difficulty = mapping[message.text]
    user = await repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await repo.create_user(message.from_user.id)
    await repo.set_user_difficulty(user["id"], difficulty)
    user["difficulty"] = difficulty
    await message.answer("Рівень оновлено.", reply_markup=main_menu_keyboard())
    if user.get("pet_type"):
        await learning.start_or_continue(
            message,
            user,
            repo,
            config,
            pet_service,
            session_service,
            task_service,
            tts_service,
        )
