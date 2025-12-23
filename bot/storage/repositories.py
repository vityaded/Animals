from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Dict, Iterable, Optional

import aiosqlite

from bot.storage import migrations


class Database:
    def __init__(self, path: Path, schema_path: Path):
        self.path = Path(path)
        self.schema_path = Path(schema_path)
        self._connect_lock = asyncio.Lock()

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._connect_lock:
            db = await aiosqlite.connect(self.path)
        db.row_factory = aiosqlite.Row
        try:
            yield db
        finally:
            await db.close()

    async def ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.schema_path, "r", encoding="utf-8") as schema_file:
            schema_sql = schema_file.read()
        async with self.connect() as conn:
            await conn.executescript(schema_sql)
            await conn.commit()
        await migrations.apply_migrations(self)


class UserRepository:
    def __init__(self, database: Database):
        self.database = database

    async def upsert_user(self, telegram_id: int, username: str | None = None) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO users (telegram_id, username) VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username
                """,
                (telegram_id, username),
            )
            await conn.commit()
            if cursor.lastrowid:
                return cursor.lastrowid
            row = await conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
            existing = await row.fetchone()
            return int(existing[0])

    async def get_user(self, telegram_id: int) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
            return await cursor.fetchone()

    async def get_user_by_id(self, user_id: int) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE id=?", (user_id,))
            return await cursor.fetchone()


class SessionRepository:
    def __init__(self, database: Database):
        self.database = database

    async def create_session(self, user_id: int, level: int, due_at: Optional[datetime]) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "INSERT INTO sessions (user_id, level, due_at) VALUES (?, ?, ?)",
                (user_id, level, due_at),
            )
            await conn.commit()
            return cursor.lastrowid

    async def update_status(self, session_id: int, status: str) -> None:
        async with self.database.connect() as conn:
            await conn.execute("UPDATE sessions SET status=? WHERE id=?", (status, session_id))
            await conn.commit()

    async def latest_session(self, user_id: int) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM sessions WHERE user_id=? ORDER BY started_at DESC LIMIT 1",
                (user_id,),
            )
            return await cursor.fetchone()

    async def get_active_sessions(self, now: datetime) -> Iterable[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM sessions WHERE status IN ('pending','active') AND (due_at IS NULL OR due_at >= ?)",
                (now,),
            )
            return await cursor.fetchall()

    async def count_sessions_started_between(self, user_id: int, start_utc: datetime, end_utc: datetime) -> int:
        """Count sessions whose started_at is within [start_utc, end_utc). started_at is stored in UTC."""
        start_s = start_utc.strftime("%Y-%m-%d %H:%M:%S")
        end_s = end_utc.strftime("%Y-%m-%d %H:%M:%S")
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM sessions
                WHERE user_id=? AND started_at >= ? AND started_at < ?
                """,
                (user_id, start_s, end_s),
            )
            row = await cursor.fetchone()
            return int(row["cnt"]) if row and row["cnt"] is not None else 0


class SessionStateRepository:
    def __init__(self, database: Database):
        self.database = database

    async def create_state(
        self,
        session_id: int,
        user_id: int,
        level: int,
        total_items: int,
        item_index: int = 0,
        blocked: int = 0,
        correct_count: int = 0,
        reward_stage: int = 0,
        mode: str = "normal",
    ) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO session_state (
                    session_id, user_id, level, item_index, total_items,
                    correct_count, reward_stage, mode,
                    blocked
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, level, item_index, total_items, correct_count, reward_stage, mode, blocked),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_state(self, session_id: int) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM session_state WHERE session_id=?", (session_id,))
            return await cursor.fetchone()

    async def get_active_state_for_user(self, user_id: int) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT ss.* FROM session_state ss
                JOIN sessions s ON ss.session_id = s.id
                WHERE ss.user_id=? AND ss.blocked=0 AND s.status IN ('pending','active')
                ORDER BY ss.updated_at DESC LIMIT 1
                """,
                (user_id,),
            )
            return await cursor.fetchone()

    async def update_index(self, session_id: int, item_index: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                "UPDATE session_state SET item_index=?, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                (item_index, session_id),
            )
            await conn.commit()

    async def increment_correct(self, session_id: int) -> int:
        """Increment correct_count for the session and return the new value."""
        async with self.database.connect() as conn:
            await conn.execute(
                "UPDATE session_state SET correct_count = correct_count + 1, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                (session_id,),
            )
            await conn.commit()
            cursor = await conn.execute("SELECT correct_count FROM session_state WHERE session_id=?", (session_id,))
            row = await cursor.fetchone()
            return int(row[0]) if row else 0

    async def set_reward_stage(self, session_id: int, reward_stage: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                "UPDATE session_state SET reward_stage=?, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                (reward_stage, session_id),
            )
            await conn.commit()

    async def set_blocked(self, session_id: int, blocked: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                "UPDATE session_state SET blocked=?, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                (blocked, session_id),
            )
            await conn.commit()

    async def delete_state(self, session_id: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute("DELETE FROM session_state WHERE session_id=?", (session_id,))
            await conn.commit()


class AttemptRepository:
    def __init__(self, database: Database):
        self.database = database

    async def log_attempt(
        self,
        session_id: int,
        question: str,
        user_answer: str,
        correct_answer: str,
        is_correct: bool,
    ) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO attempts (session_id, question, user_answer, correct_answer, is_correct)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, question, user_answer, correct_answer, int(is_correct)),
            )
            await conn.commit()
            return cursor.lastrowid

    async def attempts_for_session(self, session_id: int) -> Iterable[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM attempts WHERE session_id=?", (session_id,))
            return await cursor.fetchall()

    async def count_for_session(self, session_id: int) -> tuple[int, int]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) as total, SUM(is_correct) as correct FROM attempts WHERE session_id=?",
                (session_id,),
            )
            row = await cursor.fetchone()
            total = int(row["total"]) if row and row["total"] is not None else 0
            correct = int(row["correct"]) if row and row["correct"] is not None else 0
            return total, correct


class ProgressRepository:
    def __init__(self, database: Database):
        self.database = database

    async def save_progress(self, user_id: int, level: int, progress: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                """
                INSERT INTO level_progress (user_id, level, progress)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, level) DO UPDATE SET progress=excluded.progress, updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, level, progress),
            )
            await conn.commit()

    async def load_progress(self, user_id: int, level: int) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT progress FROM level_progress WHERE user_id=? AND level=?",
                (user_id, level),
            )
            row = await cursor.fetchone()
            return int(row[0]) if row else 0


class DailyStatsRepository:
    def __init__(self, database: Database):
        self.database = database

    async def update_stats(self, user_id: int, date: str, attempts: int, correct: int, streak: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                """
                INSERT INTO daily_stats (user_id, date, attempts, correct, streak)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    attempts=attempts+excluded.attempts,
                    correct=correct+excluded.correct,
                    streak=excluded.streak
                """,
                (user_id, date, attempts, correct, streak),
            )
            await conn.commit()

    async def get_stats(self, user_id: int, date: str) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM daily_stats WHERE user_id=? AND date=?", (user_id, date))
            return await cursor.fetchone()


class HealthRepository:
    def __init__(self, database: Database):
        self.database = database

    async def set_hearts(self, user_id: int, hearts: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                """
                INSERT INTO health (user_id, hearts)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET hearts=excluded.hearts, updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, hearts),
            )
            await conn.commit()

    async def get_hearts(self, user_id: int) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT hearts FROM health WHERE user_id=?", (user_id,))
            row = await cursor.fetchone()
            return int(row[0]) if row else 3


class ReviveRepository:
    def __init__(self, database: Database):
        self.database = database

    async def create_token(self, user_id: int, token: str, expires_at: datetime) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "INSERT INTO revive (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user_id, token, expires_at),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_active_token(self, user_id: int) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM revive WHERE user_id=? AND used=0 AND expires_at > CURRENT_TIMESTAMP ORDER BY expires_at DESC LIMIT 1",
                (user_id,),
            )
            return await cursor.fetchone()

    async def mark_used(self, revive_id: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute("UPDATE revive SET used=1 WHERE id=?", (revive_id,))
            await conn.commit()


class UserSettingsRepository:
    def __init__(self, database: Database):
        self.database = database

    async def ensure_settings(self, user_id: int, timezone: str) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                """
                INSERT INTO user_settings (user_id, timezone)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, timezone),
            )
            await conn.commit()

    async def load_settings(self, user_id: int) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,))
            return await cursor.fetchone()

    async def users_with_notifications(self) -> Iterable[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM user_settings WHERE notifications_enabled=1")
            return await cursor.fetchall()


class PetRepository:
    def __init__(self, database: Database):
        self.database = database

    async def ensure_pet(self, user_id: int, pet_type: str = "panda") -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                """
                INSERT INTO pets (user_id, pet_type)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, pet_type),
            )
            await conn.commit()

    async def load_pet(self, user_id: int) -> Optional[aiosqlite.Row]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM pets WHERE user_id=?", (user_id,))
            return await cursor.fetchone()

    async def set_pet_type(self, user_id: int, pet_type: str) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                "UPDATE pets SET pet_type=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (pet_type, user_id),
            )
            await conn.commit()

    async def update_pet(self, user_id: int, **fields) -> None:
        if not fields:
            return
        cols = ", ".join([f"{k}=?" for k in fields.keys()])
        values = list(fields.values()) + [user_id]
        sql = f"UPDATE pets SET {cols}, updated_at=CURRENT_TIMESTAMP WHERE user_id=?"
        async with self.database.connect() as conn:
            await conn.execute(sql, values)
            await conn.commit()


@dataclass
class RepositoryProvider:
    users: UserRepository
    sessions: SessionRepository
    session_state: SessionStateRepository
    attempts: AttemptRepository
    progress: ProgressRepository
    daily_stats: DailyStatsRepository
    health: HealthRepository
    revive: ReviveRepository
    user_settings: UserSettingsRepository
    pets: PetRepository

    @classmethod
    def build(cls, database: Database) -> "RepositoryProvider":
        return cls(
            users=UserRepository(database),
            sessions=SessionRepository(database),
            session_state=SessionStateRepository(database),
            attempts=AttemptRepository(database),
            progress=ProgressRepository(database),
            daily_stats=DailyStatsRepository(database),
            health=HealthRepository(database),
            revive=ReviveRepository(database),
            user_settings=UserSettingsRepository(database),
            pets=PetRepository(database),
        )

    def as_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()
