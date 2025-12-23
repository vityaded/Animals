from __future__ import annotations

from pathlib import Path

from aiogram import types
from aiogram.types import FSInputFile

from bot.services.content_service import ContentItem
from bot.services.tts_service import TTSService, TTSUnavailableError
from bot.paths import resolve_project_path


class TaskPresenter:
    def __init__(self, assets_root: Path, tts_service: TTSService):
        self.assets_root = resolve_project_path(assets_root)
        self.tts_service = tts_service

    async def _resolve_audio(self, item: ContentItem) -> Path:
        if item.sound:
            sound_path = Path(item.sound)
            if not sound_path.is_absolute():
                candidate = self.assets_root / item.sound
                if candidate.exists():
                    return candidate
                sound_path = Path(item.sound)
            if sound_path.exists():
                return sound_path
        return await self.tts_service.ensure_voice(item.text)

    def _resolve_image(self, item: ContentItem) -> Path | None:
        if not item.image:
            return None
        image_path = Path(item.image)
        if not image_path.is_absolute():
            candidate = self.assets_root / item.image
            if candidate.exists():
                return candidate
            image_path = Path(item.image)
        return image_path if image_path.exists() else None

    async def send_listen_and_read(
        self,
        message: types.Message,
        item: ContentItem,
        reply_markup: types.ReplyKeyboardMarkup | types.InlineKeyboardMarkup | None = None,
    ) -> None:
        try:
            audio_path = await self._resolve_audio(item)
        except TTSUnavailableError:
            audio_path = None
        image_path = self._resolve_image(item)

        text_msg = await message.answer(f"Прослухай і прочитай:\n{item.text}", reply_markup=reply_markup)

        if audio_path:
            await text_msg.answer_voice(FSInputFile(audio_path))
        else:
            await text_msg.answer("Аудіо тимчасово недоступне.")
