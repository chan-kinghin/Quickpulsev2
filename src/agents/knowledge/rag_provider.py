"""RAG provider — enriches agent prompts with relevant domain knowledge.

Uses LLM keyword extraction (when available) or heuristic fallback to
build FTS5 queries, then appends matching knowledge entries to prompts.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from src.agents.knowledge.knowledge_store import KnowledgeEntry, KnowledgeStore

logger = logging.getLogger(__name__)

# Common Chinese stopwords to filter out in heuristic mode
_CHINESE_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
    "吗", "什么", "怎么", "为什么", "多少", "哪些", "哪个",
    "请", "帮", "帮我", "查", "查询", "告诉", "看看", "一下",
    "能", "可以", "想", "知道", "问", "下",
})

# Keyword extraction prompt (Chinese, kept minimal for token efficiency)
_KEYWORD_EXTRACTION_PROMPT = """\
从用户问题中提取3-5个用于搜索制造业知识库的中文关键词。
只返回关键词，用空格分隔，不要其他内容。

用户问题：{question}

关键词："""


class RAGProvider:
    """Retrieval-Augmented Generation provider for agent prompts.

    Enriches prompts with relevant domain knowledge retrieved from the
    FTS5-backed KnowledgeStore. Uses LLM keyword extraction when an
    AgentLLMClient is available, falls back to heuristic extraction.

    Usage:
        provider = RAGProvider(knowledge_store)
        enriched = await provider.enrich_prompt(question, base_prompt, llm_client)
    """

    def __init__(self, knowledge_store: KnowledgeStore) -> None:
        self._store = knowledge_store

    async def get_relevant_knowledge(
        self,
        question: str,
        limit: int = 5,
        llm_client: Optional[object] = None,
    ) -> List[KnowledgeEntry]:
        """Retrieve relevant knowledge entries for a question.

        Args:
            question: The user's question.
            limit: Maximum entries to return.
            llm_client: Optional AgentLLMClient for keyword extraction.

        Returns:
            List of relevant KnowledgeEntry objects.
        """
        keywords = await self._extract_keywords(question, llm_client)
        if not keywords:
            # Fallback: use the raw question as search query
            return await self._store.search(question, limit=limit)

        search_query = " ".join(keywords)
        logger.debug("RAG search query: '%s' (from question: '%s')", search_query, question[:50])
        return await self._store.search(search_query, limit=limit)

    async def enrich_prompt(
        self,
        question: str,
        base_prompt: str,
        llm_client: Optional[object] = None,
    ) -> str:
        """Enrich a base prompt with relevant domain knowledge.

        Args:
            question: The user's question.
            base_prompt: The base system prompt to augment.
            llm_client: Optional AgentLLMClient for better keyword extraction.

        Returns:
            The enriched prompt with a knowledge reference section appended.
        """
        entries = await self.get_relevant_knowledge(
            question, limit=5, llm_client=llm_client
        )

        if not entries:
            return base_prompt

        # Build the knowledge reference section
        knowledge_section = "\n\n## 领域知识参考\n\n"
        for entry in entries:
            knowledge_section += entry.format_for_prompt() + "\n\n"

        return base_prompt + knowledge_section

    async def _extract_keywords(
        self,
        question: str,
        llm_client: Optional[object] = None,
    ) -> List[str]:
        """Extract search keywords from the user's question.

        Uses LLM extraction if llm_client is available, otherwise falls
        back to heuristic extraction.
        """
        if llm_client is not None:
            try:
                return await self._extract_keywords_llm(question, llm_client)
            except Exception as exc:
                logger.warning("LLM keyword extraction failed, using heuristic: %s", exc)

        return self._extract_keywords_heuristic(question)

    async def _extract_keywords_llm(
        self,
        question: str,
        llm_client: object,
    ) -> List[str]:
        """Extract keywords using the LLM.

        Sends a lightweight prompt asking the LLM to return 3-5 keywords.
        """
        # Import here to avoid circular dependency
        from src.agents.base import AgentLLMClient

        if not isinstance(llm_client, AgentLLMClient):
            return self._extract_keywords_heuristic(question)

        prompt = _KEYWORD_EXTRACTION_PROMPT.format(question=question)
        response = await llm_client.chat_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[],  # No tools needed for keyword extraction
            temperature=0.0,
        )

        content = response.get("content", "")
        if not content:
            return self._extract_keywords_heuristic(question)

        # Parse keywords from response (space-separated or comma-separated)
        keywords = re.split(r"[,，\s]+", content.strip())
        # Filter empty and overly short tokens
        keywords = [k.strip() for k in keywords if k.strip() and len(k.strip()) >= 2]
        return keywords[:5]  # Cap at 5

    def _extract_keywords_heuristic(self, question: str) -> List[str]:
        """Extract keywords using simple heuristic rules.

        Splits on whitespace, punctuation, and common Chinese particles.
        Also splits long Chinese runs into meaningful chunks when no
        natural delimiters are present.
        """
        # Step 1: Split on punctuation, whitespace, and common particles
        # Include Chinese functional words as split points
        tokens = re.split(
            r"[\s,，。？！、；：""''（）\(\)\[\]]+|"
            r"(?:请|帮我|帮|查询|查看|告诉我|看看|一下|怎么|什么|为什么|哪些|如何|能否)",
            question,
        )

        # Step 2: Further split tokens on "的" boundaries (very common in Chinese)
        expanded = []
        for token in tokens:
            if not token:
                continue
            parts = token.split("的")
            expanded.extend(p for p in parts if p)

        keywords = []
        seen = set()
        for token in expanded:
            token = token.strip()
            if not token:
                continue
            if token.lower() in _CHINESE_STOPWORDS:
                continue
            if len(token) < 2:
                continue
            if token.lower() in seen:
                continue
            seen.add(token.lower())
            keywords.append(token)

        return keywords[:5]
