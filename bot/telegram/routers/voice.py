from __future__ import annotations

import logging
from io import BytesIO

from aiogram import Router, types
from aiogram.filters import Command

from bot.telegram import AppContext

logger = logging.getLogger(__name__)


def setup_voice_router(ctx: AppContext) -> Router:
    router = Router()

    async def _load_active(message: types.Message):
        user = await ctx.repositories.users.get_user(message.from_user.id)
        if not user:
            await message.answer("Спочатку надішліть /start")
            return None, None
        state = await ctx.session_service.get_active_session(user["id"])
        return user, state

    @router.message(Command("hint"))
    async def cmd_hint(message: types.Message) -> None:
        user, state = await _load_active(message)
        if not user or not state:
            return
        item = await ctx.session_service.get_current_item(state.level, state.item_index)
        await message.answer(item.hint or "Підказка відсутня.")

    @router.message(Command("stop"))
    async def cmd_stop(message: types.Message) -> None:
        user, state = await _load_active(message)
        if not user or not state:
            return
        await ctx.session_service.complete_session(state.session_id, user["id"], state.level, 0, state.total_items)
        await message.answer("Сесію завершено.")

    @router.message(content_types=types.ContentType.VOICE)
    async def handle_voice(message: types.Message) -> None:
        user, state = await _load_active(message)
        if not user:
            return
        if not state:
            await message.answer("Немає активної сесії. Надішліть /session 1 щоб почати.")
            return
        if state.blocked:
            await message.answer("Серця закінчились. Використайте /revive щоб продовжити.")
            return
        file = await message.bot.get_file(message.voice.file_id)
        file_bytes = await message.bot.download_file(file.file_path, BytesIO())
        audio_bytes = file_bytes.getvalue()

        item = await ctx.session_service.get_current_item(state.level, state.item_index)
        transcript, score, ok = await ctx.speech_service.evaluate_async(audio_bytes, item.answer)
        await ctx.session_service.record_attempt(
            session_id=state.session_id,
            prompt=item.prompt,
            user_answer=transcript,
            correct_answer=item.answer,
            is_correct=ok,
        )
        streak = await ctx.progress_service.update_after_attempt(user["id"], state.level, ok)
        if ok:
            await ctx.session_service.advance_item(state.session_id)
            finished = await ctx.session_service.finish_if_needed(state.session_id, user["id"], state.level)
            if finished:
                await message.answer(f"Сесію завершено! Серія сьогодні: {streak}")
            else:
                next_state = await ctx.session_service.get_active_session(user["id"])
                if next_state:
                    next_item = await ctx.session_service.get_current_item(next_state.level, next_state.item_index)
                    await message.answer(f"✅ {score} — Правильно!\nНаступне завдання: {next_item.prompt}")
                else:
                    await message.answer("✅ Правильно!")
        else:
            hearts = await ctx.health_service.lose_heart(user["id"])
            if hearts == 0:
                await ctx.session_service.block_session(state.session_id)
                await message.answer("❌ Неправильно. Серця закінчились. /revive щоб продовжити.")
            else:
                await message.answer(f"❌ Неправильно ({score}). Залишилось сердець: {hearts}")

    return router
