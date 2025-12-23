from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.services.content_service import ContentService, LevelItem
from bot.services.session_service import SessionService
from bot.services.speech_service import SpeechService
from bot.storage.repositories import Database, RepositoryProvider


def _build_content(tmpdir: Path) -> ContentService:
    levels_dir = tmpdir / "levels"
    levels_dir.mkdir()
    (levels_dir / "level1.csv").write_text("prompt,answer,hint\nHello,Hello world,Hint\nBye,Good bye,\n", encoding="utf-8")
    return ContentService(levels_dir)


@pytest.mark.asyncio
async def test_session_state_flow():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        schema_path = Path("bot/storage/schema.sql")
        db = Database(tmp_path / "test.sqlite", schema_path)
        await db.ensure_schema()
        repos = RepositoryProvider.build(db)
        content = _build_content(tmp_path)
        session_service = SessionService(repos, content)

        user_id = await repos.users.upsert_user(1, "tester")
        session_id = await session_service.start_session(user_id, level=1, deadline_minutes=60)
        state = await session_service.get_active_session(user_id)
        assert state is not None
        assert state.item_index == 0

        await session_service.advance_item(session_id)
        state = await session_service.get_active_session(user_id)
        assert state.item_index == 1

        await session_service.repositories.session_state.update_index(session_id, state.total_items)
        finished = await session_service.finish_if_needed(session_id, user_id, 1)
        assert finished is True


def test_normalize_text_strips_punctuation():
    service = SpeechService("base", load_model=False)
    assert service.normalize_text("Hello,   world!!!") == "hello world"


def test_multiple_answers_choose_max_score():
    service = SpeechService("base", load_model=False)
    transcript = "good morning dear friend"
    _, score, ok = service._evaluate_transcript(transcript, "good morning||hello world", threshold=50)
    assert score >= 90
    assert ok is True
