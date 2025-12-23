from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

import aiosqlite

MigrationStep = Callable[[aiosqlite.Connection], Awaitable[None]]


async def _ensure_meta(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            version INTEGER NOT NULL
        );
        """
    )
    cursor = await conn.execute("SELECT COUNT(*) FROM schema_meta")
    count = (await cursor.fetchone())[0]
    if count == 0:
        await conn.execute("INSERT INTO schema_meta (version) VALUES (1)")


async def _upgrade_to_v2(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_state (
            session_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            item_index INTEGER NOT NULL DEFAULT 0,
            total_items INTEGER NOT NULL,
            blocked INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            notifications_enabled INTEGER NOT NULL DEFAULT 1,
            timezone TEXT DEFAULT 'Europe/Helsinki',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )


async def _upgrade_to_v3(conn: aiosqlite.Connection) -> None:
    # Add session_state columns for pet-action unlock tracking.
    # Guard against running on databases created from the latest schema.sql.
    cursor = await conn.execute("PRAGMA table_info(session_state)")
    existing_cols = {row[1] for row in await cursor.fetchall()}
    if "correct_count" not in existing_cols:
        await conn.execute("ALTER TABLE session_state ADD COLUMN correct_count INTEGER NOT NULL DEFAULT 0")
    if "reward_stage" not in existing_cols:
        await conn.execute("ALTER TABLE session_state ADD COLUMN reward_stage INTEGER NOT NULL DEFAULT 0")
    if "mode" not in existing_cols:
        await conn.execute("ALTER TABLE session_state ADD COLUMN mode TEXT NOT NULL DEFAULT 'normal'")

    # Pets table (one row per user).
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pets (
            user_id INTEGER PRIMARY KEY,
            pet_type TEXT NOT NULL DEFAULT 'panda',
            happiness INTEGER NOT NULL DEFAULT 80,
            hunger INTEGER NOT NULL DEFAULT 80,
            thirst INTEGER NOT NULL DEFAULT 80,
            hygiene INTEGER NOT NULL DEFAULT 80,
            energy INTEGER NOT NULL DEFAULT 80,
            mood INTEGER NOT NULL DEFAULT 80,
            health INTEGER NOT NULL DEFAULT 80,
            action_tokens INTEGER NOT NULL DEFAULT 0,
            missed_sessions_streak INTEGER NOT NULL DEFAULT 0,
            resurrect_streak INTEGER NOT NULL DEFAULT 0,
            is_dead INTEGER NOT NULL DEFAULT 0,
            last_checked_at TIMESTAMP,
            last_session_completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )

async def _upgrade_to_v4(conn: aiosqlite.Connection) -> None:
    # Users: current_level
    cursor = await conn.execute("PRAGMA table_info(users)")
    existing_cols = {row[1] for row in await cursor.fetchall()}
    if "current_level" not in existing_cols:
        await conn.execute("ALTER TABLE users ADD COLUMN current_level INTEGER NOT NULL DEFAULT 1")

    # Session state: deck, attempts counter
    cursor = await conn.execute("PRAGMA table_info(session_state)")
    existing_cols = {row[1] for row in await cursor.fetchall()}
    if "deck_json" not in existing_cols:
        await conn.execute("ALTER TABLE session_state ADD COLUMN deck_json TEXT")
    if "current_attempts" not in existing_cols:
        await conn.execute("ALTER TABLE session_state ADD COLUMN current_attempts INTEGER NOT NULL DEFAULT 0")

    # Daily stats: first-try columns
    cursor = await conn.execute("PRAGMA table_info(daily_stats)")
    existing_cols = {row[1] for row in await cursor.fetchall()}
    if "first_try_total" not in existing_cols:
        await conn.execute("ALTER TABLE daily_stats ADD COLUMN first_try_total INTEGER NOT NULL DEFAULT 0")
    if "first_try_errors" not in existing_cols:
        await conn.execute("ALTER TABLE daily_stats ADD COLUMN first_try_errors INTEGER NOT NULL DEFAULT 0")

    # Attempts table: new columns (keep legacy ones)
    cursor = await conn.execute("PRAGMA table_info(attempts)")
    existing_cols = {row[1] for row in await cursor.fetchall()}
    add_cols = []
    if "user_id" not in existing_cols:
        add_cols.append(("user_id", "INTEGER"))
    if "content_id" not in existing_cols:
        add_cols.append(("content_id", "TEXT"))
    if "expected_text" not in existing_cols:
        add_cols.append(("expected_text", "TEXT"))
    if "transcript" not in existing_cols:
        add_cols.append(("transcript", "TEXT"))
    if "similarity" not in existing_cols:
        add_cols.append(("similarity", "INTEGER"))
    if "is_first_try" not in existing_cols:
        add_cols.append(("is_first_try", "INTEGER NOT NULL DEFAULT 0"))
    for name, coltype in add_cols:
        await conn.execute(f"ALTER TABLE attempts ADD COLUMN {name} {coltype}")

    # Item progress table
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS item_progress (
            user_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            content_id TEXT NOT NULL,
            passed_at TEXT,
            PRIMARY KEY (user_id, level, content_id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        );
        """
    )


async def _upgrade_to_v5(conn: aiosqlite.Connection) -> None:
    # Reward/pet columns were added in v3; ensure 'mode' present for older DBs.
    cursor = await conn.execute("PRAGMA table_info(session_state)")
    existing_cols = {row[1] for row in await cursor.fetchall()}
    if "mode" not in existing_cols:
        await conn.execute("ALTER TABLE session_state ADD COLUMN mode TEXT NOT NULL DEFAULT 'normal'")


MIGRATIONS: dict[int, MigrationStep] = {
    2: _upgrade_to_v2,
    3: _upgrade_to_v3,
    4: _upgrade_to_v4,
    5: _upgrade_to_v5,
}


async def _current_version(conn: aiosqlite.Connection) -> int:
    cursor = await conn.execute("SELECT version FROM schema_meta LIMIT 1")
    row = await cursor.fetchone()
    return int(row[0])


async def _set_version(conn: aiosqlite.Connection, version: int) -> None:
    await conn.execute("UPDATE schema_meta SET version=?", (version,))


async def apply_migrations(database) -> None:
    async with database.connect() as conn:
        await _ensure_meta(conn)
        version = await _current_version(conn)
        target = max(MIGRATIONS.keys(), default=version)
        for next_version in range(version + 1, target + 1):
            step = MIGRATIONS.get(next_version)
            if step:
                await step(conn)
                await _set_version(conn, next_version)
                await conn.commit()
