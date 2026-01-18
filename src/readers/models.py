"""Pydantic models for all Kingdee form readers."""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ProductionOrderModel(BaseModel):
    """Production Order Model (PRD_MO) - Parent Item."""

    bill_no: str
    mto_number: str
    workshop: str
    material_code: str
    material_name: str
    specification: str
    aux_attributes: str = ""  # Field may not exist in all Kingdee setups
    qty: Decimal
    status: str
    create_date: Optional[str] = None


class ProductionBOMModel(BaseModel):
    """Production BOM Model (PRD_PPBOM) - Child Item."""

    mo_bill_no: str
    mto_number: str
    material_code: str
    material_name: str
    specification: str
    aux_attributes: str = ""  # Populated from BD_FLEXSITEMDETAILV lookup
    aux_prop_id: int = 0  # FAuxPropId - reference to BD_FLEXSITEMDETAILV
    material_type: int
    need_qty: Decimal
    picked_qty: Decimal
    no_picked_qty: Decimal


class ProductionReceiptModel(BaseModel):
    """Production Receipt Model (PRD_INSTOCK)."""

    mto_number: str
    material_code: str
    real_qty: Decimal
    must_qty: Decimal


class PurchaseOrderModel(BaseModel):
    """Purchase Order Model (PUR_PurchaseOrder)."""

    bill_no: str
    mto_number: str
    material_code: str
    material_name: str = ""
    specification: str = ""
    aux_attributes: str = ""  # Populated from BD_FLEXSITEMDETAILV lookup
    aux_prop_id: int = 0  # FAuxPropId - reference to BD_FLEXSITEMDETAILV
    order_qty: Decimal
    stock_in_qty: Decimal
    remain_stock_in_qty: Decimal


class PurchaseReceiptModel(BaseModel):
    """Purchase Receipt Model (STK_InStock)."""

    mto_number: str
    material_code: str
    real_qty: Decimal
    must_qty: Decimal
    bill_type_number: str


class SubcontractingOrderModel(BaseModel):
    """Subcontracting Order Model (SUB_POORDER)."""

    bill_no: str
    mto_number: str
    material_code: str
    order_qty: Decimal
    stock_in_qty: Decimal
    no_stock_in_qty: Decimal


class MaterialPickingModel(BaseModel):
    """Material Picking Model (PRD_PickMtrl)."""

    mto_number: str
    material_code: str
    app_qty: Decimal
    actual_qty: Decimal
    ppbom_bill_no: str


class SalesDeliveryModel(BaseModel):
    """Sales Delivery Model (SAL_OUTSTOCK)."""

    mto_number: str
    material_code: str
    real_qty: Decimal
    must_qty: Decimal


class SalesOrderModel(BaseModel):
    """Sales Order Model (SAL_SaleOrder)."""

    bill_no: str
    mto_number: str
    customer_name: str
    delivery_date: Optional[str] = None
