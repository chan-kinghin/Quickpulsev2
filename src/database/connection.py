"""Database connection utilities."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from contextlib import asynccontextmanager
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
        """Apply schema migrations for cache table enhancements.

        Migrations are SQL files in the migrations/ directory.
        Each migration runs once and is tracked in _migrations table.
        """
        migrations_dir = Path(__file__).parent / "migrations"
        if not migrations_dir.exists():
            return

        # Create migrations tracking table
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                name TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Get already applied migrations
        async with self._connection.execute("SELECT name FROM _migrations") as cursor:
            applied = {row[0] for row in await cursor.fetchall()}

        # Apply new migrations in sorted order
        for migration_file in sorted(migrations_dir.glob("*.sql")):
            if migration_file.name not in applied:
                # Special handling for migrations that add columns (SQLite lacks IF NOT EXISTS)
                if migration_file.name == "003_add_bom_short_name.sql":
                    # Check if column already exists (schema.sql may have it)
                    if await self._column_exists("cached_sales_orders", "bom_short_name"):
                        # Mark as applied without running (column exists from schema.sql)
                        await self._connection.execute(
                            "INSERT INTO _migrations (name) VALUES (?)",
                            [migration_file.name]
                        )
                        continue

                sql = migration_file.read_text(encoding="utf-8")
                await self._connection.executescript(sql)
                await self._connection.execute(
                    "INSERT INTO _migrations (name) VALUES (?)",
                    [migration_file.name]
                )

    async def _column_exists(self, table: str, column: str) -> bool:
        """Check if a column exists in a table."""
        async with self._connection.execute(f"PRAGMA table_info({table})") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
            return column in columns

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

    # =========================================================================
    # Transaction support for atomic batch operations
    # =========================================================================

    @asynccontextmanager
    async def transaction(self):
        """Context manager for explicit transaction control.

        Enables atomic batch operations - all writes succeed together
        or all roll back on error.

        Usage:
            async with db.transaction():
                await db.execute_write_no_commit(...)
                await db.executemany_no_commit(...)
            # Commits on exit, rolls back on exception
        """
        try:
            yield
            await self._connection.commit()
        except Exception:
            await self._connection.rollback()
            raise

    async def execute_write_no_commit(self, query: str, params=None) -> None:
        """Execute write without immediate commit (use within transaction)."""
        await self._connection.execute(query, params or [])

    async def executemany_no_commit(self, query: str, params: Iterable[Sequence]) -> None:
        """Execute many without immediate commit (use within transaction)."""
        await self._connection.executemany(query, params)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
