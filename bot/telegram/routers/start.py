from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command, CommandStart

from bot.telegram import AppContext
from bot.telegram.keyboards import choose_pet_inline_kb, main_menu_kb


def setup_start_router(ctx: AppContext) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: types.Message) -> None:
        user_id = await ctx.repositories.users.upsert_user(message.from_user.id, message.from_user.username)
        await ctx.repositories.user_settings.ensure_settings(user_id, timezone=ctx.timezone)
        existing_pet = await ctx.repositories.pets.load_pet(user_id)
        await ctx.pet_service.ensure_pet(user_id)
        await ctx.pet_service.rollover_if_needed(user_id)
        if existing_pet is None:
            await message.answer("Обери свою тваринку:", reply_markup=choose_pet_inline_kb())
        await message.answer(
            "Привіт! Ми читаємо разом, щоб піклуватися про тваринку.\n"
            "Натисни «Піклуватися», щоб почати читання.\n"
            "Натисни «Моя тваринка», щоб дізнатися, що потрібно зробити сьогодні.",
            reply_markup=main_menu_kb(),
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
            await message.answer("Готово.")
        else:
            token = await ctx.health_service.generate_revive(user["id"])
            await message.answer(f"Токен на відновлення: {token}")

    return router
