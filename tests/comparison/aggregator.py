"""Aggregation logic for raw Kingdee data.

This module implements material-type-specific aggregation rules:
- 07.xx (成品): Group by (material_code, aux_prop_id)
- 05.xx (自制): Group by material_code only
- 03.xx (外购): Group by (material_code, aux_prop_id)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from tests.comparison.field_specs import MaterialType, get_material_type
from tests.comparison.raw_fetcher import RawMTOData, RawRecord


@dataclass
class AggregatedMaterial:
    """Aggregated quantities for a single material."""

    material_code: str
    aux_prop_id: int | None
    material_type: MaterialType | None

    # Source order quantities
    required_qty: Decimal = Decimal(0)  # 需求量
    order_qty: Decimal = Decimal(0)  # 订单数量 (same as required_qty)

    # Receipt quantities
    receipt_qty: Decimal = Decimal(0)  # 入库量
    stock_in_qty: Decimal = Decimal(0)  # For PO built-in (03.xx)
    remain_stock_in_qty: Decimal = Decimal(0)  # For PO built-in (03.xx)

    # Delivery/Picking quantities
    picked_qty: Decimal = Decimal(0)  # 已领量 (delivery or picking)
    app_qty: Decimal = Decimal(0)  # For PRD_PickMtrl (05.xx unpicked calc)
    actual_qty: Decimal = Decimal(0)  # For PRD_PickMtrl

    # Calculated fields
    @property
    def unpicked_qty(self) -> Decimal:
        """未领量 - calculated based on material type."""
        if self.material_type == MaterialType.SELF_MADE:
            # For 05.xx: FAppQty - FActualQty (can be negative = 超领)
            return self.app_qty - self.actual_qty
        else:
            # For 07.xx, 03.xx: required_qty - picked_qty
            return self.required_qty - self.picked_qty

    @property
    def unreceived_qty(self) -> Decimal:
        """未入库量 - calculated based on material type."""
        if self.material_type == MaterialType.PURCHASED:
            # For 03.xx: Use PO's built-in FRemainStockInQty
            return self.remain_stock_in_qty
        else:
            # For 07.xx, 05.xx: order_qty - receipt_qty
            return self.order_qty - self.receipt_qty

    @property
    def sales_outbound_qty(self) -> Decimal:
        """销售出库 - only for 07.xx (same as picked_qty)."""
        if self.material_type == MaterialType.FINISHED_GOODS:
            return self.picked_qty
        return Decimal(0)


@dataclass
class AggregatedData:
    """All aggregated data for one MTO."""

    mto: str
    materials: dict[tuple[str, int | None], AggregatedMaterial] = field(
        default_factory=dict
    )

    def get_material(
        self, material_code: str, aux_prop_id: int | None = None
    ) -> AggregatedMaterial | None:
        """Get aggregated material by code and aux_prop_id."""
        return self.materials.get((material_code, aux_prop_id))

    def all_materials(self) -> list[AggregatedMaterial]:
        """Get all aggregated materials."""
        return list(self.materials.values())


class RawDataAggregator:
    """Aggregates raw Kingdee data according to material type rules."""

    def aggregate(self, raw_data: RawMTOData) -> AggregatedData:
        """Aggregate all raw data into per-material totals."""
        result = AggregatedData(mto=raw_data.mto)

        # Process source orders (determines required_qty)
        self._aggregate_sales_orders(raw_data.sales_orders, result)
        self._aggregate_production_orders(raw_data.production_orders, result)
        self._aggregate_purchase_orders(raw_data.purchase_orders, result)

        # Process receipts (determines receipt_qty)
        self._aggregate_production_receipts(raw_data.production_receipts, result)

        # Process deliveries (determines picked_qty for 07.xx)
        self._aggregate_sales_deliveries(raw_data.sales_deliveries, result)

        # Process material pickings (determines picked_qty for 05.xx, 03.xx)
        self._aggregate_material_pickings(raw_data.material_pickings, result)

        return result

    def _get_or_create_material(
        self,
        result: AggregatedData,
        material_code: str,
        aux_prop_id: int | None,
    ) -> AggregatedMaterial:
        """Get or create an aggregated material entry."""
        material_type = get_material_type(material_code)

        # Determine grouping key based on material type
        if material_type == MaterialType.SELF_MADE:
            # 05.xx groups by material_code only
            key = (material_code, None)
        else:
            # 07.xx and 03.xx group by (material_code, aux_prop_id)
            key = (material_code, aux_prop_id)

        if key not in result.materials:
            result.materials[key] = AggregatedMaterial(
                material_code=material_code,
                aux_prop_id=key[1],
                material_type=material_type,
            )

        return result.materials[key]

    def _aggregate_sales_orders(
        self, records: list[RawRecord], result: AggregatedData
    ) -> None:
        """Aggregate SAL_SaleOrder records (07.xx required_qty)."""
        for rec in records:
            if not rec.material_code.startswith("07."):
                continue
            mat = self._get_or_create_material(
                result, rec.material_code, rec.aux_prop_id
            )
            mat.required_qty += rec.qty
            mat.order_qty += rec.qty

    def _aggregate_production_orders(
        self, records: list[RawRecord], result: AggregatedData
    ) -> None:
        """Aggregate PRD_MO records (05.xx required_qty)."""
        for rec in records:
            if not rec.material_code.startswith("05."):
                continue
            mat = self._get_or_create_material(
                result, rec.material_code, None  # No aux_prop_id for 05.xx
            )
            mat.required_qty += rec.qty
            mat.order_qty += rec.qty

    def _aggregate_purchase_orders(
        self, records: list[RawRecord], result: AggregatedData
    ) -> None:
        """Aggregate PUR_PurchaseOrder records (03.xx required_qty + built-in stock)."""
        for rec in records:
            if not rec.material_code.startswith("03."):
                continue
            mat = self._get_or_create_material(
                result, rec.material_code, rec.aux_prop_id
            )
            mat.required_qty += rec.qty
            mat.order_qty += rec.qty
            # Built-in cumulative fields
            if rec.stock_in_qty is not None:
                mat.stock_in_qty += rec.stock_in_qty
                mat.receipt_qty += rec.stock_in_qty  # Use stock_in_qty as receipt
            if rec.remain_stock_in_qty is not None:
                mat.remain_stock_in_qty += rec.remain_stock_in_qty

    def _aggregate_production_receipts(
        self, records: list[RawRecord], result: AggregatedData
    ) -> None:
        """Aggregate PRD_INSTOCK records (receipt_qty for 05.xx, 07.xx)."""
        for rec in records:
            material_type = get_material_type(rec.material_code)
            if material_type not in (MaterialType.FINISHED_GOODS, MaterialType.SELF_MADE):
                continue

            if material_type == MaterialType.SELF_MADE:
                aux_prop_id = None  # 05.xx doesn't use aux
            else:
                aux_prop_id = rec.aux_prop_id

            mat = self._get_or_create_material(result, rec.material_code, aux_prop_id)
            mat.receipt_qty += rec.qty

    def _aggregate_sales_deliveries(
        self, records: list[RawRecord], result: AggregatedData
    ) -> None:
        """Aggregate SAL_OUTSTOCK records (picked_qty for 07.xx)."""
        for rec in records:
            if not rec.material_code.startswith("07."):
                continue
            mat = self._get_or_create_material(
                result, rec.material_code, rec.aux_prop_id
            )
            mat.picked_qty += rec.qty

    def _aggregate_material_pickings(
        self, records: list[RawRecord], result: AggregatedData
    ) -> None:
        """Aggregate PRD_PickMtrl records (picked_qty for 05.xx, 03.xx)."""
        for rec in records:
            material_type = get_material_type(rec.material_code)
            if material_type not in (MaterialType.SELF_MADE, MaterialType.PURCHASED):
                continue

            # PRD_PickMtrl always groups by material_code only
            mat = self._get_or_create_material(result, rec.material_code, None)
            mat.picked_qty += rec.qty  # FActualQty
            if rec.app_qty is not None:
                mat.app_qty += rec.app_qty  # FAppQty
            mat.actual_qty += rec.qty  # For unpicked calc
