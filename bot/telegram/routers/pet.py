from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.db.repo import Repo
from bot.services.pet_service import PetService
from bot.services.session_service import SessionService
from bot.services.task_service import TaskService
from bot.services.tts_service import TTSService
from bot.telegram.keyboards import main_menu_keyboard
from bot.telegram.media_utils import answer_pet_card
from bot.telegram.routers import learning

router = Router()


@router.callback_query(F.data.startswith("pet:"))
async def pick_pet(
    callback: CallbackQuery,
    repo: Repo,
    pet_service: PetService,
    session_service: SessionService,
    task_service: TaskService,
    tts_service: TTSService,
) -> None:
    pet_type = callback.data.split(":", 1)[1]
    user = await repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        user = await repo.create_user(callback.from_user.id)
    await repo.set_user_pet_type(user["id"], pet_type)
    user["pet_type"] = pet_type
    status = await pet_service.get_or_create_status(user["id"])
    state = pet_service.pick_state(status)
    caption = f"Твоя тваринка готова!\n{pet_service.status_text(status)}"
    await answer_pet_card(
        callback.message,
        pet_type,
        state,
        caption,
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer("Тваринка обрана!")
    await learning.start_or_continue(
        callback.message,
        user,
        repo,
        pet_service.config,
        pet_service,
        session_service,
        task_service,
        tts_service,
    )


@router.message(F.text == "Моя тваринка")
async def show_pet(
    message: Message,
    repo: Repo,
    pet_service: PetService,
) -> None:
    user = await repo.get_user_by_telegram_id(message.from_user.id)
    if not user or not user.get("pet_type"):
        await message.answer("Спочатку обери тваринку.")
        return
    status = await pet_service.get_or_create_status(user["id"])
    state = pet_service.pick_state(status)
    caption = pet_service.status_text(status)
    await answer_pet_card(message, user["pet_type"], state, caption)
