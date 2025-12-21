from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional


class Database:
    def __init__(self, path: Path, schema_path: Path):
        self.path = Path(path)
        self.schema_path = Path(schema_path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def ensure_schema(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.schema_path, "r", encoding="utf-8") as schema_file:
            schema_sql = schema_file.read()
        with closing(self.connect()) as conn:
            conn.executescript(schema_sql)
            conn.commit()


class UserRepository:
    def __init__(self, database: Database):
        self.database = database

    def upsert_user(self, telegram_id: int, username: str | None = None) -> int:
        with closing(self.database.connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (telegram_id, username) VALUES (?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username
                """,
                (telegram_id, username),
            )
            if cursor.lastrowid:
                user_id = cursor.lastrowid
            else:
                user_id = conn.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()[0]
            conn.commit()
            return user_id

    def get_user(self, telegram_id: int) -> Optional[sqlite3.Row]:
        with closing(self.database.connect()) as conn:
            return conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()


class SessionRepository:
    def __init__(self, database: Database):
        self.database = database

    def create_session(self, user_id: int, level: int, due_at: Optional[datetime]) -> int:
        with closing(self.database.connect()) as conn:
            cursor = conn.execute(
                "INSERT INTO sessions (user_id, level, due_at) VALUES (?, ?, ?)",
                (user_id, level, due_at),
            )
            conn.commit()
            return cursor.lastrowid

    def update_status(self, session_id: int, status: str) -> None:
        with closing(self.database.connect()) as conn:
            conn.execute("UPDATE sessions SET status=? WHERE id=?", (status, session_id))
            conn.commit()

    def latest_session(self, user_id: int) -> Optional[sqlite3.Row]:
        with closing(self.database.connect()) as conn:
            return conn.execute(
                "SELECT * FROM sessions WHERE user_id=? ORDER BY started_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()


class AttemptRepository:
    def __init__(self, database: Database):
        self.database = database

    def log_attempt(
        self,
        session_id: int,
        question: str,
        user_answer: str,
        correct_answer: str,
        is_correct: bool,
    ) -> int:
        with closing(self.database.connect()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO attempts (session_id, question, user_answer, correct_answer, is_correct)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, question, user_answer, correct_answer, int(is_correct)),
            )
            conn.commit()
            return cursor.lastrowid

    def attempts_for_session(self, session_id: int) -> Iterable[sqlite3.Row]:
        with closing(self.database.connect()) as conn:
            return conn.execute("SELECT * FROM attempts WHERE session_id=?", (session_id,)).fetchall()


class ProgressRepository:
    def __init__(self, database: Database):
        self.database = database

    def save_progress(self, user_id: int, level: int, progress: int) -> None:
        with closing(self.database.connect()) as conn:
            conn.execute(
                """
                INSERT INTO level_progress (user_id, level, progress)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, level) DO UPDATE SET progress=excluded.progress, updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, level, progress),
            )
            conn.commit()

    def load_progress(self, user_id: int, level: int) -> int:
        with closing(self.database.connect()) as conn:
            row = conn.execute(
                "SELECT progress FROM level_progress WHERE user_id=? AND level=?",
                (user_id, level),
            ).fetchone()
            return int(row[0]) if row else 0


class DailyStatsRepository:
    def __init__(self, database: Database):
        self.database = database

    def update_stats(self, user_id: int, date: str, attempts: int, correct: int, streak: int) -> None:
        with closing(self.database.connect()) as conn:
            conn.execute(
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
            conn.commit()

    def get_stats(self, user_id: int, date: str) -> Optional[sqlite3.Row]:
        with closing(self.database.connect()) as conn:
            return conn.execute("SELECT * FROM daily_stats WHERE user_id=? AND date=?", (user_id, date)).fetchone()


class HealthRepository:
    def __init__(self, database: Database):
        self.database = database

    def set_hearts(self, user_id: int, hearts: int) -> None:
        with closing(self.database.connect()) as conn:
            conn.execute(
                """
                INSERT INTO health (user_id, hearts)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET hearts=excluded.hearts, updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, hearts),
            )
            conn.commit()

    def get_hearts(self, user_id: int) -> int:
        with closing(self.database.connect()) as conn:
            row = conn.execute("SELECT hearts FROM health WHERE user_id=?", (user_id,)).fetchone()
            return int(row[0]) if row else 3


class ReviveRepository:
    def __init__(self, database: Database):
        self.database = database

    def create_token(self, user_id: int, token: str, expires_at: datetime) -> int:
        with closing(self.database.connect()) as conn:
            cursor = conn.execute(
                "INSERT INTO revive (user_id, token, expires_at) VALUES (?, ?, ?)",
                (user_id, token, expires_at),
            )
            conn.commit()
            return cursor.lastrowid

    def get_active_token(self, user_id: int) -> Optional[sqlite3.Row]:
        with closing(self.database.connect()) as conn:
            return conn.execute(
                "SELECT * FROM revive WHERE user_id=? AND used=0 AND expires_at > CURRENT_TIMESTAMP ORDER BY expires_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()

    def mark_used(self, revive_id: int) -> None:
        with closing(self.database.connect()) as conn:
            conn.execute("UPDATE revive SET used=1 WHERE id=?", (revive_id,))
            conn.commit()


class RepositoryProvider:
    def __init__(self, database: Database):
        self.users = UserRepository(database)
        self.sessions = SessionRepository(database)
        self.attempts = AttemptRepository(database)
        self.progress = ProgressRepository(database)
        self.daily_stats = DailyStatsRepository(database)
        self.health = HealthRepository(database)
        self.revive = ReviveRepository(database)

    def as_dict(self) -> Dict[str, object]:
        return self.__dict__.copy()
