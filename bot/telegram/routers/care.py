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

CARE_MAP = {
    "feed": "hunger",
    "water": "thirst",
    "wash": "hygiene",
    "sleep": "energy",
    "play": "mood",
    "heal": "health",
}


@router.message(F.text == "Піклуватися")
async def care_message(
    message: Message,
    repo: Repo,
    pet_service: PetService,
    session_service: SessionService,
) -> None:
    user = await repo.get_user_by_telegram_id(message.from_user.id)
    if not user or not user.get("pet_type"):
        await message.answer("Спочатку обери тваринку.")
        return
    session = await session_service.get_active_session(user["id"])
    if session and session.get("awaiting_care"):
        await learning.show_care_gate(message, session, user, repo, pet_service)
        return
    status = await pet_service.get_or_create_status(user["id"])
    state = pet_service.pick_state(status)
    caption = f"Все добре!\n{pet_service.status_text(status)}"
    await answer_pet_card(
        message,
        user["pet_type"],
        state,
        caption,
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("care:"))
async def care_choice(
    callback: CallbackQuery,
    repo: Repo,
    pet_service: PetService,
    session_service: SessionService,
    task_service: TaskService,
    tts_service: TTSService,
) -> None:
    user = await repo.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Немає користувача.")
        return
    session = await session_service.get_active_session(user["id"])
    if not session or not session.get("awaiting_care"):
        await callback.answer("Наразі догляд не потрібен.")
        return
    care_data = repo.decode_care_json(session.get("care_json"))
    if not care_data:
        await callback.answer("Наразі догляд не потрібен.")
        return
    choice = callback.data.split(":", 1)[1]
    chosen_need = CARE_MAP.get(choice)
    if not chosen_need:
        await callback.answer("Невідома дія.")
        return
    status = await pet_service.apply_care_choice(
        user["id"], care_data["active_need"], chosen_need
    )
    session = await session_service.clear_care(session)
    state = pet_service.pick_state(status)
    caption = f"Дякую!\n{pet_service.status_text(status)}"
    await callback.message.answer(
        "✅ Догляд виконано.", reply_markup=main_menu_keyboard()
    )
    await answer_pet_card(
        callback.message,
        user["pet_type"],
        state,
        caption,
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()
    await learning.send_task(callback.message, session, task_service, tts_service)
