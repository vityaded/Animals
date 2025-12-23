from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import Config
from bot.db.repo import Repo
from bot.services.asr_service import ASRService
from bot.services.pet_service import PetService
from bot.services.session_service import SessionService
from bot.services.task_service import TaskService
from bot.services.tts_service import TTSService
from bot.telegram.keyboards import care_keyboard, main_menu_keyboard
from bot.telegram.media_utils import answer_pet_card

router = Router()


async def start_or_continue(
    message: Message,
    user: dict,
    repo: Repo,
    config: Config,
    pet_service: PetService,
    session_service: SessionService,
    task_service: TaskService,
    tts_service: TTSService,
) -> None:
    session, created = await session_service.get_or_create_active_session(
        user["id"], user["difficulty"]
    )
    if session.get("awaiting_care"):
        await show_care_gate(message, session, user, repo, pet_service)
        return
    if created:
        status = await pet_service.get_or_create_status(user["id"])
        state = pet_service.pick_state(status)
        caption = f"Починаємо!\n{pet_service.status_text(status)}"
        await answer_pet_card(message, user["pet_type"], state, caption)
    await send_task(message, session, task_service, tts_service)


async def send_task(
    message: Message,
    session: dict,
    task_service: TaskService,
    tts_service: TTSService,
) -> None:
    target = task_service.get_task(session["difficulty"], session["task_index"])
    if not target:
        await message.answer("Немає завдань для цього рівня.")
        return
    audio_path = await tts_service.synthesize(target)
    caption = f"Прослухай і прочитай:\n{target}"
    await message.answer_audio(audio=audio_path, caption=caption)


async def show_care_gate(
    message: Message,
    session: dict,
    user: dict,
    repo: Repo,
    pet_service: PetService,
) -> None:
    care_data = repo.decode_care_json(session.get("care_json"))
    if not care_data:
        return
    caption = "Подбай про тваринку:"
    await answer_pet_card(
        message,
        user["pet_type"],
        care_data["need_state"],
        caption,
        reply_markup=None,
    )
    await message.answer(
        "Обери дію:",
        reply_markup=care_keyboard(care_data["options"]),
    )


@router.message(Command("stop"))
async def stop_session(
    message: Message,
    repo: Repo,
    pet_service: PetService,
    session_service: SessionService,
) -> None:
    user = await repo.get_user_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer("Сесію не знайдено.")
        return
    session = await session_service.get_active_session(user["id"])
    if not session:
        await message.answer("Сесію не знайдено.")
        return
    await session_service.end_session(session)
    status = await pet_service.get_or_create_status(user["id"])
    state = pet_service.pick_state(status)
    caption = f"Сесія завершена. Виконано завдань: {session['task_index']}\n{pet_service.status_text(status)}"
    await answer_pet_card(
        message,
        user["pet_type"],
        state,
        caption,
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.voice)
async def handle_voice(
    message: Message,
    repo: Repo,
    config: Config,
    pet_service: PetService,
    session_service: SessionService,
    task_service: TaskService,
    tts_service: TTSService,
    asr_service: ASRService,
) -> None:
    user = await repo.get_user_by_telegram_id(message.from_user.id)
    if not user or not user.get("pet_type"):
        return
    session = await session_service.get_active_session(user["id"])
    if not session or session.get("awaiting_care"):
        await message.answer("Спершу подбай про тваринку.")
        return
    target = task_service.get_task(session["difficulty"], session["task_index"])
    if not target:
        await message.answer("Немає завдань для цього рівня.")
        return
    is_match, _ = await asr_service.transcribe_and_match(message.bot, message.voice, target)
    if not is_match:
        await message.answer("❌ Спробуй ще раз")
        await send_task(message, session, task_service, tts_service)
        return

    await message.answer("✅ Добре!")
    correct_count = session["task_index"] + 1
    status = await pet_service.update_on_correct_answer(user["id"], correct_count)
    session = await session_service.advance_task(session)
    if session["task_index"] in config.care_gates and session["active"] == 1:
        session = await session_service.set_awaiting_care(session, status)
        await show_care_gate(message, session, user, repo, pet_service)
        return
    if session["active"] == 0:
        state = pet_service.pick_state(status)
        caption = (
            f"Сесія завершена. Виконано завдань: {session['task_index']}\n"
            f"{pet_service.status_text(status)}"
        )
        await answer_pet_card(
            message,
            user["pet_type"],
            state,
            caption,
            reply_markup=main_menu_keyboard(),
        )
        return
    await send_task(message, session, task_service, tts_service)
