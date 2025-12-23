from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)


class TTSUnavailableError(RuntimeError):
    """Raised when TTS backend is unavailable."""


class TTSService:
    def __init__(
        self,
        cache_dir: Path | str = "data/tts_cache",
        voice: str = "en-GB-RyanNeural",
        rate: str = "-10%",
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.voice = voice
        self.rate = rate

    def _hash_text(self, text: str) -> str:
        normalized = " ".join(text.split()).strip().lower()
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    async def ensure_voice(self, text: str) -> Path:
        if not text.strip():
            raise ValueError("Text is empty, cannot generate audio")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._hash_text(text)}.ogg"
        path = self.cache_dir / filename
        if path.exists():
            return path

        communicate = edge_tts.Communicate(text, voice=self.voice, rate=self.rate)
        try:
            with open(path, "wb") as output:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        output.write(chunk["data"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to generate TTS audio: %s", exc)
            path.unlink(missing_ok=True)
            raise TTSUnavailableError("Failed to generate TTS audio") from exc
        return path

    def ensure_voice_sync(self, text: str) -> Path:
        """Compatibility helper for sync callers."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            return asyncio.run_coroutine_threadsafe(self.ensure_voice(text), loop).result()
        return asyncio.run(self.ensure_voice(text))
