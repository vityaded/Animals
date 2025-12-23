from __future__ import annotations

from pathlib import Path

from bot.config import Config


class TaskService:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.content_dir = Path("content")
        self.level1_mono = self._load_lines("level1_words_mono.txt")
        self.level1_bi = self._load_lines("level1_words_bi.txt")
        self.level2 = self._load_lines("level2_phrases.txt")
        self.level3 = self._load_lines("level3_sentences.txt")

    def _load_lines(self, filename: str) -> list[str]:
        path = self.content_dir / filename
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as file:
            return [line.strip() for line in file if line.strip()]

    def get_task(self, difficulty: int, index: int) -> str:
        if difficulty == 1:
            midpoint = self.config.session_len // 2
            if index < midpoint:
                pool = self.level1_mono
            else:
                pool = self.level1_bi
        elif difficulty == 2:
            pool = self.level2
        else:
            pool = self.level3
        if not pool:
            return ""
        return pool[index % len(pool)]
