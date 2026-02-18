"""FTS5-backed knowledge store for manufacturing domain knowledge.

Uses SQLite FTS5 for full-text search — no vector DB, no embeddings.
Designed for <5MB memory footprint on a 512MB CVM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from src.database.connection import Database

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeEntry:
    """A single knowledge base entry."""

    id: int
    concept_id: str
    category: str
    title: str
    content: str
    tags: str

    def format_for_prompt(self) -> str:
        """Format this entry for inclusion in an LLM prompt."""
        return f"### {self.title}\n{self.content}"


class KnowledgeStore:
    """FTS5-backed knowledge store for domain knowledge.

    Schema uses a content table + FTS5 virtual table with content sync.
    Supports search by Chinese keywords via unicode61 tokenizer.

    Usage:
        store = KnowledgeStore()
        await store.initialize(db)
        results = await store.search("入库完成率")
    """

    _SCHEMA_SQL = """
        CREATE TABLE IF NOT EXISTS knowledge_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_id TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
            title, content, tags,
            content=knowledge_entries,
            content_rowid=id,
            tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge_entries BEGIN
            INSERT INTO knowledge_fts(rowid, title, content, tags)
            VALUES (new.id, new.title, new.content, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge_entries BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content, tags)
            VALUES ('delete', old.id, old.title, old.content, old.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge_entries BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content, tags)
            VALUES ('delete', old.id, old.title, old.content, old.tags);
            INSERT INTO knowledge_fts(rowid, title, content, tags)
            VALUES (new.id, new.title, new.content, new.tags);
        END;
    """

    _INSERT_SQL = """
        INSERT INTO knowledge_entries (concept_id, category, title, content, tags)
        VALUES (?, ?, ?, ?, ?)
    """

    _SEARCH_SQL = """
        SELECT e.id, e.concept_id, e.category, e.title, e.content, e.tags
        FROM knowledge_entries e
        JOIN knowledge_fts f ON e.id = f.rowid
        WHERE knowledge_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """

    _COUNT_SQL = "SELECT COUNT(*) FROM knowledge_entries"

    def __init__(self) -> None:
        self._db: Optional[Database] = None

    async def initialize(self, db: Database) -> None:
        """Create tables and seed with initial data if empty.

        Args:
            db: The Database instance (same one used by the app).
        """
        self._db = db

        # Create schema (executescript handles multiple statements)
        conn = db._connection
        await conn.executescript(self._SCHEMA_SQL)
        await conn.commit()

        # Seed if empty
        entry_count = await self.count()
        if entry_count == 0:
            await self._seed()
            logger.info("Knowledge store seeded with initial data")
        else:
            logger.debug("Knowledge store already has %d entries", entry_count)

    async def _seed(self) -> None:
        """Populate the knowledge store with seed data."""
        from src.agents.knowledge.seed_data import SEED_ENTRIES

        for entry in SEED_ENTRIES:
            await self._db.execute_write(
                self._INSERT_SQL,
                [
                    entry["concept_id"],
                    entry["category"],
                    entry["title"],
                    entry["content"],
                    entry.get("tags", ""),
                ],
            )
        logger.info("Seeded %d knowledge entries", len(SEED_ENTRIES))

    async def search(self, query: str, limit: int = 5) -> List[KnowledgeEntry]:
        """Search the knowledge base using FTS5.

        Args:
            query: Search query (Chinese or English keywords).
            limit: Maximum results to return (default 5).

        Returns:
            List of matching KnowledgeEntry objects, ranked by relevance.
        """
        if not self._db:
            logger.warning("KnowledgeStore not initialized")
            return []

        if not query or not query.strip():
            return []

        # Build FTS5 query: split tokens and OR them for broader recall.
        # FTS5 unicode61 tokenizer splits on word boundaries, which works
        # for Chinese characters (each character is a token).
        tokens = query.strip().split()
        if not tokens:
            return []

        # Use OR between tokens for broader matching
        fts_query = " OR ".join(tokens)

        try:
            rows = await self._db.execute_read(self._SEARCH_SQL, [fts_query, limit])
            return [
                KnowledgeEntry(
                    id=row[0],
                    concept_id=row[1],
                    category=row[2],
                    title=row[3],
                    content=row[4],
                    tags=row[5],
                )
                for row in rows
            ]
        except Exception as exc:
            # FTS5 query syntax errors shouldn't crash the system
            logger.warning("Knowledge search failed for query '%s': %s", query, exc)
            return []

    async def add_entry(
        self,
        concept_id: str,
        category: str,
        title: str,
        content: str,
        tags: str = "",
    ) -> int:
        """Insert a new knowledge entry.

        Returns the new entry's row ID.
        """
        if not self._db:
            raise RuntimeError("KnowledgeStore not initialized")

        await self._db.execute_write(
            self._INSERT_SQL,
            [concept_id, category, title, content, tags],
        )
        rows = await self._db.execute_read("SELECT last_insert_rowid()")
        return rows[0][0]

    async def count(self) -> int:
        """Return the number of entries in the knowledge store."""
        if not self._db:
            return 0
        rows = await self._db.execute_read(self._COUNT_SQL)
        return rows[0][0]
