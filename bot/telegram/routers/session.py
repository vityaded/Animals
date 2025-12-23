from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile

from pathlib import Path

from bot.telegram import AppContext
from bot.telegram.keyboards import session_inline_kb


def setup_session_router(ctx: AppContext) -> Router:
    router = Router()

    async def _ensure_user(message: types.Message):
        return await ctx.repositories.users.get_user(message.from_user.id)

    async def _send_current_task(message: types.Message, state) -> None:
        item = await ctx.session_service.get_current_item(state.level, state.item_index)
        await message.answer(f"Завдання #{state.item_index + 1}: {item.prompt}", reply_markup=session_inline_kb())

    @router.message(Command("session"))
    async def cmd_session(message: types.Message, command: CommandObject) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку надішліть /start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        pet = await ctx.pet_service.apply_decay(user["id"])
        if pet.is_dead:
            await message.answer("Your pet is dead/asleep. Use /resurrect. / Твоя тваринка померла/спить. Використай /resurrect.")
            return
        # new session => reset per-session action tokens
        await ctx.pet_service.reset_action_tokens(user["id"])
        level = int(command.args) if command.args and command.args.isdigit() else 1
        session_id = await ctx.session_service.start_session(user_id=user["id"], level=level, deadline_minutes=90)
        state = await ctx.session_service.get_active_session(user["id"])
        if not state:
            await message.answer("Не вдалося запустити сесію.")
            return
        # show current pet state once at the start
        state_key = ctx.pet_service.pick_state(pet)
        img = ctx.pet_service.asset_path(pet.pet_type, state_key)
        if img and img.exists() and img.suffix.lower() in {".jpg", ".png"}:
            await message.answer_photo(
                FSInputFile(Path(img)),
                caption="Keep your pet happy: learn 10 units. After 5 correct answers you unlock a care action. / Тримай тваринку щасливою: 10 завдань. Після 5 правильних відкривається дія.",
            )
        await message.answer(f"Session #{session_id} started for level {level}. / Сесію #{session_id} (рівень {level}) запущено.")
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
