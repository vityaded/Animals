from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from bot.services.content_service import ContentItem, ContentService
from bot.storage.repositories import RepositoryProvider


@dataclass
class DeckItem:
    level: int
    content_id: str

    @classmethod
    def from_raw(cls, raw: object, default_level: int) -> "DeckItem":
        if isinstance(raw, dict):
            return cls(level=int(raw.get("level", default_level)), content_id=str(raw.get("content_id", "")))
        return cls(level=default_level, content_id=str(raw))

    def to_dict(self) -> dict:
        return {"level": self.level, "content_id": self.content_id}


@dataclass
class SessionState:
    session_id: int
    user_id: int
    level: int
    deck: list[DeckItem]
    item_index: int
    total_items: int
    correct_count: int
    reward_stage: int
    mode: str
    blocked: bool
    current_attempts: int
    wrong_total: int
    care_stage: int
    awaiting_care: int
    care_json: Optional[str]

    @classmethod
    def from_row(cls, row) -> "SessionState":
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        deck: list[DeckItem] = []
        if "deck_json" in keys and row["deck_json"]:
            try:
                raw_deck = json.loads(row["deck_json"])
                deck = [DeckItem.from_raw(entry, row["level"]) for entry in raw_deck]
            except Exception:
                deck = []
        return cls(
            session_id=row["session_id"],
            user_id=row["user_id"],
            level=row["level"],
            deck=deck,
            item_index=row["item_index"],
            total_items=row["total_items"],
            correct_count=row["correct_count"] if "correct_count" in keys else 0,
            reward_stage=row["reward_stage"] if "reward_stage" in keys else 0,
            mode=row["mode"] if "mode" in keys else "normal",
            blocked=bool(row["blocked"]),
            current_attempts=row["current_attempts"] if "current_attempts" in keys else 0,
            wrong_total=row["wrong_total"] if "wrong_total" in keys else 0,
            care_stage=row["care_stage"] if "care_stage" in keys else 0,
            awaiting_care=row["awaiting_care"] if "awaiting_care" in keys else 0,
            care_json=row["care_json"] if "care_json" in keys else None,
        )

    def deck_ids(self) -> list[str]:
        return [item.content_id for item in self.deck]

    def current_item(self) -> DeckItem | None:
        if 0 <= self.item_index < len(self.deck):
            return self.deck[self.item_index]
        return None


class SessionService:
    def __init__(self, repositories: RepositoryProvider, content_service: ContentService):
        self.repositories = repositories
        self.content_service = content_service

    async def start_session(self, user_id: int, level: int, deadline_minutes: int, total_items: int = 10) -> int:
        due_at = datetime.now(timezone.utc) + timedelta(minutes=deadline_minutes)
        session_id = await self.repositories.sessions.create_session(user_id, level, due_at)
        await self.repositories.sessions.update_status(session_id, "active")
        deck = await self.build_deck(user_id, level, total_items)
        await self.repositories.session_state.create_state(
            session_id=session_id,
            user_id=user_id,
            level=level,
            deck_json=json.dumps([item.to_dict() for item in deck], ensure_ascii=False),
            total_items=len(deck),
            item_index=0,
            blocked=0,
            correct_count=0,
            reward_stage=0,
            mode="normal",
            current_attempts=0,
            wrong_total=0,
            care_stage=0,
            awaiting_care=0,
            care_json=None,
        )
        return session_id

    async def start_freecare_gate(self, user_id: int, level: int, content_id: str) -> int:
        """
        Starts a tiny 1-item session used to unlock a care choice.
        Must NOT count as a normal reading session (mode != 'normal').
        """
        session_id = await self.repositories.sessions.create_session(user_id, level, due_at=None)
        await self.repositories.sessions.update_status(session_id, "active")
        deck = [DeckItem(level=level, content_id=content_id)]
        await self.repositories.session_state.create_state(
            session_id=session_id,
            user_id=user_id,
            level=level,
            deck_json=json.dumps([item.to_dict() for item in deck], ensure_ascii=False),
            total_items=1,
            item_index=0,
            blocked=0,
            correct_count=0,
            reward_stage=0,
            mode="freecare",
            current_attempts=0,
            wrong_total=0,
            care_stage=0,
            awaiting_care=0,
            care_json=None,
        )
        return session_id

    async def start_revival(self, user_id: int, level: int = 1, deadline_minutes: int = 180) -> int:
        """Start a special session where the user processes 20 cards to revive a dead pet."""
        due_at = datetime.now(timezone.utc) + timedelta(minutes=deadline_minutes)
        session_id = await self.repositories.sessions.create_session(user_id, level, due_at)
        await self.repositories.sessions.update_status(session_id, "active")
        deck = await self.build_deck(user_id, level, total_items=20)
        await self.repositories.session_state.create_state(
            session_id=session_id,
            user_id=user_id,
            level=level,
            deck_json=json.dumps([item.to_dict() for item in deck], ensure_ascii=False),
            total_items=len(deck),
            item_index=0,
            blocked=0,
            correct_count=0,
            reward_stage=0,
            mode="revival",
            current_attempts=0,
            wrong_total=0,
            care_stage=0,
            awaiting_care=0,
            care_json=None,
        )
        return session_id

    async def get_active_session(self, user_id: int) -> Optional[SessionState]:
        row = await self.repositories.session_state.get_active_state_for_user(user_id)
        return SessionState.from_row(row) if row else None

    async def get_current_item(self, deck_item: DeckItem) -> ContentItem:
        return self.content_service.get_item(deck_item.level, deck_item.content_id)

    async def advance_item(self, session_id: int) -> None:
        state_row = await self.repositories.session_state.get_state(session_id)
        if not state_row:
            return
        next_index = state_row["item_index"] + 1
        await self.repositories.session_state.update_index(session_id, next_index)
        await self.repositories.session_state.update_attempts(session_id, 0)

    async def finish_if_needed(self, session_id: int, user_id: int, level: int) -> bool:
        state_row = await self.repositories.session_state.get_state(session_id)
        if not state_row:
            return True
        if state_row["item_index"] < state_row["total_items"]:
            return False
        total, correct = await self.repositories.attempts.count_for_session(session_id)
        await self.complete_session(session_id, user_id, level, correct, total)
        await self.repositories.session_state.delete_state(session_id)
        return True

    async def record_attempt(
        self,
        session_id: int,
        user_id: int,
        content_id: str,
        expected_text: str,
        transcript: str,
        similarity: int,
        is_first_try: bool,
        is_correct: bool,
    ) -> int:
        return await self.repositories.attempts.log_attempt(
            session_id=session_id,
            user_id=user_id,
            content_id=content_id,
            expected_text=expected_text,
            transcript=transcript,
            similarity=similarity,
            is_first_try=is_first_try,
            is_correct=is_correct,
            question=expected_text,
            user_answer=transcript,
            correct_answer=expected_text,
        )

    async def complete_session(self, session_id: int, user_id: int, level: int, correct: int, total: int) -> None:
        status = "passed" if total and correct == total else "done"
        await self.repositories.sessions.update_status(session_id, status)
        current_progress = await self.repositories.progress.load_progress(user_id, level)
        new_progress = max(current_progress, correct)
        await self.repositories.progress.save_progress(user_id, level, new_progress)

    async def get_latest_session(self, user_id: int) -> Optional[dict]:
        session = await self.repositories.sessions.latest_session(user_id)
        if not session:
            return None
        attempts = await self.repositories.attempts.attempts_for_session(session["id"])
        return {"session": session, "attempts": attempts}

    async def block_session(self, session_id: int) -> None:
        await self.repositories.session_state.set_blocked(session_id, 1)
        await self.repositories.sessions.update_status(session_id, "blocked")

    async def revive_session(self, session_id: int) -> None:
        await self.repositories.session_state.set_blocked(session_id, 0)
        await self.repositories.sessions.update_status(session_id, "active")

    async def get_items_for_level(self, level: int) -> list[ContentItem]:
        return self.content_service.get_level_items(level)

    async def build_deck(self, user_id: int, current_level: int, total_items: int) -> list[DeckItem]:
        now = datetime.now(timezone.utc)
        progress_rows = await self.repositories.item_progress.list_all(user_id)

        def parse_ts(value: object | None) -> Optional[datetime]:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            try:
                dt = datetime.fromisoformat(str(value).replace(" ", "T"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None

        progress_map: dict[tuple[int, str], dict[str, object]] = {}
        for row in progress_rows:
            cols = set(row.keys()) if hasattr(row, "keys") else set()
            progress_map[(int(row["level"]), row["content_id"])] = {
                "learn_correct_count": row["learn_correct_count"] if "learn_correct_count" in cols else 0,
                "review_stage": row["review_stage"] if "review_stage" in cols else 0,
                "next_due_at": parse_ts(row["next_due_at"]) if "next_due_at" in cols else None,
                "last_seen_at": parse_ts(row["last_seen_at"]) if "last_seen_at" in cols else None,
            }

        def is_finished(level: int, content_id: str) -> bool:
            row = progress_map.get((level, content_id))
            return bool(row and row.get("review_stage") == 3)

        def due_items() -> list[DeckItem]:
            due: list[DeckItem] = []
            for (lvl, cid), meta in progress_map.items():
                next_due = meta.get("next_due_at")
                if next_due and next_due <= now:
                    due.append(DeckItem(level=lvl, content_id=cid))
            due.sort(
                key=lambda x: progress_map.get((x.level, x.content_id), {}).get("next_due_at") or now,
            )
            return due

        deck: list[DeckItem] = []
        chosen: set[tuple[int, str]] = set()

        # Step 1: due review items.
        for item in due_items():
            if len(deck) >= total_items:
                break
            if (item.level, item.content_id) in chosen:
                continue
            deck.append(item)
            chosen.add((item.level, item.content_id))

        def add_items(item_level: int, items: list[ContentItem]) -> None:
            random.shuffle(items)
            for itm in items:
                if len(deck) >= total_items:
                    break
                key = (item_level, itm.id)
                if key in chosen:
                    continue
                if is_finished(item_level, itm.id):
                    continue
                deck.append(DeckItem(level=item_level, content_id=itm.id))
                chosen.add(key)

        # Step 2: unfinished items from current level (respect mono/di gating for level 1).
        try:
            level_items = self.content_service.get_level_items(current_level)
        except FileNotFoundError:
            level_items = []
        if current_level == 1:
            mono_items = [i for i in level_items if (i.sublevel or "").lower() == "mono"]
            di_items = [i for i in level_items if (i.sublevel or "").lower() == "di"]
            unfinished_mono = [i for i in mono_items if not is_finished(1, i.id)]
            if unfinished_mono:
                add_items(1, unfinished_mono)
            if len(deck) < total_items:
                unfinished_di = [i for i in di_items if not is_finished(1, i.id)]
                add_items(1, unfinished_di or di_items)
        else:
            unfinished = [i for i in level_items if not is_finished(current_level, i.id)]
            add_items(current_level, unfinished or level_items)

        # Step 3: any unfinished items from other levels.
        for lvl in self.content_service.available_levels():
            if len(deck) >= total_items or lvl == current_level:
                continue
            try:
                items = self.content_service.get_level_items(lvl)
            except FileNotFoundError:
                continue
            unfinished = [i for i in items if not is_finished(lvl, i.id)]
            add_items(lvl, unfinished or items)

        # If still not enough, allow repeats from current level pool.
        if len(deck) < total_items and level_items:
            idx = 0
            pool = level_items
            while len(deck) < total_items and pool:
                itm = pool[idx % len(pool)]
                deck.append(DeckItem(level=current_level, content_id=itm.id))
                idx += 1

        return deck[:total_items]
