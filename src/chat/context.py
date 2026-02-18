"""Context builders — serialize SQL results for the LLM."""

from __future__ import annotations

MAX_SQL_ROWS = 50


def build_sql_result_context(
    rows: list[tuple | list],
    column_names: list[str],
) -> str:
    """Format SQL query results as a markdown table for the LLM.

    Caps at MAX_SQL_ROWS rows.
    """
    if not rows:
        return "(无结果)"

    capped = rows[:MAX_SQL_ROWS]
    header = "| " + " | ".join(column_names) + " |"
    separator = "| " + " | ".join("---" for _ in column_names) + " |"
    body_lines = []
    for row in capped:
        cells = [str(c) if c is not None else "" for c in row]
        body_lines.append("| " + " | ".join(cells) + " |")

    parts = [header, separator] + body_lines
    if len(rows) > MAX_SQL_ROWS:
        parts.append(f"\n(共 {len(rows)} 行，仅显示前 {MAX_SQL_ROWS} 行)")

    return "\n".join(parts)
