"""Context builders — serialize MTO data and SQL results for the LLM."""

from __future__ import annotations

from typing import Any

# Material type code → display name
_MATERIAL_TYPES = {1: "自制", 2: "外购", 3: "委外"}

MAX_ITEMS_PER_TYPE = 20
MAX_SQL_ROWS = 50


def build_mto_context(mto_data: dict[str, Any]) -> str:
    """Serialize an MTOStatusResponse dict into compact text for the LLM.

    Groups child items by material type, caps per-type to MAX_ITEMS_PER_TYPE,
    and includes semantic metrics when present.  Target: <2 000 tokens.
    """
    lines: list[str] = []

    parent = mto_data.get("parent_item") or {}
    lines.append(f"MTO: {parent.get('mto_number', '?')}")
    if parent.get("customer_name"):
        lines.append(f"客户: {parent['customer_name']}")
    if parent.get("delivery_date"):
        lines.append(f"交期: {parent['delivery_date']}")
    if parent.get("material_name"):
        lines.append(f"成品: {parent['material_name']}")
    if parent.get("specification"):
        lines.append(f"规格: {parent['specification']}")
    lines.append("")

    children = mto_data.get("child_items") or []
    grouped: dict[str, list[dict]] = {}
    for item in children:
        mt_code = item.get("material_type_code") or item.get("material_type", 0)
        mt_name = _MATERIAL_TYPES.get(int(mt_code), f"类型{mt_code}")
        grouped.setdefault(mt_name, []).append(item)

    for mt_name, items in grouped.items():
        lines.append(f"## {mt_name} ({len(items)}项)")
        for item in items[:MAX_ITEMS_PER_TYPE]:
            code = item.get("material_code", "?")
            name = item.get("material_name", "?")
            line = f"- {code} {name}"

            # Append relevant quantity info
            qty_parts: list[str] = []
            for key in (
                "sales_order_qty",
                "purchase_order_qty",
                "prod_instock_must_qty",
                "prod_instock_real_qty",
                "purchase_stock_in_qty",
                "pick_actual_qty",
            ):
                val = item.get(key)
                if val is not None and float(val) != 0:
                    qty_parts.append(f"{key}={val}")
            if qty_parts:
                line += f" | {', '.join(qty_parts)}"

            # Append metrics
            metrics = item.get("metrics") or {}
            metric_parts: list[str] = []
            for mname, mval in metrics.items():
                if isinstance(mval, dict) and mval.get("value") is not None:
                    metric_parts.append(f"{mval.get('label', mname)}={mval['value']}")
            if metric_parts:
                line += f" | {', '.join(metric_parts)}"

            lines.append(line)

        if len(items) > MAX_ITEMS_PER_TYPE:
            lines.append(f"  ...及其他 {len(items) - MAX_ITEMS_PER_TYPE} 项")
        lines.append("")

    return "\n".join(lines)


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
