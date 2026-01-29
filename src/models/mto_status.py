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
    """BOM component (child item) with status."""

    material_code: str
    material_name: str
    specification: str
    aux_attributes: str
    material_type: int = Field(..., serialization_alias="material_type_code")
    material_type_name: str = Field(..., serialization_alias="material_type")
    required_qty: Decimal
    picked_qty: Decimal
    unpicked_qty: Decimal
    order_qty: Decimal
    receipt_qty: Decimal = Field(..., serialization_alias="received_qty")
    unreceived_qty: Decimal
    pick_request_qty: Decimal
    pick_actual_qty: Decimal
    delivered_qty: Decimal = Field(..., serialization_alias="sales_outbound_qty")
    inventory_qty: Decimal = Field(..., serialization_alias="current_stock")
    receipt_source: str


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
