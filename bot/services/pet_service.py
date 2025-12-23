from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from bot.storage.repositories import PetRepository


PET_TYPES = ("panda", "dog", "dinosaur", "fox", "cat")


def _parse_sqlite_ts(value: Optional[object]) -> Optional[datetime]:
    """Parse SQLite CURRENT_TIMESTAMP strings as UTC datetimes."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    s = str(value)
    try:
        # SQLite default: "YYYY-MM-DD HH:MM:SS"
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        try:
            dt = datetime.fromisoformat(s.replace(" ", "T"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None


def _clamp(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(v)))


@dataclass
class PetStatus:
    pet_type: str
    happiness: int
    hunger: int
    thirst: int
    hygiene: int
    energy: int
    mood: int
    health: int
    action_tokens: int
    missed_sessions_streak: int
    resurrect_streak: int
    is_dead: bool

    @classmethod
    def from_row(cls, row) -> "PetStatus":
        return cls(
            pet_type=row["pet_type"],
            happiness=int(row["happiness"]),
            hunger=int(row["hunger"]),
            thirst=int(row["thirst"]),
            hygiene=int(row["hygiene"]),
            energy=int(row["energy"]),
            mood=int(row["mood"]),
            health=int(row["health"]),
            action_tokens=int(row["action_tokens"]),
            missed_sessions_streak=int(row["missed_sessions_streak"]),
            resurrect_streak=int(row["resurrect_streak"]),
            is_dead=bool(row["is_dead"]),
        )


class PetService:
    """Virtual pet state machine.

    Rules implemented (as agreed):
    - 10 language units per session, 2 sessions/day. Missing sessions matters.
    - Missed session streak: 2 missed sessions => big happiness drop (handled as -10 per missed session).
      3 missed sessions => sick. 4 missed sessions (≈2 days) => dead.
    - After 5 correct answers in a session => 1 care action token, after 10 correct => 2nd token.
    - Dead pet can be resurrected by 20 correct answers in a row in /resurrect mode.
    """

    def __init__(
        self,
        repo: PetRepository,
        assets_root: Path,
        timezone_name: str,
        session_times: list[str],
    ) -> None:
        self.repo = repo
        self.assets_root = assets_root
        self.tz = ZoneInfo(timezone_name)
        self.session_times = session_times

    async def ensure_pet(self, user_id: int, default_pet: str = "panda") -> None:
        await self.repo.ensure_pet(user_id, pet_type=default_pet)

    async def get_status(self, user_id: int) -> Optional[PetStatus]:
        row = await self.repo.load_pet(user_id)
        return PetStatus.from_row(row) if row else None

    async def choose_pet(self, user_id: int, pet_type: str) -> None:
        if pet_type not in PET_TYPES:
            pet_type = "panda"
        await self.repo.set_pet_type(user_id, pet_type)

    def _session_slots_between(self, start_local: datetime, end_local: datetime) -> list[datetime]:
        """Return scheduled session timestamps (local tz) in (start, end]."""
        slots: list[datetime] = []
        cur_date = start_local.date()
        end_date = end_local.date()
        while cur_date <= end_date:
            for hhmm in self.session_times:
                try:
                    hh, mm = [int(x) for x in hhmm.split(":", 1)]
                except Exception:
                    continue
                slot_dt = datetime.combine(cur_date, time(hh, mm), tzinfo=self.tz)
                if start_local < slot_dt <= end_local:
                    slots.append(slot_dt)
            cur_date = (datetime.combine(cur_date, time(0, 0), tzinfo=self.tz) + timedelta(days=1)).date()
        slots.sort()
        return slots

    async def apply_decay(self, user_id: int, now_utc: Optional[datetime] = None) -> PetStatus:
        """Apply missed-session decay once per passed scheduled slot."""
        now_utc = now_utc or datetime.now(timezone.utc)
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None

        last_checked = _parse_sqlite_ts(row["last_checked_at"]) or now_utc
        last_checked_local = last_checked.astimezone(self.tz)
        now_local = now_utc.astimezone(self.tz)

        missed_streak = int(row["missed_sessions_streak"])
        happiness = int(row["happiness"])
        hunger = int(row["hunger"])
        thirst = int(row["thirst"])
        hygiene = int(row["hygiene"])
        energy = int(row["energy"])
        mood = int(row["mood"])
        health = int(row["health"])
        is_dead = bool(row["is_dead"])
        action_tokens = int(row["action_tokens"])
        resurrect_streak = int(row["resurrect_streak"])

        if is_dead:
            # Still advance last_checked so we don't repeatedly process the same time window.
            await self.repo.update_pet(user_id, last_checked_at=now_utc.strftime("%Y-%m-%d %H:%M:%S"))
            return PetStatus.from_row(await self.repo.load_pet(user_id))

        slots = self._session_slots_between(last_checked_local, now_local)
        if slots:
            for _ in slots:
                missed_streak += 1
                # per-missed-session decay
                happiness -= 10
                hunger -= 12
                thirst -= 12
                hygiene -= 8
                energy -= 10
                mood -= 8
                health -= 6

            # sick / dead thresholds
            if missed_streak >= 4:
                is_dead = True
                happiness = 0
                health = 0
                action_tokens = 0
                resurrect_streak = 0
            elif missed_streak >= 3:
                # sick
                health = min(health, 25)
                happiness = min(happiness, 40)

        updates = {
            "missed_sessions_streak": int(missed_streak),
            "happiness": _clamp(happiness),
            "hunger": _clamp(hunger),
            "thirst": _clamp(thirst),
            "hygiene": _clamp(hygiene),
            "energy": _clamp(energy),
            "mood": _clamp(mood),
            "health": _clamp(health),
            "is_dead": 1 if is_dead else 0,
            "action_tokens": int(action_tokens),
            "resurrect_streak": int(resurrect_streak),
            "last_checked_at": now_utc.strftime("%Y-%m-%d %H:%M:%S"),
        }
        await self.repo.update_pet(user_id, **updates)
        row2 = await self.repo.load_pet(user_id)
        return PetStatus.from_row(row2)

    async def reset_action_tokens(self, user_id: int) -> None:
        await self.repo.update_pet(user_id, action_tokens=0)

    async def add_action_token(self, user_id: int, max_tokens: int = 2) -> int:
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None
        cur = int(row["action_tokens"])
        if cur >= max_tokens:
            return cur
        cur += 1
        await self.repo.update_pet(user_id, action_tokens=cur)
        return cur

    async def on_correct_attempt(self, user_id: int) -> None:
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None
        await self.repo.update_pet(
            user_id,
            happiness=_clamp(int(row["happiness"]) + 2),
            mood=_clamp(int(row["mood"]) + 1),
        )

    async def on_wrong_attempt(self, user_id: int) -> None:
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None
        await self.repo.update_pet(
            user_id,
            happiness=_clamp(int(row["happiness"]) - 3),
            mood=_clamp(int(row["mood"]) - 2),
        )

    async def on_session_completed(self, user_id: int, now_utc: Optional[datetime] = None) -> None:
        now_utc = now_utc or datetime.now(timezone.utc)
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None
        await self.repo.update_pet(
            user_id,
            last_session_completed_at=now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            last_checked_at=now_utc.strftime("%Y-%m-%d %H:%M:%S"),
            missed_sessions_streak=0,
            is_dead=0,
            resurrect_streak=0,
            happiness=_clamp(int(row["happiness"]) + 10),
            hunger=_clamp(int(row["hunger"]) + 4),
            thirst=_clamp(int(row["thirst"]) + 4),
            hygiene=_clamp(int(row["hygiene"]) + 2),
            energy=_clamp(int(row["energy"]) + 3),
            mood=_clamp(int(row["mood"]) + 5),
            health=_clamp(int(row["health"]) + 3),
        )

    async def resurrect_progress(self, user_id: int, ok: bool) -> int:
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None
        streak = int(row["resurrect_streak"])
        if ok:
            streak += 1
        else:
            streak = 0
        await self.repo.update_pet(user_id, resurrect_streak=streak)
        return streak

    async def revive(self, user_id: int) -> None:
        await self.repo.update_pet(
            user_id,
            is_dead=0,
            missed_sessions_streak=0,
            resurrect_streak=0,
            happiness=60,
            hunger=60,
            thirst=60,
            hygiene=60,
            energy=60,
            mood=60,
            health=60,
            action_tokens=0,
        )

    async def perform_action(self, user_id: int, action: str) -> Tuple[bool, str]:
        """Consume 1 action token and improve pet stats."""
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None
        if bool(row["is_dead"]):
            return False, "Тваринка спить 💤. Натисни «Прочитай», щоб оживити."
        tokens = int(row["action_tokens"])
        if tokens <= 0:
            return False, "Дій поки немає. Прочитай 5 одиниць — і з'явиться дія."

        hunger = int(row["hunger"])
        thirst = int(row["thirst"])
        hygiene = int(row["hygiene"])
        energy = int(row["energy"])
        mood = int(row["mood"])
        health = int(row["health"])
        happiness = int(row["happiness"])

        action = action.lower().strip()
        if action == "feed":
            hunger += 35
            happiness += 5
            msg = "🍎 Нагодували!"
        elif action == "water":
            thirst += 35
            happiness += 5
            msg = "💧 Напоїли!"
        elif action == "wash":
            hygiene += 35
            happiness += 4
            msg = "🫧 Помили!"
        elif action == "sleep":
            energy += 40
            happiness += 3
            msg = "😴 Відпочили!"
        elif action == "play":
            mood += 40
            happiness += 6
            msg = "🎾 Пограли!"
        elif action == "heal":
            health += 35
            happiness += 3
            msg = "🩹 Полікували!"
        else:
            return False, "Невідома дія."

        tokens -= 1
        await self.repo.update_pet(
            user_id,
            action_tokens=tokens,
            hunger=_clamp(hunger),
            thirst=_clamp(thirst),
            hygiene=_clamp(hygiene),
            energy=_clamp(energy),
            mood=_clamp(mood),
            health=_clamp(health),
            happiness=_clamp(happiness),
        )
        return True, f"{msg} Дії: {tokens}/2"

    async def on_wrong(self, user_id: int) -> None:
        await self.on_wrong_attempt(user_id)

    async def on_correct(self, user_id: int) -> None:
        row = await self.repo.load_pet(user_id)
        if not row:
            await self.ensure_pet(user_id)
            row = await self.repo.load_pet(user_id)
        assert row is not None
        if bool(row["is_dead"]):
            return
        await self.repo.update_pet(
            user_id,
            happiness=_clamp(int(row["happiness"]) + 1),
            mood=_clamp(int(row["mood"]) + 1),
        )

    def pick_state(self, pet: PetStatus) -> str:
        """Return a state key (filename without extension)."""
        if pet.is_dead:
            return "health_3"
        # sick state
        if pet.missed_sessions_streak >= 3 or pet.health <= 25:
            return "health_3"

        # priority: basic needs
        # hunger (4)
        if pet.hunger < 60:
            if pet.hunger < 5:
                return "hunger_4"
            if pet.hunger < 20:
                return "hunger_3"
            if pet.hunger < 40:
                return "hunger_2"
            return "hunger_1"

        if pet.thirst < 60:
            if pet.thirst < 20:
                return "thirst_3"
            if pet.thirst < 40:
                return "thirst_2"
            return "thirst_1"

        if pet.hygiene < 70:
            if pet.hygiene < 30:
                return "hygiene_3"
            if pet.hygiene < 50:
                return "hygiene_2"
            return "hygiene_1"

        if pet.energy < 70:
            if pet.energy < 30:
                return "energy_3"
            if pet.energy < 50:
                return "energy_2"
            return "energy_1"

        if pet.mood < 70:
            if pet.mood < 15:
                return "mood_4"
            if pet.mood < 30:
                return "mood_3"
            if pet.mood < 50:
                return "mood_2"
            return "mood_1"

        if pet.health < 70:
            if pet.health < 30:
                return "health_3"
            if pet.health < 50:
                return "health_2"
            return "health_1"

        # happy/bonus
        return f"bonus_{random.randint(1,10)}"

    def asset_path(self, pet_type: str, state: str) -> Optional[Path]:
        pet_dir = self.assets_root / pet_type
        for ext in ("jpg", "png"):
            p = pet_dir / f"{state}.{ext}"
            if p.exists():
                return p
        # fallbacks for placeholder dev files
        p = pet_dir / f"{state}.png.placeholder"
        if p.exists():
            return p
        # generic fallbacks
        for ext in ("jpg", "png"):
            p = pet_dir / f"happy.{ext}"
            if p.exists():
                return p
        return None

    def status_text(self, pet: PetStatus) -> str:
        # Kid-friendly, minimal Ukrainian status.
        if pet.is_dead:
            status = "Тваринка спить 💤"
        elif pet.missed_sessions_streak >= 3:
            status = "Тваринка хворіє 🤒"
        elif pet.happiness >= 80:
            status = "Тваринка щаслива 🙂"
        elif pet.happiness >= 50:
            status = "Тваринка норм 🙂"
        else:
            status = "Тваринці сумно 🙁"

        return f"{status}\nДії: {pet.action_tokens}/2"
