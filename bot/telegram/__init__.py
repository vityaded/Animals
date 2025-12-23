from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.services.content_service import ContentService
    from bot.services.health_service import HealthService
    from bot.services.progress_service import ProgressService
    from bot.services.session_service import SessionService
    from bot.services.task_presenter import TaskPresenter
    from bot.services.speech_service import SpeechService
    from bot.services.tts_service import TTSService
    from bot.services.pet_service import PetService
    from bot.storage.repositories import RepositoryProvider


@dataclass
class AppContext:
    repositories: "RepositoryProvider"
    content_service: "ContentService"
    session_service: "SessionService"
    progress_service: "ProgressService"
    health_service: "HealthService"
    pet_service: "PetService"
    speech_service: "SpeechService"
    tts_service: "TTSService"
    task_presenter: "TaskPresenter"
    timezone: str
