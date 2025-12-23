from __future__ import annotations

from pathlib import Path

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile

from bot.telegram import AppContext
from bot.telegram.keyboards import choose_pet_inline_kb


def setup_pet_router(ctx: AppContext) -> Router:
    router = Router()

    async def _ensure_user(message: types.Message):
        return await ctx.repositories.users.get_user(message.from_user.id)

    async def _send_pet_card(chat: types.Message | types.CallbackQuery, user_id: int) -> None:
        pet = await ctx.pet_service.apply_decay(user_id)
        state_key = ctx.pet_service.pick_state(pet)
        path = ctx.pet_service.asset_path(pet.pet_type, state_key)
        text = ctx.pet_service.status_text(pet)
        if isinstance(chat, types.CallbackQuery):
            msg = chat.message
        else:
            msg = chat

        if path and path.exists() and path.suffix.lower() in {".jpg", ".png"}:
            await msg.answer_photo(FSInputFile(Path(path)), caption=text)
        else:
            await msg.answer(text)

    @router.message(Command("choosepet"))
    async def cmd_choosepet(message: types.Message, command: CommandObject | None = None) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Send /start first. / Спочатку /start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        await message.answer(
            "Choose your animal / Обери тваринку:",
            reply_markup=choose_pet_inline_kb(),
        )

    @router.callback_query(F.data.startswith("pet_choose:"))
    async def on_choose(callback: types.CallbackQuery) -> None:
        user = await ctx.repositories.users.get_user(callback.from_user.id)
        if not user:
            await callback.answer("/start", show_alert=True)
            return
        _, pet_type = callback.data.split(":", 1)
        await ctx.pet_service.ensure_pet(user["id"])
        await ctx.pet_service.choose_pet(user["id"], pet_type)
        await callback.message.answer(f"✅ Selected: {pet_type} / Обрано: {pet_type}")
        await _send_pet_card(callback, user["id"])
        await callback.answer()

    @router.message(Command("pet"))
    async def cmd_pet(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("Send /start first. / Спочатку /start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        await _send_pet_card(message, user["id"])

    # Care actions
    @router.message(Command("feed"))
    async def cmd_feed(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("/start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        ok, txt = await ctx.pet_service.perform_action(user["id"], "feed")
        await message.answer(txt)
        if ok:
            await _send_pet_card(message, user["id"])

    @router.message(Command("water"))
    async def cmd_water(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("/start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        ok, txt = await ctx.pet_service.perform_action(user["id"], "water")
        await message.answer(txt)
        if ok:
            await _send_pet_card(message, user["id"])

    @router.message(Command("wash"))
    async def cmd_wash(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("/start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        ok, txt = await ctx.pet_service.perform_action(user["id"], "wash")
        await message.answer(txt)
        if ok:
            await _send_pet_card(message, user["id"])

    @router.message(Command("sleep"))
    async def cmd_sleep(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("/start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        ok, txt = await ctx.pet_service.perform_action(user["id"], "sleep")
        await message.answer(txt)
        if ok:
            await _send_pet_card(message, user["id"])

    @router.message(Command("play"))
    async def cmd_play(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("/start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        ok, txt = await ctx.pet_service.perform_action(user["id"], "play")
        await message.answer(txt)
        if ok:
            await _send_pet_card(message, user["id"])

    @router.message(Command("heal"))
    async def cmd_heal(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("/start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        ok, txt = await ctx.pet_service.perform_action(user["id"], "heal")
        await message.answer(txt)
        if ok:
            await _send_pet_card(message, user["id"])

    @router.message(Command("resurrect"))
    async def cmd_resurrect(message: types.Message) -> None:
        user = await _ensure_user(message)
        if not user:
            await message.answer("/start")
            return
        await ctx.pet_service.ensure_pet(user["id"])
        pet = await ctx.pet_service.apply_decay(user["id"])
        if not pet.is_dead:
            await message.answer("Your pet is alive. / Твоя тваринка жива.")
            return
        existing = await ctx.session_service.get_active_session(user["id"])
        if existing and existing.mode != "resurrect":
            await message.answer(
                "You already have an active session. Send /stop first, then /resurrect. /\n"
                "Вже є активна сесія. Спочатку /stop, потім /resurrect."
            )
            return
        # Start resurrection session (voice answers). We cycle tasks until streak=20.
        session_id = await ctx.session_service.start_resurrection(user_id=user["id"], level=1)
        state = await ctx.session_service.get_active_session(user["id"])
        await message.answer(
            f"🧟 Resurrection challenge started (20 correct in a row). Session #{session_id}.\n"
            f"Почали воскресіння: 20 правильних підряд.")
        if state:
            item = await ctx.session_service.get_current_item(state.level, state.item_index)
            await message.answer(f"Task: {item.prompt} / Завдання: {item.prompt}")

    return router
