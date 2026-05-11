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
    # BD_MATERIAL.MaterialGroup.FName (e.g. "硅胶防水袋"). Sourced from PPBOM via
    # FMaterialId.FMaterialGroup single-chain field. Empty string for synthetic
    # rows (materials not in PPBOM) — Phase 1 deliberately doesn't enrich those.
    material_group_name: str = ""
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
                   status, create_date, aux_prop_id,
                   photo_file_id_1, photo_file_id_2, photo_file_id_3,
                   synced_at
            FROM cached_production_orders
            WHERE mto_number LIKE ?
            ORDER BY synced_at DESC
            """,
            [f"{mto_number}%"],
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # Parse synced_at from first row (index 14 after photo_file_id_1/2/3).
        synced_at = self._parse_timestamp(rows[0][14])
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
                   need_qty, picked_qty, no_picked_qty, material_group_name, synced_at
            FROM cached_production_bom
            WHERE mo_bill_no IN ({placeholders})
            ORDER BY synced_at DESC
            """,
            bill_nos,
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # synced_at is now at index 12 (after material_group_name at 11)
        synced_times = [self._parse_timestamp(row[12]) for row in rows if row[12]]
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
                   need_qty, picked_qty, no_picked_qty, material_group_name, synced_at
            FROM cached_production_bom
            WHERE mto_number LIKE ?
            ORDER BY synced_at DESC
            """,
            [f"{mto_number}%"],
        )

        if not rows:
            return CacheResult(data=[], synced_at=None, is_fresh=False)

        # synced_at is now at index 12 (after material_group_name at 11)
        synced_times = [self._parse_timestamp(row[12]) for row in rows if row[12]]
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
                   bom_short_name, material_group_name, raw_data, synced_at
            FROM cached_sales_orders
            WHERE mto_number LIKE ?
            """,
            [f"{mto_number}%"],
        )
        return self._build_cache_result(
            rows, self._row_to_sales_order, synced_at_index=13
        )

    async def get_mto_bom_joined(self, mto_number: str) -> CacheResult:
        """Get BOM items with all receipt/pick/order data pre-joined via SQL.

        Uses pre-aggregated subqueries to avoid the multiplicative join problem
        when multiple BOM rows share the same (material_code, aux_prop_id).

        Each receipt/order table has THREE JOINs (3-tier aux_prop_id fallback):
        - Tier 1: Exact match on (material_code, aux_prop_id)
        - Tier 2 (BOM aux!=0, Kingdee receipt aux=0): pr0 / pk0 / etc.
        - Tier 2.5 (Wave 5B): BOM aux!=0, Tier-1+Tier-2 miss → fall back
          to all-aux rollup with partial-match dedup (see `_recv_dedup_cte`).
        - Tier 3 (BOM aux=0): sum ALL receipts; same partial-match dedup.
        COALESCE prefers exact match; later tiers fire only when earlier miss.
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
            -- Wave 4D → Wave 5B (Bug A): per-code aggregate enabling
            -- partial-match dedup of fallback rollup. Wave 4D bailed out
            -- entirely if ANY BOM-aux had a Tier-1 exact match; Wave 5B
            -- splits the rollup so exact-matched aux claim their share
            -- and non-matched aux share the REMAINDER (rollup minus
            -- already-matched amount). Real-data: AS2602033 /
            -- 05.02.08.037 had a partial match → pre-Wave-5B both rows
            -- fired (Tier-1: 32544) AND (Tier-2.5: 32544 rollup) →
            -- SUM=65088=2× target.
            mo_match_per_code AS (
                SELECT br.material_code,
                       MAX(CASE WHEN mo.mo_qty > 0 THEN 1 ELSE 0 END) as has_any_exact,
                       COUNT(*) as group_count,
                       -- Sum of Tier-1 exact-matched PRD_MO qty across
                       -- the BOM-aux groups for this code. Used to
                       -- compute remainder = rollup - this_amount.
                       SUM(CASE WHEN mo.mo_qty > 0 THEN mo.mo_qty ELSE 0 END)
                           as exact_matched_amount,
                       -- Count of BOM-aux groups that have NO Tier-1
                       -- match. Used to detect single non-matched group
                       -- vs multi-non-matched cases.
                       SUM(CASE WHEN mo.mo_qty IS NULL OR mo.mo_qty <= 0
                                THEN 1 ELSE 0 END) as non_matched_count
                FROM bom_raw br
                LEFT JOIN prd_mo_agg mo
                    ON mo.material_code = br.material_code
                   AND mo.aux_prop_id = br.aux_prop_id
                GROUP BY br.material_code
            ),
            -- Per-row election rank.
            -- `elect_rank`: aux=0 wins; among specific aux, smallest wins.
            --   Mirrors mto_handler.py:_build_bom_joined_rows_from_live
            --   election in the legacy Wave 4D path (any-exact / no-exact
            --   single dedup).
            -- `nm_elect_rank`: same shape, but ONLY ranks within the
            --   subset of non-matched (Tier-1 missed) BOM-aux groups.
            --   Used for Wave 5B partial-match dedup — the elected
            --   non-matched group claims the remainder, all other non-
            --   matched groups get 0. Matched groups still use Tier-1.
            bom_ranked_for_dedup AS (
                SELECT br.*,
                       (mo.mo_qty IS NULL OR mo.mo_qty <= 0) as is_non_matched,
                       ROW_NUMBER() OVER (
                           PARTITION BY br.material_code
                           ORDER BY (CASE WHEN br.aux_prop_id = 0 THEN 0 ELSE 1 END),
                                    br.aux_prop_id
                       ) as elect_rank,
                       ROW_NUMBER() OVER (
                           PARTITION BY br.material_code,
                                        (CASE WHEN mo.mo_qty IS NULL OR mo.mo_qty <= 0
                                              THEN 1 ELSE 0 END)
                           ORDER BY (CASE WHEN br.aux_prop_id = 0 THEN 0 ELSE 1 END),
                                    br.aux_prop_id
                       ) as nm_elect_rank
                FROM bom_raw br
                LEFT JOIN prd_mo_agg mo
                    ON mo.material_code = br.material_code
                   AND mo.aux_prop_id = br.aux_prop_id
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
                -- Wave 5B partial-match dedup (extends Wave 4D):
                -- self-made codes with multiple BOM-aux groups split the
                -- team's PRD_MO target between exact-matched aux (Tier-1
                -- claims their exact share) and non-matched aux (share
                -- the remainder via the elected non-matched aux).
                --   exact_matched_amount = SUM(mo.mo_qty for matched aux)
                --   remainder = MAX(0, mo_all.mo_qty - exact_matched_amount)
                --   elected non-matched aux (nm_elect_rank=1) gets remainder
                --   other non-matched aux get 0
                -- When no exact match exists (legacy Wave 4D), exact_
                -- matched_amount=0 → remainder=mo_all.mo_qty, behaviour
                -- identical to Wave 4D.
                -- Real-data: AS2602033 / 05.02.08.037 had partial match →
                -- pre-Wave-5B SUM(must_qty)=65088 (2× target 32544); post-
                -- Wave-5B Tier-1 row claims 32544, non-matched row claims
                -- max(0, 32544 - 32544) = 0 → SUM=32544.
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
                           -- Wave 5B partial-match dedup: non-matched
                           -- BOM-aux row, multiple BOM-aux groups exist,
                           -- elected non-matched representative → claim
                           -- remainder (rollup - exact_matched_amount).
                           WHEN br.material_type = 1
                                AND br.is_non_matched
                                AND mo_all.mo_qty IS NOT NULL
                                AND mc.group_count > 1
                                AND br.nm_elect_rank = 1
                               THEN MAX(0, COALESCE(mo_all.mo_qty, 0)
                                            - COALESCE(mc.exact_matched_amount, 0))
                           -- Non-elected non-matched aux → 0 (the
                           -- elected representative already claimed the
                           -- remainder for this code).
                           WHEN br.material_type = 1
                                AND br.is_non_matched
                                AND mc.group_count > 1
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
                /* Wave 5B: Tier-2.5 fall-through — when BOM aux!=0 and Tier 1
                   (pr) + Tier 2 (pr0) miss, fall through to all-aux rollup
                   (pr_all). Partial-match dedup is applied post-SQL in
                   `_apply_recv_partial_match_dedup` to zero non-elected
                   non-matched siblings. Mirrors live's `_get` _recv_tier_state. */
                ROUND(COALESCE(
                    pr.real_qty,
                    CASE WHEN pr.material_code IS NULL AND br.aux_prop_id != 0 THEN pr0.real_qty END,
                    pr_all.real_qty,
                    0
                ), 2) as prod_receipt_real_qty,
                -- Use BOM need_qty (PPBOM.FMustQty) instead of receipt SUM(must_qty)
                -- which inflates across multiple receipt batches (see commit c7df68c)
                ROUND(COALESCE(ba.need_qty, 0), 2) as prod_receipt_must_qty,
                /* Wave 5B: Tier-2.5 fall-through to all-aux rollup. See
                   prod_receipt_real_qty above; post-SQL dedup in
                   `_apply_recv_partial_match_dedup`. */
                ROUND(COALESCE(
                    pk.actual_qty,
                    CASE WHEN pk.material_code IS NULL AND br.aux_prop_id != 0 THEN pk0.actual_qty END,
                    pk_all.actual_qty,
                    0
                ), 2) as pick_actual_qty,
                ROUND(COALESCE(
                    pk.app_qty,
                    CASE WHEN pk.material_code IS NULL AND br.aux_prop_id != 0 THEN pk0.app_qty END,
                    pk_all.app_qty,
                    0
                ), 2) as pick_app_qty,
                ROUND(COALESCE(
                    po.order_qty,
                    CASE WHEN po.material_code IS NULL AND br.aux_prop_id != 0 THEN po0.order_qty END,
                    po_all.order_qty,
                    0
                ), 2) as purchase_order_qty,
                ROUND(COALESCE(
                    po.stock_in_qty,
                    CASE WHEN po.material_code IS NULL AND br.aux_prop_id != 0 THEN po0.stock_in_qty END,
                    po_all.stock_in_qty,
                    0
                ), 2) as purchase_stock_in_qty,
                ROUND(COALESCE(
                    pur.real_qty,
                    CASE WHEN pur.material_code IS NULL AND br.aux_prop_id != 0 THEN pur0.real_qty END,
                    pur_all.real_qty,
                    0
                ), 2) as purchase_receipt_real_qty,
                ROUND(COALESCE(
                    sub.order_qty,
                    CASE WHEN sub.material_code IS NULL AND br.aux_prop_id != 0 THEN sub0.order_qty END,
                    sub_all.order_qty,
                    0
                ), 2) as subcontract_order_qty,
                ROUND(COALESCE(
                    sub.stock_in_qty,
                    CASE WHEN sub.material_code IS NULL AND br.aux_prop_id != 0 THEN sub0.stock_in_qty END,
                    sub_all.stock_in_qty,
                    0
                ), 2) as subcontract_stock_in_qty,
                ROUND(COALESCE(
                    sd.real_qty,
                    CASE WHEN sd.material_code IS NULL AND br.aux_prop_id != 0 THEN sd0.real_qty END,
                    sd_all.real_qty,
                    0
                ), 2) as delivery_real_qty,
                /* match_quality labels per source — telemetry only (Stage 1 of PLAN_aux_match_visibility).
                   Mirrors the COALESCE tier ordering above. Wave 5B widened
                   `all_aux_rollup` to fire for BOTH aux=0 and aux!=0 (Tier-3
                   AND Tier-2.5). */
                CASE
                    WHEN pr.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND pr0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN pr_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as prod_receipt_match_quality,
                CASE
                    WHEN pk.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND pk0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN pk_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as pick_match_quality,
                CASE
                    WHEN po.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND po0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN po_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as purchase_order_match_quality,
                CASE
                    WHEN pur.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND pur0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN pur_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as purchase_receipt_match_quality,
                CASE
                    WHEN sub.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND sub0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN sub_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as subcontract_match_quality,
                CASE
                    WHEN sd.material_code IS NOT NULL THEN 'exact'
                    WHEN br.aux_prop_id != 0 AND sd0.material_code IS NOT NULL THEN 'aux_zero_fallback'
                    WHEN sd_all.material_code IS NOT NULL THEN 'all_aux_rollup'
                    ELSE 'no_match'
                END as delivery_match_quality,
                COALESCE(br.material_group_name, '') as material_group_name,
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

        # synced_at is the last column (index 28 — after 6 telemetry CASE columns
        # at 21-26 and material_group_name at 27)
        synced_times = [self._parse_timestamp(row[28]) for row in rows if row[28]]
        oldest_sync = min(synced_times) if synced_times else None
        is_fresh = self._is_fresh(oldest_sync) if oldest_sync else False

        self._log_fallback_telemetry(mto_number, rows)

        data = [self._row_to_bom_joined(row) for row in rows]
        # Wave 5B (Bug B) — receipt-side partial-match dedup.
        # The SQL above adds Tier-2.5 fall-through to all_aux rollup for
        # every receipt source, but this would inflate by N× when multiple
        # BOM-aux groups for the same code all consume the rollup. Mirror
        # live's `_recv_tier_state` here: distribute the rollup so exact-
        # matched aux keep their Tier-1 value and the elected non-matched
        # aux claims the remainder; non-elected non-matched aux get 0.
        # See `_apply_recv_partial_match_dedup` for the rule.
        self._apply_recv_partial_match_dedup(data)
        return CacheResult(data=data, synced_at=oldest_sync, is_fresh=is_fresh)

    @staticmethod
    def _apply_recv_partial_match_dedup(data: list) -> None:
        """In-place receipt-side Tier-2.5/3 partial-match dedup.

        Wave 5B (Bug B). For each (material_code, source) where multiple
        BOM-aux rows hit Tier-2.5 or Tier-3 (i.e. their qty came from
        all_aux rollup not exact match), distribute the rollup so:
          - exact-matched rows (match_quality='exact') keep their value
          - the elected non-matched row (aux=0 wins; else smallest aux)
            claims `remainder = max(0, rollup - sum_of_exact_amounts)`
          - other non-matched rows are zeroed

        Mirrors `mto_handler._build_bom_joined_rows_from_live` /
        `_recv_tier_state` and matches `mo_match_per_code` cache CTE
        semantics for the demand side.

        Real-data: AK2510034 / 05.02.15.62 — pre-Wave-5B QP returns
        prod_receipt_real_qty=0; post-fix the elected BOM-aux row claims
        the rollup (=1444) and SUM matches Kingdee.

        Sources processed:
          (qty_attr, quality_key)
          - prod_receipt_real_qty  / prod_receipt
          - prod_receipt_must_qty  / prod_receipt   (mirrors real_qty's match,
                                                     but holds need_qty — see note)
          - pick_actual_qty        / pick
          - pick_app_qty           / pick
          - purchase_order_qty     / purchase_order
          - purchase_stock_in_qty  / purchase_order
          - purchase_receipt_real_qty / purchase_receipt
          - subcontract_order_qty  / subcontract
          - subcontract_stock_in_qty / subcontract
          - delivery_real_qty      / delivery

        Note on prod_receipt_must_qty: it's sourced from BOM need_qty
        (already deduplicated via `bom_agg.need_qty` in the demand side),
        not from receipts directly, so it's intentionally skipped here.
        """
        # Group rows by material_code
        by_code: dict[str, list] = {}
        for row in data:
            by_code.setdefault(row.material_code, []).append(row)

        # (qty_attr, quality_key)
        qty_to_quality = [
            ("prod_receipt_real_qty", "prod_receipt"),
            ("pick_actual_qty", "pick"),
            ("pick_app_qty", "pick"),
            ("purchase_order_qty", "purchase_order"),
            ("purchase_stock_in_qty", "purchase_order"),
            ("purchase_receipt_real_qty", "purchase_receipt"),
            ("subcontract_order_qty", "subcontract"),
            ("subcontract_stock_in_qty", "subcontract"),
            ("delivery_real_qty", "delivery"),
        ]

        ZERO = Decimal("0")
        for code, rows_for_code in by_code.items():
            if len(rows_for_code) < 2:
                continue  # single-group: no dedup needed
            for qty_attr, quality_key in qty_to_quality:
                # Identify exact-matched vs non-matched rows for THIS source.
                exact = []
                non_matched = []
                for r in rows_for_code:
                    q = (r.match_quality_breakdown or {}).get(quality_key)
                    val = getattr(r, qty_attr, ZERO) or ZERO
                    if q == "exact":
                        exact.append((r, val))
                    else:
                        non_matched.append((r, val))
                if not non_matched:
                    continue
                # Determine if any non-matched row has a fallback value
                # (i.e. all_aux_rollup was the source). If all non-matched
                # are 'no_match' / 0, no dedup needed.
                if not any(v > 0 for _, v in non_matched):
                    continue
                # The all_aux rollup value is whatever a non-matched row
                # received from SQL (they all received the same rollup
                # because the SQL CTE returns one rollup per code).
                rollup = max((v for _, v in non_matched), default=ZERO)
                exact_sum = sum((v for _, v in exact), ZERO)
                remainder = max(ZERO, rollup - exact_sum)
                # Election: aux=0 wins; else smallest aux among non-matched.
                non_matched_sorted = sorted(
                    non_matched,
                    key=lambda rv: (
                        0 if rv[0].aux_prop_id == 0 else 1,
                        rv[0].aux_prop_id,
                    ),
                )
                elected_row = non_matched_sorted[0][0]
                for r, _ in non_matched:
                    if r is elected_row:
                        setattr(r, qty_attr, remainder)
                    else:
                        setattr(r, qty_attr, ZERO)

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
        27: material_group_name,
        28: synced_at (accessed in get_mto_bom_joined for freshness check)

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
            material_group_name=row[27] or "",
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
        8: status, 9: create_date, 10: aux_prop_id,
        11: photo_file_id_1, 12: photo_file_id_2, 13: photo_file_id_3,
        14: synced_at
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
            photo_file_id_1=row[11],
            photo_file_id_2=row[12],
            photo_file_id_3=row[13],
        )

    def _row_to_bom(self, row: tuple) -> ProductionBOMModel:
        """Convert database row to ProductionBOMModel.

        Row columns (after schema optimization):
        0: mo_bill_no, 1: mto_number, 2: material_code, 3: material_name,
        4: specification, 5: aux_attributes, 6: aux_prop_id, 7: material_type,
        8: need_qty, 9: picked_qty, 10: no_picked_qty,
        11: material_group_name, 12: synced_at
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
            material_group_name=row[11] or "",
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
        8: delivery_date, 9: qty, 10: bom_short_name, 11: material_group_name,
        12: raw_data, 13: synced_at
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
            material_group_name=row[11] or "",
        )
