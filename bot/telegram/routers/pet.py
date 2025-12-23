from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command

from bot.telegram import AppContext
from bot.telegram.keyboards import BTN_PET, choose_pet_inline_kb
from bot.telegram.media import answer_photo_safe
from bot.telegram.routers.session import start_or_continue


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
        await answer_photo_safe(msg, path if (path and path.exists()) else None, caption=text)

    @router.message(Command("debug_pet_assets"))
    async def cmd_debug_pet_assets(message: types.Message) -> None:
        if ctx.admin_ids and message.from_user.id not in ctx.admin_ids:
            await message.answer("Недоступно.")
            return
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку /start")
            return
        pet = await ctx.pet_service.rollover_if_needed(user["id"])
        state_key = ctx.pet_service.pick_state(pet)
        path = ctx.pet_service.asset_path(pet.pet_type, state_key)
        exists = path.exists() if path else False
        size = None
        if exists:
            try:
                size = path.stat().st_size
            except Exception:
                size = None
        await message.answer(
            "\n".join(
                [
                    f"Assets root: {ctx.pet_service.assets_root}",
                    f"Pet: {pet.pet_type}",
                    f"State: {state_key}",
                    f"Path: {path if path else 'none'}",
                    f"Exists: {exists}",
                    f"Size: {size if size is not None else 'unknown'} bytes",
                ]
            )
        )

    @router.message(Command("choosepet"))
    async def cmd_choosepet(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку /start")
            return
        await message.answer(
            "Обери тваринку:",
            reply_markup=choose_pet_inline_kb(ctx.pet_service.available_pet_types()),
        )

    @router.callback_query(lambda c: c.data and (c.data.startswith("pick_pet:") or c.data.startswith("pet_choose:")))
    async def on_choose(callback: types.CallbackQuery) -> None:
        user = await ctx.repositories.users.get_user(callback.from_user.id)
        if not user:
            await callback.answer("/start", show_alert=True)
            return
        _, pet_type = callback.data.split(":", 1)
        previous_pet = await ctx.repositories.pets.load_pet(user["id"])
        await ctx.pet_service.ensure_pet(user["id"])
        await ctx.pet_service.choose_pet(user["id"], pet_type)
        await callback.answer()
        await callback.message.answer(f"✅ Обрано: {pet_type}")
        await _send_pet_card(callback, user["id"])
        await start_or_continue(ctx, callback.message, level=None, user_id=user["telegram_id"])

    @router.message(Command("pet"))
    async def cmd_pet(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку /start")
            return
        pet_row = await ctx.repositories.pets.load_pet(user["id"])
        if pet_row is None:
            await message.answer(
                "Спочатку обери тваринку:",
                reply_markup=choose_pet_inline_kb(ctx.pet_service.available_pet_types()),
            )
            return
        await _send_pet_card(message, user["id"])

    @router.message(F.text == BTN_PET)
    async def on_pet_button(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Спочатку /start")
            return
        pet_row = await ctx.repositories.pets.load_pet(user["id"])
        if pet_row is None:
            await message.answer(
                "Спочатку обери тваринку:",
                reply_markup=choose_pet_inline_kb(ctx.pet_service.available_pet_types()),
            )
            return
        await _send_pet_card(message, user["id"])

    return router
