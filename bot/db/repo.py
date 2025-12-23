from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import aiosqlite


class Repo:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_user(self, telegram_id: int) -> Dict[str, Any]:
        created_at = int(time.time())
        async with await self._connect() as conn:
            cursor = await conn.execute(
                "INSERT INTO users (telegram_id, created_at) VALUES (?, ?)",
                (telegram_id, created_at),
            )
            await conn.commit()
            user_id = cursor.lastrowid
            return {
                "id": user_id,
                "telegram_id": telegram_id,
                "pet_type": None,
                "difficulty": 1,
                "created_at": created_at,
            }

    async def set_user_pet_type(self, user_id: int, pet_type: str) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                "UPDATE users SET pet_type = ? WHERE id = ?",
                (pet_type, user_id),
            )
            await conn.commit()

    async def set_user_difficulty(self, user_id: int, difficulty: int) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                "UPDATE users SET difficulty = ? WHERE id = ?",
                (difficulty, user_id),
            )
            await conn.commit()

    async def delete_user_by_telegram_id(self, telegram_id: int) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                "DELETE FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            await conn.commit()

    async def get_pet_status(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM pet_status WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_pet_status(self, user_id: int) -> Dict[str, Any]:
        updated_at = int(time.time())
        async with await self._connect() as conn:
            await conn.execute(
                """
                INSERT INTO pet_status (user_id, updated_at)
                VALUES (?, ?)
                """,
                (user_id, updated_at),
            )
            await conn.commit()
            return {
                "user_id": user_id,
                "hunger": 1,
                "thirst": 1,
                "hygiene": 1,
                "energy": 1,
                "mood": 1,
                "health": 1,
                "updated_at": updated_at,
                "is_dead": 0,
            }

    async def update_pet_status(self, user_id: int, values: Dict[str, Any]) -> None:
        updated_at = int(time.time())
        values = {**values, "updated_at": updated_at}
        assignments = ", ".join(f"{key} = ?" for key in values.keys())
        params = list(values.values()) + [user_id]
        async with await self._connect() as conn:
            await conn.execute(
                f"UPDATE pet_status SET {assignments} WHERE user_id = ?",
                params,
            )
            await conn.commit()

    async def get_active_session(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with await self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM sessions WHERE user_id = ? AND active = 1",
                (user_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_session(self, user_id: int, difficulty: int) -> Dict[str, Any]:
        started_at = int(time.time())
        async with await self._connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO sessions (user_id, difficulty, started_at)
                VALUES (?, ?, ?)
                """,
                (user_id, difficulty, started_at),
            )
            await conn.commit()
            session_id = cursor.lastrowid
            return {
                "id": session_id,
                "user_id": user_id,
                "active": 1,
                "difficulty": difficulty,
                "task_index": 0,
                "awaiting_care": 0,
                "care_json": None,
                "started_at": started_at,
                "ended_at": None,
            }

    async def update_session(self, session_id: int, values: Dict[str, Any]) -> None:
        assignments = ", ".join(f"{key} = ?" for key in values.keys())
        params = list(values.values()) + [session_id]
        async with await self._connect() as conn:
            await conn.execute(
                f"UPDATE sessions SET {assignments} WHERE id = ?",
                params,
            )
            await conn.commit()

    async def end_session(self, session_id: int) -> None:
        async with await self._connect() as conn:
            await conn.execute(
                "UPDATE sessions SET active = 0, ended_at = ? WHERE id = ?",
                (int(time.time()), session_id),
            )
            await conn.commit()

    @staticmethod
    def decode_care_json(care_json: Optional[str]) -> Optional[Dict[str, Any]]:
        if not care_json:
            return None
        return json.loads(care_json)

    @staticmethod
    def encode_care_json(data: Dict[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False)
