from __future__ import annotations

import logging
from io import BytesIO

from aiogram import F, Router, types
from aiogram.filters import Command

from bot.telegram import AppContext
from bot.telegram.keyboards import BTN_READ, care_actions_inline_kb

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

    async def _send_task(message: types.Message, state) -> None:
        item = await ctx.session_service.get_current_item(state.level, state.deck_ids, state.item_index)
        await ctx.task_presenter.send_listen_and_read(message, item)

    @router.message(Command("stop"))
    async def cmd_stop(message: types.Message) -> None:
        user, state = await _load_active(message)
        if not user or not state:
            return
        await ctx.session_service.complete_session(state.session_id, user["id"], state.level, 0, state.total_items)
        await message.answer("Сесію завершено.")

    @router.message(F.voice)
    async def handle_voice(message: types.Message) -> None:
        user, state = await _load_active(message)
        if not user:
            return
        if not state:
            await message.answer(f"Натисни «{BTN_READ}».")
            return

        await ctx.pet_service.ensure_pet(user["id"])
        pet = await ctx.pet_service.apply_decay(user["id"])
        if pet.is_dead and state.mode != "resurrect":
            await message.answer(f"Тваринка заснула. Натисни «{BTN_READ}» щоб оживити.")
            return

        file = await message.bot.get_file(message.voice.file_id)
        file_bytes = await message.bot.download_file(file.file_path, BytesIO())
        audio_bytes = file_bytes.getvalue()

        try:
            item = await ctx.session_service.get_current_item(state.level, state.deck_ids, state.item_index)
        except Exception:
            await message.answer("Контент недоступний.")
            return

        transcript, score, ok = await ctx.speech_service.evaluate_async(audio_bytes, item.text)
        is_first_try = state.current_attempts == 0

        await ctx.session_service.record_attempt(
            session_id=state.session_id,
            user_id=user["id"],
            content_id=item.id,
            expected_text=item.text,
            transcript=transcript,
            similarity=score,
            is_first_try=is_first_try,
            is_correct=ok,
        )

        if state.mode == "resurrect":
            streak = await ctx.pet_service.resurrect_progress(user["id"], ok)
            if ok:
                await ctx.session_service.advance_item(state.session_id)
                if streak >= 20:
                    await ctx.pet_service.revive(user["id"])
                    await ctx.session_service.complete_session(state.session_id, user["id"], state.level, 0, state.total_items)
                    await message.answer("✅ Тваринка ожила!")
                    pet2 = await ctx.pet_service.apply_decay(user["id"])
                    state_key = ctx.pet_service.pick_state(pet2)
                    path = ctx.pet_service.asset_path(pet2.pet_type, state_key)
                    if path:
                        from aiogram.types import FSInputFile
                        from pathlib import Path

                        if path.exists() and path.suffix.lower() in {".jpg", ".png"}:
                            await message.answer_photo(FSInputFile(Path(path)))
                    return
                next_state = await ctx.session_service.get_active_session(user["id"])
                if next_state:
                    next_item = await ctx.session_service.get_current_item(
                        next_state.level, next_state.deck_ids, next_state.item_index
                    )
                    await message.answer(f"✅ {streak}/20")
                    await ctx.task_presenter.send_listen_and_read(message, next_item)
                else:
                    await message.answer(f"✅ {streak}/20")
            else:
                await ctx.repositories.session_state.update_attempts(state.session_id, state.current_attempts + 1)
                await message.answer("Спробуй ще раз.")
                await _send_task(message, state)
            return

        await ctx.progress_service.update_after_attempt(user["id"], state.level, ok, is_first_try)

        if ok:
            await ctx.pet_service.on_correct(user["id"])
            await ctx.repositories.item_progress.mark_passed(user["id"], state.level, item.id)
            new_correct = await ctx.repositories.session_state.increment_correct(state.session_id)
            row = await ctx.repositories.session_state.get_state(state.session_id)
            reward_stage = int(row["reward_stage"]) if row and "reward_stage" in row.keys() else 0
            if new_correct >= 5 and reward_stage < 1:
                await ctx.pet_service.add_action_token(user["id"])
                await ctx.repositories.session_state.set_reward_stage(state.session_id, 1)
                await message.answer("Обери, що зробити з тваринкою:", reply_markup=care_actions_inline_kb())
            if new_correct >= 10 and reward_stage < 2:
                await ctx.pet_service.add_action_token(user["id"])
                await ctx.repositories.session_state.set_reward_stage(state.session_id, 2)
                await message.answer("Ще одна дія для тваринки:", reply_markup=care_actions_inline_kb())

            await ctx.session_service.advance_item(state.session_id)
            finished = await ctx.session_service.finish_if_needed(state.session_id, user["id"], state.level)
            if finished:
                await ctx.pet_service.on_session_completed(user["id"])
                await message.answer("Готово!")
                pet2 = await ctx.pet_service.apply_decay(user["id"])
                state_key = ctx.pet_service.pick_state(pet2)
                path = ctx.pet_service.asset_path(pet2.pet_type, state_key)
                if path:
                    from aiogram.types import FSInputFile
                    from pathlib import Path

                    if path.exists() and path.suffix.lower() in {".jpg", ".png"}:
                        await message.answer_photo(FSInputFile(Path(path)))
            else:
                next_state = await ctx.session_service.get_active_session(user["id"])
                if next_state:
                    next_item = await ctx.session_service.get_current_item(
                        next_state.level, next_state.deck_ids, next_state.item_index
                    )
                    await message.answer("✅")
                    await ctx.task_presenter.send_listen_and_read(message, next_item)
                else:
                    await message.answer("✅")
        else:
            await ctx.repositories.session_state.update_attempts(state.session_id, state.current_attempts + 1)
            await ctx.pet_service.on_wrong(user["id"])
            await message.answer("Спробуй ще раз.")
            await _send_task(message, state)

    return router
