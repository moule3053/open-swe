"""Apply the idempotent platform schema before services start."""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from openswe_platform.common.config import get_settings


async def migrate() -> None:
    database_url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    schema = Path(__file__).parents[1] / "migrations" / "001_init.sql"
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute("SELECT pg_advisory_lock(hashtext('openswe-platform-migration'))")
        await connection.execute(schema.read_text())
    finally:
        await connection.close()


def main() -> None:
    asyncio.run(migrate())


if __name__ == "__main__":
    main()
