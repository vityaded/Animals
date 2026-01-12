from __future__ import annotations

import json
import logging

from aiogram import F, Router, types

from bot.telegram import AppContext
from bot.telegram.keyboards import care_inline_kb, choose_pet_inline_kb, main_menu_kb, repeat_inline_kb
from bot.telegram.media_utils import answer_photo_or_text

logger = logging.getLogger(__name__)


def setup_fallback_router(ctx: AppContext) -> Router:
    router = Router()

    def _parse_care_options(state) -> tuple[list[str], str | None]:
        options = ["feed", "water", "play"]
        need_state = None
        if state.care_json:
            try:
                data = json.loads(state.care_json)
                options = data.get("options", options)
                need_state = data.get("need_state")
            except Exception:
                pass
        return options, need_state

    async def _send_task(message: types.Message, state) -> None:
        deck_item = state.current_item()
        if not deck_item:
            if state.item_index >= state.total_items:
                await ctx.session_service.finish_if_needed(state.session_id, state.user_id, state.level)
                await message.answer(
                    "Сесію завершено. Натисни «Піклуватися», щоб почати знову.",
                    reply_markup=main_menu_kb(),
                )
                return
            deck = await ctx.session_service.build_deck(state.user_id, state.level, max(1, state.total_items))
            if not deck:
                await ctx.session_service.finish_if_needed(state.session_id, state.user_id, state.level)
                await message.answer(
                    "Контент недоступний. Натисни «Піклуватися», щоб спробувати ще раз.",
                    reply_markup=main_menu_kb(),
                )
                return
            new_index = min(state.item_index, max(0, len(deck) - 1))
            await ctx.repositories.session_state.update_deck(
                state.session_id, json.dumps([item.to_dict() for item in deck], ensure_ascii=False), len(deck)
            )
            await ctx.repositories.session_state.update_index(state.session_id, new_index)
            state = await ctx.session_service.get_active_session(state.user_id)
            if not state or not state.current_item():
                await message.answer(
                    "Контент недоступний. Натисни «Піклуватися», щоб спробувати ще раз.",
                    reply_markup=main_menu_kb(),
                )
                return
            deck_item = state.current_item()
        try:
            item = await ctx.session_service.get_current_item(deck_item)
        except (KeyError, FileNotFoundError) as exc:
            logger.warning("Missing content item for session %s: %s", state.session_id, exc)
            await ctx.session_service.advance_item(state.session_id)
            updated = await ctx.session_service.get_active_session(state.user_id)
            if not updated:
                return
            if updated.item_index >= updated.total_items:
                await ctx.session_service.finish_if_needed(updated.session_id, updated.user_id, updated.level)
                await message.answer(
                    "Сесію завершено. Натисни «Піклуватися», щоб почати знову.",
                    reply_markup=main_menu_kb(),
                )
                return
            await _send_task(message, updated)
            return
        await ctx.task_presenter.send_listen_and_read(message, item, reply_markup=repeat_inline_kb(state.session_id))

    @router.message(~F.voice)
    async def on_fallback(message: types.Message) -> None:
        user_id = await ctx.repositories.users.upsert_user(message.from_user.id, message.from_user.username)
        await ctx.repositories.user_settings.ensure_settings(user_id, timezone=ctx.timezone)
        user = await ctx.repositories.users.get_user(message.from_user.id)
        if not user:
            await message.answer("Спочатку надішліть /start")
            return
        pet_row = await ctx.repositories.pets.load_pet(user_id)
        if pet_row is None:
            pet_types = ctx.pet_service.available_pet_types()
            if not pet_types:
                await ctx.pet_service.ensure_pet(user_id, default_pet="panda")
                await message.answer(
                    "Ми обрали для тебе тваринку: Панда 🐼.\nНатисни «Піклуватися», щоб почати.",
                    reply_markup=main_menu_kb(),
                )
                return
            await message.answer("Обери свою тваринку:", reply_markup=choose_pet_inline_kb(pet_types))
            return

        state = await ctx.session_service.get_active_session(user_id)
        if state:
            if state.awaiting_care:
                pet = await ctx.pet_service.rollover_if_needed(user_id)
                options, need_state = _parse_care_options(state)
                img = ctx.pet_service.asset_path(pet.pet_type, need_state) if need_state else None
                await answer_photo_or_text(
                    message,
                    img,
                    "Подбай про тваринку:",
                    reply_markup=care_inline_kb(options, state.session_id),
                )
                return
            await message.answer(
                "Надішли голосову відповідь, щоб продовжити.",
                reply_markup=main_menu_kb(),
            )
            await _send_task(message, state)
            return

        await message.answer(
            "Натисни «Піклуватися», щоб почати читання, або «Моя тваринка», щоб подивитися стан.",
            reply_markup=main_menu_kb(),
        )

    return router
