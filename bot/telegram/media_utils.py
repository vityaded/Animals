from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aiogram import types
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)


async def answer_photo_or_text(
    message: types.Message,
    photo_path: Optional[Path],
    text: str,
    reply_markup: types.InlineKeyboardMarkup | types.ReplyKeyboardMarkup | None = None,
) -> None:
    if photo_path and photo_path.exists():
        try:
            await message.answer_photo(FSInputFile(str(photo_path)), caption=text, reply_markup=reply_markup)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send photo %s: %s", photo_path, exc)

    await message.answer(text, reply_markup=reply_markup)
