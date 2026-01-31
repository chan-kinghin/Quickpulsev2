"""Field specifications for QuickPulse vs Kingdee data validation.

This module defines:
1. Field mappings between UI columns and Kingdee fields
2. Chinese names for error reporting
3. Validation rules per material type
4. The list of 52 MTOs to test
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Literal, Optional, Tuple


class MaterialType(Enum):
    """Material type classification based on material_code prefix."""

    FINISHED_GOODS = "07"  # 成品
    SELF_MADE = "05"  # 自制
    PURCHASED = "03"  # 外购


@dataclass
class FieldSpec:
    """Specification for a single quantity field."""

    json_field: str  # Field name in QuickPulse JSON response
    chinese_name: str  # Chinese name for UI/error messages
    validate: bool  # Whether to validate this field
    description: str  # What this field represents


# Field specifications with Chinese names
FIELD_SPECS: dict[str, FieldSpec] = {
    "required_qty": FieldSpec(
        json_field="required_qty",
        chinese_name="需求量",
        validate=True,
        description="Demand/requirement quantity from source order",
    ),
    "picked_qty": FieldSpec(
        json_field="picked_qty",
        chinese_name="已领量",
        validate=True,
        description="Quantity picked/delivered (SAL_OUTSTOCK or PRD_PickMtrl)",
    ),
    "unpicked_qty": FieldSpec(
        json_field="unpicked_qty",
        chinese_name="未领量",
        validate=True,
        description="Unpicked quantity (can be negative for 超领)",
    ),
    "order_qty": FieldSpec(
        json_field="order_qty",
        chinese_name="订单数量",
        validate=True,
        description="Order quantity (usually same as required_qty)",
    ),
    "receipt_qty": FieldSpec(
        json_field="receipt_qty",
        chinese_name="入库量",
        validate=True,
        description="Quantity received into warehouse",
    ),
    "unreceived_qty": FieldSpec(
        json_field="unreceived_qty",
        chinese_name="未入库量",
        validate=True,
        description="Outstanding quantity not yet received",
    ),
    "sales_outbound_qty": FieldSpec(
        json_field="sales_outbound_qty",
        chinese_name="销售出库",
        validate=True,
        description="Sales delivery quantity (07.xx only)",
    ),
    "current_stock": FieldSpec(
        json_field="current_stock",
        chinese_name="即时库存",
        validate=False,  # SKIP - complex to validate
        description="Current inventory level (not validated)",
    ),
}

# List of fields that should be validated (exclude current_stock)
VALIDATED_FIELDS = [name for name, spec in FIELD_SPECS.items() if spec.validate]


@dataclass
class KingdeeFieldMapping:
    """Mapping of a field to its Kingdee source per material type."""

    material_type: MaterialType
    kingdee_form: str  # Form ID (e.g., SAL_SaleOrder)
    kingdee_field: str  # Field name (e.g., FQty)
    aggregation: Literal["material_only", "material_and_aux"]
    is_calculated: bool = False
    calculation: str | None = None  # e.g., "required_qty - picked_qty"


# Kingdee field mappings per (field, material_type)
KINGDEE_MAPPINGS: dict[tuple[str, MaterialType], KingdeeFieldMapping] = {
    # 需求量 (required_qty)
    ("required_qty", MaterialType.FINISHED_GOODS): KingdeeFieldMapping(
        material_type=MaterialType.FINISHED_GOODS,
        kingdee_form="SAL_SaleOrder",
        kingdee_field="FQty",
        aggregation="material_and_aux",
    ),
    ("required_qty", MaterialType.SELF_MADE): KingdeeFieldMapping(
        material_type=MaterialType.SELF_MADE,
        kingdee_form="PRD_MO",
        kingdee_field="FQty",
        aggregation="material_only",
    ),
    ("required_qty", MaterialType.PURCHASED): KingdeeFieldMapping(
        material_type=MaterialType.PURCHASED,
        kingdee_form="PUR_PurchaseOrder",
        kingdee_field="FQty",
        aggregation="material_and_aux",
    ),
    # 已领量 (picked_qty)
    ("picked_qty", MaterialType.FINISHED_GOODS): KingdeeFieldMapping(
        material_type=MaterialType.FINISHED_GOODS,
        kingdee_form="SAL_OUTSTOCK",
        kingdee_field="FRealQty",
        aggregation="material_and_aux",
    ),
    ("picked_qty", MaterialType.SELF_MADE): KingdeeFieldMapping(
        material_type=MaterialType.SELF_MADE,
        kingdee_form="PRD_PickMtrl",
        kingdee_field="FActualQty",
        aggregation="material_only",
    ),
    ("picked_qty", MaterialType.PURCHASED): KingdeeFieldMapping(
        material_type=MaterialType.PURCHASED,
        kingdee_form="PRD_PickMtrl",
        kingdee_field="FActualQty",
        aggregation="material_only",
    ),
    # 未领量 (unpicked_qty)
    ("unpicked_qty", MaterialType.FINISHED_GOODS): KingdeeFieldMapping(
        material_type=MaterialType.FINISHED_GOODS,
        kingdee_form="CALCULATED",
        kingdee_field="",
        aggregation="material_and_aux",
        is_calculated=True,
        calculation="required_qty - picked_qty",
    ),
    ("unpicked_qty", MaterialType.SELF_MADE): KingdeeFieldMapping(
        material_type=MaterialType.SELF_MADE,
        kingdee_form="PRD_PickMtrl",
        kingdee_field="FAppQty - FActualQty",
        aggregation="material_only",
    ),
    ("unpicked_qty", MaterialType.PURCHASED): KingdeeFieldMapping(
        material_type=MaterialType.PURCHASED,
        kingdee_form="CALCULATED",
        kingdee_field="",
        aggregation="material_only",
        is_calculated=True,
        calculation="required_qty - picked_qty",
    ),
    # 入库量 (receipt_qty)
    ("receipt_qty", MaterialType.FINISHED_GOODS): KingdeeFieldMapping(
        material_type=MaterialType.FINISHED_GOODS,
        kingdee_form="PRD_INSTOCK",
        kingdee_field="FRealQty",
        aggregation="material_and_aux",
    ),
    ("receipt_qty", MaterialType.SELF_MADE): KingdeeFieldMapping(
        material_type=MaterialType.SELF_MADE,
        kingdee_form="PRD_INSTOCK",
        kingdee_field="FRealQty",
        aggregation="material_only",
    ),
    ("receipt_qty", MaterialType.PURCHASED): KingdeeFieldMapping(
        material_type=MaterialType.PURCHASED,
        kingdee_form="PUR_PurchaseOrder",
        kingdee_field="FStockInQty",
        aggregation="material_and_aux",
    ),
    # 未入库量 (unreceived_qty)
    ("unreceived_qty", MaterialType.FINISHED_GOODS): KingdeeFieldMapping(
        material_type=MaterialType.FINISHED_GOODS,
        kingdee_form="CALCULATED",
        kingdee_field="",
        aggregation="material_and_aux",
        is_calculated=True,
        calculation="order_qty - receipt_qty",
    ),
    ("unreceived_qty", MaterialType.SELF_MADE): KingdeeFieldMapping(
        material_type=MaterialType.SELF_MADE,
        kingdee_form="CALCULATED",
        kingdee_field="",
        aggregation="material_only",
        is_calculated=True,
        calculation="order_qty - receipt_qty",
    ),
    ("unreceived_qty", MaterialType.PURCHASED): KingdeeFieldMapping(
        material_type=MaterialType.PURCHASED,
        kingdee_form="PUR_PurchaseOrder",
        kingdee_field="FRemainStockInQty",
        aggregation="material_and_aux",
    ),
    # 销售出库 (sales_outbound_qty) - only for finished goods
    ("sales_outbound_qty", MaterialType.FINISHED_GOODS): KingdeeFieldMapping(
        material_type=MaterialType.FINISHED_GOODS,
        kingdee_form="SAL_OUTSTOCK",
        kingdee_field="FRealQty",
        aggregation="material_and_aux",
    ),
}


def get_material_type(material_code: str) -> MaterialType | None:
    """Determine material type from material code prefix."""
    if material_code.startswith("07."):
        return MaterialType.FINISHED_GOODS
    elif material_code.startswith("05."):
        return MaterialType.SELF_MADE
    elif material_code.startswith("03."):
        return MaterialType.PURCHASED
    return None


# User-provided MTOs for validation (52 total)
USER_MTOS = [
    "AS2601019",
    "DS261007S",
    "AK2601017-1",
    "AK2601017-2",
    "DS261013S",
    "WS2601001",
    "DK261001S",
    "DS261002S",
    "AS2511046",
    "DS261020S",
    "AS2601001-1/-2",
    "AS2601001-3",
    "AS2601034",
    "AS2601036",
    "WS2601006",
    "AS2601014",
    "WS2601002",
    "WS2601007",
    "AS2601033",
    "WS2601004",
    "AS2512006",
    "AK2601006",
    "AS2601006",
    "AK2510048-1",
    "AS2512069",
    "AK2512059",
    "AS2512059",
    "AS2512060",
    "AK2512060",
    "DS25C312S",
    "AS2511058",
    "AS2511058-1",
    "AK2512018-1",
    "AS2512038",
    "AS2511037",
    "AS2511030",
    "AK2509054-5",
    "AS2512073",
    "AS2512037-1/-2",
    "AS2512037-3/-4",
    "DS25C315S",
    "AS2512074-1/-2",
    "AS2512074-3",
    "AS2512054",
    "AS2510048",
    "DK261018S",
    "AS2512032",
    "AS2512035",
    "AS2510066",
    "AS2512002",
    "AS2512055",
    "AS2510064-1",
]


@dataclass
class FieldValidation:
    """Result of validating a single field."""

    field_name: str
    chinese_name: str
    qp_value: Decimal
    kd_value: Decimal
    match: bool
    delta: Decimal

    @classmethod
    def create(
        cls, field_name: str, qp_value: Decimal, kd_value: Decimal
    ) -> "FieldValidation":
        """Create a FieldValidation with computed match and delta."""
        spec = FIELD_SPECS.get(field_name)
        chinese_name = spec.chinese_name if spec else field_name
        match = qp_value == kd_value
        delta = qp_value - kd_value
        return cls(
            field_name=field_name,
            chinese_name=chinese_name,
            qp_value=qp_value,
            kd_value=kd_value,
            match=match,
            delta=delta,
        )


@dataclass
class MaterialValidation:
    """Validation results for a single material in an MTO."""

    material_code: str
    material_name: str
    aux_attributes: str | None
    material_type: MaterialType | None
    validations: dict[str, FieldValidation]

    @property
    def all_match(self) -> bool:
        """Check if all validated fields match."""
        return all(v.match for v in self.validations.values())

    @property
    def failed_fields(self) -> list[FieldValidation]:
        """Get list of fields that failed validation."""
        return [v for v in self.validations.values() if not v.match]


@dataclass
class ComparisonResult:
    """Result of comparing QuickPulse vs Kingdee for one MTO."""

    mto: str
    items: list[MaterialValidation]
    error: str | None = None

    @property
    def all_match(self) -> bool:
        """Check if all items match."""
        return all(item.all_match for item in self.items)

    @property
    def failed_items(self) -> list[MaterialValidation]:
        """Get list of items with failed validations."""
        return [item for item in self.items if not item.all_match]

    @property
    def total_fields_checked(self) -> int:
        """Total number of fields checked."""
        return sum(len(item.validations) for item in self.items)

    @property
    def total_fields_passed(self) -> int:
        """Total number of fields that passed."""
        return sum(
            1
            for item in self.items
            for v in item.validations.values()
            if v.match
        )
