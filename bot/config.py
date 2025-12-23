from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str
    assets_root: str
    ffmpeg_bin: str
    whisper_model: str
    tts_voice: str
    session_len: int
    care_gates: List[int]
    log_level: str


def _parse_care_gates(raw: str) -> List[int]:
    values = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            values.append(int(item))
    return values


def load_config() -> Config:
    load_dotenv()
    return Config(
        bot_token=os.environ.get("BOT_TOKEN", ""),
        db_path=os.environ.get("DB_PATH", "var/db.sqlite3"),
        assets_root=os.environ.get("ASSETS_ROOT", "assets/pets"),
        ffmpeg_bin=os.environ.get("FFMPEG_BIN", "ffmpeg"),
        whisper_model=os.environ.get("WHISPER_MODEL", "small"),
        tts_voice=os.environ.get("TTS_VOICE", "en-US-AriaNeural"),
        session_len=int(os.environ.get("SESSION_LEN", "10")),
        care_gates=_parse_care_gates(os.environ.get("CARE_GATES", "5,10")),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )


_cached_config: Config | None = None


def get_config() -> Config:
    global _cached_config
    if _cached_config is None:
        _cached_config = load_config()
    return _cached_config
