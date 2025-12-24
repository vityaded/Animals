from __future__ import annotations

import hashlib
import html
from pathlib import Path

from aiogram import types
from aiogram.types import FSInputFile

from bot.services.content_service import ContentItem
from bot.services.tts_service import TTSService, TTSUnavailableError
from bot.paths import resolve_project_path


class TaskPresenter:
    def __init__(
        self,
        assets_root: Path,
        tts_service: TTSService,
        text_img_cache_dir: Path | str = "data/text_img_cache",
        text_card_width: int = 1080,
    ) -> None:
        self.assets_root = resolve_project_path(assets_root)
        self.tts_service = tts_service
        self.text_img_cache_dir = resolve_project_path(text_img_cache_dir)
        self.text_card_width = text_card_width

    async def _resolve_audio(self, item: ContentItem) -> Path | None:
        clean_text = " ".join(item.text.split()).strip()
        if item.sound:
            sound_path = Path(item.sound)
            if not sound_path.is_absolute():
                candidate = self.assets_root / item.sound
                if candidate.exists():
                    if candidate.stat().st_size > 0:
                        return candidate
                    sound_path = candidate
            if sound_path.exists() and sound_path.stat().st_size > 0:
                return sound_path
        if not clean_text:
            return None
        return await self.tts_service.ensure_voice(clean_text)

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

    def _hash_text(self, text: str) -> str:
        normalized = " ".join(text.split()).strip().lower()
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    def _render_text_card(self, text: str) -> Path | None:
        """
        Telegram can't change font size in messages.
        To make the unit ~3× bigger, render it into a PNG and send as photo.
        """
        clean = " ".join(text.split()).strip()
        if not clean:
            return None

        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
        except Exception:  # noqa: BLE001
            return None

        self.text_img_cache_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.text_img_cache_dir / f"{self._hash_text(clean)}.png"
        if out_path.exists():
            return out_path

        width = int(self.text_card_width)
        padding = 72
        max_w = width - padding * 2
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        def wrap_for_font(font: ImageFont.FreeTypeFont) -> list[str]:
            words = clean.split()
            if not words:
                return []
            lines: list[str] = []
            cur = words[0]
            for w in words[1:]:
                candidate = f"{cur} {w}"
                tmp = Image.new("RGB", (10, 10), "white")
                d = ImageDraw.Draw(tmp)
                bbox = d.textbbox((0, 0), candidate, font=font)
                if (bbox[2] - bbox[0]) <= max_w:
                    cur = candidate
                else:
                    lines.append(cur)
                    cur = w
            lines.append(cur)
            return lines

        best_font = None
        best_lines: list[str] = []
        best_line_h = 0
        best_spacing = 12

        for size in [140, 120, 108, 96, 88, 80, 72, 64, 56, 48]:
            try:
                font = ImageFont.truetype(font_path, size=size)
            except Exception:  # noqa: BLE001
                font = ImageFont.load_default()
            lines = wrap_for_font(font)
            if not lines:
                continue

            tmp = Image.new("RGB", (10, 10), "white")
            d = ImageDraw.Draw(tmp)
            bbox_h = d.textbbox((0, 0), "Ag", font=font)
            line_h = bbox_h[3] - bbox_h[1]
            spacing = max(10, int(size * 0.22))
            total_h = len(lines) * line_h + (len(lines) - 1) * spacing
            if total_h <= 720:
                best_font = font
                best_lines = lines
                best_line_h = line_h
                best_spacing = spacing
                break

        if best_font is None:
            try:
                best_font = ImageFont.truetype(font_path, size=48)
            except Exception:  # noqa: BLE001
                best_font = ImageFont.load_default()
            best_lines = wrap_for_font(best_font)
            tmp = Image.new("RGB", (10, 10), "white")
            d = ImageDraw.Draw(tmp)
            bbox_h = d.textbbox((0, 0), "Ag", font=best_font)
            best_line_h = bbox_h[3] - bbox_h[1]
            best_spacing = 12

        total_h = len(best_lines) * best_line_h + (len(best_lines) - 1) * best_spacing
        height = max(520, min(900, total_h + padding * 2))

        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        y = (height - total_h) // 2
        for line in best_lines:
            bbox = draw.textbbox((0, 0), line, font=best_font)
            line_w = bbox[2] - bbox[0]
            x = (width - line_w) // 2
            draw.text((x, y), line, font=best_font, fill="black")
            y += best_line_h + best_spacing

        img.save(out_path, format="PNG")
        return out_path

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

        card_path = self._render_text_card(item.text)
        if card_path:
            prompt_msg = await message.answer_photo(
                FSInputFile(str(card_path)),
                caption="<b>Прослухай і прочитай:</b>",
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            safe = html.escape(item.text)
            prompt_msg = await message.answer(
                f"<b>Прослухай і прочитай:</b>\n<b>{safe}</b>",
                parse_mode="HTML",
                reply_markup=reply_markup,
            )

        if image_path:
            await prompt_msg.answer_photo(FSInputFile(str(image_path)))

        if audio_path:
            await prompt_msg.answer_voice(FSInputFile(str(audio_path)))
        else:
            await prompt_msg.answer("Аудіо тимчасово недоступне.")
