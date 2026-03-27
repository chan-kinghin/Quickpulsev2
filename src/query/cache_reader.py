"""Cache reader for MTO queries from SQLite.

This module provides fast cached lookups for MTO data, avoiding
expensive Kingdee API calls when cached data is fresh.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
class BOMJoinedRow:
    """Pre-joined BOM row with aggregated data from all source tables."""

    # BOM fields
    mo_bill_no: str
    mto_number: str
    material_code: str
    material_name: str
    specification: str
    aux_attributes: str
    aux_prop_id: int
    material_type: int  # 1=自制, 2=外购, 3=委外
    need_qty: Decimal
    picked_qty: Decimal
    no_picked_qty: Decimal
    # Aggregated from production receipts (PRD_INSTOCK)
    prod_receipt_real_qty: Decimal
    prod_receipt_must_qty: Decimal
    # Aggregated from material picking (PRD_PickMtrl)
    pick_actual_qty: Decimal
    pick_app_qty: Decimal
    # Aggregated from purchase orders (PUR_PurchaseOrder)
    purchase_order_qty: Decimal
    purchase_stock_in_qty: Decimal
    # Aggregated from purchase receipts (STK_InStock)
    purchase_receipt_real_qty: Decimal
    # Aggregated from subcontracting orders (SUB_POORDER)
    subcontract_order_qty: Decimal
    subcontract_stock_in_qty: Decimal
    # Aggregated from sales delivery (SAL_OUTSTOCK)
    delivery_real_qty: Decimal


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
        """Get cached production orders for MTO number (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, workshop, material_code,
                   material_name, specification, aux_attributes, qty,
                   status, create_date, aux_prop_id, synced_at
            FROM cached_production_orders
            WHERE mto_number LIKE ?
            ORDER BY synced_at DESC
            """,
            [f"{mto_number}%"],
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # Parse synced_at from first row (now at index 11)
        synced_at = self._parse_timestamp(rows[0][11])
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

    async def get_production_bom_by_mto(self, mto_number: str) -> CacheResult:
        """Get cached BOM entries for MTO number (prefix match).

        用于获取 03 级包材的领料数据。
        """
        rows = await self.db.execute_read(
            """
            SELECT mo_bill_no, mto_number, material_code, material_name,
                   specification, aux_attributes, aux_prop_id, material_type,
                   need_qty, picked_qty, no_picked_qty, synced_at
            FROM cached_production_bom
            WHERE mto_number LIKE ?
            ORDER BY synced_at DESC
            """,
            [f"{mto_number}%"],
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # Get oldest synced_at (worst case freshness) - now at index 11
        synced_times = [self._parse_timestamp(row[11]) for row in rows if row[11]]
        oldest_sync = min(synced_times) if synced_times else None
        is_fresh = self._is_fresh(oldest_sync) if oldest_sync else False

        # Convert rows to ProductionBOMModel
        bom_entries = [self._row_to_bom(row) for row in rows]

        return CacheResult(data=bom_entries, synced_at=oldest_sync, is_fresh=is_fresh)

    async def get_purchase_orders(self, mto_number: str) -> CacheResult:
        """Get cached purchase orders (外购件) for MTO number (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, material_name, specification,
                   aux_attributes, aux_prop_id, order_qty, stock_in_qty,
                   remain_stock_in_qty, raw_data, synced_at
            FROM cached_purchase_orders
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )
        return self._build_cache_result(
            rows, self._row_to_purchase_order, synced_at_index=11
        )

    async def get_subcontracting_orders(self, mto_number: str) -> CacheResult:
        """Get cached subcontracting orders (委外件) for MTO number (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, order_qty, stock_in_qty,
                   no_stock_in_qty, aux_prop_id, raw_data, synced_at
            FROM cached_subcontracting_orders
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )
        return self._build_cache_result(
            rows, self._row_to_subcontracting_order, synced_at_index=8
        )

    async def get_production_receipts(self, mto_number: str) -> CacheResult:
        """Get cached production receipts (自制件入库) for MTO number (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, real_qty, must_qty,
                   aux_prop_id, raw_data, synced_at
            FROM cached_production_receipts
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )
        return self._build_cache_result(
            rows, self._row_to_production_receipt, synced_at_index=7
        )

    async def get_purchase_receipts(self, mto_number: str) -> CacheResult:
        """Get cached purchase receipts (外购/委外入库) for MTO number (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, real_qty, must_qty,
                   bill_type_number, aux_prop_id, raw_data, synced_at
            FROM cached_purchase_receipts
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )
        return self._build_cache_result(
            rows, self._row_to_purchase_receipt, synced_at_index=8
        )

    async def get_material_picking(self, mto_number: str) -> CacheResult:
        """Get cached material picking records (生产领料) for MTO number (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT mto_number, material_code, app_qty, actual_qty, ppbom_bill_no,
                   aux_prop_id, raw_data, synced_at
            FROM cached_material_picking
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )
        return self._build_cache_result(
            rows, self._row_to_material_picking, synced_at_index=7
        )

    async def get_sales_delivery(self, mto_number: str) -> CacheResult:
        """Get cached sales delivery records (销售出库) for MTO number (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, real_qty, must_qty,
                   aux_prop_id, raw_data, synced_at
            FROM cached_sales_delivery
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )
        return self._build_cache_result(
            rows, self._row_to_sales_delivery, synced_at_index=7
        )

    async def get_sales_orders(self, mto_number: str) -> CacheResult:
        """Get cached sales orders (客户/交期) for MTO number (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT bill_no, mto_number, material_code, material_name, specification,
                   aux_attributes, aux_prop_id, customer_name, delivery_date, qty,
                   bom_short_name, raw_data, synced_at
            FROM cached_sales_orders
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )
        return self._build_cache_result(
            rows, self._row_to_sales_order, synced_at_index=12
        )

    async def get_mto_bom_joined(self, mto_number: str) -> CacheResult:
        """Get BOM items with all receipt/pick/order data pre-joined via SQL.

        Uses pre-aggregated subqueries to avoid the multiplicative join problem
        when multiple BOM rows share the same (material_code, aux_prop_id).

        Each receipt/order table has THREE JOINs (3-tier aux_prop_id fallback):
        - Tier 1: Exact match on (material_code, aux_prop_id)
        - Tier 2: When BOM has specific aux (!=0), fallback to receipts with aux=0
        - Tier 3: When BOM has generic aux (=0), sum ALL receipts for that material
        COALESCE prefers exact match; Tier 2/3 are mutually exclusive by aux value.
        """
        pattern = f"{mto_number}%"
        rows = await self.db.execute_read(
            """
            WITH bom_ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY material_code, aux_prop_id
                    ORDER BY synced_at DESC, id DESC
                ) AS rn
                FROM cached_production_bom
                WHERE mto_number LIKE ? AND material_code NOT LIKE '07.%'
            ),
            bom_repr AS (SELECT * FROM bom_ranked WHERE rn = 1),
            bom_agg AS (
                SELECT material_code, aux_prop_id,
                       SUM(need_qty) as need_qty, SUM(picked_qty) as picked_qty,
                       SUM(no_picked_qty) as no_picked_qty, MAX(synced_at) as synced_at
                FROM cached_production_bom
                WHERE mto_number LIKE ? AND material_code NOT LIKE '07.%'
                GROUP BY material_code, aux_prop_id
            )
            SELECT
                br.mo_bill_no,
                br.mto_number,
                br.material_code,
                br.material_name,
                br.specification,
                br.aux_attributes,
                br.aux_prop_id,
                br.material_type,
                ROUND(ba.need_qty, 2) as need_qty,
                ROUND(ba.picked_qty, 2) as picked_qty,
                ROUND(ba.no_picked_qty, 2) as no_picked_qty,
                ROUND(COALESCE(
                    pr.real_qty,
                    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id != 0 THEN pr0.real_qty END,
                    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id = 0 THEN pr_all.real_qty END,
                    0
                ), 2) as prod_receipt_real_qty,
                ROUND(COALESCE(
                    pr.must_qty,
                    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id != 0 THEN pr0.must_qty END,
                    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id = 0 THEN pr_all.must_qty END,
                    0
                ), 2) as prod_receipt_must_qty,
                ROUND(COALESCE(
                    pk.actual_qty,
                    CASE WHEN pk.material_code IS NULL AND br.aux_prop_id != 0 THEN pk0.actual_qty END,
                    CASE WHEN pk.material_code IS NULL AND br.aux_prop_id = 0 THEN pk_all.actual_qty END,
                    0
                ), 2) as pick_actual_qty,
                ROUND(COALESCE(
                    pk.app_qty,
                    CASE WHEN pk.material_code IS NULL AND br.aux_prop_id != 0 THEN pk0.app_qty END,
                    CASE WHEN pk.material_code IS NULL AND br.aux_prop_id = 0 THEN pk_all.app_qty END,
                    0
                ), 2) as pick_app_qty,
                ROUND(COALESCE(
                    po.order_qty,
                    CASE WHEN po.material_code IS NULL AND br.aux_prop_id != 0 THEN po0.order_qty END,
                    CASE WHEN po.material_code IS NULL AND br.aux_prop_id = 0 THEN po_all.order_qty END,
                    0
                ), 2) as purchase_order_qty,
                ROUND(COALESCE(
                    po.stock_in_qty,
                    CASE WHEN po.material_code IS NULL AND br.aux_prop_id != 0 THEN po0.stock_in_qty END,
                    CASE WHEN po.material_code IS NULL AND br.aux_prop_id = 0 THEN po_all.stock_in_qty END,
                    0
                ), 2) as purchase_stock_in_qty,
                ROUND(COALESCE(
                    pur.real_qty,
                    CASE WHEN pur.material_code IS NULL AND br.aux_prop_id != 0 THEN pur0.real_qty END,
                    CASE WHEN pur.material_code IS NULL AND br.aux_prop_id = 0 THEN pur_all.real_qty END,
                    0
                ), 2) as purchase_receipt_real_qty,
                ROUND(COALESCE(
                    sub.order_qty,
                    CASE WHEN sub.material_code IS NULL AND br.aux_prop_id != 0 THEN sub0.order_qty END,
                    CASE WHEN sub.material_code IS NULL AND br.aux_prop_id = 0 THEN sub_all.order_qty END,
                    0
                ), 2) as subcontract_order_qty,
                ROUND(COALESCE(
                    sub.stock_in_qty,
                    CASE WHEN sub.material_code IS NULL AND br.aux_prop_id != 0 THEN sub0.stock_in_qty END,
                    CASE WHEN sub.material_code IS NULL AND br.aux_prop_id = 0 THEN sub_all.stock_in_qty END,
                    0
                ), 2) as subcontract_stock_in_qty,
                ROUND(COALESCE(
                    sd.real_qty,
                    CASE WHEN sd.material_code IS NULL AND br.aux_prop_id != 0 THEN sd0.real_qty END,
                    CASE WHEN sd.material_code IS NULL AND br.aux_prop_id = 0 THEN sd_all.real_qty END,
                    0
                ), 2) as delivery_real_qty,
                ba.synced_at
            FROM bom_repr br
            JOIN bom_agg ba ON br.material_code = ba.material_code
                           AND br.aux_prop_id = ba.aux_prop_id

            /* --- Production receipts (PRD_INSTOCK) --- */
            LEFT JOIN (
                SELECT material_code, aux_prop_id,
                       SUM(real_qty) as real_qty, SUM(must_qty) as must_qty
                FROM cached_production_receipts WHERE mto_number LIKE ?
                GROUP BY material_code, aux_prop_id
            ) pr ON br.material_code = pr.material_code
                 AND br.aux_prop_id = pr.aux_prop_id
            LEFT JOIN (
                SELECT material_code,
                       SUM(real_qty) as real_qty, SUM(must_qty) as must_qty
                FROM cached_production_receipts
                WHERE mto_number LIKE ? AND aux_prop_id = 0
                GROUP BY material_code
            ) pr0 ON br.material_code = pr0.material_code
            LEFT JOIN (
                SELECT material_code,
                       SUM(real_qty) as real_qty, SUM(must_qty) as must_qty
                FROM cached_production_receipts WHERE mto_number LIKE ?
                GROUP BY material_code
            ) pr_all ON br.material_code = pr_all.material_code

            /* --- Material picking (PRD_PickMtrl) --- */
            LEFT JOIN (
                SELECT material_code, aux_prop_id,
                       SUM(actual_qty) as actual_qty, SUM(app_qty) as app_qty
                FROM cached_material_picking WHERE mto_number LIKE ?
                GROUP BY material_code, aux_prop_id
            ) pk ON br.material_code = pk.material_code
                 AND br.aux_prop_id = pk.aux_prop_id
            LEFT JOIN (
                SELECT material_code,
                       SUM(actual_qty) as actual_qty, SUM(app_qty) as app_qty
                FROM cached_material_picking
                WHERE mto_number LIKE ? AND aux_prop_id = 0
                GROUP BY material_code
            ) pk0 ON br.material_code = pk0.material_code
            LEFT JOIN (
                SELECT material_code,
                       SUM(actual_qty) as actual_qty, SUM(app_qty) as app_qty
                FROM cached_material_picking WHERE mto_number LIKE ?
                GROUP BY material_code
            ) pk_all ON br.material_code = pk_all.material_code

            /* --- Purchase orders (PUR_PurchaseOrder) --- */
            LEFT JOIN (
                SELECT material_code, aux_prop_id,
                       SUM(order_qty) as order_qty, SUM(stock_in_qty) as stock_in_qty
                FROM cached_purchase_orders WHERE mto_number LIKE ?
                GROUP BY material_code, aux_prop_id
            ) po ON br.material_code = po.material_code
                 AND br.aux_prop_id = po.aux_prop_id
            LEFT JOIN (
                SELECT material_code,
                       SUM(order_qty) as order_qty, SUM(stock_in_qty) as stock_in_qty
                FROM cached_purchase_orders
                WHERE mto_number LIKE ? AND aux_prop_id = 0
                GROUP BY material_code
            ) po0 ON br.material_code = po0.material_code
            LEFT JOIN (
                SELECT material_code,
                       SUM(order_qty) as order_qty, SUM(stock_in_qty) as stock_in_qty
                FROM cached_purchase_orders WHERE mto_number LIKE ?
                GROUP BY material_code
            ) po_all ON br.material_code = po_all.material_code

            /* --- Purchase receipts (STK_InStock) --- */
            LEFT JOIN (
                SELECT material_code, aux_prop_id,
                       SUM(real_qty) as real_qty
                FROM cached_purchase_receipts WHERE mto_number LIKE ?
                GROUP BY material_code, aux_prop_id
            ) pur ON br.material_code = pur.material_code
                  AND br.aux_prop_id = pur.aux_prop_id
            LEFT JOIN (
                SELECT material_code,
                       SUM(real_qty) as real_qty
                FROM cached_purchase_receipts
                WHERE mto_number LIKE ? AND aux_prop_id = 0
                GROUP BY material_code
            ) pur0 ON br.material_code = pur0.material_code
            LEFT JOIN (
                SELECT material_code,
                       SUM(real_qty) as real_qty
                FROM cached_purchase_receipts WHERE mto_number LIKE ?
                GROUP BY material_code
            ) pur_all ON br.material_code = pur_all.material_code

            /* --- Subcontracting orders (SUB_POORDER) --- */
            LEFT JOIN (
                SELECT material_code, aux_prop_id,
                       SUM(order_qty) as order_qty, SUM(stock_in_qty) as stock_in_qty
                FROM cached_subcontracting_orders WHERE mto_number LIKE ?
                GROUP BY material_code, aux_prop_id
            ) sub ON br.material_code = sub.material_code
                  AND br.aux_prop_id = sub.aux_prop_id
            LEFT JOIN (
                SELECT material_code,
                       SUM(order_qty) as order_qty, SUM(stock_in_qty) as stock_in_qty
                FROM cached_subcontracting_orders
                WHERE mto_number LIKE ? AND aux_prop_id = 0
                GROUP BY material_code
            ) sub0 ON br.material_code = sub0.material_code
            LEFT JOIN (
                SELECT material_code,
                       SUM(order_qty) as order_qty, SUM(stock_in_qty) as stock_in_qty
                FROM cached_subcontracting_orders WHERE mto_number LIKE ?
                GROUP BY material_code
            ) sub_all ON br.material_code = sub_all.material_code

            /* --- Sales delivery (SAL_OUTSTOCK) --- */
            LEFT JOIN (
                SELECT material_code, aux_prop_id,
                       SUM(real_qty) as real_qty
                FROM cached_sales_delivery WHERE mto_number LIKE ?
                GROUP BY material_code, aux_prop_id
            ) sd ON br.material_code = sd.material_code
                 AND br.aux_prop_id = sd.aux_prop_id
            LEFT JOIN (
                SELECT material_code,
                       SUM(real_qty) as real_qty
                FROM cached_sales_delivery
                WHERE mto_number LIKE ? AND aux_prop_id = 0
                GROUP BY material_code
            ) sd0 ON br.material_code = sd0.material_code
            LEFT JOIN (
                SELECT material_code,
                       SUM(real_qty) as real_qty
                FROM cached_sales_delivery WHERE mto_number LIKE ?
                GROUP BY material_code
            ) sd_all ON br.material_code = sd_all.material_code

            ORDER BY br.material_code
            """,
            [pattern] * 20,
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # synced_at is the last column (index 21)
        synced_times = [self._parse_timestamp(row[21]) for row in rows if row[21]]
        oldest_sync = min(synced_times) if synced_times else None
        is_fresh = self._is_fresh(oldest_sync) if oldest_sync else False

        data = [self._row_to_bom_joined(row) for row in rows]
        return CacheResult(data=data, synced_at=oldest_sync, is_fresh=is_fresh)

    def _row_to_bom_joined(self, row: tuple) -> BOMJoinedRow:
        """Convert joined query row to BOMJoinedRow.

        Row columns:
        0: mo_bill_no, 1: mto_number, 2: material_code, 3: material_name,
        4: specification, 5: aux_attributes, 6: aux_prop_id, 7: material_type,
        8: need_qty, 9: picked_qty, 10: no_picked_qty,
        11: prod_receipt_real_qty, 12: prod_receipt_must_qty,
        13: pick_actual_qty, 14: pick_app_qty,
        15: purchase_order_qty, 16: purchase_stock_in_qty,
        17: purchase_receipt_real_qty,
        18: subcontract_order_qty, 19: subcontract_stock_in_qty,
        20: delivery_real_qty,
        21: synced_at (accessed in get_mto_bom_joined for freshness check)
        """
        return BOMJoinedRow(
            mo_bill_no=row[0] or "",
            mto_number=row[1] or "",
            material_code=row[2] or "",
            material_name=row[3] or "",
            specification=row[4] or "",
            aux_attributes=row[5] or "",
            aux_prop_id=int(row[6] or 0),
            material_type=int(row[7] or 0),
            need_qty=Decimal(str(row[8] or 0)),
            picked_qty=Decimal(str(row[9] or 0)),
            no_picked_qty=Decimal(str(row[10] or 0)),
            prod_receipt_real_qty=Decimal(str(row[11] or 0)),
            prod_receipt_must_qty=Decimal(str(row[12] or 0)),
            pick_actual_qty=Decimal(str(row[13] or 0)),
            pick_app_qty=Decimal(str(row[14] or 0)),
            purchase_order_qty=Decimal(str(row[15] or 0)),
            purchase_stock_in_qty=Decimal(str(row[16] or 0)),
            purchase_receipt_real_qty=Decimal(str(row[17] or 0)),
            subcontract_order_qty=Decimal(str(row[18] or 0)),
            subcontract_stock_in_qty=Decimal(str(row[19] or 0)),
            delivery_real_qty=Decimal(str(row[20] or 0)),
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
        """Quick check if MTO data exists and is fresh without loading full data (prefix match)."""
        rows = await self.db.execute_read(
            """
            SELECT MAX(synced_at) as latest_sync
            FROM cached_production_orders
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )

        if not rows or not rows[0][0]:
            return False, None

        synced_at = self._parse_timestamp(rows[0][0])
        return self._is_fresh(synced_at), synced_at

    def _is_fresh(self, synced_at: Optional[datetime]) -> bool:
        """Check if cache is within TTL.

        Note: SQLite CURRENT_TIMESTAMP uses UTC but returns naive datetimes,
        so we compare using naive UTC to avoid aware/naive mismatch.
        """
        if not synced_at:
            return False
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if synced_at.tzinfo is not None:
            synced_at = synced_at.replace(tzinfo=None)
        return now_utc - synced_at < self.ttl

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
        8: status, 9: create_date, 10: aux_prop_id, 11: synced_at
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
            aux_prop_id=int(row[10] or 0),
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
        """Convert database row to SubcontractingOrderModel.

        Row columns:
        0: bill_no, 1: mto_number, 2: material_code, 3: order_qty,
        4: stock_in_qty, 5: no_stock_in_qty, 6: aux_prop_id, 7: raw_data,
        8: synced_at
        """
        # Extract material_name and specification from raw_data JSON
        material_name = ""
        specification = ""
        if row[7]:
            try:
                raw_data = json.loads(row[7]) if isinstance(row[7], str) else row[7]
                material_name = raw_data.get("material_name", "")
                specification = raw_data.get("specification", "")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass  # Use defaults

        return SubcontractingOrderModel(
            bill_no=row[0] or "",
            mto_number=row[1] or "",
            material_code=row[2] or "",
            material_name=material_name,
            specification=specification,
            order_qty=Decimal(str(row[3] or 0)),
            stock_in_qty=Decimal(str(row[4] or 0)),
            no_stock_in_qty=Decimal(str(row[5] or 0)),
            aux_prop_id=row[6] or 0,
        )

    def _row_to_production_receipt(self, row: tuple) -> ProductionReceiptModel:
        """Convert database row to ProductionReceiptModel.

        Row columns:
        0: bill_no, 1: mto_number, 2: material_code, 3: real_qty, 4: must_qty,
        5: aux_prop_id, 6: raw_data, 7: synced_at

        Note: material_name and specification come from raw_data JSON if available,
        otherwise default to empty string (will be populated from live API).
        """
        # Try to extract material_name and specification from raw_data JSON
        material_name = ""
        specification = ""
        if row[6]:
            try:
                raw_data = json.loads(row[6]) if isinstance(row[6], str) else row[6]
                material_name = raw_data.get("material_name", "")
                specification = raw_data.get("specification", "")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass  # Use defaults

        return ProductionReceiptModel(
            bill_no=row[0] or "",
            mto_number=row[1] or "",
            material_code=row[2] or "",
            material_name=material_name,
            specification=specification,
            real_qty=Decimal(str(row[3] or 0)),
            must_qty=Decimal(str(row[4] or 0)),
            aux_prop_id=row[5] or 0,
        )

    def _row_to_purchase_receipt(self, row: tuple) -> PurchaseReceiptModel:
        """Convert database row to PurchaseReceiptModel.

        Row columns:
        0: bill_no, 1: mto_number, 2: material_code, 3: real_qty, 4: must_qty,
        5: bill_type_number, 6: aux_prop_id, 7: raw_data, 8: synced_at
        """
        # Extract material_name and specification from raw_data JSON
        material_name = ""
        specification = ""
        if row[7]:
            try:
                raw_data = json.loads(row[7]) if isinstance(row[7], str) else row[7]
                material_name = raw_data.get("material_name", "")
                specification = raw_data.get("specification", "")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass  # Use defaults

        return PurchaseReceiptModel(
            bill_no=row[0] or "",
            mto_number=row[1] or "",
            material_code=row[2] or "",
            material_name=material_name,
            specification=specification,
            real_qty=Decimal(str(row[3] or 0)),
            must_qty=Decimal(str(row[4] or 0)),
            bill_type_number=row[5] or "",
            aux_prop_id=row[6] or 0,
        )

    def _row_to_material_picking(self, row: tuple) -> MaterialPickingModel:
        """Convert database row to MaterialPickingModel.

        Row columns:
        0: mto_number, 1: material_code, 2: app_qty, 3: actual_qty,
        4: ppbom_bill_no, 5: aux_prop_id, 6: raw_data, 7: synced_at
        """
        # Extract material_name and specification from raw_data JSON
        material_name = ""
        specification = ""
        if row[6]:
            try:
                raw_data = json.loads(row[6]) if isinstance(row[6], str) else row[6]
                material_name = raw_data.get("material_name", "")
                specification = raw_data.get("specification", "")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass  # Use defaults

        return MaterialPickingModel(
            mto_number=row[0] or "",
            material_code=row[1] or "",
            material_name=material_name,
            specification=specification,
            app_qty=Decimal(str(row[2] or 0)),
            actual_qty=Decimal(str(row[3] or 0)),
            ppbom_bill_no=row[4] or "",
            aux_prop_id=row[5] or 0,  # For variant-aware matching
        )

    def _row_to_sales_delivery(self, row: tuple) -> SalesDeliveryModel:
        """Convert database row to SalesDeliveryModel.

        Row columns:
        0: bill_no, 1: mto_number, 2: material_code, 3: real_qty, 4: must_qty,
        5: aux_prop_id, 6: raw_data, 7: synced_at
        """
        # Extract material_name and specification from raw_data JSON
        material_name = ""
        specification = ""
        if row[6]:
            try:
                raw_data = json.loads(row[6]) if isinstance(row[6], str) else row[6]
                material_name = raw_data.get("material_name", "")
                specification = raw_data.get("specification", "")
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass  # Use defaults

        return SalesDeliveryModel(
            bill_no=row[0] or "",
            mto_number=row[1] or "",
            material_code=row[2] or "",
            material_name=material_name,
            specification=specification,
            real_qty=Decimal(str(row[3] or 0)),
            must_qty=Decimal(str(row[4] or 0)),
            aux_prop_id=row[5] or 0,
        )

    def _row_to_sales_order(self, row: tuple) -> SalesOrderModel:
        """Convert database row to SalesOrderModel.

        Row columns:
        0: bill_no, 1: mto_number, 2: material_code, 3: material_name,
        4: specification, 5: aux_attributes, 6: aux_prop_id, 7: customer_name,
        8: delivery_date, 9: qty, 10: bom_short_name, 11: raw_data, 12: synced_at
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
            bom_short_name=row[10] or "",
        )
