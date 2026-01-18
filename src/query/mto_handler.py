"""Handler for MTO status lookups."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from typing import Callable

from src.models.mto_status import ChildItem, MTOStatusResponse, ParentItem
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

ZERO = Decimal("0")


@dataclass
class _AggregatedBOMEntry:
    """Wrapper for aggregated BOM entry with summed quantities."""

    _base: object  # Original entry for metadata
    need_qty: Decimal
    picked_qty: Decimal
    no_picked_qty: Decimal

    @property
    def material_code(self) -> str:
        return self._base.material_code

    @property
    def material_name(self) -> str:
        return self._base.material_name

    @property
    def specification(self) -> str:
        return self._base.specification

    @property
    def aux_attributes(self) -> str:
        return self._base.aux_attributes

    @property
    def mto_number(self) -> str:
        return self._base.mto_number

    @property
    def material_type(self) -> int:
        return self._base.material_type

    @property
    def aux_prop_id(self) -> int:
        return self._base.aux_prop_id


class MaterialType(IntEnum):
    """Material type codes from Kingdee."""

    SELF_MADE = 1  # 自制
    PURCHASED = 2  # 外购
    SUBCONTRACTED = 3  # 委外

    @property
    def display_name(self) -> str:
        return {1: "自制", 2: "外购", 3: "委外"}.get(self.value, "未知")


@dataclass
class MaterialTypeData:
    """Aggregated quantity data for a material type."""

    order_qty: dict[str, Decimal]
    receipt_qty: dict[str, Decimal]
    remain_qty: dict[str, Decimal]
    receipt_source: str


class MTOQueryHandler:
    """Handler for MTO number lookups."""

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

    async def get_status(self, mto_number: str) -> MTOStatusResponse:
        prod_orders = await self._readers["production_order"].fetch_by_mto(mto_number)
        if not prod_orders:
            raise ValueError(f"No production orders found for MTO {mto_number}")

        raw_bom_entries = []
        for order in prod_orders:
            raw_bom_entries.extend(
                await self._readers["production_bom"].fetch_by_bill_no(order.bill_no)
            )

        # Aggregate BOM entries (self-made items only)
        bom_entries = self._aggregate_bom_entries(raw_bom_entries)

        # Fetch all data in parallel
        (
            prod_receipts,
            purchase_orders,
            purchase_receipts,
            subcontract_orders,
            material_picks,
            sales_deliveries,
            sales_orders,
        ) = await asyncio.gather(
            self._readers["production_receipt"].fetch_by_mto(mto_number),
            self._readers["purchase_order"].fetch_by_mto(mto_number),
            self._readers["purchase_receipt"].fetch_by_mto(mto_number),
            self._readers["subcontracting_order"].fetch_by_mto(mto_number),
            self._readers["material_picking"].fetch_by_mto(mto_number),
            self._readers["sales_delivery"].fetch_by_mto(mto_number),
            self._readers["sales_order"].fetch_by_mto(mto_number),
        )

        # Build material type lookup table (for self-made items receipt matching)
        type_data = self._build_material_type_data(
            prod_receipts, purchase_orders, purchase_receipts, subcontract_orders
        )

        # Build common aggregations
        pick_request = _sum_by_material(material_picks, "app_qty")
        pick_actual = _sum_by_material(material_picks, "actual_qty")
        delivered = _sum_by_material(sales_deliveries, "real_qty")

        # Collect aux_prop_ids for lookup
        aux_prop_ids = []
        for entry in raw_bom_entries:
            if hasattr(entry, "aux_prop_id") and entry.aux_prop_id:
                aux_prop_ids.append(entry.aux_prop_id)
        for po in purchase_orders:
            if hasattr(po, "aux_prop_id") and po.aux_prop_id:
                aux_prop_ids.append(po.aux_prop_id)

        # Lookup aux property descriptions from BD_FLEXSITEMDETAILV
        aux_descriptions = await self._client.lookup_aux_properties(aux_prop_ids)

        # Get sales order info (customer, delivery date)
        sales_order = sales_orders[0] if sales_orders else None
        parent = self._build_parent(prod_orders[0], sales_order)

        # Build children list:
        # 1. Self-made items from BOM
        children = [
            self._build_child(entry, type_data, pick_request, pick_actual, delivered, aux_descriptions)
            for entry in bom_entries
        ]

        # 2. Purchased items directly from purchase orders (not from BOM)
        purchased_children = self._build_purchased_children(
            purchase_orders, pick_request, pick_actual, delivered, aux_descriptions
        )
        children.extend(purchased_children)

        # 3. Subcontracted items directly from subcontracting orders (not from BOM)
        subcontract_children = self._build_subcontract_children(
            subcontract_orders, purchase_receipts, pick_request, pick_actual, delivered
        )
        children.extend(subcontract_children)

        return MTOStatusResponse(
            mto_number=mto_number,
            parent=parent,
            children=children,
            query_time=datetime.now(),
        )

    def _build_material_type_data(
        self, prod_receipts, purchase_orders, purchase_receipts, subcontract_orders
    ) -> dict[int, MaterialTypeData]:
        """Build lookup table for material type-specific quantities."""
        # Split purchase receipts by bill type
        purchase_only = [r for r in purchase_receipts if r.bill_type_number == "RKD01_SYS"]
        subcontract_only = [r for r in purchase_receipts if r.bill_type_number == "RKD02_SYS"]

        return {
            MaterialType.SELF_MADE: MaterialTypeData(
                order_qty={},  # Uses BOM need_qty directly
                receipt_qty=_sum_by_material(prod_receipts, "real_qty"),
                remain_qty={},
                receipt_source="PRD_INSTOCK",
            ),
            MaterialType.PURCHASED: MaterialTypeData(
                order_qty=_sum_by_material(purchase_orders, "order_qty"),
                receipt_qty=_sum_by_material(purchase_only, "real_qty"),
                remain_qty=_sum_by_material(purchase_orders, "remain_stock_in_qty"),
                receipt_source="STK_InStock(RKD01_SYS)",
            ),
            MaterialType.SUBCONTRACTED: MaterialTypeData(
                order_qty=_sum_by_material(subcontract_orders, "order_qty"),
                receipt_qty=_sum_by_material(subcontract_only, "real_qty"),
                remain_qty=_sum_by_material(subcontract_orders, "no_stock_in_qty"),
                receipt_source="STK_InStock(RKD02_SYS)",
            ),
        }

    def _build_parent(self, order, sales_order=None) -> ParentItem:
        return ParentItem(
            mto_number=order.mto_number,
            customer_name=sales_order.customer_name if sales_order else "",
            delivery_date=sales_order.delivery_date if sales_order else None,
        )

    def _aggregate_bom_entries(self, entries: list) -> list:
        """Aggregate BOM entries by (material_code, aux_attributes, mto_number).

        Business rule: The unique identifier for a BOM item is the combination of:
        - 物料编码 (material_code)
        - 辅助属性 (aux_attributes) - e.g., color, size variants
        - 计划跟踪号 (mto_number)

        Same material_code with different aux_attributes (e.g., "蓝色款" vs "红色款")
        are different SKUs and should NOT be merged.
        """
        if not entries:
            return []

        aggregated: dict[tuple[str, str, str], dict] = {}
        for entry in entries:
            # Use (material_code, aux_attributes, mto_number) as composite key
            key = (entry.material_code, entry.aux_attributes, entry.mto_number)
            if key not in aggregated:
                # First occurrence - store the entry data
                aggregated[key] = {
                    "entry": entry,
                    "need_qty": entry.need_qty,
                    "picked_qty": entry.picked_qty,
                    "no_picked_qty": entry.no_picked_qty,
                }
            else:
                # Subsequent occurrences - accumulate quantities
                aggregated[key]["need_qty"] += entry.need_qty
                aggregated[key]["picked_qty"] += entry.picked_qty
                aggregated[key]["no_picked_qty"] += entry.no_picked_qty
                # Keep the latest entry for other fields
                aggregated[key]["entry"] = entry

        # Convert back to entry-like objects with aggregated quantities
        return [
            _AggregatedBOMEntry(
                data["entry"],
                data["need_qty"],
                data["picked_qty"],
                data["no_picked_qty"],
            )
            for data in aggregated.values()
        ]

    def _build_purchased_children(
        self, purchase_orders, pick_request, pick_actual, delivered, aux_descriptions: dict[int, str]
    ) -> list[ChildItem]:
        """Build ChildItem list from purchase orders (外购件).

        Business rule: Purchased items come directly from PUR_PurchaseOrder,
        not from BOM. They are linked by MTO number.
        """
        # Aggregate by (material_code, aux_prop_id, mto_number) to avoid duplicates
        # Note: aux_prop_id distinguishes different variants of the same material
        aggregated: dict[tuple[str, int, str], dict] = {}
        for po in purchase_orders:
            aux_prop_id = getattr(po, "aux_prop_id", 0) or 0
            key = (po.material_code, aux_prop_id, po.mto_number)
            if key not in aggregated:
                aggregated[key] = {
                    "po": po,
                    "aux_prop_id": aux_prop_id,
                    "order_qty": po.order_qty,
                    "stock_in_qty": po.stock_in_qty,
                    "remain_qty": po.remain_stock_in_qty,
                }
            else:
                aggregated[key]["order_qty"] += po.order_qty
                aggregated[key]["stock_in_qty"] += po.stock_in_qty
                aggregated[key]["remain_qty"] += po.remain_stock_in_qty
                aggregated[key]["po"] = po  # Keep latest for metadata

        children = []
        for data in aggregated.values():
            po = data["po"]
            code = po.material_code
            aux_prop_id = data["aux_prop_id"]
            # Get aux_attributes from lookup, fallback to model's aux_attributes
            aux_attrs = aux_descriptions.get(aux_prop_id, "") or po.aux_attributes
            children.append(ChildItem(
                material_code=code,
                material_name=po.material_name,
                specification=po.specification,
                aux_attributes=aux_attrs,
                material_type=MaterialType.PURCHASED,
                material_type_name="外购",
                required_qty=data["order_qty"],  # For purchased, required = order qty
                picked_qty=ZERO,  # Not applicable for purchased items
                unpicked_qty=ZERO,
                order_qty=data["order_qty"],
                receipt_qty=data["stock_in_qty"],
                unreceived_qty=data["remain_qty"],
                pick_request_qty=pick_request.get(code, ZERO),
                pick_actual_qty=pick_actual.get(code, ZERO),
                delivered_qty=delivered.get(code, ZERO),
                inventory_qty=ZERO,
                receipt_source="PUR_PurchaseOrder",
            ))
        return children

    def _build_subcontract_children(
        self, subcontract_orders, purchase_receipts, pick_request, pick_actual, delivered
    ) -> list[ChildItem]:
        """Build ChildItem list from subcontracting orders (委外件).

        Business rule: Subcontracted items come directly from subcontracting orders,
        not from BOM. They are linked by MTO number.
        """
        # Filter subcontracting receipts
        subcontract_receipts = [r for r in purchase_receipts if r.bill_type_number == "RKD02_SYS"]
        receipt_by_material = _sum_by_material(subcontract_receipts, "real_qty")

        # Aggregate by (material_code, mto_number)
        aggregated: dict[tuple[str, str], dict] = {}
        for so in subcontract_orders:
            key = (so.material_code, so.mto_number)
            if key not in aggregated:
                aggregated[key] = {
                    "so": so,
                    "order_qty": so.order_qty,
                    "stock_in_qty": so.stock_in_qty,
                    "no_stock_in_qty": so.no_stock_in_qty,
                }
            else:
                aggregated[key]["order_qty"] += so.order_qty
                aggregated[key]["stock_in_qty"] += so.stock_in_qty
                aggregated[key]["no_stock_in_qty"] += so.no_stock_in_qty
                aggregated[key]["so"] = so

        children = []
        for data in aggregated.values():
            so = data["so"]
            code = so.material_code
            children.append(ChildItem(
                material_code=code,
                material_name="",  # SubcontractingOrderModel doesn't have name
                specification="",
                aux_attributes="",
                material_type=MaterialType.SUBCONTRACTED,
                material_type_name="委外",
                required_qty=data["order_qty"],
                picked_qty=ZERO,
                unpicked_qty=ZERO,
                order_qty=data["order_qty"],
                receipt_qty=receipt_by_material.get(code, data["stock_in_qty"]),
                unreceived_qty=data["no_stock_in_qty"],
                pick_request_qty=pick_request.get(code, ZERO),
                pick_actual_qty=pick_actual.get(code, ZERO),
                delivered_qty=delivered.get(code, ZERO),
                inventory_qty=ZERO,
                receipt_source="SUB_POORDER",
            ))
        return children

    def _build_child(
        self, entry, type_data: dict[int, MaterialTypeData], pick_request, pick_actual, delivered,
        aux_descriptions: dict[int, str]
    ) -> ChildItem:
        code = entry.material_code
        mat_type = entry.material_type
        data = type_data.get(mat_type)

        if data:
            # Self-made uses BOM need_qty as order_qty
            order_qty = entry.need_qty if mat_type == MaterialType.SELF_MADE else data.order_qty.get(code, ZERO)
            receipt_qty = data.receipt_qty.get(code, ZERO)
            unreceived = data.remain_qty.get(code, order_qty - receipt_qty)
            source = data.receipt_source
        else:
            order_qty = receipt_qty = unreceived = ZERO
            source = ""

        # Get aux_attributes from lookup, fallback to entry's aux_attributes
        aux_prop_id = getattr(entry, "aux_prop_id", 0) or 0
        aux_attrs = aux_descriptions.get(aux_prop_id, "") or entry.aux_attributes

        return ChildItem(
            material_code=code,
            material_name=entry.material_name,
            specification=entry.specification,
            aux_attributes=aux_attrs,
            material_type=mat_type,
            material_type_name=MaterialType(mat_type).display_name if mat_type in (1, 2, 3) else "未知",
            required_qty=entry.need_qty,
            picked_qty=entry.picked_qty,
            unpicked_qty=entry.no_picked_qty,
            order_qty=order_qty,
            receipt_qty=receipt_qty,
            unreceived_qty=unreceived,
            pick_request_qty=pick_request.get(code, ZERO),
            pick_actual_qty=pick_actual.get(code, ZERO),
            delivered_qty=delivered.get(code, ZERO),
            inventory_qty=ZERO,
            receipt_source=source,
        )


def _sum_by_material(records, field: str) -> dict[str, Decimal]:
    """Sum a field by material_code."""
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r in records:
        code = getattr(r, "material_code", "")
        if code:
            totals[code] += getattr(r, field)
    return totals
