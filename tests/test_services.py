from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.services.content_service import ContentService
from bot.services.pet_service import PetService
from bot.services.session_service import SessionService
from bot.services.speech_service import SpeechService
from bot.storage.repositories import Database, RepositoryProvider


def _build_content(tmpdir: Path) -> ContentService:
    levels_dir = tmpdir / "levels"
    levels_dir.mkdir()
    (levels_dir / "level1.csv").write_text(
        "id,text,sound,image,sublevel\n"
        "mono1,Hello world,,,mono\n"
        "mono2,Good bye,,,mono\n"
        "di1,Blue sky,,,di\n",
        encoding="utf-8",
    )
    return ContentService(levels_dir)


@pytest.mark.asyncio
async def test_spaced_repetition_progression():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = Database(tmp_path / "test.sqlite", Path("bot/storage/schema.sql"))
        await db.ensure_schema()
        repos = RepositoryProvider.build(db)
        content = _build_content(tmp_path)
        session_service = SessionService(repos, content)
        user_id = await repos.users.upsert_user(1, "tester")
        now = datetime.now(timezone.utc)

        # Learning phase
        await repos.item_progress.record_correct(user_id, 1, "mono1", now_utc=now)
        row = await repos.item_progress.get_progress(user_id, 1, "mono1")
        assert row["learn_correct_count"] == 1
        await repos.item_progress.record_wrong(user_id, 1, "mono1", now_utc=now + timedelta(seconds=1))
        row = await repos.item_progress.get_progress(user_id, 1, "mono1")
        assert row["learn_correct_count"] == 1  # wrong does not reset progress

        await repos.item_progress.record_correct(user_id, 1, "mono1", now_utc=now + timedelta(seconds=2))
        row = await repos.item_progress.get_progress(user_id, 1, "mono1")
        assert row["learn_correct_count"] == 2
        assert row["review_stage"] == 1
        assert row["next_due_at"] is not None

        # Review stage transitions
        await repos.item_progress.record_correct(user_id, 1, "mono1", now_utc=now + timedelta(minutes=11))
        row = await repos.item_progress.get_progress(user_id, 1, "mono1")
        assert row["review_stage"] == 2
        assert row["next_due_at"] is not None

        await repos.item_progress.record_correct(user_id, 1, "mono1", now_utc=now + timedelta(days=3))
        row = await repos.item_progress.get_progress(user_id, 1, "mono1")
        assert row["review_stage"] == 3
        assert row["next_due_at"] is None


@pytest.mark.asyncio
async def test_care_stage_and_bonus_and_rollover():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = Database(tmp_path / "test.sqlite", Path("bot/storage/schema.sql"))
        await db.ensure_schema()
        repos = RepositoryProvider.build(db)
        content = _build_content(tmp_path)
        session_service = SessionService(repos, content)
        pet_service = PetService(repos.pets, assets_root=Path("assets/pets"), timezone_name="Europe/Kyiv")
        user_id = await repos.users.upsert_user(1, "tester")
        await pet_service.ensure_pet(user_id)

        await session_service.start_session(user_id, level=1, deadline_minutes=60, total_items=10)
        state = await session_service.get_active_session(user_id)
        assert state is not None
        assert state.item_index == 0

        # Simulate reaching care checkpoints.
        await repos.session_state.update_index(state.session_id, 5)
        updated = await session_service.get_active_session(user_id)
        assert updated is not None and updated.item_index == 5
        assert updated.care_stage == 0
        await repos.session_state.set_care_state(state.session_id, awaiting_care=1, care_stage=1, care_json="{}")
        updated = await session_service.get_active_session(user_id)
        assert updated.awaiting_care == 1 and updated.care_stage == 1

        await repos.session_state.set_care_state(state.session_id, awaiting_care=0, care_stage=1, care_json=None)
        await repos.session_state.update_index(state.session_id, 10)
        updated = await session_service.get_active_session(user_id)
        assert updated.item_index == 10
        await repos.session_state.set_care_state(state.session_id, awaiting_care=1, care_stage=2, care_json="{}")
        updated = await session_service.get_active_session(user_id)
        assert updated.care_stage == 2

        # Bonus reduces needs but not below 1
        await repos.pets.update_pet(
            user_id,
            hunger_level=3,
            thirst_level=3,
            hygiene_level=3,
            energy_level=3,
            mood_level=3,
            health_level=3,
        )
        status = await pet_service.apply_bonus(user_id)
        assert status.hunger_level == 2
        assert status.mood_level >= 1

        # Rollover kills pet after 2 zero days
        yesterday = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
        await repos.pets.update_pet(user_id, last_day=yesterday, sessions_today=0, consecutive_zero_days=1)
        status = await pet_service.rollover_if_needed(user_id, now_utc=datetime.now(timezone.utc))
        assert status.is_dead is True


def test_speech_service_threshold():
    service = SpeechService("base", load_model=False)
    transcript = "good morning dear friend"
    _, score, ok = service._evaluate_transcript(transcript, "good morning||hello world", threshold=80)
    assert score >= 90
    assert ok is True



def test_speech_service_relaxed_close_phonemes_vowels():
    service = SpeechService("base", load_model=False)
    # long/short vowel close pairs should be accepted by phonetic scoring
    _, score1, ok1 = service._evaluate_transcript("sheep", "ship", threshold=80)
    assert ok1 is True
    assert score1 >= 80

    _, score2, ok2 = service._evaluate_transcript("fool", "full", threshold=80)
    assert ok2 is True
    assert score2 >= 80


@pytest.mark.asyncio
async def test_deck_is_consecutive_and_levels_advance():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = Database(tmp_path / "test.sqlite", Path("bot/storage/schema.sql"))
        await db.ensure_schema()
        repos = RepositoryProvider.build(db)

        # Build 2 levels with known CSV order
        levels_dir = tmp_path / "levels"
        levels_dir.mkdir()
        (levels_dir / "level1.csv").write_text(
            "id,text,sound,image\n"
            "a1,cat,,\n"
            "a2,dog,,\n"
            "a3,sun,,\n",
            encoding="utf-8",
        )
        (levels_dir / "level2.csv").write_text(
            "id,text,sound,image\n"
            "b1,a red ball,,\n"
            "b2,a blue bag,,\n",
            encoding="utf-8",
        )
        content = ContentService(levels_dir)
        session_service = SessionService(repos, content)

        user_id = await repos.users.upsert_user(1, "tester")

        deck = await session_service.build_deck(user_id, current_level=1, total_items=3)
        assert [d.content_id for d in deck] == ["a1", "a2", "a3"]

        # Finish all level1 items (drive them to review_stage=3)
        now = datetime.now(timezone.utc)
        for cid in ["a1", "a2", "a3"]:
            await repos.item_progress.record_correct(user_id, 1, cid, now_utc=now)
            await repos.item_progress.record_correct(
                user_id, 1, cid, now_utc=now + timedelta(seconds=1)
            )
            await repos.item_progress.record_correct(
                user_id, 1, cid, now_utc=now + timedelta(minutes=11)
            )
            await repos.item_progress.record_correct(
                user_id, 1, cid, now_utc=now + timedelta(days=3)
            )

        deck2 = await session_service.build_deck(user_id, current_level=1, total_items=2)
        assert [d.content_id for d in deck2] == ["b1", "b2"]

        u = await repos.users.get_user_by_id(user_id)
        assert int(u["current_level"]) == 2
