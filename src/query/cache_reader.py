"""Cache reader for MTO queries from SQLite.

This module provides fast cached lookups for MTO data, avoiding
expensive Kingdee API calls when cached data is fresh.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
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
    # Per-source aux match quality: {source: 'exact'|'aux_zero_fallback'|'all_aux_rollup'|'no_match'}
    # Empty dict when not populated (live path until Stage 4, cache path until Stage 3).
    match_quality_breakdown: dict = field(default_factory=dict)


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
            WITH matching_mtos AS (
                SELECT DISTINCT mto_number
                FROM cached_production_bom
                WHERE mto_number LIKE ?
            ),
            bom_ranked AS (
                SELECT b.*, ROW_NUMBER() OVER (
                    PARTITION BY b.material_code, b.aux_prop_id
                    ORDER BY b.synced_at DESC, b.id DESC
                ) AS rn
                FROM cached_production_bom b
                JOIN matching_mtos m ON b.mto_number = m.mto_number
                WHERE b.material_code NOT LIKE '07.%'
            ),
            bom_repr AS (SELECT * FROM bom_ranked WHERE rn = 1),
            -- PRD_MO aggregation: production target per (material_code, aux_prop_id).
            -- Used to override SUM(need_qty) for self-made (material_type=1) where the
            -- same component appears in N parent PPBOMs within one MTO and summing
            -- yields N × actual target. See bug-patterns.md #10 (BOM-rollup variant).
            prd_mo_agg AS (
                SELECT po.material_code, po.aux_prop_id,
                       SUM(po.qty) as mo_qty
                FROM cached_production_orders po
                JOIN matching_mtos m ON po.mto_number = m.mto_number
                GROUP BY po.material_code, po.aux_prop_id
            ),
            -- Same, rolled up across ALL aux variants. Serves as both:
            --   Tier-2: PPBOM has aux≠0 but PRD_MO recorded at aux=0
            --   Tier-3: PPBOM has aux=0 (generic) but PRD_MO at one or more
            --           specific aux values (real case: AS2603009 / 05.07.02.01
            --           — PPBOM aux=0, PRD_MO aux=105814).
            -- Symmetric to the receipt-side `pr_all` rollup CTE.
            prd_mo_agg_all AS (
                SELECT po.material_code,
                       SUM(po.qty) as mo_qty
                FROM cached_production_orders po
                JOIN matching_mtos m ON po.mto_number = m.mto_number
                GROUP BY po.material_code
            ),
            -- Raw BOM aggregation per (material_code, aux_prop_id). Self-made
            -- override happens in bom_agg below.
            bom_raw AS (
                SELECT b.material_code, b.aux_prop_id,
                       MAX(b.material_type) as material_type,
                       SUM(b.need_qty) as sum_need_qty,
                       MAX(b.need_qty) as max_need_qty,
                       SUM(b.picked_qty) as picked_qty,
                       SUM(b.no_picked_qty) as no_picked_qty,
                       MAX(b.synced_at) as synced_at
                FROM cached_production_bom b
                JOIN matching_mtos m ON b.mto_number = m.mto_number
                WHERE b.material_code NOT LIKE '07.%'
                GROUP BY b.material_code, b.aux_prop_id
            ),
            -- Wave 4B (Issue #1): set of material_codes that appear in
            -- cached_purchase_orders for matching MTOs. Used to override
            -- PPBOM.FMaterialType when it incorrectly says self-made (=1) for
            -- a 03.xx purchased material — see bom_agg below.
            pur_keys AS (
                SELECT DISTINCT po.material_code
                FROM cached_purchase_orders po
                JOIN matching_mtos m ON po.mto_number = m.mto_number
            ),
            -- Wave 4D (cache mirror of live's Wave 4C dedup): per-code
            -- aggregate showing whether ANY (code, aux) BOM row has a Tier-1
            -- exact PRD_MO match. Used by bom_agg below to apply Tier-2.5/3
            -- rollup dedup (cache mirror of mto_handler.py Step 1 dedup).
            mo_match_per_code AS (
                SELECT br.material_code,
                       MAX(CASE WHEN mo.mo_qty > 0 THEN 1 ELSE 0 END) as has_any_exact,
                       COUNT(*) as group_count
                FROM bom_raw br
                LEFT JOIN prd_mo_agg mo
                    ON mo.material_code = br.material_code
                   AND mo.aux_prop_id = br.aux_prop_id
                GROUP BY br.material_code
            ),
            -- Per-row election rank: aux=0 wins over specific aux; among
            -- specific aux, smallest wins. Mirrors the dict iteration order
            -- in mto_handler.py:_build_bom_joined_rows_from_live (where the
            -- first encountered BOM-aux group becomes the elected row).
            bom_ranked_for_dedup AS (
                SELECT br.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY br.material_code
                           ORDER BY (CASE WHEN br.aux_prop_id = 0 THEN 0 ELSE 1 END),
                                    br.aux_prop_id
                       ) as elect_rank
                FROM bom_raw br
            ),
            bom_agg AS (
                -- Wave 4B (Issue #1): material_type override for 03.xx purchased
                -- materials.  Kingdee's PRD_PPBOM.FMaterialType is essentially
                -- always 1 in this tenant (CLAUDE.md "carries no routing info"),
                -- so 03.xx purchased materials get classified as self-made and
                -- routed through the BOM-rollup PRD_MO override below — which
                -- inflates `prod_instock_must_qty` 5–16× for cases where the
                -- same material appears in many parent BOMs (e.g. AS2603009 /
                -- 03.03.001: cache=593 vs live=51 — 11.6×).
                --
                -- The live path avoids this in mto_handler.py:889-911 by
                -- explicitly emitting purchase-order materials with
                -- material_type=2.  Mirror that behavior here:
                --   IF material_code LIKE '03.%' AND material has a PUR row
                --      → corrected_material_type=2 (purchased)
                --   ELSE → keep PPBOM's material_type as-is.
                --
                -- This is the CTE-internal "Option A".  Alternative (Option B)
                -- would be to compute corrected type in _bom_row_to_child, but
                -- that risks affecting the live path which already handles 2b
                -- via synthetic-row emission — so cleanest to fix at the cache
                -- SQL boundary.
                --
                -- For self-made (corrected_material_type=1), prefer PRD_MO.FQty
                -- over SUM(need_qty) (Pattern 10 BOM-rollup cap).  For purchased
                -- (corrected_material_type=2) / subcontracted (3) / unknown:
                -- keep SUM — purchased materials legitimately accumulate across
                -- parent BOMs (one combined PO covers all parents).
                -- Wave 4D dedup: when a self-made code has multiple BOM-aux
                -- groups, no exact PRD_MO match for any of them, and Tier-2.5/3
                -- rollup applies → only the elected row (rank=1) carries the
                -- full team rollup; sibling rows get 0. This mirrors live's
                -- Wave 4C Step 1 dedup, preventing the SUM(must_qty)-by-code
                -- = N × team-target shape (real-data: AS2602033 / 05.02.12.44
                -- pre-fix cache=51840 vs live=8640, ratio 6×).
                SELECT br.material_code, br.aux_prop_id,
                       CASE
                           WHEN br.material_code LIKE '03.%'
                                AND pk.material_code IS NOT NULL
                               THEN 2
                           ELSE br.material_type
                       END as corrected_material_type,
                       CASE
                           -- 03.xx purchased override (Wave 4B)
                           WHEN br.material_code LIKE '03.%'
                                AND pk.material_code IS NOT NULL
                               THEN br.sum_need_qty
                           -- Tier 1 exact match — always assign
                           WHEN br.material_type = 1
                                AND mo.mo_qty IS NOT NULL AND mo.mo_qty > 0
                               THEN mo.mo_qty
                           -- Tier 2.5/3 rollup w/ multi-group dedup (Wave 4D)
                           WHEN br.material_type = 1
                                AND mo_all.mo_qty IS NOT NULL AND mo_all.mo_qty > 0
                                AND mc.has_any_exact = 0
                                AND mc.group_count > 1
                                AND br.elect_rank = 1
                               THEN mo_all.mo_qty
                           WHEN br.material_type = 1
                                AND mo_all.mo_qty IS NOT NULL
                                AND mc.has_any_exact = 0
                                AND mc.group_count > 1
                                AND br.elect_rank > 1
                               THEN 0
                           -- Single-group fallback (no dedup needed)
                           WHEN br.material_type = 1
                               THEN COALESCE(mo_all.mo_qty, br.max_need_qty)
                           ELSE br.sum_need_qty
                       END as need_qty,
                       br.picked_qty, br.no_picked_qty, br.synced_at
                FROM bom_ranked_for_dedup br
                LEFT JOIN prd_mo_agg mo
                    ON mo.material_code = br.material_code
                   AND mo.aux_prop_id = br.aux_prop_id
                LEFT JOIN prd_mo_agg_all mo_all
                    ON mo_all.material_code = br.material_code
                LEFT JOIN pur_keys pk
                    ON pk.material_code = br.material_code
                LEFT JOIN mo_match_per_code mc
                    ON mc.material_code = br.material_code
            )
            SELECT
                br.mo_bill_no,
                br.mto_number,
                br.material_code,
                br.material_name,
                br.specification,
                br.aux_attributes,
                br.aux_prop_id,
                ba.corrected_material_type as material_type,
                ROUND(ba.need_qty, 2) as need_qty,
                ROUND(ba.picked_qty, 2) as picked_qty,
                ROUND(ba.no_picked_qty, 2) as no_picked_qty,
                ROUND(COALESCE(
                    pr.real_qty,
                    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id != 0 THEN pr0.real_qty END,
                    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id = 0 THEN pr_all.real_qty END,
                    0
                ), 2) as prod_receipt_real_qty,
                -- Use BOM need_qty (PPBOM.FMustQty) instead of receipt SUM(must_qty)
                -- which inflates across multiple receipt batches (see commit c7df68c)
                ROUND(COALESCE(ba.need_qty, 0), 2) as prod_receipt_must_qty,
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
                /* match_quality labels per source — telemetry only (Stage 1 of PLAN_aux_match_visibility).
                   Mirrors the COALESCE tier ordering above so each label = which tier produced the qty. */
                CASE
                    WHEN pr.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND pr0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN br.aux_prop_id = 0 AND pr_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as prod_receipt_match_quality,
                CASE
                    WHEN pk.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND pk0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN br.aux_prop_id = 0 AND pk_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as pick_match_quality,
                CASE
                    WHEN po.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND po0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN br.aux_prop_id = 0 AND po_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as purchase_order_match_quality,
                CASE
                    WHEN pur.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND pur0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN br.aux_prop_id = 0 AND pur_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as purchase_receipt_match_quality,
                CASE
                    WHEN sub.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND sub0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN br.aux_prop_id = 0 AND sub_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as subcontract_match_quality,
                CASE
                    WHEN sd.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND sd0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN br.aux_prop_id = 0 AND sd_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as delivery_match_quality,
                ba.synced_at
            FROM bom_repr br
            JOIN bom_agg ba ON br.material_code = ba.material_code
                           AND br.aux_prop_id = ba.aux_prop_id

            /* --- Production receipts (PRD_INSTOCK) --- */
            LEFT JOIN (
                SELECT r.material_code, r.aux_prop_id,
                       SUM(r.real_qty) as real_qty, SUM(r.must_qty) as must_qty
                FROM cached_production_receipts r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code, r.aux_prop_id
            ) pr ON br.material_code = pr.material_code
                 AND br.aux_prop_id = pr.aux_prop_id
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.real_qty) as real_qty, SUM(r.must_qty) as must_qty
                FROM cached_production_receipts r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                WHERE r.aux_prop_id = 0
                GROUP BY r.material_code
            ) pr0 ON br.material_code = pr0.material_code
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.real_qty) as real_qty, SUM(r.must_qty) as must_qty
                FROM cached_production_receipts r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code
            ) pr_all ON br.material_code = pr_all.material_code

            /* --- Material picking (PRD_PickMtrl) --- */
            LEFT JOIN (
                SELECT r.material_code, r.aux_prop_id,
                       SUM(r.actual_qty) as actual_qty, SUM(r.app_qty) as app_qty
                FROM cached_material_picking r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code, r.aux_prop_id
            ) pk ON br.material_code = pk.material_code
                 AND br.aux_prop_id = pk.aux_prop_id
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.actual_qty) as actual_qty, SUM(r.app_qty) as app_qty
                FROM cached_material_picking r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                WHERE r.aux_prop_id = 0
                GROUP BY r.material_code
            ) pk0 ON br.material_code = pk0.material_code
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.actual_qty) as actual_qty, SUM(r.app_qty) as app_qty
                FROM cached_material_picking r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code
            ) pk_all ON br.material_code = pk_all.material_code

            /* --- Purchase orders (PUR_PurchaseOrder) --- */
            LEFT JOIN (
                SELECT r.material_code, r.aux_prop_id,
                       SUM(r.order_qty) as order_qty, SUM(r.stock_in_qty) as stock_in_qty
                FROM cached_purchase_orders r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code, r.aux_prop_id
            ) po ON br.material_code = po.material_code
                 AND br.aux_prop_id = po.aux_prop_id
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.order_qty) as order_qty, SUM(r.stock_in_qty) as stock_in_qty
                FROM cached_purchase_orders r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                WHERE r.aux_prop_id = 0
                GROUP BY r.material_code
            ) po0 ON br.material_code = po0.material_code
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.order_qty) as order_qty, SUM(r.stock_in_qty) as stock_in_qty
                FROM cached_purchase_orders r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code
            ) po_all ON br.material_code = po_all.material_code

            /* --- Purchase receipts (STK_InStock) --- */
            LEFT JOIN (
                SELECT r.material_code, r.aux_prop_id,
                       SUM(r.real_qty) as real_qty
                FROM cached_purchase_receipts r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code, r.aux_prop_id
            ) pur ON br.material_code = pur.material_code
                  AND br.aux_prop_id = pur.aux_prop_id
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.real_qty) as real_qty
                FROM cached_purchase_receipts r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                WHERE r.aux_prop_id = 0
                GROUP BY r.material_code
            ) pur0 ON br.material_code = pur0.material_code
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.real_qty) as real_qty
                FROM cached_purchase_receipts r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code
            ) pur_all ON br.material_code = pur_all.material_code

            /* --- Subcontracting orders (SUB_POORDER) --- */
            LEFT JOIN (
                SELECT r.material_code, r.aux_prop_id,
                       SUM(r.order_qty) as order_qty, SUM(r.stock_in_qty) as stock_in_qty
                FROM cached_subcontracting_orders r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code, r.aux_prop_id
            ) sub ON br.material_code = sub.material_code
                  AND br.aux_prop_id = sub.aux_prop_id
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.order_qty) as order_qty, SUM(r.stock_in_qty) as stock_in_qty
                FROM cached_subcontracting_orders r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                WHERE r.aux_prop_id = 0
                GROUP BY r.material_code
            ) sub0 ON br.material_code = sub0.material_code
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.order_qty) as order_qty, SUM(r.stock_in_qty) as stock_in_qty
                FROM cached_subcontracting_orders r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code
            ) sub_all ON br.material_code = sub_all.material_code

            /* --- Sales delivery (SAL_OUTSTOCK) --- */
            LEFT JOIN (
                SELECT r.material_code, r.aux_prop_id,
                       SUM(r.real_qty) as real_qty
                FROM cached_sales_delivery r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code, r.aux_prop_id
            ) sd ON br.material_code = sd.material_code
                 AND br.aux_prop_id = sd.aux_prop_id
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.real_qty) as real_qty
                FROM cached_sales_delivery r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                WHERE r.aux_prop_id = 0
                GROUP BY r.material_code
            ) sd0 ON br.material_code = sd0.material_code
            LEFT JOIN (
                SELECT r.material_code,
                       SUM(r.real_qty) as real_qty
                FROM cached_sales_delivery r
                JOIN matching_mtos m ON r.mto_number = m.mto_number
                GROUP BY r.material_code
            ) sd_all ON br.material_code = sd_all.material_code

            ORDER BY br.material_code
            """,
            [pattern],
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # synced_at is the last column (index 27 — after 6 telemetry CASE columns at 21-26)
        synced_times = [self._parse_timestamp(row[27]) for row in rows if row[27]]
        oldest_sync = min(synced_times) if synced_times else None
        is_fresh = self._is_fresh(oldest_sync) if oldest_sync else False

        self._log_fallback_telemetry(mto_number, rows)

        data = [self._row_to_bom_joined(row) for row in rows]
        return CacheResult(data=data, synced_at=oldest_sync, is_fresh=is_fresh)

    @staticmethod
    def _log_fallback_telemetry(mto_number: str, rows: list) -> None:
        """Emit one structured log per MTO query summarising aux fallback usage.

        Stage 1 of PLAN_aux_match_visibility (2026-04-25). Aggregates the per-source
        match_quality labels at columns 21..26 into counts so Loki can chart fallback
        rates. Read-only — does not affect the returned BOMJoinedRow data.
        """
        sources = (
            ("prod_receipt", 21),
            ("pick", 22),
            ("purchase_order", 23),
            ("purchase_receipt", 24),
            ("subcontract", 25),
            ("delivery", 26),
        )
        breakdown: dict[str, dict[str, int]] = {}
        non_exact_total = 0
        for label, idx in sources:
            counts: dict[str, int] = {}
            for row in rows:
                tier = row[idx] or "no_match"
                counts[tier] = counts.get(tier, 0) + 1
                if tier not in ("exact", "no_match"):
                    non_exact_total += 1
            breakdown[label] = counts

        # Use INFO so it lands in Loki without extra config; one line per MTO query.
        # Embed JSON in message because JSONFormatter doesn't propagate `extra` fields.
        logger.info(
            "mto_fallback_telemetry mto=%s bom_rows=%d non_exact_hits=%d breakdown=%s",
            mto_number,
            len(rows),
            non_exact_total,
            json.dumps(breakdown, ensure_ascii=False),
        )

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
        21: prod_receipt_match_quality, 22: pick_match_quality,
        23: purchase_order_match_quality, 24: purchase_receipt_match_quality,
        25: subcontract_match_quality, 26: delivery_match_quality,
        27: synced_at (accessed in get_mto_bom_joined for freshness check)

        Columns 21-26 are Stage 1 telemetry — consumed by _log_fallback_telemetry,
        not yet propagated to BOMJoinedRow (Stage 3 of PLAN_aux_match_visibility).
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
            match_quality_breakdown={
                "prod_receipt": row[21] or "no_match",
                "pick": row[22] or "no_match",
                "purchase_order": row[23] or "no_match",
                "purchase_receipt": row[24] or "no_match",
                "subcontract": row[25] or "no_match",
                "delivery": row[26] or "no_match",
            },
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
        """Quick check if MTO data exists and is fresh without loading full data (prefix match).

        Checks the OLDEST synced_at across all 9 cache tables to give
        accurate staleness — the freshness is only as good as the most
        outdated table.
        """
        tables = [
            "cached_production_orders",
            "cached_production_bom",
            "cached_purchase_orders",
            "cached_subcontracting_orders",
            "cached_production_receipts",
            "cached_purchase_receipts",
            "cached_material_picking",
            "cached_sales_delivery",
            "cached_sales_orders",
        ]
        # UNION the per-table MAX(synced_at), then take the MIN (oldest).
        union_parts = [
            f"SELECT MAX(synced_at) AS latest FROM {t} WHERE mto_number LIKE ?"
            for t in tables
        ]
        query = f"SELECT MIN(latest) FROM ({' UNION ALL '.join(union_parts)})"
        params = [f"{mto_number}%"] * len(tables)

        rows = await self.db.execute_read(query, params)

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
