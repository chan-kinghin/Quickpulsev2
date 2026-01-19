"""Database connection utilities."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import aiosqlite


class Database:
    """Async SQLite database wrapper."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._connection = await aiosqlite.connect(self.db_path)
        await self._init_schema()

    async def _init_schema(self) -> None:
        schema_path = Path(__file__).parent / "schema.sql"
        schema = schema_path.read_text(encoding="utf-8")
        await self._connection.executescript(schema)
        await self._apply_migrations()
        await self._connection.commit()

    async def _apply_migrations(self) -> None:
        """Apply schema migrations for cache table enhancements."""
        # Note: mto_number column doesn't exist in cached_production_bom yet
        # It's extracted from raw_data JSON in cache_reader.py
        # Index on mto_number would require schema migration first
        pass

    async def execute(self, query: str, params=None):
        async with self._connection.execute(query, params or []) as cursor:
            return await cursor.fetchall()

    async def execute_read(self, query: str, params=None):
        """Execute a read query and return all results."""
        async with self._connection.execute(query, params or []) as cursor:
            return await cursor.fetchall()

    async def execute_write(self, query: str, params=None) -> None:
        await self._connection.execute(query, params or [])
        await self._connection.commit()

    async def executemany(self, query: str, params: Iterable[Sequence]) -> None:
        await self._connection.executemany(query, params)
        await self._connection.commit()

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
