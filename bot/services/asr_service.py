from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel
from rapidfuzz import fuzz

from bot.config import Config
from bot.utils.text_norm import normalize_text


class ASRService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._model: WhisperModel | None = None

    def _get_model(self) -> WhisperModel:
        if self._model is None:
            self._model = WhisperModel(self.config.whisper_model)
        return self._model

    async def _convert_to_wav(self, input_path: Path, output_path: Path) -> None:
        process = await asyncio.create_subprocess_exec(
            self.config.ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate()
        if process.returncode != 0:
            raise RuntimeError("ffmpeg conversion failed")

    async def transcribe_and_match(self, bot, voice, target: str) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            ogg_path = Path(tmpdir) / "input.ogg"
            wav_path = Path(tmpdir) / "input.wav"
            await bot.download(voice, destination=ogg_path)
            await self._convert_to_wav(ogg_path, wav_path)
            text = await asyncio.to_thread(self._transcribe_file, wav_path)
        normalized_target = normalize_text(target)
        normalized_text = normalize_text(text)
        is_match = self._match(normalized_text, normalized_target)
        return is_match, text

    def _transcribe_file(self, path: Path) -> str:
        model = self._get_model()
        segments, _ = model.transcribe(str(path))
        return " ".join(segment.text.strip() for segment in segments).strip()

    @staticmethod
    def _match(transcript: str, target: str) -> bool:
        if not transcript or not target:
            return False
        if transcript == target:
            return True
        if target in transcript:
            return True
        return fuzz.ratio(transcript, target) / 100 >= 0.86
