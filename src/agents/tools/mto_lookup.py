"""MTO lookup tool — wraps the existing MTOQueryHandler for agent use.

Gives the agent access to the full MTO status query (production orders,
BOM, receipts, picking, deliveries) without needing to construct SQL.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agents.base import ToolDefinition

logger = logging.getLogger(__name__)


def create_mto_lookup_tool(mto_handler) -> ToolDefinition:
    """Create the MTO lookup tool bound to an MTOQueryHandler instance.

    Args:
        mto_handler: The MTOQueryHandler instance from app.state.

    Returns:
        A ToolDefinition that queries full MTO status.
    """

    async def handler(mto_number: str) -> str:
        """Query full MTO status for a given MTO number.

        Args:
            mto_number: The MTO number to query (e.g., "AK2510034").

        Returns:
            JSON summary of MTO status including parent item and children.
        """
        try:
            result = await mto_handler.query(mto_number)
        except Exception as exc:
            return f"MTO查询失败: {exc}"

        if not result:
            return f"未找到MTO: {mto_number}"

        # Serialize to a compact summary
        summary = {
            "mto_number": mto_number,
            "parent_item": None,
            "child_count": 0,
            "children_summary": [],
        }

        if result.parent_item:
            pi = result.parent_item
            summary["parent_item"] = {
                "bill_no": pi.bill_no,
                "material_code": pi.material_code,
                "material_name": pi.material_name,
                "qty": float(pi.qty) if pi.qty else 0,
            }

        if result.child_items:
            summary["child_count"] = len(result.child_items)
            # Include first 20 children to stay within token budget
            for child in result.child_items[:20]:
                child_info = {
                    "material_code": child.material_code,
                    "material_name": child.material_name,
                }
                if child.metrics:
                    child_info["metrics"] = {
                        k: {"value": str(v.value) if v.value is not None else None, "status": v.status}
                        for k, v in child.metrics.items()
                    }
                summary["children_summary"].append(child_info)

            if len(result.child_items) > 20:
                summary["note"] = f"仅显示前20项，共{len(result.child_items)}项子件"

        return json.dumps(summary, ensure_ascii=False, indent=2)

    return ToolDefinition(
        name="mto_lookup",
        description=(
            "查询指定MTO编号的完整生产状态，包括父项、子件、入库完成率等。"
            "输入MTO编号（如 AK2510034），返回结构化的状态数据。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "mto_number": {
                    "type": "string",
                    "description": "MTO编号，如 AK2510034",
                },
            },
            "required": ["mto_number"],
        },
        handler=handler,
    )
