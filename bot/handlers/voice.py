from __future__ import annotations

from bot.services.speech_service import SpeechService
from bot.services.session_service import SessionService
from bot.storage.repositories import RepositoryProvider


SIMILARITY_THRESHOLD = 85


def handle_voice_answer(
    repositories: RepositoryProvider,
    session_service: SessionService,
    speech_service: SpeechService,
    telegram_id: int,
    level: int,
    prompt: str,
    expected_answer: str,
    audio_bytes: bytes,
) -> str:
    user = repositories.users.get_user(telegram_id)
    if not user:
        return "Спочатку надішліть /start"
    latest = session_service.get_latest_session(user["id"])
    if not latest:
        return "Немає активної сесії. Запустіть нову."

    transcript, score, ok = speech_service.evaluate(audio_bytes, expected_answer, threshold=SIMILARITY_THRESHOLD)
    session_id = latest["session"]["id"]
    session_service.record_attempt(
        session_id=session_id,
        prompt=prompt,
        user_answer=transcript,
        correct_answer=expected_answer,
        is_correct=ok,
    )
    status = "✅" if ok else "❌"
    return f"{status} {transcript} (similarity {score}%)"
