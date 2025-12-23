from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from bot.storage.repositories import PetRepository


PET_TYPES = ("panda", "dog", "dinosaur", "fox", "cat")


@dataclass
class PetStatus:
    pet_type: str
    hunger_level: int
    thirst_level: int
    hygiene_level: int
    energy_level: int
    mood_level: int
    health_level: int
    sessions_today: int
    last_day: Optional[str]
    consecutive_zero_days: int
    is_dead: bool

    @classmethod
    def from_row(cls, row) -> "PetStatus":
        cols = set(row.keys()) if hasattr(row, "keys") else set()
        return cls(
            pet_type=row["pet_type"],
            hunger_level=int(row["hunger_level"] if "hunger_level" in cols else 1),
            thirst_level=int(row["thirst_level"] if "thirst_level" in cols else 1),
            hygiene_level=int(row["hygiene_level"] if "hygiene_level" in cols else 1),
            energy_level=int(row["energy_level"] if "energy_level" in cols else 1),
            mood_level=int(row["mood_level"] if "mood_level" in cols else 1),
            health_level=int(row["health_level"] if "health_level" in cols else 1),
            sessions_today=int(row["sessions_today"] if "sessions_today" in cols else 0),
            last_day=row["last_day"] if "last_day" in cols else None,
            consecutive_zero_days=int(row["consecutive_zero_days"] if "consecutive_zero_days" in cols else 0),
            is_dead=bool(row["is_dead"] if "is_dead" in cols else 0),
        )


class PetService:
    """Virtual pet model with discrete needs and daily rollover."""

    def __init__(self, repo: PetRepository, assets_root: Path, timezone_name: str = "Europe/Kyiv") -> None:
        self.repo = repo
        self.assets_root = assets_root
        self.tz = ZoneInfo(timezone_name)

    async def ensure_pet(self, user_id: int, default_pet: str = "panda") -> None:
        await self.repo.ensure_pet(user_id, pet_type=default_pet)

    def available_pet_types(self) -> list[str]:
        if self.assets_root.exists():
            found = [p.name for p in self.assets_root.iterdir() if p.is_dir()]
        else:
            found = []
        if not found:
            return []
        ordered = [p for p in PET_TYPES if p in found]
        for pet in found:
            if pet not in ordered:
                ordered.append(pet)
        return ordered or found

    async def choose_pet(self, user_id: int, pet_type: str) -> None:
        if pet_type not in PET_TYPES:
            pet_type = "panda"
        await self.repo.set_pet_type(user_id, pet_type)

    async def _load_status(self, user_id: int) -> PetStatus:
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None
        return PetStatus.from_row(row)

    async def rollover_if_needed(self, user_id: int, now_utc: Optional[datetime] = None) -> PetStatus:
        now_utc = now_utc or datetime.now(timezone.utc)
        status = await self._load_status(user_id)
        today_local = now_utc.astimezone(self.tz).date()
        last_day_str = status.last_day
        if last_day_str:
            try:
                last_day = date.fromisoformat(last_day_str)
            except Exception:
                last_day = today_local
        else:
            last_day = today_local

        updates = {}
        if status.last_day is None:
            status.last_day = today_local.isoformat()
            updates["last_day"] = status.last_day
        if last_day != today_local:
            if status.sessions_today == 0:
                status.consecutive_zero_days += 1
                status.hunger_level = min(3, status.hunger_level + 1)
                status.thirst_level = min(3, status.thirst_level + 1)
                status.hygiene_level = min(3, status.hygiene_level + 1)
                status.energy_level = min(3, status.energy_level + 1)
                status.mood_level = min(3, status.mood_level + 1)
                status.health_level = min(3, status.health_level + 1)
                if status.consecutive_zero_days >= 2:
                    status.is_dead = True
            else:
                status.consecutive_zero_days = 0
            status.sessions_today = 0
            status.last_day = today_local.isoformat()
            updates = {
                "hunger_level": status.hunger_level,
                "thirst_level": status.thirst_level,
                "hygiene_level": status.hygiene_level,
                "energy_level": status.energy_level,
                "mood_level": status.mood_level,
                "health_level": status.health_level,
                "sessions_today": status.sessions_today,
                "consecutive_zero_days": status.consecutive_zero_days,
                "last_day": status.last_day,
                "is_dead": 1 if status.is_dead else 0,
            }

        if updates:
            await self.repo.update_pet(user_id, **updates)
            status = await self._load_status(user_id)
        return status

    async def increment_sessions_today(self, user_id: int) -> None:
        status = await self._load_status(user_id)
        await self.repo.update_pet(user_id, sessions_today=status.sessions_today + 1)

    async def get_sessions_needed_today(self, user_id: int) -> int:
        status = await self._load_status(user_id)
        return max(0, 2 - status.sessions_today)

    async def get_worst_need(self, user_id: int) -> Tuple[str, int]:
        status = await self._load_status(user_id)
        return self._worst_need(status)

    def _worst_need(self, status: PetStatus) -> Tuple[str, int]:
        need_map = {
            "hunger": status.hunger_level,
            "thirst": status.thirst_level,
            "hygiene": status.hygiene_level,
            "energy": status.energy_level,
            "mood": status.mood_level,
            "health": status.health_level,
        }
        max_level = max(need_map.values())
        worst = [k for k, v in need_map.items() if v == max_level]
        choice = random.choice(worst)
        return choice, max_level

    async def apply_care_choice(self, user_id: int, action_key: str, active_need_key: str) -> PetStatus:
        status = await self._load_status(user_id)
        levels = {
            "hunger": status.hunger_level,
            "thirst": status.thirst_level,
            "hygiene": status.hygiene_level,
            "energy": status.energy_level,
            "mood": status.mood_level,
            "health": status.health_level,
        }
        if action_key == active_need_key:
            levels[action_key] = max(1, levels[action_key] - 2)
        else:
            if action_key in levels:
                levels[action_key] = max(1, levels[action_key] - 1)

        await self.repo.update_pet(
            user_id,
            hunger_level=levels["hunger"],
            thirst_level=levels["thirst"],
            hygiene_level=levels["hygiene"],
            energy_level=levels["energy"],
            mood_level=levels["mood"],
            health_level=levels["health"],
        )
        return await self._load_status(user_id)

    async def apply_bonus(self, user_id: int) -> PetStatus:
        status = await self._load_status(user_id)
        levels = {
            "hunger_level": max(1, status.hunger_level - 1),
            "thirst_level": max(1, status.thirst_level - 1),
            "hygiene_level": max(1, status.hygiene_level - 1),
            "energy_level": max(1, status.energy_level - 1),
            "mood_level": max(1, status.mood_level - 1),
            "health_level": max(1, status.health_level - 1),
        }
        await self.repo.update_pet(user_id, **levels)
        return await self._load_status(user_id)

    async def revive(self, user_id: int) -> PetStatus:
        today = datetime.now(self.tz).date().isoformat()
        await self.repo.update_pet(
            user_id,
            hunger_level=1,
            thirst_level=1,
            hygiene_level=1,
            energy_level=1,
            mood_level=1,
            health_level=1,
            sessions_today=0,
            consecutive_zero_days=0,
            is_dead=0,
            last_day=today,
        )
        return await self._load_status(user_id)

    def pick_state(self, status: PetStatus) -> str:
        if status.is_dead:
            return "health_3"
        need_key, level = self._worst_need(status)
        return f"{need_key}_{level}"

    def asset_path(self, pet_type: str, state: str) -> Optional[Path]:
        pet_dir = self.assets_root / pet_type
        for ext in ("jpg", "png"):
            p = pet_dir / f"{state}.{ext}"
            if p.exists():
                return p
        p = pet_dir / f"{state}.png.placeholder"
        if p.exists():
            return p
        for ext in ("jpg", "png"):
            p = pet_dir / f"happy.{ext}"
            if p.exists():
                return p
        return None

    def status_text(self, status: PetStatus) -> str:
        if status.is_dead:
            return "Тваринка померла. Потрібно відновити"
        if status.sessions_today <= 0:
            return "Потрібно 2 рази піклуватися"
        if status.sessions_today == 1:
            return "Потрібно ще 1 раз піклуватися"
        return "Ти молодець — сьогодні достатньо"
