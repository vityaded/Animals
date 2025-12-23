from __future__ import annotations

from aiogram.types import Message

from bot.config import get_config
from bot.services.pet_service import PetService


async def answer_pet_card(
    message: Message,
    pet_type: str,
    state_key: str,
    caption: str,
    reply_markup=None,
) -> None:
    config = get_config()
    image_path = PetService.asset_path(config.assets_root, pet_type, state_key)
    if image_path:
        await message.answer_photo(
            photo=image_path,
            caption=caption,
            reply_markup=reply_markup,
        )
    else:
        await message.answer(caption, reply_markup=reply_markup)
