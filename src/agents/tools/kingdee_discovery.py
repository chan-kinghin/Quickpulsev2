"""Kingdee field discovery tool — agent tool wrapper for KingdeeFieldDiscovery.

Exposes field discovery as a ToolDefinition so the schema mapper agent
can introspect available fields via the standard tool-calling interface.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agents.base import ToolDefinition
from src.agents.schema_mapping.discovery import KingdeeFieldDiscovery

logger = logging.getLogger(__name__)


def create_kingdee_discovery_tool(
    discovery: KingdeeFieldDiscovery,
) -> ToolDefinition:
    """Create the Kingdee field discovery tool.

    Args:
        discovery: A KingdeeFieldDiscovery instance.

    Returns:
        A ToolDefinition that discovers fields for a material class.
    """

    async def handler(
        material_class: Optional[str] = None,
    ) -> str:
        """Discover available Kingdee fields for a material class.

        Args:
            material_class: Material class ID (e.g. "finished_goods").
                           If omitted, discovers fields for all classes.

        Returns:
            JSON description of discovered fields.
        """
        if material_class:
            fields = await discovery.discover_fields(material_class)
            if not fields:
                return json.dumps(
                    {"error": f"未找到物料类别: {material_class}"},
                    ensure_ascii=False,
                )
            return json.dumps(
                {
                    "material_class": material_class,
                    "field_count": len(fields),
                    "fields": [f.to_dict() for f in fields],
                },
                ensure_ascii=False,
                indent=2,
            )
        else:
            all_fields = await discovery.discover_all_classes()
            result = {}
            for class_id, fields in all_fields.items():
                result[class_id] = {
                    "field_count": len(fields),
                    "fields": [f.to_dict() for f in fields],
                }
            return json.dumps(result, ensure_ascii=False, indent=2)

    return ToolDefinition(
        name="kingdee_discovery",
        description=(
            "发现金蝶ERP字段信息。传入物料类别ID（如 'finished_goods'）"
            "返回该类别的所有已知字段及其元数据（来源表单、中文标签、数据类型等）。"
            "不传参数则返回所有类别的字段。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "material_class": {
                    "type": "string",
                    "description": "物料类别ID，如 finished_goods, self_made, purchased",
                },
            },
            "required": [],
        },
        handler=handler,
    )
