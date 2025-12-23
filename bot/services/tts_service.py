from __future__ import annotations

import hashlib
from pathlib import Path

import edge_tts

from bot.config import Config
from bot.utils.paths import ensure_parent


class TTSService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.cache_dir = Path("var/tts_cache")

    def _cache_path(self, text: str) -> Path:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.mp3"

    async def synthesize(self, text: str) -> str:
        path = self._cache_path(text)
        if path.exists():
            return str(path)
        ensure_parent(str(path))
        communicate = edge_tts.Communicate(text, self.config.tts_voice)
        await communicate.save(str(path))
        return str(path)
