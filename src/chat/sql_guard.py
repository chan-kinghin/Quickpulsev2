"""SQL safety validation for LLM-generated queries."""

from __future__ import annotations

import re

from src.exceptions import ChatSQLError

# Tables the LLM is allowed to query
ALLOWED_TABLES = frozenset(
    {
        "cached_production_orders",
        "cached_production_bom",
        "cached_purchase_orders",
        "cached_subcontracting_orders",
        "cached_production_receipts",
        "cached_purchase_receipts",
        "cached_material_picking",
        "cached_sales_delivery",
        "cached_sales_orders",
        "sync_history",
    }
)

# Forbidden keywords (case-insensitive, word-boundary matched)
_FORBIDDEN_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "VACUUM",
    "REINDEX",
    "LOAD_EXTENSION",
    "LOAD",
]

_FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Match table names in FROM and JOIN clauses
_TABLE_PATTERN = re.compile(
    r"(?:FROM|JOIN)\s+(\w+)", re.IGNORECASE
)

# Match CTE names: WITH name AS (...)
_CTE_NAME_PATTERN = re.compile(
    r"\bWITH\s+(\w+)\s+AS\b", re.IGNORECASE
)

MAX_QUERY_LENGTH = 2000


def _strip_comments(sql: str) -> str:
    """Remove SQL comments (-- line comments and /* */ block comments)."""
    # Block comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Line comments
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql.strip()


def validate_sql(query: str) -> str:
    """Validate and sanitize an LLM-generated SQL query.

    Returns the cleaned query string.
    Raises ChatSQLError on any validation failure.
    """
    if not query or not query.strip():
        raise ChatSQLError("空的SQL查询")

    if len(query) > MAX_QUERY_LENGTH:
        raise ChatSQLError(f"SQL查询过长（最大{MAX_QUERY_LENGTH}字符）")

    cleaned = _strip_comments(query)

    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Remove trailing semicolons
    cleaned = cleaned.rstrip(";").strip()

    # Block multiple statements
    if ";" in cleaned:
        raise ChatSQLError("不允许多条SQL语句")

    # Must start with SELECT or WITH (for CTEs)
    first_word = cleaned.split()[0].upper() if cleaned.split() else ""
    if first_word not in ("SELECT", "WITH"):
        raise ChatSQLError("只允许 SELECT 查询")

    # Block forbidden keywords
    match = _FORBIDDEN_PATTERN.search(cleaned)
    if match:
        raise ChatSQLError(f"禁止使用 {match.group(1).upper()} 操作")

    # Extract CTE alias names so they don't trigger the table whitelist
    cte_names = set()
    sql_upper = cleaned.upper()
    first_cte = re.search(r"\bWITH\s+(\w+)\s+AS\b", sql_upper)
    if first_cte:
        cte_names.add(first_cte.group(1).lower())
        for match in re.finditer(r",\s*(\w+)\s+AS\b", sql_upper[first_cte.end():]):
            cte_names.add(match.group(1).lower())
    allowed = ALLOWED_TABLES | cte_names

    # Check table whitelist
    tables_found = _TABLE_PATTERN.findall(cleaned)
    for table in tables_found:
        if table.lower() not in allowed:
            raise ChatSQLError(f"不允许访问表: {table}")

    # Auto-append LIMIT if missing
    if not re.search(r"\bLIMIT\b", cleaned, re.IGNORECASE):
        cleaned += " LIMIT 100"

    return cleaned
