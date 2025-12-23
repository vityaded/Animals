from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile

from bot.telegram import AppContext
from bot.telegram.keyboards import BTN_PET, choose_pet_inline_kb


def setup_pet_router(ctx: AppContext) -> Router:
    router = Router()

    async def _ensure_user(message: types.Message):
        return await ctx.repositories.users.get_user(message.from_user.id)

    async def _send_pet_card(chat: types.Message | types.CallbackQuery, user_id: int) -> None:
        pet = await ctx.pet_service.rollover_if_needed(user_id)
        state_key = ctx.pet_service.pick_state(pet)
        path = ctx.pet_service.asset_path(pet.pet_type, state_key)
        text = ctx.pet_service.status_text(pet)
        msg = chat.message if isinstance(chat, types.CallbackQuery) else chat
        if path and path.exists():
            await msg.answer_photo(FSInputFile(path), caption=text)
        else:
            await msg.answer(text)

    @router.message(Command("choosepet"))
    async def cmd_choosepet(message: types.Message, command: CommandObject | None = None) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку /start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        await message.answer("Обери тваринку:", reply_markup=choose_pet_inline_kb())

    @router.callback_query(F.data.startswith("pet_choose:"))
    async def on_choose(callback: types.CallbackQuery) -> None:
        user = await ctx.repositories.users.get_user(callback.from_user.id)
        if not user:
            await callback.answer("/start", show_alert=True)
            return
        _, pet_type = callback.data.split(":", 1)
        await ctx.pet_service.ensure_pet(user["id"])
        await ctx.pet_service.choose_pet(user["id"], pet_type)
        await callback.message.answer(f"✅ Обрано: {pet_type}")
        await _send_pet_card(callback, user["id"])
        await callback.answer()

    @router.message(Command("pet"))
    async def cmd_pet(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку /start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        await _send_pet_card(message, user["id"])

    @router.message(F.text == BTN_PET)
    async def on_pet_button(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку /start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        await _send_pet_card(message, user["id"])

    return router
