from __future__ import annotations
from dataclasses import dataclass

from bot.db.repo import Repo
from bot.services.pet_service import PetService
from bot.services.session_service import SessionService
from bot.services.task_service import TaskService
from bot.services.tts_service import TTSService
from bot.services.asr_service import ASRService
from bot.config import Config

@dataclass(slots=True)
class Ctx:
    config: Config
    repo: Repo
    pet: PetService
    sessions: SessionService
    tasks: TaskService
    tts: TTSService
    asr: ASRService
