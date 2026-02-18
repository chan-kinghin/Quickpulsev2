"""Tests for Phase 4 — knowledge store, RAG provider, ontology, seed data."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.agents.knowledge.ontology import (
    DOMAIN_CONCEPTS,
    DomainConcept,
    get_concept,
    get_concepts_by_category,
)
from src.agents.knowledge.knowledge_store import KnowledgeEntry, KnowledgeStore
from src.agents.knowledge.rag_provider import RAGProvider
from src.agents.knowledge.seed_data import SEED_ENTRIES
from src.database.connection import Database


# ---------------------------------------------------------------------------
# Domain Ontology
# ---------------------------------------------------------------------------


class TestDomainOntology:
    """Tests for the domain ontology definitions."""

    def test_has_20_concepts(self):
        assert len(DOMAIN_CONCEPTS) == 20

    def test_concept_has_required_fields(self):
        for concept in DOMAIN_CONCEPTS:
            assert concept.id
            assert concept.name_zh
            assert concept.name_en
            assert concept.description
            assert concept.category in ("process", "document", "field", "metric", "rule")

    def test_get_concept_by_id(self):
        mto = get_concept("mto")
        assert mto is not None
        assert mto.name_en == "MTO Number"

    def test_get_concept_returns_none_for_unknown(self):
        assert get_concept("nonexistent") is None

    def test_get_concepts_by_category(self):
        documents = get_concepts_by_category("document")
        assert len(documents) > 0
        assert all(c.category == "document" for c in documents)

    def test_get_concepts_by_category_empty(self):
        result = get_concepts_by_category("nonexistent_category")
        assert result == []

    def test_all_ids_unique(self):
        ids = [c.id for c in DOMAIN_CONCEPTS]
        assert len(ids) == len(set(ids))

    def test_key_concepts_exist(self):
        expected_ids = [
            "mto", "production_order", "bom", "fulfillment_rate",
            "over_pick", "document_status", "material_type",
        ]
        existing_ids = {c.id for c in DOMAIN_CONCEPTS}
        for eid in expected_ids:
            assert eid in existing_ids, f"Missing concept: {eid}"


# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------


class TestSeedData:
    """Tests for the seed data definitions."""

    def test_seed_entries_count(self):
        assert len(SEED_ENTRIES) == 77

    def test_seed_entries_have_required_fields(self):
        for entry in SEED_ENTRIES:
            assert "concept_id" in entry
            assert "category" in entry
            assert "title" in entry
            assert "content" in entry

    def test_seed_entries_categories(self):
        categories = {e["category"] for e in SEED_ENTRIES}
        assert "concept" in categories
        assert "field" in categories
        assert "rule" in categories
        assert "query_pattern" in categories
        assert "table" in categories


# ---------------------------------------------------------------------------
# KnowledgeEntry
# ---------------------------------------------------------------------------


class TestKnowledgeEntry:
    """Tests for KnowledgeEntry dataclass."""

    def test_format_for_prompt(self):
        entry = KnowledgeEntry(
            id=1,
            concept_id="mto",
            category="concept",
            title="MTO (计划跟踪号)",
            content="MTO is the core tracking unit.",
            tags="mto,tracking",
        )
        formatted = entry.format_for_prompt()
        assert "### MTO (计划跟踪号)" in formatted
        assert "core tracking unit" in formatted


# ---------------------------------------------------------------------------
# KnowledgeStore (FTS5)
# ---------------------------------------------------------------------------


class TestKnowledgeStore:
    """Tests for KnowledgeStore with in-memory SQLite database."""

    @pytest_asyncio.fixture
    async def db(self):
        """Create an in-memory database for testing."""
        database = Database(Path(":memory:"))
        database._connection = await __import__("aiosqlite").connect(":memory:")
        yield database
        await database._connection.close()

    @pytest_asyncio.fixture
    async def store(self, db):
        """Create and initialize a KnowledgeStore."""
        store = KnowledgeStore()
        await store.initialize(db)
        return store

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, db):
        store = KnowledgeStore()
        await store.initialize(db)

        # Check that knowledge_entries table exists
        rows = await db.execute_read(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_entries'"
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_initialize_seeds_data(self, store):
        count = await store.count()
        assert count == len(SEED_ENTRIES)

    @pytest.mark.asyncio
    async def test_search_returns_relevant_entries(self, store):
        results = await store.search("MTO")
        assert len(results) > 0
        assert any("MTO" in r.title or "MTO" in r.content for r in results)

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_empty(self, store):
        results = await store.search("")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_whitespace_query_returns_empty(self, store):
        results = await store.search("   ")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_limit(self, store):
        results = await store.search("MTO", limit=2)
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_add_entry(self, store):
        initial_count = await store.count()

        new_id = await store.add_entry(
            concept_id="test_concept",
            category="test",
            title="Test Entry",
            content="This is a test knowledge entry.",
            tags="test,entry",
        )

        assert new_id > 0
        assert await store.count() == initial_count + 1

    @pytest.mark.asyncio
    async def test_added_entry_is_searchable(self, store):
        await store.add_entry(
            concept_id="unique_test",
            category="test",
            title="Unique Searchable Entry",
            content="This entry contains xyzzy12345 for search testing.",
            tags="unique,xyzzy12345",
        )

        results = await store.search("xyzzy12345")
        assert len(results) >= 1
        assert any("xyzzy12345" in r.content or "xyzzy12345" in r.tags for r in results)

    @pytest.mark.asyncio
    async def test_search_uninitialized_returns_empty(self):
        store = KnowledgeStore()
        results = await store.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_count_uninitialized_returns_zero(self):
        store = KnowledgeStore()
        assert await store.count() == 0

    @pytest.mark.asyncio
    async def test_add_entry_uninitialized_raises(self):
        store = KnowledgeStore()
        with pytest.raises(RuntimeError, match="not initialized"):
            await store.add_entry("a", "b", "c", "d")

    @pytest.mark.asyncio
    async def test_second_initialize_does_not_re_seed(self, db):
        """If already seeded, initialize should not double-seed."""
        store = KnowledgeStore()
        await store.initialize(db)
        count_after_first = await store.count()

        # Initialize again
        await store.initialize(db)
        count_after_second = await store.count()

        assert count_after_first == count_after_second

    @pytest.mark.asyncio
    async def test_search_chinese_keywords(self, store):
        """Search with Chinese characters should work via unicode61 tokenizer."""
        results = await store.search("入库完成率")
        assert len(results) > 0


# ---------------------------------------------------------------------------
# RAGProvider
# ---------------------------------------------------------------------------


class TestRAGProvider:
    """Tests for the RAG provider."""

    @pytest_asyncio.fixture
    async def store_with_data(self):
        """Create an in-memory store with seed data."""
        database = Database(Path(":memory:"))
        database._connection = await __import__("aiosqlite").connect(":memory:")
        store = KnowledgeStore()
        await store.initialize(database)
        yield store
        await database._connection.close()

    def test_heuristic_keyword_extraction(self):
        provider = RAGProvider(MagicMock())
        keywords = provider._extract_keywords_heuristic(
            "AK2510034的入库完成率是多少？"
        )
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        # Should extract meaningful keywords, not stopwords
        assert all(len(k) >= 2 for k in keywords)

    def test_heuristic_filters_stopwords(self):
        provider = RAGProvider(MagicMock())
        keywords = provider._extract_keywords_heuristic("请帮我查询一下超领的情况")
        # "请", "帮我", "查询", "一下" should be filtered
        for kw in keywords:
            assert kw not in ("请", "帮我", "查询", "一下", "的")

    def test_heuristic_caps_at_5_keywords(self):
        provider = RAGProvider(MagicMock())
        long_question = "物料编码 物料类型 入库完成率 超领 采购订单 委外订单 生产订单 领料"
        keywords = provider._extract_keywords_heuristic(long_question)
        assert len(keywords) <= 5

    @pytest.mark.asyncio
    async def test_enrich_prompt_appends_knowledge(self, store_with_data):
        provider = RAGProvider(store_with_data)
        base_prompt = "You are a test agent."
        enriched = await provider.enrich_prompt("入库完成率", base_prompt)

        assert enriched.startswith(base_prompt)
        assert "领域知识参考" in enriched

    @pytest.mark.asyncio
    async def test_enrich_prompt_returns_base_when_no_results(self, store_with_data):
        provider = RAGProvider(store_with_data)
        base_prompt = "Test prompt"
        # Use a very specific query unlikely to match
        enriched = await provider.enrich_prompt(
            "xyzzy_nonexistent_99999", base_prompt
        )
        # Should return base prompt unchanged when no results
        assert enriched == base_prompt

    @pytest.mark.asyncio
    async def test_get_relevant_knowledge_with_llm_client(self, store_with_data):
        """When LLM client is provided, it should be used for keyword extraction."""
        from src.agents.base import AgentLLMClient

        mock_client = MagicMock(spec=AgentLLMClient)
        mock_client.chat_with_tools = AsyncMock(return_value={
            "content": "MTO 入库 完成率",
            "tool_calls": [],
            "usage": {"total_tokens": 5},
        })

        provider = RAGProvider(store_with_data)
        results = await provider.get_relevant_knowledge(
            "What about the fulfillment?",
            llm_client=mock_client,
        )

        assert isinstance(results, list)
        mock_client.chat_with_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_relevant_knowledge_fallback_on_llm_error(self, store_with_data):
        """If LLM keyword extraction fails, should fall back to heuristic."""
        from src.agents.base import AgentLLMClient

        mock_client = MagicMock(spec=AgentLLMClient)
        mock_client.chat_with_tools = AsyncMock(
            side_effect=Exception("LLM unavailable")
        )

        provider = RAGProvider(store_with_data)
        # Should not raise — falls back to heuristic
        results = await provider.get_relevant_knowledge(
            "入库完成率",
            llm_client=mock_client,
        )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_relevant_knowledge_without_llm(self, store_with_data):
        """Without LLM client, should use heuristic extraction."""
        provider = RAGProvider(store_with_data)
        results = await provider.get_relevant_knowledge("超领")
        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Knowledge Search Tool
# ---------------------------------------------------------------------------


class TestKnowledgeSearchTool:
    """Tests for the knowledge_search tool."""

    @pytest_asyncio.fixture
    async def search_tool(self):
        """Create a knowledge_search tool with seeded store."""
        from src.agents.tools.knowledge_search import create_knowledge_search_tool

        database = Database(Path(":memory:"))
        database._connection = await __import__("aiosqlite").connect(":memory:")
        store = KnowledgeStore()
        await store.initialize(database)
        tool = create_knowledge_search_tool(store)
        yield tool
        await database._connection.close()

    def test_tool_metadata(self):
        from src.agents.tools.knowledge_search import create_knowledge_search_tool

        store = MagicMock()
        tool = create_knowledge_search_tool(store)
        assert tool.name == "knowledge_search"
        assert "query" in tool.parameters["required"]

    @pytest.mark.asyncio
    async def test_search_returns_formatted_results(self, search_tool):
        result = await search_tool.handler(query="MTO")
        assert "相关知识" in result

    @pytest.mark.asyncio
    async def test_search_no_results(self, search_tool):
        result = await search_tool.handler(query="xyzzy_nothing_999")
        assert "未找到" in result
