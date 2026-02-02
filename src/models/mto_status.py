"""Pydantic models for MTO status responses."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ParentItem(BaseModel):
    """Order info with sales order details."""

    mto_number: str
    customer_name: str = ""
    delivery_date: Optional[str] = None


class ChildItem(BaseModel):
    """BOM component (child item) with status.

    字段名称直接对应金蝶原始字段：
    - sales_order_qty: 销售订单.数量 (成品07.xx用)
    - prod_instock_must_qty: 生产入库单.应收数量 (自制件05.xx用)
    - purchase_order_qty: 采购订单.数量 (外购件03.xx用)
    - pick_actual_qty: 生产领料单.实发数量 (自制件/外购件用)
    - prod_instock_real_qty: 生产入库单.实收数量 (成品/自制件用)
    - purchase_stock_in_qty: 采购订单.累计入库数量 (外购件用)
    """

    # 基础信息
    material_code: str
    material_name: str
    specification: str
    aux_attributes: str
    material_type: int = Field(..., serialization_alias="material_type_code")
    material_type_name: str = Field(..., serialization_alias="material_type")

    # 金蝶原始字段 - 数量类（根据物料类型，只有一个有值）
    sales_order_qty: Decimal = Field(default=Decimal(0), description="销售订单.数量")
    prod_instock_must_qty: Decimal = Field(default=Decimal(0), description="生产入库单.应收数量")
    purchase_order_qty: Decimal = Field(default=Decimal(0), description="采购订单.数量")

    # 金蝶原始字段 - 领料/入库
    pick_actual_qty: Decimal = Field(default=Decimal(0), description="生产领料单.实发数量")
    prod_instock_real_qty: Decimal = Field(default=Decimal(0), description="生产入库单.实收数量")
    purchase_stock_in_qty: Decimal = Field(default=Decimal(0), description="采购订单.累计入库数量")


class MTOStatusResponse(BaseModel):
    """Complete MTO status response."""

    mto_number: str
    parent: ParentItem = Field(..., serialization_alias="parent_item")
    children: list[ChildItem] = Field(..., serialization_alias="child_items")
    query_time: datetime
    data_source: str = Field(
        default="live",
        description="Data source: 'cache' for cached data, 'live' for real-time API",
    )
    cache_age_seconds: Optional[int] = Field(
        default=None,
        description="Age of cached data in seconds (only present when data_source='cache')",
    )


class OrderNode(BaseModel):
    """Order node in relationship tree."""

    bill_no: str
    label: str


class DocumentNode(BaseModel):
    """Document linked to an order."""

    bill_no: str
    label: str
    linked_order: Optional[str] = None


class MTORelatedOrdersResponse(BaseModel):
    """Response for /api/mto/{mto_number}/related-orders."""

    mto_number: str
    orders: dict[str, list[OrderNode]]
    documents: dict[str, list[DocumentNode]]
    query_time: datetime
    data_source: str = "live"


class MTOSummary(BaseModel):
    """Summary for search results."""

    mto_number: str
    material_name: str
    order_qty: Decimal
    status: str
