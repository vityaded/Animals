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


MIGRATIONS: dict[int, MigrationStep] = {
    2: _upgrade_to_v2,
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
