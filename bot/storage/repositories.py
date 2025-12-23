from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncIterator, Dict, Iterable, List, Optional

import aiosqlite

from bot.storage import migrations


def _row_to_dict(row: aiosqlite.Row | None) -> Optional[dict]:
    return dict(row) if row is not None else None


def _rows_to_dicts(rows: Iterable[aiosqlite.Row] | None) -> list[dict]:
    return [dict(r) for r in rows] if rows else []


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

    async def get_user(self, telegram_id: int) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
            row = await cursor.fetchone()
            return _row_to_dict(row)

    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE id=?", (user_id,))
            row = await cursor.fetchone()
            return _row_to_dict(row)


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

    async def latest_session(self, user_id: int) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM sessions WHERE user_id=? ORDER BY started_at DESC LIMIT 1",
                (user_id,),
            )
            row = await cursor.fetchone()
            return _row_to_dict(row)

    async def get_active_sessions(self, now: datetime) -> List[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM sessions WHERE status IN ('pending','active') AND (due_at IS NULL OR due_at >= ?)",
                (now,),
            )
            rows = await cursor.fetchall()
            return _rows_to_dicts(rows)

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
        deck_json: str | None = None,
        item_index: int = 0,
        blocked: int = 0,
        correct_count: int = 0,
        reward_stage: int = 0,
        mode: str = "normal",
        current_attempts: int = 0,
        wrong_total: int = 0,
        care_stage: int = 0,
        awaiting_care: int = 0,
        care_json: str | None = None,
    ) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO session_state (
                    session_id, user_id, level, deck_json, item_index, total_items,
                    correct_count, reward_stage, mode, current_attempts, wrong_total,
                    care_stage, awaiting_care, care_json, blocked
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    level,
                    deck_json,
                    item_index,
                    total_items,
                    correct_count,
                    reward_stage,
                    mode,
                    current_attempts,
                    wrong_total,
                    care_stage,
                    awaiting_care,
                    care_json,
                    blocked,
                ),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_state(self, session_id: int) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM session_state WHERE session_id=?", (session_id,))
            row = await cursor.fetchone()
            return _row_to_dict(row)

    async def get_active_state_for_user(self, user_id: int) -> Optional[dict]:
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
            row = await cursor.fetchone()
            return _row_to_dict(row)

    async def update_index(self, session_id: int, item_index: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                "UPDATE session_state SET item_index=?, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                (item_index, session_id),
            )
            await conn.commit()

    async def update_attempts(self, session_id: int, current_attempts: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                "UPDATE session_state SET current_attempts=?, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                (current_attempts, session_id),
            )
            await conn.commit()

    async def update_deck(self, session_id: int, deck_json: str, total_items: int) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                """
                UPDATE session_state
                SET deck_json=?, total_items=?, updated_at=CURRENT_TIMESTAMP
                WHERE session_id=?
                """,
                (deck_json, total_items, session_id),
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

    async def increment_wrong_total(self, session_id: int) -> int:
        async with self.database.connect() as conn:
            await conn.execute(
                "UPDATE session_state SET wrong_total = wrong_total + 1, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                (session_id,),
            )
            await conn.commit()
            cursor = await conn.execute("SELECT wrong_total FROM session_state WHERE session_id=?", (session_id,))
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

    async def set_care_state(
        self,
        session_id: int,
        awaiting_care: int,
        care_stage: Optional[int] = None,
        care_json: Optional[str] = None,
    ) -> None:
        updates = ["awaiting_care=?"]
        values: list[object] = [awaiting_care]
        if care_stage is not None:
            updates.append("care_stage=?")
            values.append(care_stage)
        if care_json is not None:
            updates.append("care_json=?")
            values.append(care_json)
        values.append(session_id)
        sql = f"UPDATE session_state SET {', '.join(updates)}, updated_at=CURRENT_TIMESTAMP WHERE session_id=?"
        async with self.database.connect() as conn:
            await conn.execute(sql, values)
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
        user_id: int,
        content_id: str | None,
        expected_text: str,
        transcript: str,
        similarity: int,
        is_first_try: bool,
        is_correct: bool,
        question: str | None = None,
        user_answer: str | None = None,
        correct_answer: str | None = None,
    ) -> int:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO attempts (
                    session_id, user_id, content_id, expected_text, transcript, similarity,
                    is_first_try, is_correct, question, user_answer, correct_answer
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    content_id,
                    expected_text,
                    transcript,
                    similarity,
                    int(is_first_try),
                    int(is_correct),
                    question,
                    user_answer,
                    correct_answer,
                ),
            )
            await conn.commit()
            return cursor.lastrowid

    async def attempts_for_session(self, session_id: int) -> List[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM attempts WHERE session_id=?", (session_id,))
            rows = await cursor.fetchall()
            return _rows_to_dicts(rows)

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

    async def update_stats(
        self,
        user_id: int,
        date: str,
        attempts: int,
        correct: int,
        streak: int,
        first_try_total: int = 0,
        first_try_errors: int = 0,
    ) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                """
                INSERT INTO daily_stats (user_id, date, attempts, correct, streak, first_try_total, first_try_errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, date) DO UPDATE SET
                    attempts=attempts+excluded.attempts,
                    correct=correct+excluded.correct,
                    first_try_total=first_try_total+excluded.first_try_total,
                    first_try_errors=first_try_errors+excluded.first_try_errors,
                    streak=excluded.streak
                """,
                (user_id, date, attempts, correct, streak, first_try_total, first_try_errors),
            )
            await conn.commit()

    async def get_stats(self, user_id: int, date: str) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM daily_stats WHERE user_id=? AND date=?", (user_id, date))
            row = await cursor.fetchone()
            return _row_to_dict(row)


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

    async def get_active_token(self, user_id: int) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM revive WHERE user_id=? AND used=0 AND expires_at > CURRENT_TIMESTAMP ORDER BY expires_at DESC LIMIT 1",
                (user_id,),
            )
            row = await cursor.fetchone()
            return _row_to_dict(row)

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

    async def load_settings(self, user_id: int) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,))
            row = await cursor.fetchone()
            return _row_to_dict(row)

    async def users_with_notifications(self) -> List[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM user_settings WHERE notifications_enabled=1")
            rows = await cursor.fetchall()
            return _rows_to_dicts(rows)


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

    async def load_pet(self, user_id: int) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM pets WHERE user_id=?", (user_id,))
            row = await cursor.fetchone()
            return _row_to_dict(row)

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


class ItemProgressRepository:
    def __init__(self, database: Database):
        self.database = database

    async def _ensure_row(self, user_id: int, level: int, content_id: str) -> None:
        async with self.database.connect() as conn:
            await conn.execute(
                """
                INSERT INTO item_progress (user_id, level, content_id)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, level, content_id) DO NOTHING
                """,
                (user_id, level, content_id),
            )
            await conn.commit()

    async def get_progress(self, user_id: int, level: int, content_id: str) -> Optional[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM item_progress WHERE user_id=? AND level=? AND content_id=?",
                (user_id, level, content_id),
            )
            row = await cursor.fetchone()
            return _row_to_dict(row)

    async def list_all(self, user_id: int) -> list[dict]:
        async with self.database.connect() as conn:
            cursor = await conn.execute("SELECT * FROM item_progress WHERE user_id=?", (user_id,))
            rows = await cursor.fetchall()
            return _rows_to_dicts(rows)

    async def get_due_items(self, user_id: int, now_utc: datetime) -> list[tuple[int, str, Optional[datetime]]]:
        async with self.database.connect() as conn:
            cursor = await conn.execute(
                """
                SELECT level, content_id, next_due_at
                FROM item_progress
                WHERE user_id=? AND next_due_at IS NOT NULL AND next_due_at <= ?
                ORDER BY next_due_at ASC
                """,
                (user_id, now_utc),
            )
            rows = await cursor.fetchall()
            return [(int(r["level"]), r["content_id"], r["next_due_at"]) for r in rows] if rows else []

    async def record_correct(self, user_id: int, level: int, content_id: str, now_utc: datetime) -> None:
        await self._ensure_row(user_id, level, content_id)
        async with self.database.connect() as conn:
            row_cursor = await conn.execute(
                "SELECT learn_correct_count, review_stage FROM item_progress WHERE user_id=? AND level=? AND content_id=?",
                (user_id, level, content_id),
            )
            row = await row_cursor.fetchone()
            learn_count = int(row["learn_correct_count"]) if row and row["learn_correct_count"] is not None else 0
            review_stage = int(row["review_stage"]) if row and row["review_stage"] is not None else 0

            if review_stage == 0 and learn_count < 2:
                learn_count += 1
                if learn_count >= 2:
                    review_stage = 1
                    next_due_at = now_utc + timedelta(minutes=10)
                else:
                    next_due_at = None
            elif review_stage == 1:
                review_stage = 2
                next_due_at = now_utc + timedelta(days=2)
            elif review_stage == 2:
                review_stage = 3
                next_due_at = None
            else:
                next_due_at = None

            await conn.execute(
                """
                UPDATE item_progress
                SET learn_correct_count=?, review_stage=?, next_due_at=?, last_seen_at=?
                WHERE user_id=? AND level=? AND content_id=?
                """,
                (
                    learn_count,
                    review_stage,
                    next_due_at,
                    now_utc,
                    user_id,
                    level,
                    content_id,
                ),
            )
            await conn.commit()

    async def record_wrong(self, user_id: int, level: int, content_id: str, now_utc: datetime) -> None:
        await self._ensure_row(user_id, level, content_id)
        async with self.database.connect() as conn:
            row_cursor = await conn.execute(
                "SELECT review_stage FROM item_progress WHERE user_id=? AND level=? AND content_id=?",
                (user_id, level, content_id),
            )
            row = await row_cursor.fetchone()
            review_stage = int(row["review_stage"]) if row and row["review_stage"] is not None else 0
            next_due_at = now_utc + timedelta(minutes=10) if review_stage >= 1 else None
            await conn.execute(
                """
                UPDATE item_progress
                SET next_due_at=?, last_seen_at=?
                WHERE user_id=? AND level=? AND content_id=?
                """,
                (next_due_at, now_utc, user_id, level, content_id),
            )
            await conn.commit()


@dataclass
class RepositoryProvider:
    database: Database
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
    item_progress: ItemProgressRepository

    @classmethod
    def build(cls, database: Database) -> "RepositoryProvider":
        return cls(
            database=database,
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
            item_progress=ItemProgressRepository(database),
        )

    def as_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()

    async def reset_all(self) -> None:
        async with self.database.connect() as conn:
            await conn.execute("PRAGMA foreign_keys=OFF")
            try:
                await conn.execute("BEGIN")
                try:
                    for table in (
                        "attempts",
                        "session_state",
                        "sessions",
                        "level_progress",
                        "daily_stats",
                        "health",
                        "revive",
                        "user_settings",
                        "pets",
                        "item_progress",
                        "users",
                    ):
                        await conn.execute(f"DELETE FROM {table}")
                    await conn.commit()
                except Exception:
                    await conn.rollback()
                    raise
                await conn.execute("VACUUM")
            finally:
                await conn.execute("PRAGMA foreign_keys=ON")
