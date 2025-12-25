from __future__ import annotations

import json

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from bot.telegram import AppContext
from bot.telegram.keyboards import BTN_CARE, care_inline_kb, choose_pet_inline_kb, repeat_inline_kb
from bot.telegram.media_utils import answer_photo_or_text


async def _send_current_task(ctx: AppContext, message: types.Message, state) -> None:
    current = state.current_item()
    if not current:
        await message.answer("Немає карток для показу.")
        return
    item = await ctx.session_service.get_current_item(current)
    await ctx.task_presenter.send_listen_and_read(message, item, reply_markup=repeat_inline_kb())


async def start_or_continue(
    ctx: AppContext, message: types.Message, level: int | None = None, user_id: int | None = None
) -> None:
    telegram_id = user_id or message.from_user.id
    user = await ctx.repositories.users.get_user(telegram_id)
    if not user:
        await message.answer("Спочатку натисни /start")
        return

    pet_row = await ctx.repositories.pets.load_pet(user["id"])
    if pet_row is None:
        await message.answer(
            "Спочатку обери тваринку:",
            reply_markup=choose_pet_inline_kb(ctx.pet_service.available_pet_types()),
        )
        return

    pet = await ctx.pet_service.rollover_if_needed(user["id"])
    state = await ctx.session_service.get_active_session(user["id"])

    if pet.is_dead:
        if not state or state.mode != "revival":
            await ctx.session_service.start_revival(
                user_id=user["id"], level=level or int(user.get("current_level", 1))
            )
            state = await ctx.session_service.get_active_session(user["id"])
            await message.answer("Тваринка померла. Починаємо відновлення: 20 карток.")
        if state:
            pet_now = await ctx.pet_service.rollover_if_needed(user["id"])
            img = ctx.pet_service.asset_path(pet_now.pet_type, ctx.pet_service.pick_state(pet_now))
            await answer_photo_or_text(message, img, ctx.pet_service.status_text(pet_now))
            await _send_current_task(ctx, message, state)
        return

    if state:
        if state.mode == "normal" and state.awaiting_care:
            options = ["feed", "water", "play"]
            need_state = None
            if state.care_json:
                try:
                    data = json.loads(state.care_json)
                    options = data.get("options", options)
                    need_state = data.get("need_state")
                except Exception:
                    pass
            pet = await ctx.pet_service.rollover_if_needed(user["id"])
            img = ctx.pet_service.asset_path(pet.pet_type, need_state) if need_state else None
            await answer_photo_or_text(
                message,
                img,
                "Подбай про тваринку:",
                reply_markup=care_inline_kb(options),
            )
            return
        await _send_current_task(ctx, message, state)
        return

    user_level = level if level is not None else int(user.get("current_level", 1))
    await ctx.session_service.start_session(user_id=user["id"], level=user_level, deadline_minutes=240, total_items=10)
    state = await ctx.session_service.get_active_session(user["id"])
    if not state:
        await message.answer("Не вдалося почати сесію.")
        return
    if state.total_items == 0:
        await message.answer("Контент недоступний для цього рівня.")
        return
    pet = await ctx.pet_service.rollover_if_needed(user["id"])
    state_key = ctx.pet_service.pick_state(pet)
    img = ctx.pet_service.asset_path(pet.pet_type, state_key)
    caption = ctx.pet_service.status_text(pet)
    await answer_photo_or_text(message, img, caption)
    await _send_current_task(ctx, message, state)


def setup_session_router(ctx: AppContext) -> Router:
    router = Router()

    # Kid main button
    @router.message(F.text == BTN_CARE)
    async def on_read_button(message: types.Message) -> None:
        await start_or_continue(ctx, message, level=None)

    @router.message(Command("session"))
    async def cmd_session(message: types.Message, command: CommandObject) -> None:
        # Dev shortcut: /session [level]
        level = int(command.args) if command.args and command.args.isdigit() else 1
        await start_or_continue(ctx, message, level=level)

    @router.message(Command("next_session"))
    async def cmd_next_session(message: types.Message) -> None:
        user = await ctx.repositories.users.get_user(message.from_user.id)
        if not user:
            await message.answer("Спочатку натисни /start")
            return
        state = await ctx.session_service.get_active_session(user["id"])
        if state:
            await ctx.session_service.complete_session(
                state.session_id,
                user["id"],
                state.level,
                state.correct_count,
                state.total_items,
            )
        await start_or_continue(ctx, message, level=None, user_id=message.from_user.id)

    return router
