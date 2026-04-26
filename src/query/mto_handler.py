"""Handler for MTO status lookups with config-driven material class logic."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict, defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum
from typing import Optional, TYPE_CHECKING

from cachetools import TTLCache

from src.mto_config import MTOConfig, MaterialClassConfig
from src.models.mto_status import (
    ChildItem,
    MTOStatusResponse,
    ParentItem,
    OrderNode,
    DocumentNode,
    MTORelatedOrdersResponse,
)
from src.semantic.enrichment import enrich_response

logger = logging.getLogger(__name__)
from src.readers import (
    MaterialPickingReader,
    ProductionBOMReader,
    ProductionOrderReader,
    ProductionReceiptReader,
    PurchaseOrderReader,
    PurchaseReceiptReader,
    SalesDeliveryReader,
    SalesOrderReader,
    SubcontractingOrderReader,
)

if TYPE_CHECKING:
    from src.query.cache_reader import CacheReader

from src.query.cache_reader import BOMJoinedRow

ZERO = Decimal("0")


class MaterialType(IntEnum):
    """Material type codes from Kingdee."""

    SELF_MADE = 1  # 自制
    PURCHASED = 2  # 外购
    SUBCONTRACTED = 3  # 委外

    @property
    def display_name(self) -> str:
        return {1: "自制", 2: "包材", 3: "委外"}.get(self.value, "未知")


class MTOQueryHandler:
    """Handler for MTO number lookups with config-driven material class logic.

    Data source strategy by material code pattern:
    - 07.xx.xxx (成品): Source from SAL_SaleOrder, receipts from PRD_INSTOCK
    - 05.xx.xxx (自制): Source from PRD_MO, receipts from PRD_INSTOCK
    - 03.xx.xxx (外购): Source from PUR_PurchaseOrder (has built-in stock_in_qty)

    Cache tiers:
    - L1 (Memory): TTLCache for sub-10ms response on hot queries
    - L2 (SQLite): Persistent cache for ~100ms response
    - L3 (Kingdee): Live API fallback, 1-5s response
    """

    def __init__(
        self,
        production_order_reader: ProductionOrderReader,
        production_bom_reader: ProductionBOMReader,
        production_receipt_reader: ProductionReceiptReader,
        purchase_order_reader: PurchaseOrderReader,
        purchase_receipt_reader: PurchaseReceiptReader,
        subcontracting_order_reader: SubcontractingOrderReader,
        material_picking_reader: MaterialPickingReader,
        sales_delivery_reader: SalesDeliveryReader,
        sales_order_reader: SalesOrderReader,
        cache_reader: Optional["CacheReader"] = None,
        mto_config: Optional[MTOConfig] = None,
        metric_engine=None,
        memory_cache_enabled: bool = True,
        memory_cache_size: int = 600,
        memory_cache_ttl: int = 300,
    ):
        self._readers = {
            "production_order": production_order_reader,
            "production_bom": production_bom_reader,
            "production_receipt": production_receipt_reader,
            "purchase_order": purchase_order_reader,
            "purchase_receipt": purchase_receipt_reader,
            "subcontracting_order": subcontracting_order_reader,
            "material_picking": material_picking_reader,
            "sales_delivery": sales_delivery_reader,
            "sales_order": sales_order_reader,
        }
        # Store client reference for aux property lookups
        self._client = production_order_reader.client

        # Load MTO configuration (material class mappings)
        self._mto_config = mto_config or MTOConfig()

        # Semantic layer metric engine (None = disabled)
        self._metric_engine = metric_engine

        # L2: SQLite cache reader
        self._cache_reader = cache_reader

        # L1: In-memory TTLCache for sub-10ms responses
        self._memory_cache_enabled = memory_cache_enabled
        if memory_cache_enabled:
            self._memory_cache: TTLCache = TTLCache(
                maxsize=memory_cache_size, ttl=memory_cache_ttl
            )
            self._cache_lock = asyncio.Lock()
        else:
            self._memory_cache = None
            self._cache_lock = None

        # Cache statistics
        self._memory_hits = 0
        self._memory_misses = 0
        self._sqlite_hits = 0
        self._sqlite_misses = 0

        # Query frequency tracking for smart cache warming (bounded to 10k entries)
        self._query_counter: OrderedDict = OrderedDict()
        self._query_counter_max = 10000

    def _get_material_class(self, material_code: str) -> tuple[str | None, MaterialClassConfig | None]:
        """Get material class ID and config for a material code.

        Uses config patterns to determine material class:
        - 07.xx.xxx → finished_goods (成品)
        - 05.xx.xxx → self_made (自制)
        - 03.xx.xxx → purchased (外购)

        Returns:
            Tuple of (class_id, config) or (None, None) if no match
        """
        class_config = self._mto_config.get_class_for_material(material_code)
        if class_config:
            return class_config.id, class_config
        return None, None

    async def get_status(
        self,
        mto_number: str,
        use_cache: bool = True,
        source: Optional[str] = None,
        strict_aux: bool = False,
    ) -> MTOStatusResponse:
        """Get MTO status with three-tier cache strategy.

        Args:
            mto_number: The MTO number to query
            use_cache: If True, try caches before live API (default: True)
            source: Force data source - 'cache' or 'live'. Overrides use_cache.
            strict_aux: If True, disable the 3-tier aux fallback. Rows where
                receipts/picks/orders did not match the BOM aux exactly are
                returned with qty=0 and match_quality=no_match instead of
                being estimated. Bypasses L1 memory cache to avoid mixing
                strict/non-strict results.

        Returns:
            MTOStatusResponse with data_source metadata

        Cache tiers checked in order:
        1. L1 (Memory): ~1-5ms - TTLCache for hot queries
        2. L2 (SQLite): ~100ms - Persistent cache
        3. L3 (Kingdee): ~1-5s - Live API
        """
        # Handle explicit source parameter (overrides use_cache)
        if source == "cache":
            if self._cache_reader is None:
                raise ValueError("Cache not available")
            result = await self._try_cache(mto_number, strict_aux=strict_aux)
            if result is None:
                raise ValueError(f"No cached data found for MTO {mto_number}")
            return result
        elif source == "live":
            return await self._fetch_live(mto_number, strict_aux=strict_aux)
        # else: source is None → existing behavior using use_cache flag

        # Track query frequency for smart cache warming (bounded)
        self._query_counter[mto_number] = self._query_counter.get(mto_number, 0) + 1
        self._query_counter.move_to_end(mto_number)
        if len(self._query_counter) > self._query_counter_max:
            self._query_counter.popitem(last=False)

        # L1: Check in-memory cache first (sub-10ms response).
        # Skip when strict_aux=True so the cached non-strict result isn't
        # served — the L1 cache is keyed by mto_number alone.
        if use_cache and not strict_aux and self._memory_cache is not None:
            async with self._cache_lock:
                if mto_number in self._memory_cache:
                    self._memory_hits += 1
                    logger.debug("L1 memory cache hit for MTO %s", mto_number)
                    return self._memory_cache[mto_number]
                self._memory_misses += 1

        # L2: Try SQLite cache if enabled and cache reader available
        result = None
        if use_cache and self._cache_reader:
            result = await self._try_cache(mto_number, strict_aux=strict_aux)
            if result and result.children:
                self._sqlite_hits += 1
                logger.debug("L2 SQLite cache hit for MTO %s", mto_number)
            else:
                self._sqlite_misses += 1
                # Cache returned no children - fall back to live mode
                if result and not result.children:
                    logger.info(
                        "MTO %s: cache has no children, falling back to live mode",
                        mto_number
                    )
                    result = None  # Force fallback to live

        # L3: Fallback to live Kingdee API
        if not result:
            result = await self._fetch_live(mto_number, strict_aux=strict_aux)

        # Populate L1 cache with result — only for non-strict queries.
        if use_cache and not strict_aux and self._memory_cache is not None and result:
            async with self._cache_lock:
                self._memory_cache[mto_number] = result

        return result

    @staticmethod
    def _apply_strict_aux_filter(rows: list) -> list:
        """Stage 6: zero out qtys that came from a non-exact aux fallback.

        For each BOMJoinedRow, look at match_quality_breakdown. If a source
        used Tier 2 (aux_zero_fallback) or Tier 3 (all_aux_rollup), zero the
        corresponding qty fields and rewrite the breakdown entry to no_match.
        Tier 1 (exact) and existing no_match rows pass through unchanged.

        This makes data-quality issues visible to power users without
        forcing it on the default view.
        """
        SOURCE_TO_FIELDS = {
            "prod_receipt": ("prod_receipt_real_qty",),
            "pick": ("pick_actual_qty", "pick_app_qty"),
            "purchase_order": ("purchase_order_qty", "purchase_stock_in_qty"),
            "purchase_receipt": ("purchase_receipt_real_qty",),
            "subcontract": ("subcontract_order_qty", "subcontract_stock_in_qty"),
            "delivery": ("delivery_real_qty",),
        }
        NON_EXACT = ("aux_zero_fallback", "all_aux_rollup")

        out = []
        for row in rows:
            breakdown = dict(row.match_quality_breakdown or {})
            zero_fields: dict[str, Decimal] = {}
            mutated = False
            for source, fields in SOURCE_TO_FIELDS.items():
                if breakdown.get(source) in NON_EXACT:
                    breakdown[source] = "no_match"
                    for f in fields:
                        zero_fields[f] = ZERO
                    mutated = True
            if mutated:
                row = replace(row, match_quality_breakdown=breakdown, **zero_fields)
            out.append(row)
        return out

    async def get_related_orders(self, mto_number: str) -> MTORelatedOrdersResponse:
        """Get all order/document bill numbers related to an MTO number."""
        (
            sales_orders,
            prod_orders,
            purchase_orders,
            prod_receipts,
            material_picks,
            sales_deliveries,
            purchase_receipts,
        ) = await asyncio.gather(
            self._readers["sales_order"].fetch_by_mto(mto_number),
            self._readers["production_order"].fetch_by_mto(mto_number),
            self._readers["purchase_order"].fetch_by_mto(mto_number),
            self._readers["production_receipt"].fetch_by_mto(mto_number),
            self._readers["material_picking"].fetch_by_mto(mto_number),
            self._readers["sales_delivery"].fetch_by_mto(mto_number),
            self._readers["purchase_receipt"].fetch_by_mto(mto_number),
        )

        if not any(
            [
                sales_orders,
                prod_orders,
                purchase_orders,
                prod_receipts,
                material_picks,
                sales_deliveries,
                purchase_receipts,
            ]
        ):
            raise ValueError(f"No data found for MTO {mto_number}")

        def _unique_order_nodes(items, label: str) -> list[OrderNode]:
            seen: set[str] = set()
            nodes: list[OrderNode] = []
            for item in items:
                bill_no = getattr(item, "bill_no", "") or ""
                if not bill_no or bill_no in seen:
                    continue
                seen.add(bill_no)
                nodes.append(OrderNode(bill_no=bill_no, label=label))
            return nodes

        def _unique_document_nodes(
            items, label: str, linked_field: Optional[str] = None
        ) -> list[DocumentNode]:
            seen: set[str] = set()
            nodes: list[DocumentNode] = []
            for item in items:
                bill_no = getattr(item, "bill_no", "") or ""
                if not bill_no or bill_no in seen:
                    continue
                seen.add(bill_no)
                linked_order = None
                if linked_field:
                    linked_order = getattr(item, linked_field, None) or None
                nodes.append(
                    DocumentNode(
                        bill_no=bill_no,
                        label=label,
                        linked_order=linked_order,
                    )
                )
            return nodes

        orders = {
            "sales_orders": _unique_order_nodes(sales_orders, "销售订单"),
            "production_orders": _unique_order_nodes(prod_orders, "生产订单"),
            "purchase_orders": _unique_order_nodes(purchase_orders, "采购订单"),
        }
        documents = {
            "production_receipts": _unique_document_nodes(
                prod_receipts, "生产入库", linked_field="mo_bill_no"
            ),
            "material_pickings": _unique_document_nodes(material_picks, "生产领料"),
            "sales_deliveries": _unique_document_nodes(sales_deliveries, "销售出库"),
            "purchase_receipts": _unique_document_nodes(purchase_receipts, "采购入库"),
        }

        return MTORelatedOrdersResponse(
            mto_number=mto_number,
            orders=orders,
            documents=documents,
            query_time=datetime.now(timezone.utc),
            data_source="live",
        )

    async def _try_cache(
        self, mto_number: str, strict_aux: bool = False
    ) -> Optional[MTOStatusResponse]:
        """Attempt to build response from cache using BOM-first architecture.

        Uses a single SQL JOIN query (get_mto_bom_joined) to fetch all BOM children
        with pre-aggregated receipt/pick/order data, replacing the previous 8 parallel
        cache queries and complex routing logic.

        Data flow:
        1. Parallel fetch: sales orders, prod orders, and BOM-joined query
        2. Finished goods (07.xx) from SAL_SaleOrder (NOT from BOM)
        3. All other children from BOMJoinedRow → _bom_row_to_child()
        """
        # Fetch sales orders, prod orders, and the BOM-joined query in parallel
        (
            sales_orders_result,
            prod_orders_result,
            bom_joined_result,
        ) = await asyncio.gather(
            self._cache_reader.get_sales_orders(mto_number),
            self._cache_reader.get_production_orders(mto_number),
            self._cache_reader.get_mto_bom_joined(mto_number),
        )

        # Need at least some source data
        if not (sales_orders_result.data or prod_orders_result.data):
            return None

        # Log warning when serving stale cached data
        stale_sources = [
            name for name, result in [
                ("sales_orders", sales_orders_result),
                ("prod_orders", prod_orders_result),
                ("bom_joined", bom_joined_result),
            ]
            if result.data and not result.is_fresh
        ]
        if stale_sources:
            logger.warning(
                "MTO %s: serving stale cache data (sources: %s)",
                mto_number, ", ".join(stale_sources),
            )

        # Extract data from cache results
        sales_orders = sales_orders_result.data or []
        prod_orders = prod_orders_result.data or []
        bom_rows = bom_joined_result.data or []

        if strict_aux:
            bom_rows = self._apply_strict_aux_filter(bom_rows)

        # Collect aux_prop_ids for description lookup
        aux_prop_ids = set()
        for so in sales_orders:
            if hasattr(so, "aux_prop_id") and so.aux_prop_id:
                aux_prop_ids.add(so.aux_prop_id)
        for row in bom_rows:
            if row.aux_prop_id:
                aux_prop_ids.add(row.aux_prop_id)

        # Lookup aux property descriptions from Kingdee
        aux_descriptions = await self._client.lookup_aux_properties(list(aux_prop_ids))

        children = []

        # --- Finished goods (07.xx) from SAL_SaleOrder (NOT from BOM) ---
        # BOM-joined query now excludes 07.xx, so fetch 07.xx receipt/delivery
        # data separately from individual cache tables
        prod_receipts_result = await self._cache_reader.get_production_receipts(mto_number)
        sales_delivery_result = await self._cache_reader.get_sales_delivery(mto_number)
        material_picking_result = await self._cache_reader.get_material_picking(mto_number)
        # Wave 6B: also pull purchase receipts (STK_InStock) — 07.xx finished
        # goods can be transferred in from sister plants / OEM partners and
        # land in STK_InStock RKD01_SYS instead of PRD_INSTOCK.
        purchase_receipts_result = await self._cache_reader.get_purchase_receipts(mto_number)

        prod_receipts_07 = [r for r in (prod_receipts_result.data or []) if r.material_code.startswith("07.")]
        sales_delivery_07 = [r for r in (sales_delivery_result.data or []) if r.material_code.startswith("07.")]
        material_picks_07 = [r for r in (material_picking_result.data or []) if r.material_code.startswith("07.")]
        purchase_receipts_07 = [r for r in (purchase_receipts_result.data or []) if r.material_code.startswith("07.")]

        receipt_by_material: dict[tuple[str, int], Decimal] = {}
        for r in prod_receipts_07:
            key = (r.material_code, getattr(r, "aux_prop_id", 0) or 0)
            receipt_by_material[key] = receipt_by_material.get(key, ZERO) + r.real_qty

        delivered_by_material: dict[tuple[str, int], Decimal] = {}
        for r in sales_delivery_07:
            key = (r.material_code, getattr(r, "aux_prop_id", 0) or 0)
            delivered_by_material[key] = delivered_by_material.get(key, ZERO) + r.real_qty

        purchase_receipt_by_material: dict[tuple[str, int], Decimal] = {}
        for r in purchase_receipts_07:
            key = (r.material_code, getattr(r, "aux_prop_id", 0) or 0)
            purchase_receipt_by_material[key] = (
                purchase_receipt_by_material.get(key, ZERO) + r.real_qty
            )

        sales_by_key: dict[tuple[str, int], list] = defaultdict(list)
        for so in sales_orders:
            class_id, _ = self._get_material_class(so.material_code)
            if class_id == "finished_goods":
                aux_prop_id = getattr(so, "aux_prop_id", 0) or 0
                key = (so.material_code, aux_prop_id)
                sales_by_key[key].append(so)

        for key, so_list in sales_by_key.items():
            child = self._build_aggregated_sales_child(
                so_list, receipt_by_material, delivered_by_material,
                aux_descriptions,
                purchase_receipt_by_material=purchase_receipt_by_material,
            )
            children.append(child)

        # --- BOM children: convert each BOMJoinedRow to ChildItem ---
        for row in bom_rows:
            child = self._bom_row_to_child(row, aux_descriptions)
            children.append(child)

        # Build parent from first available sales order
        parent = self._build_parent_from_sales(sales_orders[0] if sales_orders else None, mto_number)

        # Calculate cache age
        cache_age = None
        for result in [sales_orders_result, prod_orders_result, bom_joined_result]:
            if result.synced_at:
                now_local = datetime.now()
                synced = result.synced_at if result.synced_at.tzinfo is None else result.synced_at.replace(tzinfo=None)
                cache_age = int((now_local - synced).total_seconds())
                break

        result = MTOStatusResponse(
            mto_number=mto_number,
            parent=parent,
            children=children,
            query_time=datetime.now(timezone.utc),
            data_source="cache",
            cache_age_seconds=cache_age,
        )

        if self._metric_engine:
            enrich_response(result, self._metric_engine)

        return result

    async def _fetch_live(
        self, mto_number: str, strict_aux: bool = False
    ) -> MTOStatusResponse:
        """Fetch data from live Kingdee API using BOM-first architecture.

        Uses the same _bom_row_to_child method as the cache path for consistent
        child item construction. Finished goods (07.xx) are handled separately
        via _build_aggregated_sales_child.

        Data flow:
        1. 9 parallel Kingdee API calls
        2. Finished goods (07.xx) from SAL_SaleOrder (NOT from BOM)
        3. All other children: live data → BOMJoinedRow → _bom_row_to_child()
        """
        # Fetch all source forms and receipt data in parallel
        (
            sales_orders,
            prod_orders,
            purchase_orders,
            prod_receipts,
            purchase_receipts,
            subcontracting_orders,
            material_picks,
            sales_deliveries,
            production_bom,
        ) = await asyncio.gather(
            self._readers["sales_order"].fetch_by_mto(mto_number),
            self._readers["production_order"].fetch_by_mto(mto_number),
            self._readers["purchase_order"].fetch_by_mto(mto_number),
            self._readers["production_receipt"].fetch_by_mto(mto_number),
            self._readers["purchase_receipt"].fetch_by_mto(mto_number),
            self._readers["subcontracting_order"].fetch_by_mto(mto_number),
            self._readers["material_picking"].fetch_by_mto(mto_number),
            self._readers["sales_delivery"].fetch_by_mto(mto_number),
            self._readers["production_bom"].fetch_by_mto(mto_number),
        )

        # Aggregate stats at info level
        logger.info(
            "MTO %s live query results: SAL_SaleOrder=%d, PRD_MO=%d, PUR=%d, PRD_INSTOCK=%d",
            mto_number, len(sales_orders), len(prod_orders), len(purchase_orders), len(prod_receipts)
        )

        # Collect aux_prop_ids for lookup
        aux_prop_ids = set()
        for items in [sales_orders, purchase_orders, prod_receipts,
                      sales_deliveries, material_picks, production_bom]:
            for item in items:
                if hasattr(item, "aux_prop_id") and item.aux_prop_id:
                    aux_prop_ids.add(item.aux_prop_id)

        # Lookup aux property descriptions from BD_FLEXSITEMDETAILV
        aux_descriptions = await self._client.lookup_aux_properties(list(aux_prop_ids))

        children = []

        # --- Finished goods (07.xx) from SAL_SaleOrder ---
        receipt_by_material = _sum_by_material_and_aux(prod_receipts, "real_qty")
        delivered_by_material = _sum_by_material_and_aux(sales_deliveries, "real_qty")
        # Wave 6B: include STK_InStock (purchase_receipts) so finished goods
        # transferred from sister plants are visible (DK251003S 07.02.151/154).
        purchase_receipt_by_material = _sum_by_material_and_aux(
            purchase_receipts, "real_qty"
        )

        sales_by_key: dict[tuple[str, int], list] = defaultdict(list)
        for so in sales_orders:
            class_id, _ = self._get_material_class(so.material_code)
            if class_id == "finished_goods":
                key = (so.material_code, getattr(so, "aux_prop_id", 0) or 0)
                sales_by_key[key].append(so)

        for key, so_list in sales_by_key.items():
            child = self._build_aggregated_sales_child(
                so_list, receipt_by_material, delivered_by_material,
                aux_descriptions,
                purchase_receipt_by_material=purchase_receipt_by_material,
            )
            children.append(child)

        # --- BOM children via shared path ---
        bom_rows = self._build_bom_joined_rows_from_live(
            production_bom, prod_orders, prod_receipts, material_picks,
            purchase_orders, purchase_receipts, subcontracting_orders,
            sales_deliveries,
        )

        if strict_aux:
            bom_rows = self._apply_strict_aux_filter(bom_rows)

        for row in bom_rows:
            child = self._bom_row_to_child(row, aux_descriptions)
            children.append(child)

        # Build parent from first available sales order
        parent = self._build_parent_from_sales(sales_orders[0] if sales_orders else None, mto_number)

        # Check if we have any data
        if not children and not sales_orders and not prod_orders and not purchase_orders:
            raise ValueError(f"No data found for MTO {mto_number}")

        result = MTOStatusResponse(
            mto_number=mto_number,
            parent=parent,
            children=children,
            query_time=datetime.now(timezone.utc),
            data_source="live",
        )

        if self._metric_engine:
            enrich_response(result, self._metric_engine)

        return result

    def _build_bom_joined_rows_from_live(
        self,
        production_bom: list,
        prod_orders: list,
        prod_receipts: list,
        material_picks: list,
        purchase_orders: list,
        purchase_receipts: list,
        subcontracting_orders: list,
        sales_deliveries: list,
    ) -> list[BOMJoinedRow]:
        """Convert live API data into BOMJoinedRow format for shared enrichment.

        Does the same aggregation as the SQL JOIN in cache_reader, but in Python
        for live data. Groups BOM items by (material_code, aux_prop_id).

        For items found in source orders/receipts/picks but NOT in PPBOM,
        synthetic BOMJoinedRow entries are created so they still appear in output.
        """
        # Pre-aggregate all source data by (material_code, aux_prop_id)
        receipt_real = _sum_by_material_and_aux(prod_receipts, "real_qty")
        receipt_must = _sum_by_material_and_aux(prod_receipts, "must_qty")
        pick_actual_map = _sum_by_material_and_aux(material_picks, "actual_qty")
        pick_app_map = _sum_by_material_and_aux(material_picks, "app_qty")
        po_order = _sum_by_material_and_aux(purchase_orders, "order_qty")
        po_stock_in = _sum_by_material_and_aux(purchase_orders, "stock_in_qty")
        pur_real = _sum_by_material_and_aux(purchase_receipts, "real_qty")
        sub_order = _sum_by_material_and_aux(subcontracting_orders, "order_qty")
        sub_stock_in = _sum_by_material_and_aux(subcontracting_orders, "stock_in_qty")
        del_real = _sum_by_material_and_aux(sales_deliveries, "real_qty")

        # Aggregate by material_code for aux=0 only (fallback for unmatched aux)
        _by_code: dict[str, dict] = {}
        for label, aux_dict in [
            ("receipt_real", receipt_real), ("receipt_must", receipt_must),
            ("pick_actual", pick_actual_map), ("pick_app", pick_app_map),
            ("po_order", po_order), ("po_stock_in", po_stock_in),
            ("pur_real", pur_real), ("sub_order", sub_order),
            ("sub_stock_in", sub_stock_in), ("del_real", del_real),
        ]:
            code_totals: dict[str, Decimal] = {}
            for (code, _aux), val in aux_dict.items():
                if _aux == 0:
                    code_totals[code] = code_totals.get(code, ZERO) + val
            _by_code[label] = code_totals

        # Aggregate by material_code across ALL aux variants (fallback for aux=0 BOM items)
        _by_code_all: dict[str, dict[str, Decimal]] = {}
        for label, aux_dict in [
            ("receipt_real", receipt_real), ("receipt_must", receipt_must),
            ("pick_actual", pick_actual_map), ("pick_app", pick_app_map),
            ("po_order", po_order), ("po_stock_in", po_stock_in),
            ("pur_real", pur_real), ("sub_order", sub_order),
            ("sub_stock_in", sub_stock_in), ("del_real", del_real),
        ]:
            code_totals: dict[str, Decimal] = {}
            for (code, _aux), val in aux_dict.items():
                code_totals[code] = code_totals.get(code, ZERO) + val
            _by_code_all[label] = code_totals

        # ---- Wave 5B (receipt-side): pre-compute Tier 2.5/Tier 3 rollup
        # dedup state per receipt label.
        #
        # Bug class: when BOM has multiple aux groups for the same code AND
        # receipts are recorded at aux values disjoint from the BOM aux
        # numbering, every BOM-aux row that falls to Tier 2.5 (aux≠0 →
        # _by_code_all) or Tier 3 (aux=0 → _by_code_all) currently returns
        # the FULL all-aux rollup → SUM by code = N × actual receipt total.
        # When partial exact matches exist (some BOM-aux DO match a receipt
        # aux), the matched groups claim their exact amount AND non-matched
        # groups claim full rollup → the same shape on the receipt side
        # that Bug A fixes on the PRD_MO/demand side.
        #
        # The fix mirrors `_lookup_mo_qty`'s partial-match dedup:
        #   - exact_matched_amount = SUM of receipt qty across BOM-aux that
        #     have a Tier 1 hit in this `lookup`
        #   - remainder = max(0, all_aux_rollup - exact_matched_amount)
        #   - elect ONE non-matched BOM-aux as the representative (aux=0
        #     wins; else smallest aux). The elected row gets `remainder`.
        #     All other non-matched BOM-aux rows get 0.
        #
        # Real-data scenarios this kills:
        #   - AK2510034 / 05.02.15.62 电镀镜片: BOM at specific aux,
        #     receipts at completely different aux → pre-Wave-5B QP returns
        #     0/0 fulfilled/picked, KD shows 1444/1444. With Tier 2.5 +
        #     dedup, the elected non-matched BOM-aux returns 1444; siblings
        #     return 0; SUM matches KD.
        #
        # Per-code, per-label state is keyed off bom_groups (computed below
        # at "Step 1" — `bom_groups` is populated before this block runs).
        # We don't compute it here; instead, `_get` consults the lazily-
        # populated `_recv_tier_state` dict, which Step 1 fills before any
        # `_make_row` call. That ordering is preserved by construction:
        # `bom_groups` is built and `_recv_tier_state` populated before the
        # `for (code, aux), bom_list in bom_groups.items(): rows.append(
        # _make_row(...))` loop. See the comment in Step 1 for details.
        _recv_tier_state: dict[str, dict[str, dict]] = {}

        def _get(lookup: dict, lookup_label: str, code: str, aux: int) -> Decimal:
            """Get value by (code, aux) with bidirectional aux fallback.

            Tier 1: exact (code, aux) match.
            Tier 2: BOM aux≠0, receipt at aux=0 (`_by_code`).
            Tier 2.5 (Wave 5B, Bug B): BOM aux≠0, both Tier 1 + Tier 2
                miss → fall through to all-aux rollup `_by_code_all`. ONLY
                the elected representative aux receives the remainder
                (rollup minus exact-matched siblings). Non-elected non-
                matched aux receive 0. Mirrors `_lookup_mo_qty`'s Tier 2.5.
            Tier 3: BOM aux=0 → all-aux rollup `_by_code_all`. Same partial-
                match dedup applies — when partial exact matches exist for
                this code, only the elected aux=0 BOM-row receives the
                remainder; if aux=0 is non-elected (e.g. another BOM group
                won), it gets 0.
            """
            exact = lookup.get((code, aux))
            if exact is not None:
                return exact
            if aux != 0:
                # Tier 2: BOM has specific aux, try receipts with aux=0
                fallback = _by_code.get(lookup_label, {}).get(code)
                if fallback is not None:
                    return fallback
                # Tier 2.5: fall through to all-aux rollup with dedup state.
                state = _recv_tier_state.get(lookup_label, {}).get(code)
                if state is not None:
                    if aux == state["elected_aux"]:
                        return state["remainder"]
                    return ZERO
                # No state ⇒ either no rollup data or a single BOM-aux group
                # with no exact match. Single-group case: safe to return
                # the full rollup (same as old behaviour, no double count).
                all_sum = _by_code_all.get(lookup_label, {}).get(code)
                if all_sum is not None:
                    return all_sum
            else:
                # Tier 3: BOM has aux=0, all-aux rollup with dedup state.
                state = _recv_tier_state.get(lookup_label, {}).get(code)
                if state is not None:
                    if aux == state["elected_aux"]:
                        return state["remainder"]
                    return ZERO
                all_sum = _by_code_all.get(lookup_label, {}).get(code)
                if all_sum is not None:
                    return all_sum
            return ZERO

        def _get_quality(lookup: dict, lookup_label: str, code: str, aux: int) -> str:
            """Return the match_quality tier label, mirroring _get's branching exactly.

            Stage 4 of PLAN_aux_match_visibility — keeps live path shape-compatible
            with the cache SQL CASE expressions in get_mto_bom_joined.

            Wave 5B note: when a row is non-elected under Tier 2.5/3 partial-
            match dedup, _get returns 0 but _get_quality still reports the
            tier that WOULD have applied — this is intentional; the
            telemetry tracks WHICH path the data came from, not whether it
            was zeroed by dedup.
            """
            if (code, aux) in lookup:
                return "exact"
            if aux != 0:
                if code in _by_code.get(lookup_label, {}):
                    return "aux_zero_fallback"
                if code in _by_code_all.get(lookup_label, {}):
                    return "all_aux_rollup"
            else:
                if code in _by_code_all.get(lookup_label, {}):
                    return "all_aux_rollup"
            return "no_match"

        def _make_row(code: str, aux: int, material_name: str, specification: str,
                      aux_attributes: str, material_type: int, need_qty: Decimal,
                      picked_qty: Decimal, no_picked_qty: Decimal,
                      mo_bill_no: str = "", mto_number: str = "") -> BOMJoinedRow:
            return BOMJoinedRow(
                mo_bill_no=mo_bill_no,
                mto_number=mto_number,
                material_code=code,
                material_name=material_name,
                specification=specification,
                aux_attributes=aux_attributes,
                aux_prop_id=aux,
                material_type=material_type,
                need_qty=need_qty,
                picked_qty=picked_qty,
                no_picked_qty=no_picked_qty,
                prod_receipt_real_qty=_get(receipt_real, "receipt_real", code, aux),
                prod_receipt_must_qty=_get(receipt_must, "receipt_must", code, aux),
                pick_actual_qty=_get(pick_actual_map, "pick_actual", code, aux),
                pick_app_qty=_get(pick_app_map, "pick_app", code, aux),
                purchase_order_qty=_get(po_order, "po_order", code, aux),
                purchase_stock_in_qty=_get(po_stock_in, "po_stock_in", code, aux),
                purchase_receipt_real_qty=_get(pur_real, "pur_real", code, aux),
                subcontract_order_qty=_get(sub_order, "sub_order", code, aux),
                subcontract_stock_in_qty=_get(sub_stock_in, "sub_stock_in", code, aux),
                delivery_real_qty=_get(del_real, "del_real", code, aux),
                match_quality_breakdown={
                    # Use the receipt_real lookup as the canonical signal for
                    # prod_receipt — receipt_must is BOM-sourced now (see
                    # bug-patterns.md #10) so tracking its tier separately would
                    # be misleading.
                    "prod_receipt": _get_quality(receipt_real, "receipt_real", code, aux),
                    "pick": _get_quality(pick_actual_map, "pick_actual", code, aux),
                    "purchase_order": _get_quality(po_order, "po_order", code, aux),
                    "purchase_receipt": _get_quality(pur_real, "pur_real", code, aux),
                    "subcontract": _get_quality(sub_order, "sub_order", code, aux),
                    "delivery": _get_quality(del_real, "del_real", code, aux),
                },
            )

        # PRD_MO qty lookup — used both for synthetic rows AND for self-made
        # need_qty in Step 1 (see Pattern 10 / bug-patterns.md). Defined here
        # so it's available throughout the rest of this method.
        _mo_qty: dict[tuple[str, int], Decimal] = {}
        for po in prod_orders:
            k = (po.material_code, getattr(po, "aux_prop_id", 0) or 0)
            _mo_qty[k] = _mo_qty.get(k, ZERO) + getattr(po, "qty", ZERO)

        # Pre-compute Tier-3 rollup: total PRD_MO.FQty across ALL aux variants
        # for each material_code. Used when PPBOM has aux=0 (generic) but
        # PRD_MO carries specific aux (e.g., AS2603009 / 05.07.02.01: PPBOM
        # aux=0, PRD_MO aux=105814 → exact and aux=0 lookups both miss; need
        # to roll up PRD_MO across all aux). Symmetric to the
        # `all_aux_rollup` tier in receipt-side _get().
        _mo_qty_by_code: dict[str, Decimal] = {}
        for (c, _), v in _mo_qty.items():
            _mo_qty_by_code[c] = _mo_qty_by_code.get(c, ZERO) + v

        def _lookup_mo_qty(code: str, aux: int) -> Decimal:
            """Resolve PRD_MO.FQty for (code, aux) with 4-tier aux fallback.

            Tier 1: exact (code, aux) match.
            Tier 2: BOM has specific aux, PRD_MO recorded at aux=0.
            Tier 2.5 (Wave 4C): BOM has specific aux AND PRD_MO has only
                    other specific aux values (no aux=0 entry) — disjoint
                    aux numbering between PPBOM and PRD_MO. Roll up all
                    PRD_MO rows for the code, same answer as Tier 3 for the
                    BOM-aux=0 case. Real-data scenario: AS2602033 /
                    05.02.12.44 — PPBOM at aux=105726/197964/206684/106447/
                    106237 and PRD_MO at aux=221031/221032/221033. Without
                    this tier, Tier 1 + Tier 2 both miss and the caller
                    drops to MAX(b.need_qty), inflating the demand by N×
                    the actual production target (~2.7× in this case).
            Tier 3: BOM has generic aux=0, PRD_MO at one or more specific aux
                    values → sum across all PRD_MO rows for this material.
                    (Mirrors the receipt-side `all_aux_rollup` in _get.)

            Tier 2.5 and Tier 3 are symmetric — both reduce to "use the
            team's total production target across all aux variants" when
            PPBOM and PRD_MO disagree on aux numbering.

            NOTE — partial-match dedup (Wave 4C → Wave 5B): when multiple
            BOM-aux groups exist for the same code AND the rollup is in
            play, attributing the full rollup to every non-matched group
            inflates SUM(must_qty) by N× (Wave 4C "no exact match
            anywhere" case) or causes partial-overcount (Wave 5B "some
            exact, some not" case — AS2602033 / 05.02.08.037). The
            caller (Step 1 BOM-row builder) bypasses this helper for
            non-matched BOM-aux rows and uses the precomputed
            `_tier_2_5_state[code]` (elected_aux + remainder) instead.
            This helper is still safe to call from synthetic-row blocks
            (Step 2), where there's at most one row per (code, aux) and
            no double-count risk. See the docstring above
            `_tier_2_5_state` for the full rule.

            Returns ZERO when no PRD_MO row exists for the material at all —
            caller falls back to MAX(b.need_qty) per Pattern 10 fix.
            """
            # Tier 1: exact (code, aux)
            exact = _mo_qty.get((code, aux))
            if exact is not None and exact > 0:
                return exact
            # Tier 2: BOM specific aux → PRD_MO at aux=0
            if aux != 0:
                v = _mo_qty.get((code, 0))
                if v is not None and v > 0:
                    return v
                # Tier 2.5 (Wave 4C): both exact and aux=0 missed — PPBOM and
                # PRD_MO use disjoint aux numbering for the same code (real-
                # data case AS2602033 / 05.02.12.44). Roll up all PRD_MO for
                # the code, same answer as Tier 3 for the BOM-aux=0 case.
                # Without this fallback, the caller drops to MAX(b.need_qty)
                # and inflates the demand by N× the actual production target.
                return _mo_qty_by_code.get(code, ZERO)
            # Tier 3: BOM aux=0 → roll up ALL PRD_MO rows for this material
            return _mo_qty_by_code.get(code, ZERO)

        # --- Step 1: Build rows from PPBOM (primary source) ---
        bom_groups: dict[tuple[str, int], list] = defaultdict(list)
        for bom in production_bom:
            if bom.material_code.startswith("07."):
                continue  # finished goods handled via _build_aggregated_sales_child
            key = (bom.material_code, getattr(bom, "aux_prop_id", 0) or 0)
            bom_groups[key].append(bom)

        # Wave 4C → Wave 5B (Bug A) — per-code partial-match dedup of
        # fallback rollup across multiple BOM-aux groups for the same
        # self-made code.
        #
        # When PPBOM and PRD_MO use disjoint aux numbering for the same code
        # (real-data case AS2602033 / 05.02.12.44 — PPBOM at aux=0 +
        # 105726/106237/106447/197964/206684, PRD_MO at aux=221031/221032/
        # 221033), several BOM-aux groups land in fallback territory:
        #   - aux=0 group goes to Tier 3 rollup
        #   - specific-aux groups go to Tier 2.5 rollup OR MAX(need_qty)
        # If every fallback row receives the full team rollup (or its own
        # MAX), SUM(must_qty) by code = N × team-target instead of 1 ×
        # team-target.
        #
        # Wave 5B partial-match extension: the previous Wave 4C dedup
        # bailed out entirely if ANY BOM-aux had a Tier 1 exact match —
        # but real-data case AS2602033 / 05.02.08.037 shows the
        # over-application: PPBOM has 2 aux groups, PRD_MO has 1 exact
        # match (32544) plus extra coverage. Pre-Wave-5B both rows fired
        # Tier 1 (matched aux: 32544) AND Tier 2.5 (non-matched aux: full
        # rollup 32544) → SUM = 65088 = 2× the team's actual target.
        #
        # New rule: when partial exact matches exist, the team's total
        # target is split — exact-matched rows claim their exact share
        # (left through `_lookup_mo_qty` unchanged), while non-matched
        # rows share the REMAINDER:
        #   exact_matched_amount = SUM(_mo_qty[(c, a)] for a in BOM-aux
        #                              that has a positive Tier 1 hit)
        #   remainder = max(0, _mo_qty_by_code[c] - exact_matched_amount)
        # ONE non-matched BOM-aux (elected: aux=0 wins; else smallest
        # specific aux) receives `remainder`; all other non-matched BOM-
        # aux groups get 0.
        #
        # If no Tier 1 matches exist (legacy Wave 4C case), exact_matched=
        # 0 and remainder = full rollup — behaviour identical to Wave 4C.
        #
        # If `remainder <= 0`, all non-matched groups get 0 — the team's
        # plan is already fully accounted for in the matched groups.
        _tier_2_5_state: dict[str, dict] = {}
        _bom_codes_seen: dict[str, list[int]] = defaultdict(list)
        for (c, a) in bom_groups.keys():
            _bom_codes_seen[c].append(a)
        for c, aux_list in _bom_codes_seen.items():
            rollup = _mo_qty_by_code.get(c, ZERO)
            if rollup <= 0:
                continue
            # Identify Tier 1 exact-match BOM-aux groups vs non-matched.
            exact_matched_aux = [
                a for a in aux_list
                if (c, a) in _mo_qty and _mo_qty[(c, a)] > 0
            ]
            non_matched_aux = [a for a in aux_list if a not in exact_matched_aux]
            # If every BOM-aux has Tier 1 → no fallback rollup needed at
            # all; let _lookup_mo_qty resolve each row. (Wave 4C kept this
            # branch as "don't dedup".)
            if not non_matched_aux:
                continue
            exact_matched_amount = sum(
                (_mo_qty[(c, a)] for a in exact_matched_aux), ZERO
            )
            remainder = max(ZERO, rollup - exact_matched_amount)
            # Election rule (matches cache CTE bom_ranked_for_dedup +
            # Wave 4C "first encountered"): aux=0 wins; else smallest aux.
            if 0 in non_matched_aux:
                elected_aux = 0
            else:
                elected_aux = min(non_matched_aux)
            _tier_2_5_state[c] = {
                "elected_aux": elected_aux,
                "remainder": remainder,
                "exact_matched_aux": set(exact_matched_aux),
            }

        # ---- Wave 5B (Bug B) — receipt-side Tier 2.5/3 partial-match
        # dedup. Mirror of `_tier_2_5_state` but per receipt label.
        # Built here (post bom_groups) so the `_get` closure (defined
        # above) can consult `_recv_tier_state` at row-construction time.
        #
        # Real-data scenario: AK2510034 / 05.02.15.62 — BOM at specific
        # aux, PRD_INSTOCK / PRD_PickMtrl at completely different aux.
        # Pre-fix: every BOM-aux row returned 0 (Tier 1+2 miss; Tier 3
        # only fires for BOM aux=0). With Wave 5B Tier 2.5 fall-through
        # to all-aux rollup, the elected non-matched BOM-aux row claims
        # the receipt total; siblings stay 0; SUM matches Kingdee.
        _recv_lookups = (
            ("receipt_real", receipt_real),
            ("receipt_must", receipt_must),
            ("pick_actual", pick_actual_map),
            ("pick_app", pick_app_map),
            ("po_order", po_order),
            ("po_stock_in", po_stock_in),
            ("pur_real", pur_real),
            ("sub_order", sub_order),
            ("sub_stock_in", sub_stock_in),
            ("del_real", del_real),
        )
        for label, lookup in _recv_lookups:
            per_code: dict[str, dict] = {}
            for c, aux_list in _bom_codes_seen.items():
                rollup = _by_code_all.get(label, {}).get(c, ZERO)
                if rollup <= 0:
                    continue
                exact_matched_aux = [a for a in aux_list if (c, a) in lookup]
                non_matched_aux = [a for a in aux_list if a not in exact_matched_aux]
                if not non_matched_aux:
                    continue
                exact_matched_amount = sum(
                    (lookup[(c, a)] for a in exact_matched_aux), ZERO
                )
                remainder = max(ZERO, rollup - exact_matched_amount)
                if 0 in non_matched_aux:
                    elected_aux = 0
                else:
                    elected_aux = min(non_matched_aux)
                per_code[c] = {
                    "elected_aux": elected_aux,
                    "remainder": remainder,
                }
            if per_code:
                _recv_tier_state[label] = per_code

        rows = []
        covered_keys: set[tuple[str, int]] = set()

        for (code, aux), bom_list in bom_groups.items():
            first = bom_list[0]
            m_type = getattr(first, "material_type", 0)
            # REGRESSION GUARD (bug-patterns.md #10, BOM-rollup variant):
            # For self-made (material_type == 1), `need_qty` is the team's
            # production target — NOT the sum across parent BOMs. The same
            # self-made component can appear in N parent PPBOMs within one MTO,
            # each line carrying the full demand for that parent (e.g.,
            # 05.02.08.027 in 50 parents × 3744 = 187,200, when the actual
            # production target is 3744). The authoritative source is
            # PRD_MO.FQty for (code, aux), with fallback chain in
            # `_lookup_mo_qty` (Tier 1 exact → Tier 2 aux=0 → Tier 2.5/Tier 3
            # all-aux rollup) before degrading to MAX(b.need_qty). Tier 2.5
            # (Wave 4C) handles BOM-specific-aux + PRD_MO-other-specific-aux
            # disjoint numbering (AS2602033 / 05.02.12.44); Tier 3 (commit
            # 948054c) handles BOM-aux=0 + PRD_MO-specific-aux.
            # Old variant fixed `b8e6fc7` (receipt FMustQty sum); BOM-rollup
            # variant introduced by `ce08d69` (BOM-first refactor) and fixed
            # 2026-04-26.
            #
            # For purchased (2) / subcontracted (3): summing IS correct —
            # purchased materials legitimately accumulate across parent BOMs
            # (you place one combined order).
            if m_type == 1:
                # Wave 5B: when a code has a tier_2_5_state entry, the
                # team's total target is split between exact-matched BOM-
                # aux rows (which use _lookup_mo_qty Tier 1 directly) and
                # non-matched BOM-aux rows (which share the remainder via
                # the elected representative). See Wave 5B docstring above
                # `_tier_2_5_state`.
                state = _tier_2_5_state.get(code)
                if state is not None and aux not in state["exact_matched_aux"]:
                    # Non-matched BOM-aux group — only the elected aux
                    # carries the remainder; all others get 0.
                    if aux == state["elected_aux"]:
                        need_qty_val = state["remainder"]
                    else:
                        need_qty_val = ZERO
                else:
                    # Either an exact-matched aux (use Tier 1 via
                    # _lookup_mo_qty), or the code has no fallback state
                    # at all (single BOM-aux group, all-matched, or no
                    # PRD_MO rollup) — let `_lookup_mo_qty` resolve.
                    _mo = _lookup_mo_qty(code, aux)
                    if _mo > 0:
                        need_qty_val = _mo
                    else:
                        need_qty_val = max(
                            (getattr(b, "need_qty", ZERO) for b in bom_list),
                            default=ZERO,
                        )
            else:
                need_qty_val = sum(getattr(b, "need_qty", ZERO) for b in bom_list)
            rows.append(_make_row(
                code=code,
                aux=aux,
                material_name=getattr(first, "material_name", ""),
                specification=getattr(first, "specification", ""),
                aux_attributes=getattr(first, "aux_attributes", ""),
                material_type=m_type,
                need_qty=need_qty_val,
                picked_qty=sum(getattr(b, "picked_qty", ZERO) for b in bom_list),
                no_picked_qty=sum(getattr(b, "no_picked_qty", ZERO) for b in bom_list),
                mo_bill_no=getattr(first, "mo_bill_no", ""),
                mto_number=getattr(first, "mto_number", ""),
            ))
            covered_keys.add((code, aux))

        # --- Step 2: Synthetic rows for items NOT in PPBOM ---
        # Skip finished_goods (07.xx) — handled via _build_aggregated_sales_child.
        #
        # Dedup rule (bug-patterns.md #11):
        #  - `covered_keys` (composite (code, aux)) — exact-match dedup; enforced
        #    in every block.
        #  - `covered_codes_from_bom` (code only, seeded from BOM only) — suppresses
        #    every block when ANY BOM entry exists for that code, because the
        #    3-tier aux fallback in `_get` / `_lookup_mo_qty` already attributes
        #    non-matching aux variants' qty to the BOM row.
        #  - `covered_codes_synthetic` (code only, mutated by 2a/2c/2d) — prevents
        #    self-made-flavored blocks from double-emitting across each other
        #    (e.g., PRD_INSTOCK at aux=5001 + PRD_MO at aux=0 for the same code →
        #    one row, not two).
        #
        # Critical (Bug 5b): block 2b (PUR) does NOT consult or mutate
        # `covered_codes_synthetic`. A purchased material with multiple aux
        # variants (e.g., 03.23.009 贴纸 with 3 color SKUs and no PPBOM) is
        # legitimately N distinct rows, not 1 — the previous code-only dedup
        # silently emitted only the first variant.
        covered_codes_from_bom: set[str] = {code for code, _aux in covered_keys}
        covered_codes_synthetic: set[str] = set(covered_codes_from_bom)

        # 2a: Items from PRD_INSTOCK not in PPBOM (skip 07.xx finished goods)
        receipt_groups: dict[tuple[str, int], list] = defaultdict(list)
        for pr in prod_receipts:
            if pr.material_code.startswith("07."):
                continue
            aux = getattr(pr, "aux_prop_id", 0) or 0
            receipt_groups[(pr.material_code, aux)].append(pr)

        # Wave 6C: track which codes had an actual 2a emit (i.e., PRD_INSTOCK
        # exists). 2c uses this to decide whether the `covered_codes_synthetic`
        # gate applies. For codes with NO PRD_INSTOCK at all, 2c needs to emit
        # every PRD_MO aux variant (otherwise multi-aux self-made codes lose
        # all-but-one variant — DK251003S 05.20.01.07.011 had 3 PRD_MO aux
        # totaling 49440 but only 960 surfaced).
        codes_with_prd_instock_emit: set[str] = set()
        for (code, aux), pr_list in receipt_groups.items():
            if (code, aux) in covered_keys or code in covered_codes_synthetic:
                continue
            first = pr_list[0]
            # Items in PRD_INSTOCK are production receipts → self-made
            m_type = 1
            rows.append(_make_row(
                code=code, aux=aux,
                material_name=getattr(first, "material_name", ""),
                specification=getattr(first, "specification", ""),
                aux_attributes="",
                material_type=m_type,
                need_qty=_lookup_mo_qty(code, aux),
                picked_qty=ZERO, no_picked_qty=ZERO,
            ))
            covered_keys.add((code, aux))
            covered_codes_synthetic.add(code)
            codes_with_prd_instock_emit.add(code)

        # 2b: Purchase orders (03.xx) without PPBOM entry — multi-aux SKU-aware,
        # does NOT consult or mutate covered_codes_synthetic (see Bug 5b).
        pur_groups: dict[tuple[str, int], list] = defaultdict(list)
        for pur in purchase_orders:
            if pur.material_code.startswith("07."):
                continue
            aux = getattr(pur, "aux_prop_id", 0) or 0
            pur_groups[(pur.material_code, aux)].append(pur)

        for (code, aux), pur_list in pur_groups.items():
            # Note: deliberately NOT checking covered_codes_synthetic — Bug 5b.
            if (code, aux) in covered_keys or code in covered_codes_from_bom:
                continue
            first = pur_list[0]
            rows.append(_make_row(
                code=code, aux=aux,
                material_name=getattr(first, "material_name", ""),
                specification=getattr(first, "specification", ""),
                aux_attributes=getattr(first, "aux_attributes", ""),
                material_type=2,  # purchased
                need_qty=ZERO, picked_qty=ZERO, no_picked_qty=ZERO,
            ))
            covered_keys.add((code, aux))

        # 2c: PRD_MO (05.xx or 03.xx+selfmade) without PPBOM or receipts.
        # Self-made-flavored: shares covered_codes_synthetic with 2a/2d.
        #
        # Wave 6C carve-out: for codes with NO PRD_INSTOCK emit in 2a, drop
        # the `covered_codes_synthetic` gate so every PRD_MO aux variant
        # surfaces. Pre-Wave-6C, a code with N PRD_MO aux variants and zero
        # PRD_INSTOCK rows lost N-1 aux variants entirely (DK251003S
        # 05.20.01.07.011: 3 PRD_MO rows summing to 49440 → QP showed 960).
        # The gate is preserved when 2a fired so the receipt-side `_get`
        # rollup doesn't get attributed twice (the elected 2a row already
        # consumed the receipt rollup at its aux).
        mo_groups: dict[tuple[str, int], list] = defaultdict(list)
        for po in prod_orders:
            if po.material_code.startswith("07."):
                continue
            aux = getattr(po, "aux_prop_id", 0) or 0
            mo_groups[(po.material_code, aux)].append(po)

        for (code, aux), po_list in mo_groups.items():
            if (code, aux) in covered_keys:
                continue
            # Code-level dedup applies UNLESS 2c is the only block emitting for
            # this code (no BOM, no PRD_INSTOCK). In that case the previous
            # gate collapsed multi-aux PRD_MO into a single row — DK251003S
            # 05.20.01.07.011 had 3 PRD_MO aux summing to 49440, only 960
            # surfaced. Skip the gate only when BOM had no entry AND 2a did
            # not emit, leaving 2c free to surface every aux variant.
            if code in covered_codes_from_bom:
                continue  # BOM already represents this code (with 3-tier rollup)
            if code in codes_with_prd_instock_emit:
                continue  # 2a already emitted; preserve old single-row behavior
            first = po_list[0]
            # Use PRD_MO qty as need_qty for synthetic rows (no BOM entry)
            mo_qty = sum(getattr(p, "qty", ZERO) for p in po_list)
            rows.append(_make_row(
                code=code, aux=aux,
                material_name=getattr(first, "material_name", ""),
                specification=getattr(first, "specification", ""),
                aux_attributes=getattr(first, "aux_attributes", ""),
                material_type=1,  # self-made (PRD_MO implies production)
                need_qty=mo_qty, picked_qty=ZERO, no_picked_qty=ZERO,
            ))
            covered_keys.add((code, aux))
            covered_codes_synthetic.add(code)

        # 2d: Material picks without any other source.
        # Self-made-flavored: shares covered_codes_synthetic with 2a/2c.
        pick_groups: dict[tuple[str, int], list] = defaultdict(list)
        for pick in material_picks:
            if pick.material_code.startswith("07."):
                continue
            aux = getattr(pick, "aux_prop_id", 0) or 0
            pick_groups[(pick.material_code, aux)].append(pick)

        for (code, aux), pick_list in pick_groups.items():
            if (code, aux) in covered_keys or code in covered_codes_synthetic:
                continue
            first = pick_list[0]
            # Conservative default — picking data with no other source, assume self-made
            m_type = 1
            rows.append(_make_row(
                code=code, aux=aux,
                material_name=getattr(first, "material_name", ""),
                specification=getattr(first, "specification", ""),
                aux_attributes="",
                material_type=m_type,
                need_qty=ZERO, picked_qty=ZERO, no_picked_qty=ZERO,
            ))
            covered_keys.add((code, aux))
            covered_codes_synthetic.add(code)

        return rows

    def _build_aggregated_sales_child(
        self,
        sales_orders: list,
        receipt_by_material: dict[tuple[str, int], Decimal],
        delivered_by_material: dict[tuple[str, int], Decimal],
        aux_descriptions: dict[int, str],
        purchase_receipt_by_material: dict[tuple[str, int], Decimal] | None = None,
    ) -> ChildItem:
        """Build aggregated ChildItem for 07.xx.xxx (成品) from multiple SAL_SaleOrder records.

        字段映射 (金蝶原始字段):
        - sales_order_qty: 销售订单.数量
        - prod_instock_real_qty: 生产入库单.实收数量 (PRD_INSTOCK)
        - purchase_stock_in_qty: 采购入库单.实收数量 (STK_InStock RKD01_SYS)
          — for 07.xx finished goods that arrive via inter-company / sister-plant
          purchase rather than in-house production. Wave 6B fix: prior to this,
          STK_InStock receipts for 07.xx were silently dropped because
          _build_aggregated_sales_child only consulted PRD_INSTOCK.
          Observed on DK251003S 07.02.151/154 where SAL had qty=242/583 but
          PRD_INSTOCK had zero rows; the receipt lived in STK_InStock RKD01.
        - bom_short_name: BOM简称
        """
        first = sales_orders[0]
        code = first.material_code
        aux_prop_id = getattr(first, "aux_prop_id", 0) or 0
        aux_attrs = aux_descriptions.get(aux_prop_id, "") or getattr(first, "aux_attributes", "")
        bom_short_name = getattr(first, "bom_short_name", "") or ""

        # 销售订单.数量
        sales_order_qty = sum(getattr(so, "qty", ZERO) for so in sales_orders)

        # 生产入库单.实收数量 — try exact (code, aux) first, then sum all aux variants
        # in case SAL_SaleOrder and PRD_INSTOCK have different aux_prop_id values
        prod_instock_real_qty = self._lookup_finished_receipt(
            receipt_by_material, code, aux_prop_id
        )

        # 采购入库单.实收数量 — same Tier 1 → Tier 3 rollup against the STK_InStock
        # receipts when the 07.xx item is bought-in (sister-plant transfer, OEM,
        # consignment) rather than produced in-house.
        purchase_stock_in_qty = self._lookup_finished_receipt(
            purchase_receipt_by_material or {}, code, aux_prop_id
        )

        return ChildItem(
            material_code=code,
            material_name=getattr(first, "material_name", ""),
            specification=getattr(first, "specification", ""),
            aux_attributes=aux_attrs,
            bom_short_name=bom_short_name,
            material_type=1,  # 成品
            material_type_name="成品",
            is_finished_goods=True,
            # 金蝶原始字段
            sales_order_qty=sales_order_qty,
            prod_instock_real_qty=prod_instock_real_qty,
            purchase_stock_in_qty=purchase_stock_in_qty,
        )

    @staticmethod
    def _lookup_finished_receipt(
        receipt_by_material: dict[tuple[str, int], Decimal],
        code: str,
        aux_prop_id: int,
    ) -> Decimal:
        """Receipt lookup for 07.xx finished goods.

        Tier 1: exact (code, aux) match.
        Tier 2 (aux_zero_fallback): SAL has aux≠0, receipt has aux=0.
        Tier 3 (all_aux_rollup): no exact / Tier 2 hit — sum across all aux for this code.

        Mirrors the BOM-row receipt fallback in `_get` (the live BOMJoinedRow
        builder) so finished goods get the same coverage as self-made / packaging
        components when SAL and receipt aux_prop_ids disagree.
        """
        key = (code, aux_prop_id)
        exact = receipt_by_material.get(key)
        if exact is not None:
            return exact
        # Tier 2: receipt at aux=0
        if aux_prop_id != 0:
            zero_fallback = receipt_by_material.get((code, 0))
            if zero_fallback is not None:
                return zero_fallback
        # Tier 3: sum across all aux for this code
        rollup = sum(
            (v for k, v in receipt_by_material.items() if k[0] == code),
            ZERO,
        )
        return rollup if rollup else ZERO

    def _bom_row_to_child(
        self,
        row: BOMJoinedRow,
        aux_descriptions: dict,
    ) -> ChildItem:
        """Convert a pre-joined BOM row into a ChildItem based on material_type.

        This is the single conversion method for all BOM children (cache path).
        Finished goods (07.xx) are handled separately via _build_aggregated_sales_child.

        Routing rules (trust FMaterialType from Kingdee PPBOM directly):
        - material_type=1 → 自制 (self-made)
        - material_type=2 → 包材 (purchased)
        - material_type=3 → 委外 (subcontracted)
        """
        aux_attrs = aux_descriptions.get(row.aux_prop_id, "") or row.aux_attributes

        # Trust FMaterialType from Kingdee PPBOM directly
        effective_type = row.material_type

        # Aux match quality flows through unchanged from the cache JOIN (or live builder).
        match_quality = dict(row.match_quality_breakdown or {})

        if effective_type == 1:  # 自制
            # Use BOM need_qty as demand — it's correctly scoped per production order.
            # Previously used prd_mo_qty_by_key which cross-aggregated across MTO variants.
            return ChildItem(
                material_code=row.material_code,
                material_name=row.material_name,
                specification=row.specification,
                aux_attributes=aux_attrs,
                material_type=MaterialType.SELF_MADE,
                material_type_name="自制",
                # REGRESSION GUARD (bug-patterns.md #10): MUST use row.need_qty here.
                # Two known inflation variants — both forbidden:
                #   (a) row.prod_receipt_must_qty — receipt FMustQty values overlap
                #       across batches and are NOT additive (fixed b8e6fc7,
                #       regressed 265303a, re-fixed 2026-03-30).
                #   (b) SUM(b.need_qty for b in PPBOM lines) — when the same
                #       self-made component appears in N parent BOMs within one
                #       MTO, summing yields N × actual production target. The
                #       upstream builder (_build_bom_joined_rows_from_live and
                #       cache_reader.get_mto_bom_joined) MUST resolve self-made
                #       need_qty against PRD_MO.FQty, not by summing PPBOM lines
                #       (introduced ce08d69, fixed 2026-04-26).
                prod_instock_must_qty=row.need_qty,
                prod_instock_real_qty=row.prod_receipt_real_qty,
                pick_actual_qty=row.pick_actual_qty,
                match_quality_breakdown=match_quality,
            )
        elif effective_type == 2:  # 外购/包材
            return ChildItem(
                material_code=row.material_code,
                material_name=row.material_name,
                specification=row.specification,
                aux_attributes=aux_attrs,
                material_type=MaterialType.PURCHASED,
                material_type_name="包材",
                purchase_order_qty=row.purchase_order_qty,
                purchase_stock_in_qty=row.purchase_stock_in_qty,
                pick_actual_qty=row.pick_actual_qty,
                match_quality_breakdown=match_quality,
            )
        elif effective_type == 3:  # 委外
            return ChildItem(
                material_code=row.material_code,
                material_name=row.material_name,
                specification=row.specification,
                aux_attributes=aux_attrs,
                material_type=MaterialType.SUBCONTRACTED,
                material_type_name="委外",
                purchase_order_qty=row.subcontract_order_qty,
                purchase_stock_in_qty=row.subcontract_stock_in_qty,
                pick_actual_qty=row.pick_actual_qty,
                match_quality_breakdown=match_quality,
            )
        else:
            # Unknown type — still show it with BOM demand data
            return ChildItem(
                material_code=row.material_code,
                material_name=row.material_name,
                specification=row.specification,
                aux_attributes=aux_attrs,
                material_type=effective_type,
                material_type_name="未知",
                # REGRESSION GUARD (bug-patterns.md #10): same as self-made above
                # — both inflation variants (receipt FMustQty sum, BOM-rollup sum)
                # are forbidden. Use row.need_qty.
                prod_instock_must_qty=row.need_qty,
                match_quality_breakdown=match_quality,
            )

    def _build_parent_from_sales(self, sales_order, mto_number: str) -> ParentItem:
        """Build ParentItem from sales order information."""
        if sales_order:
            return ParentItem(
                mto_number=mto_number,
                customer_name=getattr(sales_order, "customer_name", ""),
                delivery_date=getattr(sales_order, "delivery_date", None),
            )
        return ParentItem(
            mto_number=mto_number,
            customer_name="",
            delivery_date=None,
        )

    # -------------------------------------------------------------------------
    # Cache Management Methods
    # -------------------------------------------------------------------------

    def get_cache_stats(self) -> dict:
        """Get cache statistics for monitoring.

        Returns:
            dict with cache hit rates, sizes, and configuration
        """
        total_memory = self._memory_hits + self._memory_misses
        total_sqlite = self._sqlite_hits + self._sqlite_misses

        stats = {
            "memory_cache": {
                "enabled": self._memory_cache_enabled,
                "hits": self._memory_hits,
                "misses": self._memory_misses,
                "hit_rate": self._memory_hits / total_memory if total_memory > 0 else 0.0,
                "size": len(self._memory_cache) if self._memory_cache else 0,
                "max_size": self._memory_cache.maxsize if self._memory_cache else 0,
                "ttl_seconds": self._memory_cache.ttl if self._memory_cache else 0,
            },
            "sqlite_cache": {
                "enabled": self._cache_reader is not None,
                "hits": self._sqlite_hits,
                "misses": self._sqlite_misses,
                "hit_rate": self._sqlite_hits / total_sqlite if total_sqlite > 0 else 0.0,
            },
        }
        return stats

    async def clear_memory_cache(self) -> int:
        """Clear the in-memory cache.

        Call this after sync completes to ensure fresh data.

        Returns:
            Number of entries cleared
        """
        if self._memory_cache is None:
            return 0

        async with self._cache_lock:
            count = len(self._memory_cache)
            self._memory_cache.clear()
            logger.info("Cleared %d entries from memory cache", count)
            return count

    async def invalidate_mto(self, mto_number: str) -> bool:
        """Invalidate a specific MTO from memory cache.

        Args:
            mto_number: The MTO number to invalidate

        Returns:
            True if entry was found and removed, False otherwise
        """
        if self._memory_cache is None:
            return False

        async with self._cache_lock:
            if mto_number in self._memory_cache:
                del self._memory_cache[mto_number]
                logger.debug("Invalidated MTO %s from memory cache", mto_number)
                return True
            return False

    def reset_stats(self) -> None:
        """Reset cache statistics counters and query frequency tracker."""
        self._memory_hits = 0
        self._memory_misses = 0
        self._sqlite_hits = 0
        self._sqlite_misses = 0
        self._query_counter.clear()
        logger.info("Reset cache statistics")

    async def warm_cache(self, mto_numbers: list[str]) -> dict:
        """Pre-load MTOs into memory cache.

        Call this on startup or after sync to pre-populate the cache
        with frequently-accessed MTOs for faster first queries.

        Args:
            mto_numbers: List of MTO numbers to warm

        Returns:
            dict with warming statistics
        """
        if self._memory_cache is None:
            return {"status": "disabled", "warmed": 0, "failed": 0}

        warmed = 0
        failed = 0
        for mto in mto_numbers:
            try:
                await self.get_status(mto, use_cache=True)
                warmed += 1
            except Exception as exc:
                logger.debug("Cache warming failed for MTO %s: %s", mto, exc)
                failed += 1

        logger.info("Cache warming complete: %d warmed, %d failed", warmed, failed)
        return {"status": "success", "warmed": warmed, "failed": failed}

    def get_hot_mtos(self, top_n: int = 100) -> list[str]:
        """Return most frequently queried MTOs.

        Use this to get a list of MTOs for cache warming based on
        actual query patterns.

        Args:
            top_n: Number of top MTOs to return (default: 100)

        Returns:
            List of MTO numbers sorted by query frequency
        """
        sorted_mtos = sorted(self._query_counter.items(), key=lambda x: x[1], reverse=True)
        return [mto for mto, _ in sorted_mtos[:top_n]]

    def get_query_stats(self) -> dict:
        """Get query frequency statistics.

        Returns:
            dict with query pattern information
        """
        sorted_mtos = sorted(self._query_counter.items(), key=lambda x: x[1], reverse=True)
        return {
            "total_unique_mtos": len(self._query_counter),
            "total_queries": sum(self._query_counter.values()),
            "top_10_mtos": sorted_mtos[:10],
        }


def _sum_by_material(records, field: str) -> dict[str, Decimal]:
    """Sum a field by material_code."""
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r in records:
        code = getattr(r, "material_code", "")
        if code:
            totals[code] += getattr(r, field, ZERO)
    return totals


def _sum_by_material_and_aux(records, field: str) -> dict[tuple[str, int], Decimal]:
    """Sum a field by (material_code, aux_prop_id) for variant-aware matching.

    This ensures different variants (colors, sizes) of the same material
    are tracked separately.
    """
    totals: dict[tuple[str, int], Decimal] = defaultdict(lambda: ZERO)
    for r in records:
        code = getattr(r, "material_code", "")
        aux_prop_id = getattr(r, "aux_prop_id", 0) or 0
        if code:
            key = (code, aux_prop_id)
            totals[key] += getattr(r, field, ZERO)
    return totals
