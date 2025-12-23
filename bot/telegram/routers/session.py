from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from bot.telegram import AppContext
from bot.telegram.keyboards import BTN_READ


def setup_session_router(ctx: AppContext) -> Router:
    router = Router()

    async def _ensure_user(message: types.Message):
        return await ctx.repositories.users.get_user(message.from_user.id)

    async def _send_current_task(message: types.Message, state) -> None:
        item = await ctx.session_service.get_current_item(state.level, state.deck_ids, state.item_index)
        await ctx.task_presenter.send_listen_and_read(message, item)

    def _today_range_utc() -> tuple[datetime, datetime]:
        tz = ZoneInfo(ctx.timezone)
        now_local = datetime.now(tz)
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

    async def _start_or_continue(message: types.Message, level: int | None = None) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку натисни /start")
            return

        await ctx.pet_service.ensure_pet(user["id"])
        pet = await ctx.pet_service.apply_decay(user["id"])

        state = await ctx.session_service.get_active_session(user["id"])

        # If pet is dead/asleep -> auto-start resurrection when user presses "Прочитай".
        if pet.is_dead:
            if not state or state.mode != "resurrect":
                await ctx.pet_service.reset_action_tokens(user["id"])
                await ctx.session_service.start_resurrection(user_id=user["id"], level=1)
                state = await ctx.session_service.get_active_session(user["id"])
                await message.answer("Тваринка заснула. Прочитай 20 разів підряд без помилки, щоб оживити.")
            if state:
                await _send_current_task(message, state)
            return

        # Continue existing session.
        if state:
            await _send_current_task(message, state)
            return

        # Start a new session (max 2 per day).
        start_utc, end_utc = _today_range_utc()
        sessions_today = await ctx.repositories.sessions.count_sessions_started_between(user["id"], start_utc, end_utc)
        if sessions_today >= 2:
            await message.answer("На сьогодні все. Побачимось завтра.")
            return

        user_level = level if level is not None else int(user.get("current_level", 1))
        await ctx.pet_service.reset_action_tokens(user["id"])
        await ctx.session_service.start_session(user_id=user["id"], level=user_level, deadline_minutes=240)
        state = await ctx.session_service.get_active_session(user["id"])
        if not state:
            await message.answer("Не вдалося почати сесію.")
            return
        if state.total_items == 0:
            await message.answer("Контент недоступний для цього рівня.")
            return
        await _send_current_task(message, state)

    # Kid main button
    @router.message(F.text == BTN_READ)
    async def on_read_button(message: types.Message) -> None:
        await _start_or_continue(message, level=1)

    @router.message(Command("session"))
    async def cmd_session(message: types.Message, command: CommandObject) -> None:
        # Dev shortcut: /session [level]
        level = int(command.args) if command.args and command.args.isdigit() else 1
        await _start_or_continue(message, level=level)

    return router
