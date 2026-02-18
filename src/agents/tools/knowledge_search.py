"""Knowledge search tool — searches the manufacturing domain knowledge base.

Wraps KnowledgeStore.search() as an agent-callable ToolDefinition.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.agents.base import ToolDefinition
from src.agents.knowledge.knowledge_store import KnowledgeStore

logger = logging.getLogger(__name__)


def create_knowledge_search_tool(knowledge_store: KnowledgeStore) -> ToolDefinition:
    """Create the knowledge search tool bound to a KnowledgeStore instance.

    Args:
        knowledge_store: The initialized KnowledgeStore to search.

    Returns:
        A ToolDefinition that searches the manufacturing knowledge base.
    """

    async def handler(query: str, limit: int = 5) -> str:
        """Search the knowledge base and return formatted results."""
        entries = await knowledge_store.search(query, limit=limit)

        if not entries:
            return f"未找到与 '{query}' 相关的知识条目。"

        lines = [f"找到 {len(entries)} 条相关知识：\n"]
        for i, entry in enumerate(entries, 1):
            lines.append(f"**{i}. {entry.title}** [{entry.category}]")
            lines.append(entry.content)
            if entry.tags:
                lines.append(f"标签: {entry.tags}")
            lines.append("")

        return "\n".join(lines)

    return ToolDefinition(
        name="knowledge_search",
        description=(
            "搜索制造业领域知识库，查找与生产管理相关的概念、字段说明、业务规则和SQL查询示例。"
            "输入中文关键词获取最相关的知识条目。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词（中文），如：入库完成率、超领、MTO、采购订单",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量上限，默认5",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
        handler=handler,
    )
