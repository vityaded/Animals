from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from bot.config import Config
from bot.db.repo import Repo
from bot.services.pet_service import PetService, NEED_ORDER


class SessionService:
    def __init__(self, repo: Repo, config: Config, pet_service: PetService) -> None:
        self.repo = repo
        self.config = config
        self.pet_service = pet_service

    async def get_or_create_active_session(
        self, user_id: int, difficulty: int
    ) -> Tuple[Dict[str, Any], bool]:
        session = await self.repo.get_active_session(user_id)
        if session:
            return session, False
        session = await self.repo.create_session(user_id, difficulty)
        return session, True

    async def get_active_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        return await self.repo.get_active_session(user_id)

    async def advance_task(self, session: Dict[str, Any]) -> Dict[str, Any]:
        new_index = session["task_index"] + 1
        updates = {"task_index": new_index}
        if new_index >= self.config.session_len:
            updates.update({"active": 0, "ended_at": int(time.time())})
        await self.repo.update_session(session["id"], updates)
        session.update(updates)
        return session

    async def set_awaiting_care(self, session: Dict[str, Any], status: Dict[str, Any]) -> Dict[str, Any]:
        active_need = self._pick_worst_need(status)
        need_state = f"{active_need}_{status[active_need]}"
        options = ["feed", "water", "wash", "sleep", "play", "heal"]
        care_json = {
            "active_need": active_need,
            "need_state": need_state,
            "options": options,
        }
        updates = {
            "awaiting_care": 1,
            "care_json": self.repo.encode_care_json(care_json),
        }
        await self.repo.update_session(session["id"], updates)
        session.update(updates)
        return session

    async def clear_care(self, session: Dict[str, Any]) -> Dict[str, Any]:
        updates = {"awaiting_care": 0, "care_json": None}
        await self.repo.update_session(session["id"], updates)
        session.update(updates)
        return session

    async def end_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        await self.repo.end_session(session["id"])
        session.update({"active": 0, "ended_at": int(time.time())})
        return session

    def _pick_worst_need(self, status: Dict[str, Any]) -> str:
        max_level = max(status[need] for need in NEED_ORDER)
        for need in NEED_ORDER:
            if status[need] == max_level:
                return need
        return NEED_ORDER[0]
