"""Schema lookup tool — returns SQLite table/column metadata.

Uses PRAGMA table_info to introspect the cache database schema,
giving the agent awareness of available tables and columns.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.agents.base import ToolDefinition
from src.chat.sql_guard import ALLOWED_TABLES
from src.database.connection import Database

logger = logging.getLogger(__name__)


def create_schema_lookup_tool(db: Database) -> ToolDefinition:
    """Create the schema lookup tool bound to a database instance.

    Args:
        db: The Database instance for schema introspection.

    Returns:
        A ToolDefinition that returns table/column info.
    """

    async def handler(table_name: Optional[str] = None) -> str:
        """Return schema info for a specific table or list all tables.

        Args:
            table_name: If provided, return columns for this table.
                        If omitted, return list of all allowed tables.
        """
        if table_name:
            if table_name.lower() not in ALLOWED_TABLES:
                return f"表 '{table_name}' 不在允许列表中。允许的表: {', '.join(sorted(ALLOWED_TABLES))}"

            try:
                rows = await db.execute_read(
                    f"PRAGMA table_info({table_name})"
                )
            except Exception as exc:
                return f"查询表结构失败: {exc}"

            if not rows:
                return f"表 '{table_name}' 不存在或没有列。"

            lines = [f"## {table_name} 表结构\n"]
            lines.append("| 列名 | 类型 | 可空 | 默认值 |")
            lines.append("| --- | --- | --- | --- |")
            for row in rows:
                # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
                col_name = row[1]
                col_type = row[2] or "TEXT"
                nullable = "否" if row[3] else "是"
                default = str(row[4]) if row[4] is not None else ""
                lines.append(f"| {col_name} | {col_type} | {nullable} | {default} |")

            return "\n".join(lines)
        else:
            # List all allowed tables
            lines = ["## 可用数据表\n"]
            for tbl in sorted(ALLOWED_TABLES):
                lines.append(f"- {tbl}")
            return "\n".join(lines)

    return ToolDefinition(
        name="schema_lookup",
        description=(
            "查询数据库表结构信息。不传参数返回所有可用表列表，"
            "传入 table_name 返回该表的列名和类型。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "要查询结构的表名（可选，不传则列出所有表）",
                },
            },
            "required": [],
        },
        handler=handler,
    )
