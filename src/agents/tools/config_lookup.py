"""Config lookup tool — reads sections from the loaded MTOConfig.

Gives the agent awareness of material class routing, semantic field
mappings, and receipt source configuration without hardcoding.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agents.base import ToolDefinition

logger = logging.getLogger(__name__)


def create_config_lookup_tool(mto_config) -> ToolDefinition:
    """Create the config lookup tool bound to an MTOConfig instance.

    Args:
        mto_config: The MTOConfig instance from app.state.

    Returns:
        A ToolDefinition that reads MTO configuration sections.
    """

    async def handler(section: Optional[str] = None) -> str:
        """Look up MTO configuration details.

        Args:
            section: One of "material_classes", "receipt_sources", or
                     a specific class ID like "finished_goods".
                     If omitted, returns an overview.

        Returns:
            JSON description of the requested config section.
        """
        if not section or section == "overview":
            classes = []
            for mc in mto_config.material_classes:
                classes.append({
                    "id": mc.id,
                    "display_name": mc.display_name,
                    "pattern": mc.pattern.pattern,
                    "source_form": mc.source_form,
                    "mto_field": mc.mto_field,
                })
            return json.dumps({
                "material_classes": classes,
                "receipt_sources": list(mto_config.receipt_sources.keys()),
            }, ensure_ascii=False, indent=2)

        if section == "material_classes":
            result = []
            for mc in mto_config.material_classes:
                entry = {
                    "id": mc.id,
                    "display_name": mc.display_name,
                    "pattern": mc.pattern.pattern,
                    "material_type": mc.material_type,
                    "source_form": mc.source_form,
                    "mto_field": mc.mto_field,
                    "columns": {k: _column_to_dict(v) for k, v in mc.columns.items()},
                    "item_fields": mc.item_fields,
                }
                if mc.semantic:
                    entry["semantic"] = {
                        "demand_field": mc.semantic.demand_field,
                        "fulfilled_field": mc.semantic.fulfilled_field,
                        "picking_field": mc.semantic.picking_field,
                    }
                result.append(entry)
            return json.dumps(result, ensure_ascii=False, indent=2)

        if section == "receipt_sources":
            result = {}
            for name, src in mto_config.receipt_sources.items():
                result[name] = {
                    "form_id": src.form_id,
                    "mto_field": src.mto_field,
                    "qty_field": src.qty_field,
                    "material_field": src.material_field,
                    "link_field": src.link_field,
                }
            return json.dumps(result, ensure_ascii=False, indent=2)

        # Try as a specific material class ID
        for mc in mto_config.material_classes:
            if mc.id == section:
                entry = {
                    "id": mc.id,
                    "display_name": mc.display_name,
                    "pattern": mc.pattern.pattern,
                    "material_type": mc.material_type,
                    "source_form": mc.source_form,
                    "mto_field": mc.mto_field,
                    "columns": {k: _column_to_dict(v) for k, v in mc.columns.items()},
                    "item_fields": mc.item_fields,
                }
                if mc.semantic:
                    entry["semantic"] = {
                        "demand_field": mc.semantic.demand_field,
                        "fulfilled_field": mc.semantic.fulfilled_field,
                        "picking_field": mc.semantic.picking_field,
                        "metrics": [
                            {"name": m.name, "label": m.label, "format": m.format}
                            for m in mc.semantic.metrics
                        ],
                        "provenance": mc.semantic.provenance,
                    }
                return json.dumps(entry, ensure_ascii=False, indent=2)

        return f"未知配置节: {section}。可用: overview, material_classes, receipt_sources, 或具体类ID"

    return ToolDefinition(
        name="config_lookup",
        description=(
            "查询MTO配置信息，包括物料类别路由、语义字段映射、入库数据源配置等。"
            "可传入 'overview'（概览）、'material_classes'、'receipt_sources'、"
            "或具体类ID如 'finished_goods'。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "description": "配置节名称: overview, material_classes, receipt_sources, 或具体类ID",
                },
            },
            "required": [],
        },
        handler=handler,
    )


def _column_to_dict(col) -> dict:
    """Convert a ColumnConfig to a plain dict."""
    d = {}
    if col.source:
        d["source"] = col.source
    if col.data_field:
        d["field"] = col.data_field
    if col.match_by:
        d["match_by"] = col.match_by
    if col.calculated:
        d["calculated"] = col.calculated
    if col.subtract:
        d["subtract"] = col.subtract
    return d
