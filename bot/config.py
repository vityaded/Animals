from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv
import os


automatically_loaded = load_dotenv()


@dataclass
class Config:
    telegram_token: str
    db_path: Path
    whisper_model: str
    session_times: List[str]
    reminder_minutes_before: int
    deadline_minutes_after: int

    @classmethod
    def from_env(cls) -> "Config":
        telegram_token = os.getenv("TELEGRAM_TOKEN", "")
        db_path = Path(os.getenv("DATABASE_PATH", "bot.sqlite"))
        whisper_model = os.getenv("WHISPER_MODEL", "base")
        session_times = [time.strip() for time in os.getenv("SESSION_TIMES", "09:00,18:00").split(",") if time.strip()]
        reminder_minutes_before = int(os.getenv("REMINDER_MINUTES_BEFORE", "30"))
        deadline_minutes_after = int(os.getenv("DEADLINE_MINUTES_AFTER", "90"))
        return cls(
            telegram_token=telegram_token,
            db_path=db_path,
            whisper_model=whisper_model,
            session_times=session_times,
            reminder_minutes_before=reminder_minutes_before,
            deadline_minutes_after=deadline_minutes_after,
        )
