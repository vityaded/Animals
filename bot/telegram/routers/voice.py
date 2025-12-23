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
        await ctx.pet_service.ensure_pet(user["id"])
        pet = await ctx.pet_service.apply_decay(user["id"])
        if pet.is_dead and state.mode != "resurrect":
            await message.answer("Your pet is dead/asleep. Use /resurrect. / Твоя тваринка померла/спить. Використай /resurrect.")
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
        if state.mode == "resurrect":
            # Resurrection: 20 correct answers in a row.
            streak = await ctx.pet_service.resurrect_progress(user["id"], ok)
            if ok:
                await ctx.session_service.advance_item(state.session_id)
                if streak >= 20:
                    await ctx.pet_service.revive(user["id"])
                    await ctx.session_service.complete_session(state.session_id, user["id"], state.level, 0, state.total_items)
                    await message.answer("✅ Pet revived! / Тваринку воскресили!")
                    # Show pet card
                    pet2 = await ctx.pet_service.apply_decay(user["id"])
                    state_key = ctx.pet_service.pick_state(pet2)
                    path = ctx.pet_service.asset_path(pet2.pet_type, state_key)
                    if path:
                        from aiogram.types import FSInputFile
                        from pathlib import Path

                        if path.exists() and path.suffix.lower() in {".jpg", ".png"}:
                            await message.answer_photo(FSInputFile(Path(path)), caption=ctx.pet_service.status_text(pet2))
                    return
                next_state = await ctx.session_service.get_active_session(user["id"])
                if next_state:
                    next_item = await ctx.session_service.get_current_item(next_state.level, next_state.item_index)
                    await message.answer(
                        f"✅ Correct. Streak: {streak}/20. Next: {next_item.prompt}\n"
                        f"✅ Правильно. Серія: {streak}/20. Далі: {next_item.prompt}"
                    )
                else:
                    await message.answer(f"✅ Correct. Streak: {streak}/20 / Правильно: {streak}/20")
            else:
                await message.answer(f"❌ Wrong. Streak reset: {streak}/20 / Неправильно. Серія скинута: {streak}/20")
            return

        # Normal learning mode
        streak = await ctx.progress_service.update_after_attempt(user["id"], state.level, ok)
        if ok:
            await ctx.pet_service.on_correct(user["id"])
            new_correct = await ctx.repositories.session_state.increment_correct(state.session_id)
            # Unlock care actions at 5 and 10 correct answers.
            row = await ctx.repositories.session_state.get_state(state.session_id)
            reward_stage = int(row["reward_stage"]) if row and "reward_stage" in row.keys() else 0
            if new_correct >= 5 and reward_stage < 1:
                await ctx.pet_service.add_action_token(user["id"])
                await ctx.repositories.session_state.set_reward_stage(state.session_id, 1)
                await message.answer("🎁 Care action unlocked! Use /feed /water /wash /sleep /play /heal\nДію відкрито! Використай /feed /water /wash /sleep /play /heal")
            if new_correct >= 10 and reward_stage < 2:
                await ctx.pet_service.add_action_token(user["id"])
                await ctx.repositories.session_state.set_reward_stage(state.session_id, 2)
                await message.answer("🎁 Second care action unlocked! / Другу дію відкрито!")

            await ctx.session_service.advance_item(state.session_id)
            finished = await ctx.session_service.finish_if_needed(state.session_id, user["id"], state.level)
            if finished:
                await ctx.pet_service.on_session_completed(user["id"])
                await message.answer(f"Session finished! Streak today: {streak} / Сесію завершено! Серія: {streak}")
            else:
                next_state = await ctx.session_service.get_active_session(user["id"])
                if next_state:
                    next_item = await ctx.session_service.get_current_item(next_state.level, next_state.item_index)
                    await message.answer(f"✅ {score} — Correct! Next: {next_item.prompt}\n✅ {score} — Правильно! Далі: {next_item.prompt}")
                else:
                    await message.answer("✅ Correct! / Правильно!")
        else:
            await ctx.pet_service.on_wrong(user["id"])
            hearts = await ctx.health_service.lose_heart(user["id"])
            if hearts == 0:
                await ctx.session_service.block_session(state.session_id)
                await message.answer("❌ Wrong. No hearts. Use /revive. / Неправильно. Серця закінчились. /revive")
            else:
                await message.answer(f"❌ Wrong ({score}). Hearts left: {hearts} / Неправильно. Сердець: {hearts}")

    return router
