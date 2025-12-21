from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import CommandObject

from bot.telegram import AppContext
from bot.telegram.keyboards import session_inline_kb


def setup_session_router(ctx: AppContext) -> Router:
    router = Router()

    async def _ensure_user(message: types.Message):
        return await ctx.repositories.users.get_user(message.from_user.id)

    async def _send_current_task(message: types.Message, state) -> None:
        item = await ctx.session_service.get_current_item(state.level, state.item_index)
        await message.answer(f"Завдання #{state.item_index + 1}: {item.prompt}", reply_markup=session_inline_kb())

    @router.message(commands=["session"])
    async def cmd_session(message: types.Message, command: CommandObject) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку надішліть /start")
            return
        level = int(command.args) if command.args and command.args.isdigit() else 1
        session_id = await ctx.session_service.start_session(user_id=user["id"], level=level, deadline_minutes=90)
        state = await ctx.session_service.get_active_session(user["id"])
        if not state:
            await message.answer("Не вдалося запустити сесію.")
            return
        await message.answer(f"Сесія #{session_id} для рівня {level} запущена.")
        await _send_current_task(message, state)

    @router.callback_query(F.data == "session_hint")
    async def on_hint(callback: types.CallbackQuery) -> None:
        user = await _ensure_user(callback.message)
        if not user:
            await callback.answer("Спочатку /start")
            return
        state = await ctx.session_service.get_active_session(user["id"])
        if not state:
            await callback.answer("Немає активної сесії", show_alert=True)
            return
        item = await ctx.session_service.get_current_item(state.level, state.item_index)
        await callback.message.answer(item.hint or "Підказка відсутня.")
        await callback.answer()

    @router.callback_query(F.data == "session_stop")
    async def on_stop(callback: types.CallbackQuery) -> None:
        user = await _ensure_user(callback.message)
        if not user:
            await callback.answer("Спочатку /start")
            return
        state = await ctx.session_service.get_active_session(user["id"])
        if not state:
            await callback.answer("Сесія не активна", show_alert=True)
            return
        await ctx.session_service.complete_session(state.session_id, user["id"], state.level, 0, state.total_items)
        await callback.message.answer("Сесію завершено.")
        await callback.answer()

    return router
