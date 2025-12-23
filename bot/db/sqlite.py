from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite


async def init_db(db_path: str, schema_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        with open(schema_path, "r", encoding="utf-8") as schema_file:
            await conn.executescript(schema_file.read())
        await conn.commit()


def run_init_db(db_path: str, schema_path: str) -> None:
    asyncio.run(init_db(db_path, schema_path))
