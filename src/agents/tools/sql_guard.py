"""SQL safety validation for LLM-generated queries."""

from __future__ import annotations

import re
from typing import Set

import sqlparse
from sqlparse.sql import (
    Identifier,
    IdentifierList,
    Parenthesis,
    Where,
)
from sqlparse.tokens import Keyword, DML, CTE

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

MAX_QUERY_LENGTH = 2000


def _strip_comments(sql: str) -> str:
    """Remove SQL comments (-- line comments and /* */ block comments)."""
    # Block comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Line comments
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql.strip()


def _extract_cte_names(parsed: sqlparse.sql.Statement) -> Set[str]:
    """Extract CTE alias names from a parsed SQL statement.

    Walks the token list looking for CTE definitions (WITH ... AS).
    Returns a set of lowercase CTE names.
    """
    cte_names: Set[str] = set()
    i = 0
    tokens = list(parsed.flatten())

    while i < len(tokens):
        tok = tokens[i]
        # Look for WITH keyword (CTE start)
        if tok.ttype is CTE and tok.normalized == "WITH":
            i += 1
            # Skip RECURSIVE if present
            while i < len(tokens) and tokens[i].ttype in (
                sqlparse.tokens.Whitespace,
                sqlparse.tokens.Newline,
            ):
                i += 1
            if i < len(tokens) and tokens[i].normalized == "RECURSIVE":
                i += 1
        # After WITH (or RECURSIVE), find CTE name followed by AS
        # Also handle comma-separated CTEs: , name AS (...)
        elif tok.ttype is Keyword and tok.normalized == "AS":
            # The CTE name is the previous non-whitespace token
            j = i - 1
            while j >= 0 and tokens[j].ttype in (
                sqlparse.tokens.Whitespace,
                sqlparse.tokens.Newline,
            ):
                j -= 1
            if j >= 0 and tokens[j].ttype is sqlparse.tokens.Name:
                cte_names.add(tokens[j].value.lower())
        i += 1

    return cte_names


def _extract_table_names_from_identifier(identifier: Identifier) -> Set[str]:
    """Extract table name(s) from a single Identifier token."""
    tables: Set[str] = set()

    # Check for subqueries inside the identifier
    for token in identifier.tokens:
        if isinstance(token, Parenthesis):
            # Subquery — parse recursively
            inner_sql = token.value[1:-1].strip()  # Strip parens
            if inner_sql:
                tables |= _extract_tables_from_sql(inner_sql)
            return tables

    # Regular table reference — get the real name (not alias)
    name = identifier.get_real_name()
    if name:
        tables.add(name.lower())
    return tables


def _extract_tables_from_parsed(parsed: sqlparse.sql.Statement) -> Set[str]:
    """Walk a parsed statement and extract all referenced table names."""
    tables: Set[str] = set()
    _walk_tokens(parsed.tokens, tables)
    return tables


def _is_cte_identifier(token: Identifier) -> bool:
    """Check if an Identifier is a CTE definition (contains AS keyword + Parenthesis)."""
    has_as = False
    has_paren = False
    for sub in token.tokens:
        if sub.ttype is Keyword and sub.normalized == "AS":
            has_as = True
        if isinstance(sub, Parenthesis):
            has_paren = True
    return has_as and has_paren


def _walk_tokens(tokens: list, tables: Set[str]) -> None:
    """Recursively walk token tree to find table references."""
    expecting_table = False
    in_cte_header = False  # After WITH keyword, before main SELECT

    for i, token in enumerate(tokens):
        # Track CTE header region (WITH ... before main SELECT)
        if token.ttype is CTE and token.normalized == "WITH":
            in_cte_header = True
            continue

        # DML SELECT after CTE header ends the CTE region
        if token.ttype is DML and token.normalized == "SELECT":
            in_cte_header = False
            expecting_table = False
            continue

        # CTE definition identifiers: name AS (SELECT ...)
        # Recurse into the parenthesized body to check tables there
        if in_cte_header and isinstance(token, Identifier):
            if _is_cte_identifier(token):
                for sub in token.tokens:
                    if isinstance(sub, Parenthesis):
                        inner = sub.value[1:-1].strip()
                        if inner:
                            tables |= _extract_tables_from_sql(inner)
            # In CTE header, also handle IdentifierList of CTEs
            continue

        if in_cte_header and isinstance(token, IdentifierList):
            for ident in token.get_identifiers():
                if isinstance(ident, Identifier) and _is_cte_identifier(ident):
                    for sub in ident.tokens:
                        if isinstance(sub, Parenthesis):
                            inner = sub.value[1:-1].strip()
                            if inner:
                                tables |= _extract_tables_from_sql(inner)
            continue

        # Recurse into subqueries in parentheses
        if isinstance(token, Parenthesis):
            inner = token.value[1:-1].strip()
            if inner:
                tables |= _extract_tables_from_sql(inner)
            continue

        # Recurse into WHERE clauses (may contain subqueries)
        if isinstance(token, Where):
            _walk_tokens(token.tokens, tables)
            continue

        # FROM or JOIN keyword — next identifier(s) are table references
        if token.ttype is Keyword and token.normalized in (
            "FROM",
            "JOIN",
            "INNER JOIN",
            "LEFT JOIN",
            "RIGHT JOIN",
            "FULL JOIN",
            "LEFT OUTER JOIN",
            "RIGHT OUTER JOIN",
            "FULL OUTER JOIN",
            "CROSS JOIN",
            "NATURAL JOIN",
        ):
            expecting_table = True
            continue

        # Keywords that end table-expecting context
        if token.ttype is Keyword and token.normalized in (
            "ON",
            "WHERE",
            "GROUP",
            "ORDER",
            "HAVING",
            "LIMIT",
            "UNION",
            "EXCEPT",
            "INTERSECT",
            "SET",
            "AS",
            "USING",
        ):
            expecting_table = False
            continue

        # DML keywords also end table context
        if token.ttype is DML:
            expecting_table = False
            continue

        if expecting_table:
            if isinstance(token, IdentifierList):
                # Multiple tables: FROM t1, t2, t3
                for ident in token.get_identifiers():
                    if isinstance(ident, Identifier):
                        tables |= _extract_table_names_from_identifier(ident)
                expecting_table = False
            elif isinstance(token, Identifier):
                tables |= _extract_table_names_from_identifier(token)
                expecting_table = False

        # Recurse into any other compound tokens (but not simple tokens)
        if hasattr(token, "tokens") and not isinstance(
            token, (Identifier, IdentifierList, Parenthesis, Where)
        ):
            _walk_tokens(token.tokens, tables)


def _extract_tables_from_sql(sql: str) -> Set[str]:
    """Parse a SQL string and extract all table names."""
    parsed_list = sqlparse.parse(sql)
    tables: Set[str] = set()
    for stmt in parsed_list:
        tables |= _extract_tables_from_parsed(stmt)
    return tables


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

    # Parse with sqlparse for robust table extraction
    parsed_list = sqlparse.parse(cleaned)
    if not parsed_list:
        raise ChatSQLError("无法解析SQL查询")

    parsed = parsed_list[0]

    # Extract CTE names so they don't trigger the table whitelist
    cte_names = _extract_cte_names(parsed)
    allowed = ALLOWED_TABLES | cte_names

    # Extract all referenced table names using AST walking
    tables = _extract_tables_from_parsed(parsed)

    # Check table whitelist
    for table in tables:
        if table not in allowed:
            raise ChatSQLError(f"不允许访问表: {table}")

    # Auto-append LIMIT if missing
    if not re.search(r"\bLIMIT\b", cleaned, re.IGNORECASE):
        cleaned += " LIMIT 100"

    return cleaned
