"""Handler for MTO status lookups with config-driven material class logic."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum
from threading import Lock
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

ZERO = Decimal("0")


class MaterialType(IntEnum):
    """Material type codes from Kingdee."""

    SELF_MADE = 1  # 自制
    PURCHASED = 2  # 外购
    SUBCONTRACTED = 3  # 委外

    @property
    def display_name(self) -> str:
        return {1: "自制", 2: "外购", 3: "委外"}.get(self.value, "未知")


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

        # L2: SQLite cache reader
        self._cache_reader = cache_reader

        # L1: In-memory TTLCache for sub-10ms responses
        self._memory_cache_enabled = memory_cache_enabled
        if memory_cache_enabled:
            self._memory_cache: TTLCache = TTLCache(
                maxsize=memory_cache_size, ttl=memory_cache_ttl
            )
            self._cache_lock = Lock()
        else:
            self._memory_cache = None
            self._cache_lock = None

        # Cache statistics
        self._memory_hits = 0
        self._memory_misses = 0
        self._sqlite_hits = 0
        self._sqlite_misses = 0

        # Query frequency tracking for smart cache warming
        self._query_counter: Counter = Counter()

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
        self, mto_number: str, use_cache: bool = True
    ) -> MTOStatusResponse:
        """Get MTO status with three-tier cache strategy.

        Args:
            mto_number: The MTO number to query
            use_cache: If True, try caches before live API (default: True)

        Returns:
            MTOStatusResponse with data_source metadata

        Cache tiers checked in order:
        1. L1 (Memory): ~1-5ms - TTLCache for hot queries
        2. L2 (SQLite): ~100ms - Persistent cache
        3. L3 (Kingdee): ~1-5s - Live API
        """
        # Track query frequency for smart cache warming
        self._query_counter[mto_number] += 1

        # L1: Check in-memory cache first (sub-10ms response)
        if use_cache and self._memory_cache is not None:
            with self._cache_lock:
                if mto_number in self._memory_cache:
                    self._memory_hits += 1
                    logger.debug("L1 memory cache hit for MTO %s", mto_number)
                    return self._memory_cache[mto_number]
                self._memory_misses += 1

        # L2: Try SQLite cache if enabled and cache reader available
        result = None
        if use_cache and self._cache_reader:
            result = await self._try_cache(mto_number)
            if result:
                self._sqlite_hits += 1
                logger.debug("L2 SQLite cache hit for MTO %s", mto_number)
            else:
                self._sqlite_misses += 1

        # L3: Fallback to live Kingdee API
        if not result:
            result = await self._fetch_live(mto_number)

        # Populate L1 cache with result
        if use_cache and self._memory_cache is not None and result:
            with self._cache_lock:
                self._memory_cache[mto_number] = result

        return result

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
            query_time=datetime.now(),
            data_source="live",
        )

    async def _try_cache(self, mto_number: str) -> Optional[MTOStatusResponse]:
        """Attempt to build response from cache.

        Uses config-driven logic to build children from cached data.
        Returns None if critical data is missing or stale.
        """
        # Fetch all cache data in parallel
        (
            sales_orders_result,
            prod_orders_result,
            purchase_orders_result,
            prod_receipts_result,
            purchase_receipts_result,
            material_picks_result,
            sales_delivery_result,
        ) = await asyncio.gather(
            self._cache_reader.get_sales_orders(mto_number),
            self._cache_reader.get_production_orders(mto_number),
            self._cache_reader.get_purchase_orders(mto_number),
            self._cache_reader.get_production_receipts(mto_number),
            self._cache_reader.get_purchase_receipts(mto_number),
            self._cache_reader.get_material_picking(mto_number),
            self._cache_reader.get_sales_delivery(mto_number),
        )

        # Need at least one source form to have data
        has_data = (
            sales_orders_result.data
            or prod_orders_result.data
            or purchase_orders_result.data
        )
        if not has_data:
            return None

        # Extract data from cache results
        sales_orders = sales_orders_result.data or []
        prod_orders = prod_orders_result.data or []
        purchase_orders = purchase_orders_result.data or []
        prod_receipts = prod_receipts_result.data or []
        purchase_receipts = purchase_receipts_result.data or []
        material_picks = material_picks_result.data or []
        sales_deliveries = sales_delivery_result.data or []

        # Build aggregation lookups
        pick_request = _sum_by_material(material_picks, "app_qty")
        pick_actual = _sum_by_material(material_picks, "actual_qty")
        delivered_by_material = _sum_by_material_and_aux(sales_deliveries, "real_qty")
        receipt_by_material = _sum_by_material_and_aux(prod_receipts, "real_qty")

        # For cache, aux_attributes are already resolved
        aux_descriptions: dict[int, str] = {}

        # Build children from source forms based on material class config
        children = []
        unmatched_materials = []

        # Route records based on config patterns
        # finished_goods (07.xx) from Sales Orders
        for so in sales_orders:
            class_id, _ = self._get_material_class(so.material_code)
            if class_id == "finished_goods":
                child = self._build_sales_child(
                    so, receipt_by_material, delivered_by_material,
                    pick_request, pick_actual, aux_descriptions
                )
                children.append(child)
            elif class_id is None:
                unmatched_materials.append(("SAL_SaleOrder", so.material_code))

        # self_made (05.xx) from Production Orders
        for po in prod_orders:
            class_id, _ = self._get_material_class(po.material_code)
            if class_id == "self_made":
                child = self._build_production_child(
                    po, prod_receipts, material_picks, aux_descriptions
                )
                children.append(child)
            elif class_id is None:
                unmatched_materials.append(("PRD_MO", po.material_code))

        # purchased (03.xx) from Purchase Orders
        for pur in purchase_orders:
            class_id, _ = self._get_material_class(pur.material_code)
            if class_id == "purchased":
                child = self._build_purchase_child(
                    pur, pick_request, pick_actual, aux_descriptions
                )
                children.append(child)
            elif class_id is None:
                unmatched_materials.append(("PUR_PurchaseOrder", pur.material_code))

        # Log warning for unmatched materials
        if unmatched_materials:
            logger.warning(
                "MTO %s (cache): %d materials skipped (no matching config pattern): %s",
                mto_number, len(unmatched_materials),
                ", ".join(f"{src}:{code}" for src, code in unmatched_materials[:5])
                + ("..." if len(unmatched_materials) > 5 else "")
            )

        # Build parent from first available sales order
        parent = self._build_parent_from_sales(sales_orders[0] if sales_orders else None, mto_number)

        # Calculate cache age
        cache_age = None
        for result in [sales_orders_result, prod_orders_result, purchase_orders_result]:
            if result.synced_at:
                cache_age = int((datetime.now(timezone.utc) - result.synced_at).total_seconds())
                break

        return MTOStatusResponse(
            mto_number=mto_number,
            parent=parent,
            children=children,
            query_time=datetime.now(),
            data_source="cache",
            cache_age_seconds=cache_age,
        )

    async def _fetch_live(self, mto_number: str) -> MTOStatusResponse:
        """Fetch data from live Kingdee API using config-driven logic.

        Queries source forms directly based on material code class:
        - 07.xx.xxx → SAL_SaleOrder
        - 05.xx.xxx → PRD_MO
        - 03.xx.xxx → PUR_PurchaseOrder

        Each record from source form becomes a separate row (no aggregation).
        """
        # Fetch all source forms and receipt data in parallel
        (
            sales_orders,
            prod_orders,
            purchase_orders,
            prod_receipts,
            purchase_receipts,
            material_picks,
            sales_deliveries,
        ) = await asyncio.gather(
            self._readers["sales_order"].fetch_by_mto(mto_number),
            self._readers["production_order"].fetch_by_mto(mto_number),
            self._readers["purchase_order"].fetch_by_mto(mto_number),
            self._readers["production_receipt"].fetch_by_mto(mto_number),
            self._readers["purchase_receipt"].fetch_by_mto(mto_number),
            self._readers["material_picking"].fetch_by_mto(mto_number),
            self._readers["sales_delivery"].fetch_by_mto(mto_number),
        )

        # Build aggregation lookups for receipts/deliveries
        # Key: (material_code, aux_prop_id) for variant-aware matching
        delivered_by_material = _sum_by_material_and_aux(sales_deliveries, "real_qty")
        receipt_by_material = _sum_by_material_and_aux(prod_receipts, "real_qty")
        pick_request = _sum_by_material(material_picks, "app_qty")
        pick_actual = _sum_by_material(material_picks, "actual_qty")

        # Collect aux_prop_ids for lookup
        aux_prop_ids = set()
        for so in sales_orders:
            if hasattr(so, "aux_prop_id") and so.aux_prop_id:
                aux_prop_ids.add(so.aux_prop_id)
        for pur in purchase_orders:
            if hasattr(pur, "aux_prop_id") and pur.aux_prop_id:
                aux_prop_ids.add(pur.aux_prop_id)
        for pr in prod_receipts:
            if hasattr(pr, "aux_prop_id") and pr.aux_prop_id:
                aux_prop_ids.add(pr.aux_prop_id)
        for sd in sales_deliveries:
            if hasattr(sd, "aux_prop_id") and sd.aux_prop_id:
                aux_prop_ids.add(sd.aux_prop_id)

        # Lookup aux property descriptions from BD_FLEXSITEMDETAILV
        aux_descriptions = await self._client.lookup_aux_properties(list(aux_prop_ids))

        # Build children from source forms based on material class config
        children = []
        unmatched_materials = []

        # Route records based on config patterns
        # finished_goods (07.xx) from Sales Orders
        for so in sales_orders:
            class_id, _ = self._get_material_class(so.material_code)
            if class_id == "finished_goods":
                child = self._build_sales_child(
                    so, receipt_by_material, delivered_by_material,
                    pick_request, pick_actual, aux_descriptions
                )
                children.append(child)
            elif class_id is None:
                unmatched_materials.append(("SAL_SaleOrder", so.material_code))

        # self_made (05.xx) from Production Orders
        for po in prod_orders:
            class_id, _ = self._get_material_class(po.material_code)
            if class_id == "self_made":
                child = self._build_production_child(
                    po, prod_receipts, material_picks, aux_descriptions
                )
                children.append(child)
            elif class_id is None:
                unmatched_materials.append(("PRD_MO", po.material_code))

        # purchased (03.xx) from Purchase Orders
        for pur in purchase_orders:
            class_id, _ = self._get_material_class(pur.material_code)
            if class_id == "purchased":
                child = self._build_purchase_child(
                    pur, pick_request, pick_actual, aux_descriptions
                )
                children.append(child)
            elif class_id is None:
                unmatched_materials.append(("PUR_PurchaseOrder", pur.material_code))

        # Log warning for unmatched materials
        if unmatched_materials:
            logger.warning(
                "MTO %s (live): %d materials skipped (no matching config pattern): %s",
                mto_number, len(unmatched_materials),
                ", ".join(f"{src}:{code}" for src, code in unmatched_materials[:5])
                + ("..." if len(unmatched_materials) > 5 else "")
            )

        # Build parent from first available sales order
        parent = self._build_parent_from_sales(sales_orders[0] if sales_orders else None, mto_number)

        # Check if we have any data
        if not children and not sales_orders and not prod_orders and not purchase_orders:
            raise ValueError(f"No data found for MTO {mto_number}")

        return MTOStatusResponse(
            mto_number=mto_number,
            parent=parent,
            children=children,
            query_time=datetime.now(),
            data_source="live",
        )

    def _build_sales_child(
        self,
        sales_order,
        receipt_by_material: dict[tuple[str, int], Decimal],
        delivered_by_material: dict[tuple[str, int], Decimal],
        pick_request: dict[str, Decimal],
        pick_actual: dict[str, Decimal],
        aux_descriptions: dict[int, str],
    ) -> ChildItem:
        """Build ChildItem for 07.xx.xxx (成品) from SAL_SaleOrder.

        Column mappings (from config):
        - 需求量 (required_qty): SAL_SaleOrder.qty (销售数量)
        - 已领量 (picked_qty): SAL_OUTSTOCK.real_qty (实发数量)
        - 未领量 (unpicked_qty): 需求量 - 已领量
        - 订单数量 (order_qty): = 需求量
        - 入库量 (receipt_qty): PRD_INSTOCK.real_qty (实收数量)
        - 未入库量 (unreceived_qty): 订单数量 - 入库量
        """
        code = sales_order.material_code
        aux_prop_id = getattr(sales_order, "aux_prop_id", 0) or 0
        aux_attrs = aux_descriptions.get(aux_prop_id, "") or getattr(sales_order, "aux_attributes", "")

        # Get quantities using (material_code, aux_prop_id) as key
        key = (code, aux_prop_id)
        required_qty = sales_order.qty
        picked_qty = delivered_by_material.get(key, ZERO)
        receipt_qty = receipt_by_material.get(key, ZERO)

        return ChildItem(
            material_code=code,
            material_name=getattr(sales_order, "material_name", ""),
            specification=getattr(sales_order, "specification", ""),
            aux_attributes=aux_attrs,
            material_type=1,  # 成品 treated as 自制
            material_type_name="成品",
            required_qty=required_qty,
            picked_qty=picked_qty,  # 已领量 = 出库量 for finished goods
            unpicked_qty=required_qty - picked_qty,
            order_qty=required_qty,
            receipt_qty=receipt_qty,
            unreceived_qty=required_qty - receipt_qty,
            pick_request_qty=ZERO,  # Not applicable for finished goods
            pick_actual_qty=ZERO,
            delivered_qty=picked_qty,
            inventory_qty=ZERO,
            receipt_source="PRD_INSTOCK",
        )

    def _build_production_child(
        self,
        prod_order,
        prod_receipts: list,
        material_picks: list,
        aux_descriptions: dict[int, str],
    ) -> ChildItem:
        """Build ChildItem for 05.xx.xxx (自制) from PRD_MO.

        Column mappings (from config):
        - 需求量 (required_qty): PRD_MO.qty
        - 已领量 (picked_qty): PRD_PickMtrl.actual_qty
        - 未领量 (unpicked_qty): PRD_PickMtrl.app_qty - actual_qty
        - 订单数量 (order_qty): = 需求量
        - 入库量 (receipt_qty): PRD_INSTOCK.real_qty
        - 未入库量 (unreceived_qty): 订单数量 - 入库量
        """
        code = prod_order.material_code
        aux_prop_id = 0  # Production orders typically don't have aux_prop_id
        aux_attrs = getattr(prod_order, "aux_attributes", "")

        required_qty = prod_order.qty

        # Match receipts by material_code
        receipt_qty = sum(
            r.real_qty for r in prod_receipts
            if r.material_code == code
        )

        # Match material picks by material_code
        pick_actual_total = sum(
            p.actual_qty for p in material_picks
            if p.material_code == code
        )
        pick_app_total = sum(
            p.app_qty for p in material_picks
            if p.material_code == code
        )

        return ChildItem(
            material_code=code,
            material_name=getattr(prod_order, "material_name", ""),
            specification=getattr(prod_order, "specification", ""),
            aux_attributes=aux_attrs,
            material_type=MaterialType.SELF_MADE,
            material_type_name="自制",
            required_qty=required_qty,
            picked_qty=pick_actual_total,
            unpicked_qty=pick_app_total - pick_actual_total,  # 允许负值以检测超领
            order_qty=required_qty,
            receipt_qty=receipt_qty,
            unreceived_qty=required_qty - receipt_qty,
            pick_request_qty=pick_app_total,
            pick_actual_qty=pick_actual_total,
            delivered_qty=ZERO,
            inventory_qty=ZERO,
            receipt_source="PRD_INSTOCK",
        )

    def _build_purchase_child(
        self,
        purchase_order,
        pick_request: dict[str, Decimal],
        pick_actual: dict[str, Decimal],
        aux_descriptions: dict[int, str],
    ) -> ChildItem:
        """Build ChildItem for 03.xx.xxx (外购) from PUR_PurchaseOrder.

        Column mappings (from config):
        - 需求量 (required_qty): PUR_PurchaseOrder.order_qty (采购数量)
        - 已领量 (picked_qty): PRD_PickMtrl.actual_qty
        - 未领量 (unpicked_qty): 需求量 - 已领量
        - 订单数量 (order_qty): = 需求量
        - 入库量 (receipt_qty): PUR_PurchaseOrder.stock_in_qty (累计入库数量)
        - 未入库量 (unreceived_qty): PUR_PurchaseOrder.remain_stock_in_qty (剩余入库数量)
        """
        code = purchase_order.material_code
        aux_prop_id = getattr(purchase_order, "aux_prop_id", 0) or 0
        aux_attrs = aux_descriptions.get(aux_prop_id, "") or getattr(purchase_order, "aux_attributes", "")

        required_qty = purchase_order.order_qty
        picked_qty = pick_actual.get(code, ZERO)

        return ChildItem(
            material_code=code,
            material_name=getattr(purchase_order, "material_name", ""),
            specification=getattr(purchase_order, "specification", ""),
            aux_attributes=aux_attrs,
            material_type=MaterialType.PURCHASED,
            material_type_name="外购",
            required_qty=required_qty,
            picked_qty=picked_qty,
            unpicked_qty=required_qty - picked_qty,  # 允许负值以检测超领
            order_qty=required_qty,
            receipt_qty=purchase_order.stock_in_qty,
            unreceived_qty=purchase_order.remain_stock_in_qty,
            pick_request_qty=pick_request.get(code, ZERO),
            pick_actual_qty=picked_qty,
            delivered_qty=ZERO,
            inventory_qty=ZERO,
            receipt_source="PUR_PurchaseOrder",
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

    def clear_memory_cache(self) -> int:
        """Clear the in-memory cache.

        Call this after sync completes to ensure fresh data.

        Returns:
            Number of entries cleared
        """
        if self._memory_cache is None:
            return 0

        with self._cache_lock:
            count = len(self._memory_cache)
            self._memory_cache.clear()
            logger.info("Cleared %d entries from memory cache", count)
            return count

    def invalidate_mto(self, mto_number: str) -> bool:
        """Invalidate a specific MTO from memory cache.

        Args:
            mto_number: The MTO number to invalidate

        Returns:
            True if entry was found and removed, False otherwise
        """
        if self._memory_cache is None:
            return False

        with self._cache_lock:
            if mto_number in self._memory_cache:
                del self._memory_cache[mto_number]
                logger.debug("Invalidated MTO %s from memory cache", mto_number)
                return True
            return False

    def reset_stats(self) -> None:
        """Reset cache statistics counters."""
        self._memory_hits = 0
        self._memory_misses = 0
        self._sqlite_hits = 0
        self._sqlite_misses = 0
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
        return [mto for mto, _ in self._query_counter.most_common(top_n)]

    def get_query_stats(self) -> dict:
        """Get query frequency statistics.

        Returns:
            dict with query pattern information
        """
        return {
            "total_unique_mtos": len(self._query_counter),
            "total_queries": sum(self._query_counter.values()),
            "top_10_mtos": self._query_counter.most_common(10),
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
