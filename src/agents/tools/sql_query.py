"""SQL query tool — validates and executes SQL against the cache database.

Wraps sql_guard.validate_sql() + db.execute_read_with_columns() as an
agent-callable tool.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.agents.base import ToolDefinition
from src.chat.context import build_sql_result_context
from src.chat.sql_guard import validate_sql
from src.database.connection import Database
from src.exceptions import ChatSQLError

logger = logging.getLogger(__name__)


def create_sql_query_tool(db: Database) -> ToolDefinition:
    """Create the SQL query tool bound to a database instance.

    Args:
        db: The Database instance for executing queries.

    Returns:
        A ToolDefinition that validates and executes SQL queries.
    """

    async def handler(query: str) -> str:
        """Validate and execute a SQL query, returning formatted results."""
        # Validate
        try:
            safe_sql = validate_sql(query)
        except ChatSQLError as exc:
            return f"SQL验证失败: {exc}"

        # Execute
        try:
            rows, columns = await db.execute_read_with_columns(safe_sql)
        except Exception as exc:
            return f"SQL执行失败: {exc}"

        # Format results
        result = build_sql_result_context(rows, columns)
        return f"查询: {safe_sql}\n\n{result}"

    return ToolDefinition(
        name="sql_query",
        description=(
            "执行 SQLite 查询并返回结果。只允许 SELECT 语句，"
            "只能查询缓存表（cached_production_orders, cached_production_bom 等）。"
            "自动添加 LIMIT 100。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要执行的 SQL SELECT 查询语句",
                },
            },
            "required": ["query"],
        },
        handler=handler,
    )
