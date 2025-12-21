from __future__ import annotations

from aiogram import Router, types

from bot.telegram import AppContext
from bot.telegram.keyboards import main_menu_kb


def setup_start_router(ctx: AppContext) -> Router:
    router = Router()

    @router.message(commands=["start"])
    async def cmd_start(message: types.Message) -> None:
        user_id = await ctx.repositories.users.upsert_user(message.from_user.id, message.from_user.username)
        await ctx.repositories.user_settings.ensure_settings(user_id, timezone=ctx.timezone)
        await ctx.health_service.gain_heart(user_id)
        await message.answer(
            "Вітаємо в мовному тренажері! Оберіть рівень та розпочніть першу сесію.",
            reply_markup=main_menu_kb(),
        )

    @router.message(commands=["revive"])
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
