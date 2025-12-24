from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from io import BytesIO

from aiogram import F, Router, types
from aiogram.filters import Command
from bot.telegram import AppContext
from bot.telegram.keyboards import (
    BTN_CARE,
    care_inline_kb,
    care_more_inline_kb,
    choose_pet_inline_kb,
    repeat_inline_kb,
)
from bot.telegram.media import answer_photo_safe
from bot.telegram.media_utils import answer_photo_or_text

logger = logging.getLogger(__name__)


def setup_voice_router(ctx: AppContext) -> Router:
    router = Router()

    async def _load_active(message: types.Message, telegram_id: int | None = None):
        # IMPORTANT:
        # - For normal messages: message.from_user.id is the user.
        # - For callback.message (bot's own message): message.from_user.id is the bot -> WRONG.
        uid = telegram_id if telegram_id is not None else message.from_user.id
        user = await ctx.repositories.users.get_user(uid)
        if not user:
            await message.answer("Спочатку надішліть /start")
            return None, None
        pet_row = await ctx.repositories.pets.load_pet(user["id"])
        if pet_row is None:
            await message.answer(
                "Спочатку обери тваринку:",
                reply_markup=choose_pet_inline_kb(ctx.pet_service.available_pet_types()),
            )
            return None, None
        state = await ctx.session_service.get_active_session(user["id"])
        return user, state

    async def _send_task(message: types.Message, state) -> None:
        deck_item = state.current_item()
        if not deck_item:
            await message.answer("Немає активної картки.")
            return
        item = await ctx.session_service.get_current_item(deck_item)
        await ctx.task_presenter.send_listen_and_read(message, item, reply_markup=repeat_inline_kb())

    @router.message(Command("stop"))
    async def cmd_stop(message: types.Message) -> None:
        user, state = await _load_active(message)
        if not user or not state:
            return
        await ctx.session_service.complete_session(state.session_id, user["id"], state.level, 0, state.total_items)
        await message.answer("Сесію завершено.")
        pet_now = await ctx.pet_service.rollover_if_needed(user["id"])
        img = ctx.pet_service.asset_path(pet_now.pet_type, ctx.pet_service.pick_state(pet_now))
        await answer_photo_or_text(message, img, ctx.pet_service.status_text(pet_now))

    async def _ensure_pet(user_id: int):
        return await ctx.pet_service.rollover_if_needed(user_id)

    async def _finalize_session(message: types.Message, state, wrong_total: int) -> None:
        await ctx.session_service.finish_if_needed(state.session_id, state.user_id, state.level)
        if state.mode == "normal":
            await ctx.pet_service.increment_sessions_today(state.user_id)
            if wrong_total <= 2:
                pet = await ctx.pet_service.apply_bonus(state.user_id)
                bonus_path = ctx.pet_service.asset_path(pet.pet_type, f"bonus_{random.randint(1,10)}")
                await answer_photo_safe(message, bonus_path if (bonus_path and bonus_path.exists()) else None)
            pet_now = await ctx.pet_service.rollover_if_needed(state.user_id)
            img = ctx.pet_service.asset_path(pet_now.pet_type, ctx.pet_service.pick_state(pet_now))
            await answer_photo_or_text(
                message,
                img,
                "✅ Готово!\n" + ctx.pet_service.status_text(pet_now),
                reply_markup=care_more_inline_kb(),
            )
        elif state.mode == "revival":
            await ctx.pet_service.revive(state.user_id)
            pet_now = await ctx.pet_service.rollover_if_needed(state.user_id)
            img = ctx.pet_service.asset_path(pet_now.pet_type, ctx.pet_service.pick_state(pet_now))
            await answer_photo_or_text(
                message,
                img,
                "✅ Відновлено!\n" + ctx.pet_service.status_text(pet_now),
                reply_markup=care_more_inline_kb(),
            )
        else:
            pet_now = await ctx.pet_service.rollover_if_needed(state.user_id)
            img = ctx.pet_service.asset_path(pet_now.pet_type, ctx.pet_service.pick_state(pet_now))
            await answer_photo_or_text(
                message,
                img,
                "✅ Готово!\n" + ctx.pet_service.status_text(pet_now),
                reply_markup=care_more_inline_kb(),
            )

    def _need_to_action(need_key: str) -> str:
        return {
            "hunger": "feed",
            "thirst": "water",
            "hygiene": "wash",
            "energy": "sleep",
            "mood": "play",
            "health": "heal",
        }.get(need_key, "feed")

    async def _schedule_care(user_id: int, state) -> tuple[list[str], str, str]:
        pet = await ctx.pet_service.rollover_if_needed(user_id)
        levels = {
            "hunger": pet.hunger_level,
            "thirst": pet.thirst_level,
            "hygiene": pet.hygiene_level,
            "energy": pet.energy_level,
            "mood": pet.mood_level,
            "health": pet.health_level,
        }
        max_level = max(levels.values())
        max_needs = [k for k, v in levels.items() if v == max_level]
        active_need = random.choice(max_needs)
        decoy_sources = [k for k, v in levels.items() if k != active_need and v > 1]
        if len(decoy_sources) < 2:
            decoy_sources = [k for k in levels.keys() if k != active_need]
        random.shuffle(decoy_sources)
        choices = [_need_to_action(active_need)]
        for key in decoy_sources:
            action = _need_to_action(key)
            if action not in choices:
                choices.append(action)
            if len(choices) >= 3:
                break
        while len(choices) < 3:
            for fallback in ["feed", "water", "wash", "sleep", "play", "heal"]:
                if fallback not in choices:
                    choices.append(fallback)
                if len(choices) >= 3:
                    break
        random.shuffle(choices)
        need_state = f"{active_need}_{levels[active_need]}"
        care_json = {"active_need": active_need, "need_state": need_state, "options": choices}
        await ctx.repositories.session_state.set_care_state(
            state.session_id, awaiting_care=1, care_stage=state.care_stage + 1, care_json=json.dumps(care_json)
        )
        return choices, active_need, need_state

    def _parse_ts(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            dt = datetime.fromisoformat(str(value).replace(" ", "T"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    async def _pick_freecare_two(user_id: int, level: int) -> list[str] | None:
        now = datetime.now(timezone.utc)
        recent_block = timedelta(minutes=30)

        rows = await ctx.repositories.item_progress.list_all(user_id)
        progress = {}
        for r in rows:
            key = (int(r["level"]), str(r["content_id"]))
            progress[key] = {
                "review_stage": int(r.get("review_stage") or 0),
                "last_seen_at": _parse_ts(r.get("last_seen_at")),
                "next_due_at": _parse_ts(r.get("next_due_at")),
            }

        def is_finished(cid: str) -> bool:
            meta = progress.get((level, cid))
            return bool(meta and meta["review_stage"] == 3)

        def is_due(cid: str) -> bool:
            meta = progress.get((level, cid))
            return bool(meta and meta["next_due_at"] and meta["next_due_at"] <= now)

        def is_recent(cid: str) -> bool:
            meta = progress.get((level, cid))
            return bool(meta and meta["last_seen_at"] and (now - meta["last_seen_at"]) < recent_block)

        items = ctx.content_service.get_level_items(level)
        chosen: list[str] = []
        for it in items:
            cid = it.id
            if is_finished(cid):
                continue
            if (not is_due(cid)) and is_recent(cid):
                continue
            chosen.append(cid)
            if len(chosen) == 2:
                return chosen

        return None

    @router.callback_query(F.data == "care_more")
    async def on_care_more(callback: types.CallbackQuery) -> None:
        user = await ctx.repositories.users.get_user(callback.from_user.id)
        if not user:
            await callback.answer("/start", show_alert=True)
            return
        pet_row = await ctx.repositories.pets.load_pet(user["id"])
        if pet_row is None:
            await callback.message.answer(
                "Спочатку обери тваринку:",
                reply_markup=choose_pet_inline_kb(ctx.pet_service.available_pet_types()),
            )
            await callback.answer()
            return

        active = await ctx.session_service.get_active_session(user["id"])
        if active and active.mode == "normal":
            await callback.answer("Зараз триває сесія.", show_alert=True)
            return

        current_level = int(user.get("current_level", 1))
        ids = await _pick_freecare_two(user["id"], current_level)

        if not ids:
            for lvl in ctx.content_service.available_levels():
                if lvl <= current_level:
                    continue
                ids = await _pick_freecare_two(user["id"], lvl)
                if ids:
                    current_level = lvl
                    break

        if not ids:
            await callback.answer("Немає доступних слів для «попіклуватися ще».", show_alert=True)
            return

        await ctx.session_service.start_freecare_gate(
            user_id=user["id"],
            level=current_level,
            content_ids=ids,
        )
        state = await ctx.session_service.get_active_session(user["id"])
        if state:
            await _send_task(callback.message, state)
        await callback.answer()

    @router.message(F.voice)
    async def handle_voice(message: types.Message) -> None:
        user, state = await _load_active(message)
        if not user:
            return
        if not state:
            await message.answer(f"Натисни «{BTN_CARE}».")
            return

        pet = await _ensure_pet(user["id"])
        if state.awaiting_care:
            await message.answer("Спочатку обери дію для тваринки.")
            return

        if pet.is_dead and state.mode != "revival":
            await message.answer(f"Тваринка померла. Натисни «{BTN_CARE}» щоб почати відновлення.")
            return

        file = await message.bot.get_file(message.voice.file_id)
        file_bytes = await message.bot.download_file(file.file_path, BytesIO())
        audio_bytes = file_bytes.getvalue()

        try:
            deck_item = state.current_item()
            if not deck_item:
                await message.answer("Картки закінчилися.")
                return
            item = await ctx.session_service.get_current_item(deck_item)
        except Exception:
            await message.answer("Контент недоступний.")
            return

        transcript, score, ok = await ctx.speech_service.evaluate_async(audio_bytes, item.text)
        is_first_try = state.current_attempts == 0
        await ctx.progress_service.update_after_attempt(user["id"], deck_item.level, ok, is_first_try)

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

        now_utc = datetime.now(timezone.utc)

        if ok:
            await ctx.repositories.item_progress.record_correct(
                user["id"], deck_item.level, deck_item.content_id, now_utc=now_utc
            )
            await ctx.repositories.session_state.increment_correct(state.session_id)
            await ctx.session_service.advance_item(state.session_id)
            await message.answer("✅ Добре!")
        else:
            await ctx.repositories.session_state.increment_wrong_total(state.session_id)
            await ctx.repositories.item_progress.record_wrong(
                user["id"], deck_item.level, deck_item.content_id, now_utc=now_utc
            )
            attempts = state.current_attempts + 1
            if attempts >= 5:
                await message.answer("Йдемо далі")
                await ctx.session_service.advance_item(state.session_id)
            else:
                await ctx.repositories.session_state.update_attempts(state.session_id, attempts)
                await message.answer("❌ Спробуй ще раз")
                await _send_task(message, await ctx.session_service.get_active_session(user["id"]))
                return

        updated_state = await ctx.session_service.get_active_session(user["id"])
        if not updated_state:
            return
        processed = updated_state.item_index

        # Freecare: after BOTH words are read correctly, unlock one care choice.
        if updated_state.mode == "freecare" and processed >= updated_state.total_items and updated_state.care_stage < 1:
            options, _, need_state = await _schedule_care(user["id"], updated_state)
            pet = await ctx.pet_service.rollover_if_needed(user["id"])
            img = ctx.pet_service.asset_path(pet.pet_type, need_state)
            await answer_photo_or_text(
                message,
                img,
                "Подбай про тваринку:",
                reply_markup=care_inline_kb(options),
            )
            return

        # Otherwise (word #1 done but word #2 not yet), continue by sending the next word normally.

        if updated_state.mode == "normal" and processed in (5, 10) and updated_state.care_stage < (1 if processed == 5 else 2):
            options, _, need_state = await _schedule_care(user["id"], updated_state)

            pet = await ctx.pet_service.rollover_if_needed(user["id"])
            img = ctx.pet_service.asset_path(pet.pet_type, need_state)

            await answer_photo_or_text(
                message,
                img,
                "Подбай про тваринку:",
                reply_markup=care_inline_kb(options),
            )
            return

        if updated_state.item_index >= updated_state.total_items:
            wrong_total = updated_state.wrong_total
            await _finalize_session(message, updated_state, wrong_total)
        else:
            await _send_task(message, updated_state)

    @router.callback_query(F.data == "repeat:current")
    async def on_repeat(callback: types.CallbackQuery) -> None:
        user, state = await _load_active(callback.message, telegram_id=callback.from_user.id)
        if not user or not state:
            await callback.answer()
            return
        await _send_task(callback.message, state)
        await callback.answer()

    @router.callback_query(F.data.startswith("care:"))
    async def on_care(callback: types.CallbackQuery) -> None:
        user, state = await _load_active(callback.message, telegram_id=callback.from_user.id)
        if not user or not state:
            await callback.answer()
            return
        if not state.care_json:
            await callback.answer("Сесія недоступна", show_alert=True)
            return
        try:
            care_data = json.loads(state.care_json)
        except Exception:
            care_data = {}
        action = callback.data.split(":", 1)[1]
        options = care_data.get("options", [])
        active_need = care_data.get("active_need")
        if action not in options:
            await callback.answer("Використай кнопки нижче.", show_alert=True)
            return

        status = await ctx.pet_service.apply_care_choice(user["id"], action, active_need)
        await ctx.repositories.session_state.set_care_state(state.session_id, awaiting_care=0, care_json=None)
        image_key = ctx.pet_service.pick_state(status)
        img = ctx.pet_service.asset_path(status.pet_type, image_key)
        await answer_photo_safe(callback.message, img if (img and img.exists()) else None, caption="Тваринка рада")
        updated_state = await ctx.session_service.get_active_session(user["id"])
        if not updated_state:
            await callback.answer()
            return
        if updated_state.item_index >= updated_state.total_items:
            await _finalize_session(callback.message, updated_state, updated_state.wrong_total)
        else:
            await _send_task(callback.message, updated_state)
        await callback.answer()

    return router
