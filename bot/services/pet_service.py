from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from bot.config import Config
from bot.db.repo import Repo


NEED_ORDER = ["health", "hunger", "thirst", "energy", "hygiene", "mood"]
NEED_LABELS = {
    "hunger": "Голод",
    "thirst": "Спрага",
    "hygiene": "Гігієна",
    "energy": "Енергія",
    "mood": "Настрій",
    "health": "Здоров'я",
}


class PetService:
    def __init__(self, repo: Repo, config: Config) -> None:
        self.repo = repo
        self.config = config

    async def get_or_create_status(self, user_id: int) -> Dict[str, int]:
        status = await self.repo.get_pet_status(user_id)
        if status:
            return status
        return await self.repo.create_pet_status(user_id)

    async def update_on_correct_answer(self, user_id: int, correct_count: int) -> Dict[str, int]:
        status = await self.get_or_create_status(user_id)
        updates: Dict[str, int] = {}
        if correct_count % 2 == 0:
            updates["hunger"] = min(3, status["hunger"] + 1)
        if correct_count % 3 == 0:
            updates["thirst"] = min(3, status["thirst"] + 1)
        if correct_count % 4 == 0:
            updates["energy"] = min(3, status["energy"] + 1)
        if correct_count % 5 == 0:
            updates["hygiene"] = min(3, status["hygiene"] + 1)
        if correct_count % 6 == 0:
            updates["mood"] = min(3, status["mood"] + 1)
        if updates:
            await self.repo.update_pet_status(user_id, updates)
            status.update(updates)
        return status

    @staticmethod
    def pick_state(status: Dict[str, int]) -> str:
        if status.get("is_dead"):
            return "happy"
        levels = {need: status[need] for need in NEED_ORDER}
        max_level = max(levels.values())
        if max_level == 1:
            return "happy"
        for need in NEED_ORDER:
            if levels[need] == max_level:
                return f"{need}_{max_level}"
        return "happy"

    @staticmethod
    def asset_path(assets_root: str, pet_type: str, state: str) -> Optional[str]:
        allowed_exts = {".png", ".jpg", ".jpeg", ".webp"}
        pet_dir = Path(assets_root) / pet_type
        if not pet_dir.exists():
            return None

        def find_state(target: str) -> Optional[str]:
            for path in pet_dir.iterdir():
                if path.is_file() and path.stem == target and path.suffix.lower() in allowed_exts:
                    return str(path)
            return None

        path = find_state(state)
        if path:
            return path
        if state != "happy":
            return find_state("happy")
        return None

    @staticmethod
    def status_text(status: Dict[str, int]) -> str:
        if status.get("is_dead"):
            return "Тваринка занедбана. Потрібно доглядати."
        parts = [
            f"{NEED_LABELS[need]}: {status[need]}" for need in NEED_ORDER
        ]
        return " • ".join(parts)

    async def apply_care_choice(
        self, user_id: int, active_need: str, chosen_need: str
    ) -> Dict[str, int]:
        status = await self.get_or_create_status(user_id)
        current_value = status[chosen_need]
        if chosen_need == active_need:
            new_value = max(1, current_value - 2)
        else:
            new_value = max(1, current_value - 1)
        updates = {chosen_need: new_value}
        await self.repo.update_pet_status(user_id, updates)
        status.update(updates)
        return status
