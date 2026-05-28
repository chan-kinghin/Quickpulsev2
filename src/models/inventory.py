"""Pydantic models for inventory search responses."""

from decimal import Decimal

from pydantic import BaseModel, Field

# BD_MATERIAL.FErpClsID → localized label mapping
ERP_CLASS_LABELS: dict[str, str] = {
    "1": "外购",
    "2": "自制",
    "3": "委外",
    "4": "虚拟件",
    "9": "成品",
}


class MaterialMatch(BaseModel):
    """A single material returned by /api/inventory/search."""

    # BD_MATERIAL 基础信息
    material_code: str = Field(description="BD_MATERIAL.FNumber")
    material_name: str = Field(description="BD_MATERIAL.FName")
    specification: str = Field(default="", description="BD_MATERIAL.FSpecification")

    # BD_MATERIAL.FErpClsID — 物料属性分类
    erp_class: str = Field(default="", description="BD_MATERIAL.FErpClsID raw value: 1/2/3/4/9")
    erp_class_label: str = Field(default="", description="Localized label: 外购/自制/委外/虚拟件/成品")


class InventorySearchResponse(BaseModel):
    """Response for /api/inventory/search."""

    query: str = Field(description="Original search string echoed back to caller")
    total: int = Field(description="Total number of matched materials (≤ limit cap)")
    items: list[MaterialMatch]


class WarehouseRow(BaseModel):
    """One row of inventory split by warehouse × lot × aux.

    字段直接对应金蝶 STK_Inventory：
    - warehouse_code: FStockId.FNumber
    - warehouse_name: FStockId.FName
    - lot_number: FLot.FNumber
    - aux_id: FAuxPropId (raw ID; resolved to aux_desc via BD_FLEXSITEMDETAILV)
    - base_qty: FBaseQty (按基本单位)
    - stock_org: FStockOrgId.FName
    """

    # STK_Inventory 仓库信息
    warehouse_code: str = Field(description="FStockId.FNumber")
    warehouse_name: str = Field(description="FStockId.FName")

    # 批号 / 辅助属性
    lot_number: str = Field(default="", description="FLot.FNumber")
    aux_id: int = Field(default=0, description="FAuxPropId raw integer; 0 means no aux property")
    aux_desc: str = Field(default="", description="Resolved auxiliary property description from BD_FLEXSITEMDETAILV")

    # 数量
    base_qty: Decimal = Field(default=Decimal(0), description="FBaseQty — quantity in base UOM")

    # 组织
    stock_org: str = Field(default="", description="FStockOrgId.FName")


class InventoryDetail(BaseModel):
    """Response for /api/inventory/material/{code}."""

    # 物料基础信息 (从 BD_MATERIAL 补充)
    material_code: str = Field(description="BD_MATERIAL.FNumber")
    material_name: str = Field(description="BD_MATERIAL.FName")
    specification: str = Field(default="", description="BD_MATERIAL.FSpecification")
    erp_class: str = Field(default="", description="BD_MATERIAL.FErpClsID raw value")
    erp_class_label: str = Field(default="", description="Localized label derived from erp_class")

    # 汇总数量
    total_qty: Decimal = Field(default=Decimal(0), description="Sum of FBaseQty across all rows")
    warehouse_count: int = Field(default=0, description="Number of distinct warehouses with non-zero inventory")

    # 明细行 (按仓库 × 批号 × 辅助属性拆分)
    rows: list[WarehouseRow] = Field(default_factory=list)
