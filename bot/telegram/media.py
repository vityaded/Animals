from __future__ import annotations

import logging
from pathlib import Path

from aiogram import types
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)


async def answer_photo_safe(msg: types.Message, path: Path | None, caption: str | None = None) -> bool:
    if not path:
        if caption:
            await msg.answer(caption)
        return False

    try:
        await msg.answer_photo(FSInputFile(str(path)), caption=caption)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send photo %s: %s", path, exc)
        if caption:
            await msg.answer(caption)
        return False
