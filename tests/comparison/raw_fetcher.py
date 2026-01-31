"""Raw Kingdee data fetcher for validation.

This module fetches data directly from Kingdee API (bypassing QuickPulse readers)
to enable comparison against QuickPulse aggregated output.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, List, Optional

from src.kingdee.client import KingdeeClient


@dataclass
class RawRecord:
    """A raw record from Kingdee with essential fields."""

    form_id: str
    bill_no: str
    material_code: str
    aux_prop_id: int | None
    qty: Decimal
    # Optional fields for specific forms
    app_qty: Decimal | None = None  # For PRD_PickMtrl
    stock_in_qty: Decimal | None = None  # For PUR_PurchaseOrder
    remain_stock_in_qty: Decimal | None = None  # For PUR_PurchaseOrder


@dataclass
class RawMTOData:
    """All raw Kingdee data for one MTO."""

    mto: str
    sales_orders: list[RawRecord]  # SAL_SaleOrder
    production_orders: list[RawRecord]  # PRD_MO
    purchase_orders: list[RawRecord]  # PUR_PurchaseOrder
    production_receipts: list[RawRecord]  # PRD_INSTOCK
    sales_deliveries: list[RawRecord]  # SAL_OUTSTOCK
    material_pickings: list[RawRecord]  # PRD_PickMtrl


class RawKingdeeFetcher:
    """Fetches raw data directly from Kingdee API."""

    def __init__(self, client: KingdeeClient):
        self.client = client

    async def fetch_all(self, mto: str) -> RawMTOData:
        """Fetch all raw data for an MTO from Kingdee."""
        # Fetch all data sources in parallel
        import asyncio

        (
            sales_orders,
            production_orders,
            purchase_orders,
            production_receipts,
            sales_deliveries,
            material_pickings,
        ) = await asyncio.gather(
            self._fetch_sales_orders(mto),
            self._fetch_production_orders(mto),
            self._fetch_purchase_orders(mto),
            self._fetch_production_receipts(mto),
            self._fetch_sales_deliveries(mto),
            self._fetch_material_pickings(mto),
        )

        return RawMTOData(
            mto=mto,
            sales_orders=sales_orders,
            production_orders=production_orders,
            purchase_orders=purchase_orders,
            production_receipts=production_receipts,
            sales_deliveries=sales_deliveries,
            material_pickings=material_pickings,
        )

    async def _fetch_sales_orders(self, mto: str) -> list[RawRecord]:
        """Fetch SAL_SaleOrder entries for MTO (07.xx finished goods)."""
        try:
            result = await self.client.query(
                form_id="SAL_SaleOrder",
                field_keys=[
                    "FBillNo",
                    "FMaterialId.FNumber",
                    "FAuxPropId",
                    "FQty",
                ],
                filter_string=f"FMtoNo='{mto}'",
                limit=1000,
            )
            return [
                RawRecord(
                    form_id="SAL_SaleOrder",
                    bill_no=str(row.get("FBillNo", "")),
                    material_code=str(row.get("FMaterialId.FNumber", "")),
                    aux_prop_id=self._parse_int(row.get("FAuxPropId")),
                    qty=self._parse_decimal(row.get("FQty")),
                )
                for row in result
            ]
        except Exception:
            return []

    async def _fetch_production_orders(self, mto: str) -> list[RawRecord]:
        """Fetch PRD_MO entries for MTO (05.xx self-made items)."""
        try:
            result = await self.client.query(
                form_id="PRD_MO",
                field_keys=[
                    "FBillNo",
                    "FMaterialId.FNumber",
                    "FQty",
                ],
                filter_string=f"FMTONo='{mto}'",
                limit=1000,
            )
            return [
                RawRecord(
                    form_id="PRD_MO",
                    bill_no=str(row.get("FBillNo", "")),
                    material_code=str(row.get("FMaterialId.FNumber", "")),
                    aux_prop_id=None,  # PRD_MO doesn't use aux_prop_id for grouping
                    qty=self._parse_decimal(row.get("FQty")),
                )
                for row in result
            ]
        except Exception:
            return []

    async def _fetch_purchase_orders(self, mto: str) -> list[RawRecord]:
        """Fetch PUR_PurchaseOrder entries for MTO (03.xx purchased items)."""
        try:
            result = await self.client.query(
                form_id="PUR_PurchaseOrder",
                field_keys=[
                    "FBillNo",
                    "FMaterialId.FNumber",
                    "FAuxPropId",
                    "FQty",
                    "FStockInQty",
                    "FRemainStockInQty",
                ],
                filter_string=f"FMtoNo='{mto}'",
                limit=1000,
            )
            return [
                RawRecord(
                    form_id="PUR_PurchaseOrder",
                    bill_no=str(row.get("FBillNo", "")),
                    material_code=str(row.get("FMaterialId.FNumber", "")),
                    aux_prop_id=self._parse_int(row.get("FAuxPropId")),
                    qty=self._parse_decimal(row.get("FQty")),
                    stock_in_qty=self._parse_decimal(row.get("FStockInQty")),
                    remain_stock_in_qty=self._parse_decimal(row.get("FRemainStockInQty")),
                )
                for row in result
            ]
        except Exception:
            return []

    async def _fetch_production_receipts(self, mto: str) -> list[RawRecord]:
        """Fetch PRD_INSTOCK entries for MTO (production receipts)."""
        try:
            # Match QuickPulse filter: include confirmed/completed docs (C, D)
            result = await self.client.query(
                form_id="PRD_INSTOCK",
                field_keys=[
                    "FBillNo",
                    "FMaterialId.FNumber",
                    "FAuxPropId",
                    "FRealQty",
                ],
                filter_string=f"FMtoNo='{mto}' AND FDocumentStatus IN ('C', 'D')",
                limit=1000,
            )
            return [
                RawRecord(
                    form_id="PRD_INSTOCK",
                    bill_no=str(row.get("FBillNo", "")),
                    material_code=str(row.get("FMaterialId.FNumber", "")),
                    aux_prop_id=self._parse_int(row.get("FAuxPropId")),
                    qty=self._parse_decimal(row.get("FRealQty")),
                )
                for row in result
            ]
        except Exception:
            return []

    async def _fetch_sales_deliveries(self, mto: str) -> list[RawRecord]:
        """Fetch SAL_OUTSTOCK entries for MTO (sales deliveries)."""
        try:
            # Match QuickPulse filter: include approved/confirmed docs (B, C, D)
            result = await self.client.query(
                form_id="SAL_OUTSTOCK",
                field_keys=[
                    "FBillNo",
                    "FMaterialId.FNumber",
                    "FAuxPropId",
                    "FRealQty",
                ],
                filter_string=f"FMTONO='{mto}' AND FDocumentStatus IN ('B', 'C', 'D')",  # Note: uppercase FMTONO
                limit=1000,
            )
            return [
                RawRecord(
                    form_id="SAL_OUTSTOCK",
                    bill_no=str(row.get("FBillNo", "")),
                    material_code=str(row.get("FMaterialId.FNumber", "")),
                    aux_prop_id=self._parse_int(row.get("FAuxPropId")),
                    qty=self._parse_decimal(row.get("FRealQty")),
                )
                for row in result
            ]
        except Exception:
            return []

    async def _fetch_material_pickings(self, mto: str) -> list[RawRecord]:
        """Fetch PRD_PickMtrl entries for MTO (material picking)."""
        try:
            # Match QuickPulse filter: include approved/confirmed docs (B, C)
            result = await self.client.query(
                form_id="PRD_PickMtrl",
                field_keys=[
                    "FBillNo",
                    "FMaterialId.FNumber",
                    "FAppQty",
                    "FActualQty",
                ],
                filter_string=f"FMTONO='{mto}' AND FDocumentStatus IN ('B', 'C')",  # Note: uppercase FMTONO
                limit=1000,
            )
            return [
                RawRecord(
                    form_id="PRD_PickMtrl",
                    bill_no=str(row.get("FBillNo", "")),
                    material_code=str(row.get("FMaterialId.FNumber", "")),
                    aux_prop_id=None,  # PRD_PickMtrl aggregates by material_code only
                    qty=self._parse_decimal(row.get("FActualQty")),  # actual picked
                    app_qty=self._parse_decimal(row.get("FAppQty")),  # requested
                )
                for row in result
            ]
        except Exception:
            return []

    @staticmethod
    def _parse_decimal(value: Any) -> Decimal:
        """Parse a value to Decimal, defaulting to 0."""
        if value is None:
            return Decimal(0)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(0)

    @staticmethod
    def _parse_int(value: Any) -> int | None:
        """Parse a value to int, or return None."""
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None
