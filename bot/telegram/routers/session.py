from __future__ import annotations

import json

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject

from bot.telegram import AppContext
from bot.telegram.keyboards import BTN_CARE, care_inline_kb, repeat_inline_kb


def setup_session_router(ctx: AppContext) -> Router:
    router = Router()

    async def _ensure_user(message: types.Message):
        return await ctx.repositories.users.get_user(message.from_user.id)

    async def _send_current_task(message: types.Message, state) -> None:
        current = state.current_item()
        if not current:
            await message.answer("Немає карток для показу.")
            return
        item = await ctx.session_service.get_current_item(current)
        await ctx.task_presenter.send_listen_and_read(message, item, reply_markup=repeat_inline_kb())

    async def _start_or_continue(message: types.Message, level: int | None = None) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку натисни /start")
            return

        await ctx.pet_service.ensure_pet(user["id"])
        pet = await ctx.pet_service.rollover_if_needed(user["id"])

        state = await ctx.session_service.get_active_session(user["id"])

        if pet.is_dead:
            if not state or state.mode != "revival":
                await ctx.session_service.start_revival(user_id=user["id"], level=level or int(user.get("current_level", 1)))
                state = await ctx.session_service.get_active_session(user["id"])
                await message.answer("Тваринка померла. Починаємо відновлення: 20 карток.")
            if state:
                await _send_current_task(message, state)
            return

        if state:
            if state.mode == "normal" and state.awaiting_care:
                options = ["feed", "water", "play"]
                if state.care_json:
                    try:
                        data = json.loads(state.care_json)
                        options = data.get("options", options)
                    except Exception:
                        options = options
                await message.answer("Подбай про тваринку:", reply_markup=care_inline_kb(options))
                return
            await _send_current_task(message, state)
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
        await _send_current_task(message, state)

    # Kid main button
    @router.message(F.text == BTN_CARE)
    async def on_read_button(message: types.Message) -> None:
        await _start_or_continue(message, level=None)

    @router.message(Command("session"))
    async def cmd_session(message: types.Message, command: CommandObject) -> None:
        # Dev shortcut: /session [level]
        level = int(command.args) if command.args and command.args.isdigit() else 1
        await _start_or_continue(message, level=level)

    return router
