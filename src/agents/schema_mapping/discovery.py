"""Kingdee field discovery — introspects config and DB for available fields.

Collects field metadata from two sources:
1. MTOConfig (item_fields, columns, semantic.provenance) — the configured view
2. SQLite PRAGMA table_info — the actual cache schema

This gives the mapper agent a complete picture of what fields exist
and what they're currently used for.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.database.connection import Database
from src.mto_config.mto_config import MTOConfig

logger = logging.getLogger(__name__)


@dataclass
class FieldInfo:
    """Metadata about a single Kingdee / cache field."""

    name: str
    chinese_label: Optional[str] = None
    source_form: Optional[str] = None
    data_type: str = "TEXT"
    current_role: Optional[str] = None  # semantic role if already mapped
    provenance_kingdee_field: Optional[str] = None  # e.g. "FRealQty"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"name": self.name, "data_type": self.data_type}
        if self.chinese_label:
            d["chinese_label"] = self.chinese_label
        if self.source_form:
            d["source_form"] = self.source_form
        if self.current_role:
            d["current_role"] = self.current_role
        if self.provenance_kingdee_field:
            d["provenance_kingdee_field"] = self.provenance_kingdee_field
        return d


# Well-known Chinese labels for common Kingdee field suffixes.
# Used as a fallback when no label is configured.
_KINGDEE_LABEL_HINTS: Dict[str, str] = {
    "FQty": "数量",
    "FRealQty": "实收数量",
    "FMustQty": "应收数量",
    "FActualQty": "实发数量",
    "FAppQty": "申请数量",
    "FStockInQty": "累计入库数量",
    "FRemainStockInQty": "未入库数量",
    "FBillNo": "单据编号",
    "FMaterialId.FNumber": "物料编码",
    "FMaterialId.FName": "物料名称",
    "FMaterialId.FSpecification": "规格型号",
    "FAuxPropId": "辅助属性",
}


class KingdeeFieldDiscovery:
    """Discovers available fields from MTOConfig and the SQLite cache.

    Usage:
        discovery = KingdeeFieldDiscovery(mto_config, db)
        fields = await discovery.discover_fields("finished_goods")
    """

    def __init__(self, mto_config: MTOConfig, db: Optional[Database] = None) -> None:
        self._config = mto_config
        self._db = db

    async def discover_fields(self, material_class_id: str) -> List[FieldInfo]:
        """Discover all known fields for a material class.

        Merges information from:
        - item_fields mapping (Kingdee field keys used in queries)
        - columns configuration (data sources and calculated fields)
        - semantic provenance (which Kingdee fields back semantic roles)
        - SQLite cache table columns (if database available)

        Args:
            material_class_id: e.g. "finished_goods", "self_made", "purchased"

        Returns:
            List of FieldInfo with as much metadata as available.
        """
        mc = self._find_class(material_class_id)
        if not mc:
            logger.warning("Material class '%s' not found in config", material_class_id)
            return []

        seen: Dict[str, FieldInfo] = {}

        # 1. item_fields — the raw Kingdee field keys used in API queries
        for logical_name, kingdee_key in mc.item_fields.items():
            label = _KINGDEE_LABEL_HINTS.get(kingdee_key)
            fi = FieldInfo(
                name=logical_name,
                chinese_label=label,
                source_form=mc.source_form,
                provenance_kingdee_field=kingdee_key,
            )
            seen[logical_name] = fi

        # 2. columns — the data source references for each display column
        for col_name, col_cfg in mc.columns.items():
            if col_name in seen:
                # Augment existing entry with column source info
                if col_cfg.source:
                    seen[col_name].source_form = col_cfg.source
                continue
            fi = FieldInfo(
                name=col_name,
                source_form=col_cfg.source,
            )
            if col_cfg.calculated:
                fi.data_type = "CALCULATED"
            seen[col_name] = fi

        # 3. semantic provenance — maps semantic field names to Kingdee fields
        if mc.semantic and mc.semantic.provenance:
            role_map = {
                mc.semantic.demand_field: "demand_field",
                mc.semantic.fulfilled_field: "fulfilled_field",
                mc.semantic.picking_field: "picking_field",
            }
            for semantic_name, prov in mc.semantic.provenance.items():
                fi = FieldInfo(
                    name=semantic_name,
                    source_form=prov.get("source_form"),
                    provenance_kingdee_field=prov.get("kingdee_field"),
                    chinese_label=_KINGDEE_LABEL_HINTS.get(
                        prov.get("kingdee_field", "")
                    ),
                )
                # Tag with its semantic role
                role = role_map.get(semantic_name)
                if role:
                    fi.current_role = role
                seen[semantic_name] = fi

        # 4. Receipt sources — add fields from linked receipt readers
        for src_name, src_cfg in self._config.receipt_sources.items():
            # Only include receipt sources referenced by this class's columns
            referenced = any(
                col.source == src_name for col in mc.columns.values()
            )
            if not referenced:
                continue
            qty_field_name = f"{src_name.lower()}_qty"
            if qty_field_name not in seen:
                seen[qty_field_name] = FieldInfo(
                    name=qty_field_name,
                    source_form=src_cfg.form_id,
                    provenance_kingdee_field=src_cfg.qty_field,
                    chinese_label=_KINGDEE_LABEL_HINTS.get(src_cfg.qty_field),
                )

        # 5. SQLite cache columns (if DB available)
        if self._db:
            db_fields = await self._discover_from_db(mc.source_form)
            for fi in db_fields:
                if fi.name not in seen:
                    seen[fi.name] = fi

        return list(seen.values())

    async def discover_all_classes(self) -> Dict[str, List[FieldInfo]]:
        """Discover fields for all configured material classes.

        Returns:
            Dict mapping material_class_id to its field list.
        """
        result: Dict[str, List[FieldInfo]] = {}
        for mc in self._config.material_classes:
            result[mc.id] = await self.discover_fields(mc.id)
        return result

    async def _discover_from_db(self, source_form: str) -> List[FieldInfo]:
        """Discover columns from SQLite cache tables.

        Maps source form names to their cache table names and reads
        PRAGMA table_info.
        """
        # Map Kingdee form IDs to cache table names
        form_to_table = {
            "SAL_SaleOrder": "cached_sales_orders",
            "PRD_MO": "cached_production_orders",
            "PUR_PurchaseOrder": "cached_purchase_orders",
            "PRD_INSTOCK": "cached_production_receipts",
            "STK_InStock": "cached_purchase_receipts",
            "PRD_PickMtrl": "cached_material_picking",
            "SAL_OUTSTOCK": "cached_sales_delivery",
            "SUB_POORDER": "cached_subcontracting_orders",
        }

        table_name = form_to_table.get(source_form)
        if not table_name:
            return []

        try:
            rows = await self._db.execute_read(
                f"PRAGMA table_info({table_name})"
            )
        except Exception as exc:
            logger.warning("Failed to read schema for %s: %s", table_name, exc)
            return []

        fields: List[FieldInfo] = []
        for row in rows:
            col_name = row[1]
            col_type = row[2] or "TEXT"
            fields.append(FieldInfo(
                name=col_name,
                data_type=col_type,
                source_form=source_form,
            ))
        return fields

    def _find_class(self, class_id: str):
        """Look up a MaterialClassConfig by ID."""
        for mc in self._config.material_classes:
            if mc.id == class_id:
                return mc
        return None
