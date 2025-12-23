from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command, CommandStart

from bot.telegram import AppContext
from bot.telegram.keyboards import main_menu_kb, choose_pet_inline_kb


def setup_start_router(ctx: AppContext) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: types.Message) -> None:
        user_id = await ctx.repositories.users.upsert_user(message.from_user.id, message.from_user.username)
        await ctx.repositories.user_settings.ensure_settings(user_id, timezone=ctx.timezone)
        await ctx.health_service.gain_heart(user_id)
        await ctx.pet_service.ensure_pet(user_id)
        await message.answer(
            "Welcome! / Вітаємо!\nChoose a level and start a session. / Обери рівень і почни сесію.",
            reply_markup=main_menu_kb(),
        )
        await message.answer(
            "Choose your animal / Обери тваринку:",
            reply_markup=choose_pet_inline_kb(),
        )

    @router.message(Command("revive"))
    async def cmd_revive(message: types.Message) -> None:
        user = await ctx.repositories.users.get_user(message.from_user.id)
        if not user:
            await message.answer("Спочатку надішліть /start")
            return
        ok = await ctx.health_service.use_revive(user["id"])
        if ok:
            active = await ctx.session_service.get_active_session(user["id"])
            if active:
                await ctx.session_service.revive_session(active.session_id)
            await message.answer("Сесія розблокована, серця відновлено до 3.")
        else:
            token = await ctx.health_service.generate_revive(user["id"])
            await message.answer(f"Токен на відновлення: {token}")

    return router
