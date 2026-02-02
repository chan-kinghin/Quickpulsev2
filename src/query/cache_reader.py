"""Cache reader for MTO queries from SQLite.

This module provides fast cached lookups for MTO data, avoiding
expensive Kingdee API calls when cached data is fresh.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from src.database.connection import Database

logger = logging.getLogger(__name__)
from src.readers.models import (
    MaterialPickingModel,
    ProductionBOMModel,
    ProductionOrderModel,
    ProductionReceiptModel,
    PurchaseOrderModel,
    PurchaseReceiptModel,
    SalesDeliveryModel,
    SalesOrderModel,
    SubcontractingOrderModel,
)


@dataclass
class CacheResult:
    """Result from cache query with freshness metadata."""

    data: list
    synced_at: Optional[datetime]
    is_fresh: bool


class CacheReader:
    """Read cached data from SQLite for MTO queries."""

    def __init__(self, db: Database, ttl_minutes: int = 60):
        self.db = db
        self.ttl = timedelta(minutes=ttl_minutes)

    async def get_production_orders(self, mto_number: str) -> CacheResult:
        """Get cached production orders for MTO number."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, workshop, material_code,
                   material_name, specification, aux_attributes, qty,
                   status, create_date, synced_at
            FROM cached_production_orders
            WHERE mto_number = ?
            ORDER BY synced_at DESC
            """,
            [mto_number],
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # Parse synced_at from first row (now at index 10)
        synced_at = self._parse_timestamp(rows[0][10])
        is_fresh = self._is_fresh(synced_at)

        # Convert rows to ProductionOrderModel (no JSON parsing needed)
        orders = [self._row_to_order(row) for row in rows]

        return CacheResult(data=orders, synced_at=synced_at, is_fresh=is_fresh)

    async def get_production_bom(self, bill_nos: list[str]) -> CacheResult:
        """Get cached BOM entries for given bill numbers."""
        if not bill_nos:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        placeholders = ",".join(["?"] * len(bill_nos))
        rows = await self.db.execute_read(
            f"""
            SELECT mo_bill_no, mto_number, material_code, material_name,
                   specification, aux_attributes, aux_prop_id, material_type,
                   need_qty, picked_qty, no_picked_qty, synced_at
            FROM cached_production_bom
            WHERE mo_bill_no IN ({placeholders})
            ORDER BY synced_at DESC
            """,
            bill_nos,
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # Get oldest synced_at (worst case freshness) - now at index 11
        synced_times = [self._parse_timestamp(row[11]) for row in rows if row[11]]
        oldest_sync = min(synced_times) if synced_times else None
        is_fresh = self._is_fresh(oldest_sync) if oldest_sync else False

        # Convert rows to ProductionBOMModel (no JSON parsing needed)
        bom_entries = [self._row_to_bom(row) for row in rows]

        return CacheResult(data=bom_entries, synced_at=oldest_sync, is_fresh=is_fresh)

    async def get_purchase_orders(self, mto_number: str) -> CacheResult:
        """Get cached purchase orders (外购件) for MTO number."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, material_name, specification,
                   aux_attributes, aux_prop_id, order_qty, stock_in_qty,
                   remain_stock_in_qty, raw_data, synced_at
            FROM cached_purchase_orders
            WHERE mto_number = ?
            """,
            [mto_number],
        )
        return self._build_cache_result(
            rows, self._row_to_purchase_order, synced_at_index=11
        )

    async def get_subcontracting_orders(self, mto_number: str) -> CacheResult:
        """Get cached subcontracting orders (委外件) for MTO number."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, order_qty, stock_in_qty,
                   no_stock_in_qty, raw_data, synced_at
            FROM cached_subcontracting_orders
            WHERE mto_number = ?
            """,
            [mto_number],
        )
        return self._build_cache_result(
            rows, self._row_to_subcontracting_order, synced_at_index=7
        )

    async def get_production_receipts(self, mto_number: str) -> CacheResult:
        """Get cached production receipts (自制件入库) for MTO number."""
        rows = await self.db.execute_read(
            """
            SELECT mto_number, material_code, real_qty, must_qty, aux_prop_id, raw_data, synced_at
            FROM cached_production_receipts
            WHERE mto_number = ?
            """,
            [mto_number],
        )
        return self._build_cache_result(
            rows, self._row_to_production_receipt, synced_at_index=6
        )

    async def get_purchase_receipts(self, mto_number: str) -> CacheResult:
        """Get cached purchase receipts (外购/委外入库) for MTO number."""
        rows = await self.db.execute_read(
            """
            SELECT mto_number, material_code, real_qty, must_qty, bill_type_number,
                   raw_data, synced_at
            FROM cached_purchase_receipts
            WHERE mto_number = ?
            """,
            [mto_number],
        )
        return self._build_cache_result(
            rows, self._row_to_purchase_receipt, synced_at_index=6
        )

    async def get_material_picking(self, mto_number: str) -> CacheResult:
        """Get cached material picking records (生产领料) for MTO number."""
        rows = await self.db.execute_read(
            """
            SELECT mto_number, material_code, app_qty, actual_qty, ppbom_bill_no,
                   aux_prop_id, raw_data, synced_at
            FROM cached_material_picking
            WHERE mto_number = ?
            """,
            [mto_number],
        )
        return self._build_cache_result(
            rows, self._row_to_material_picking, synced_at_index=7
        )

    async def get_sales_delivery(self, mto_number: str) -> CacheResult:
        """Get cached sales delivery records (销售出库) for MTO number."""
        rows = await self.db.execute_read(
            """
            SELECT mto_number, material_code, real_qty, must_qty, aux_prop_id, raw_data, synced_at
            FROM cached_sales_delivery
            WHERE mto_number = ?
            """,
            [mto_number],
        )
        return self._build_cache_result(
            rows, self._row_to_sales_delivery, synced_at_index=6
        )

    async def get_sales_orders(self, mto_number: str) -> CacheResult:
        """Get cached sales orders (客户/交期) for MTO number."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, material_name, specification,
                   aux_attributes, aux_prop_id, customer_name, delivery_date, qty,
                   raw_data, synced_at
            FROM cached_sales_orders
            WHERE mto_number = ?
            """,
            [mto_number],
        )
        return self._build_cache_result(
            rows, self._row_to_sales_order, synced_at_index=11
        )

    def _build_cache_result(
        self, rows: list, converter, synced_at_index: int
    ) -> CacheResult:
        """Build CacheResult from rows with given converter function."""
        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        synced_times = [
            self._parse_timestamp(row[synced_at_index])
            for row in rows
            if row[synced_at_index]
        ]
        oldest_sync = min(synced_times) if synced_times else None
        is_fresh = self._is_fresh(oldest_sync) if oldest_sync else False

        data = [converter(row) for row in rows]
        return CacheResult(data=data, synced_at=oldest_sync, is_fresh=is_fresh)

    async def check_freshness(self, mto_number: str) -> tuple[bool, Optional[datetime]]:
        """Quick check if MTO data exists and is fresh without loading full data."""
        rows = await self.db.execute_read(
            """
            SELECT MAX(synced_at) as latest_sync
            FROM cached_production_orders
            WHERE mto_number = ?
            """,
            [mto_number],
        )

        if not rows or not rows[0][0]:
            return False, None

        synced_at = self._parse_timestamp(rows[0][0])
        return self._is_fresh(synced_at), synced_at

    def _is_fresh(self, synced_at: Optional[datetime]) -> bool:
        """Check if cache is within TTL.

        Note: SQLite CURRENT_TIMESTAMP uses UTC, so we compare with utcnow().
        """
        if not synced_at:
            return False
        return datetime.utcnow() - synced_at < self.ttl

    def _parse_timestamp(self, value) -> Optional[datetime]:
        """Parse SQLite timestamp string to datetime."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    def _row_to_order(self, row: tuple) -> ProductionOrderModel:
        """Convert database row to ProductionOrderModel.

        Row columns (after schema optimization):
        0: bill_no, 1: mto_number, 2: workshop, 3: material_code,
        4: material_name, 5: specification, 6: aux_attributes, 7: qty,
        8: status, 9: create_date, 10: synced_at
        """
        return ProductionOrderModel(
            bill_no=row[0] or "",
            mto_number=row[1] or "",
            workshop=row[2] or "",
            material_code=row[3] or "",
            material_name=row[4] or "",
            specification=row[5] or "",
            aux_attributes=row[6] or "",
            qty=Decimal(str(row[7] or 0)),
            status=row[8] or "",  # Now read directly from column
            create_date=row[9],  # Now read directly from column
        )

    def _row_to_bom(self, row: tuple) -> ProductionBOMModel:
        """Convert database row to ProductionBOMModel.

        Row columns (after schema optimization):
        0: mo_bill_no, 1: mto_number, 2: material_code, 3: material_name,
        4: specification, 5: aux_attributes, 6: aux_prop_id, 7: material_type,
        8: need_qty, 9: picked_qty, 10: no_picked_qty, 11: synced_at
        """
        return ProductionBOMModel(
            mo_bill_no=row[0] or "",
            mto_number=row[1] or "",  # Now read directly from column
            material_code=row[2] or "",
            material_name=row[3] or "",
            specification=row[4] or "",  # Now read directly from column
            aux_attributes=row[5] or "",  # Now read directly from column
            aux_prop_id=row[6] or 0,  # Now read directly from column
            material_type=row[7] or 0,
            need_qty=Decimal(str(row[8] or 0)),
            picked_qty=Decimal(str(row[9] or 0)),
            no_picked_qty=Decimal(str(row[10] or 0)),
        )

    def _row_to_purchase_order(self, row: tuple) -> PurchaseOrderModel:
        """Convert database row to PurchaseOrderModel."""
        return PurchaseOrderModel(
            bill_no=row[0] or "",
            mto_number=row[1] or "",
            material_code=row[2] or "",
            material_name=row[3] or "",
            specification=row[4] or "",
            aux_attributes=row[5] or "",
            aux_prop_id=row[6] or 0,
            order_qty=Decimal(str(row[7] or 0)),
            stock_in_qty=Decimal(str(row[8] or 0)),
            remain_stock_in_qty=Decimal(str(row[9] or 0)),
        )

    def _row_to_subcontracting_order(self, row: tuple) -> SubcontractingOrderModel:
        """Convert database row to SubcontractingOrderModel."""
        return SubcontractingOrderModel(
            bill_no=row[0] or "",
            mto_number=row[1] or "",
            material_code=row[2] or "",
            order_qty=Decimal(str(row[3] or 0)),
            stock_in_qty=Decimal(str(row[4] or 0)),
            no_stock_in_qty=Decimal(str(row[5] or 0)),
        )

    def _row_to_production_receipt(self, row: tuple) -> ProductionReceiptModel:
        """Convert database row to ProductionReceiptModel.

        Row columns:
        0: mto_number, 1: material_code, 2: real_qty, 3: must_qty,
        4: aux_prop_id, 5: raw_data, 6: synced_at

        Note: material_name and specification come from raw_data JSON if available,
        otherwise default to empty string (will be populated from live API).
        """
        # Try to extract material_name and specification from raw_data JSON
        material_name = ""
        specification = ""
        if row[5]:
            try:
                import json
                raw_data = json.loads(row[5]) if isinstance(row[5], str) else row[5]
                material_name = raw_data.get("material_name", "")
                specification = raw_data.get("specification", "")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass  # Use defaults

        return ProductionReceiptModel(
            mto_number=row[0] or "",
            material_code=row[1] or "",
            material_name=material_name,
            specification=specification,
            real_qty=Decimal(str(row[2] or 0)),
            must_qty=Decimal(str(row[3] or 0)),
            aux_prop_id=row[4] or 0,  # For variant-aware matching
        )

    def _row_to_purchase_receipt(self, row: tuple) -> PurchaseReceiptModel:
        """Convert database row to PurchaseReceiptModel."""
        return PurchaseReceiptModel(
            mto_number=row[0] or "",
            material_code=row[1] or "",
            real_qty=Decimal(str(row[2] or 0)),
            must_qty=Decimal(str(row[3] or 0)),
            bill_type_number=row[4] or "",
        )

    def _row_to_material_picking(self, row: tuple) -> MaterialPickingModel:
        """Convert database row to MaterialPickingModel.

        Row columns:
        0: mto_number, 1: material_code, 2: app_qty, 3: actual_qty,
        4: ppbom_bill_no, 5: aux_prop_id, 6: raw_data, 7: synced_at
        """
        return MaterialPickingModel(
            mto_number=row[0] or "",
            material_code=row[1] or "",
            app_qty=Decimal(str(row[2] or 0)),
            actual_qty=Decimal(str(row[3] or 0)),
            ppbom_bill_no=row[4] or "",
            aux_prop_id=row[5] or 0,  # For variant-aware matching
        )

    def _row_to_sales_delivery(self, row: tuple) -> SalesDeliveryModel:
        """Convert database row to SalesDeliveryModel.

        Row columns:
        0: mto_number, 1: material_code, 2: real_qty, 3: must_qty,
        4: aux_prop_id, 5: raw_data, 6: synced_at
        """
        return SalesDeliveryModel(
            mto_number=row[0] or "",
            material_code=row[1] or "",
            real_qty=Decimal(str(row[2] or 0)),
            must_qty=Decimal(str(row[3] or 0)),
            aux_prop_id=row[4] or 0,  # For variant-aware matching
        )

    def _row_to_sales_order(self, row: tuple) -> SalesOrderModel:
        """Convert database row to SalesOrderModel.

        Row columns:
        0: bill_no, 1: mto_number, 2: material_code, 3: material_name,
        4: specification, 5: aux_attributes, 6: aux_prop_id, 7: customer_name,
        8: delivery_date, 9: qty, 10: raw_data, 11: synced_at
        """
        return SalesOrderModel(
            bill_no=row[0] or "",
            mto_number=row[1] or "",
            material_code=row[2] or "",
            material_name=row[3] or "",
            specification=row[4] or "",
            aux_attributes=row[5] or "",
            aux_prop_id=row[6] or 0,
            customer_name=row[7] or "",
            delivery_date=row[8] if row[8] else None,
            qty=Decimal(str(row[9] or 0)),
        )
