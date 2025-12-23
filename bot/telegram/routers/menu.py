from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from bot.telegram import AppContext


def setup_menu_router(ctx: AppContext) -> Router:
    router = Router()

    @router.message(Command("menu"))
    async def cmd_menu(message: types.Message) -> None:
        user = await ctx.repositories.users.get_user(message.from_user.id)
        if not user:
            await message.answer("Спочатку надішліть /start")
            return
        progress_parts = []
        for level in (1, 2, 3):
            progress = await ctx.progress_service.get_progress(user["id"], level)
            progress_parts.append(f"Рівень {level}: {progress}")
        stats = await ctx.progress_service.get_today_stats(user["id"])
        streak = stats["streak"] if stats else 0
        hearts = await ctx.health_service.get_hearts(user["id"])
        await ctx.pet_service.ensure_pet(user["id"])
        pet = await ctx.pet_service.rollover_if_needed(user["id"])
        worst_need = ctx.pet_service.pick_state(pet)
        await message.answer(
            "\n".join(progress_parts)
            + f"\nStreak today / Серія сьогодні: {streak}"
            + f"\nHearts / Серця: {hearts}"
            + f"\nPet state / Стан тваринки: {worst_need}"
        )

    return router
