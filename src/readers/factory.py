"""
Reader Factory - Generates Kingdee form readers from configuration.

This module consolidates 9 repetitive reader files into a single declarative
configuration system. Each reader is defined by:
- form_id: Kingdee form identifier
- mto_field: Field name for MTO number filtering
- field_mappings: Dict mapping model field -> (Kingdee field, type converter)
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Generic, Optional, Type, TypeVar

from pydantic import BaseModel

from src.kingdee.client import KingdeeClient
from src.readers.models import (
    MaterialPickingModel,
    ProductionBOMModel,
    ProductionOrderModel,
    ProductionReceiptModel,
    PurchaseOrderModel,
    PurchaseReceiptModel,
    SalesDeliveryModel,
    SalesOrderModel,
    SubcontractingOrderModel,
)

T = TypeVar("T", bound=BaseModel)


def _str(val: Any) -> str:
    """Convert to string, defaulting to empty string."""
    return val or ""


def _decimal(val: Any) -> Decimal:
    """Convert to Decimal, defaulting to 0."""
    return Decimal(str(val or 0))


def _int(val: Any) -> int:
    """Convert to int, defaulting to 0."""
    return int(val or 0)


def _optional_str(val: Any) -> Optional[str]:
    """Return string or None."""
    return val if val else None


@dataclass
class FieldMapping:
    """Maps a model field to its Kingdee field and converter."""

    kingdee_field: str
    converter: Callable[[Any], Any] = _str
    fallback_field: Optional[str] = None  # Alternative field name to try


@dataclass
class ReaderConfig:
    """Configuration for a Kingdee form reader."""

    form_id: str
    mto_field: str
    model_class: Type[BaseModel]
    field_mappings: dict[str, FieldMapping]
    date_field: str = "FDate"
    bill_field: str = "FBillNo"
    # Extra filter applied to all queries (e.g., status filters)
    extra_filter: str = ""


class GenericReader(Generic[T]):
    """Generic reader that works with any configuration."""

    def __init__(self, client: KingdeeClient, config: ReaderConfig):
        self.client = client
        self.config = config

    @property
    def form_id(self) -> str:
        return self.config.form_id

    @property
    def field_keys(self) -> list[str]:
        keys = []
        for mapping in self.config.field_mappings.values():
            keys.append(mapping.kingdee_field)
            if mapping.fallback_field:
                keys.append(mapping.fallback_field)
        return keys

    @property
    def mto_field(self) -> str:
        return self.config.mto_field

    @property
    def date_field(self) -> str:
        return self.config.date_field

    def to_model(self, raw_data: dict) -> T:
        """Convert raw API data to Pydantic model."""
        kwargs = {}
        for model_field, mapping in self.config.field_mappings.items():
            value = raw_data.get(mapping.kingdee_field)
            if value is None and mapping.fallback_field:
                value = raw_data.get(mapping.fallback_field)
            kwargs[model_field] = mapping.converter(value)
        return self.config.model_class(**kwargs)

    async def fetch_by_mto(self, mto_number: str) -> list[T]:
        """Query by MTO number and convert to models.

        Note: For SAL_SaleOrder, MTO can be stored in two fields:
        - FMtoNo (entry-level, newer orders)
        - F_QWJI_JHGZH (header-level, older orders)
        We query both to ensure all records are returned.
        """
        escaped_mto = mto_number.replace("'", "''")

        # Special case for SAL_SaleOrder: query both entry and header MTO fields
        # Use LIKE prefix match to include related MTOs (e.g., AS2509048 matches AS2509048-1, AS2509048-2)
        if self.form_id == "SAL_SaleOrder":
            filter_string = (
                f"(FMtoNo LIKE '{escaped_mto}%' OR F_QWJI_JHGZH LIKE '{escaped_mto}%')"
            )
        else:
            filter_string = f"{self.mto_field} LIKE '{escaped_mto}%'"

        if self.config.extra_filter:
            filter_string = f"{filter_string} AND {self.config.extra_filter}"

        raw_records = await self.client.query_all(
            form_id=self.form_id,
            field_keys=self.field_keys,
            filter_string=filter_string,
        )
        return [self.to_model(record) for record in raw_records]

    async def fetch_by_date_range(
        self,
        start_date: date,
        end_date: date,
        extra_filter: str = "",
    ) -> list[T]:
        """Query by date range and convert to models."""
        # Combine user-provided extra_filter with config's extra_filter
        combined_filter = extra_filter
        if self.config.extra_filter:
            if combined_filter:
                combined_filter = f"({combined_filter}) AND {self.config.extra_filter}"
            else:
                combined_filter = self.config.extra_filter

        raw_records = await self.client.query_by_date_range(
            form_id=self.form_id,
            field_keys=self.field_keys,
            date_field=self.date_field,
            start_date=start_date,
            end_date=end_date,
            extra_filter=combined_filter,
        )
        return [self.to_model(record) for record in raw_records]

    async def fetch_by_bill_no(
        self, bill_no: str, bill_field: Optional[str] = None
    ) -> list[T]:
        """Query by bill number."""
        field = bill_field or self.config.bill_field
        raw_records = await self.client.query_all(
            form_id=self.form_id,
            field_keys=self.field_keys,
            filter_string=f"{field}='{bill_no}'",
        )
        return [self.to_model(record) for record in raw_records]

    async def fetch_by_bill_nos(
        self, bill_nos: list[str], bill_field: Optional[str] = None
    ) -> list[T]:
        """Query by multiple bill numbers in a single batched query.

        This is much more efficient than calling fetch_by_bill_no repeatedly
        as it uses a single API call with an IN clause.
        """
        if not bill_nos:
            return []

        field = bill_field or self.config.bill_field
        # Escape single quotes in bill numbers and build IN clause
        escaped = [bn.replace("'", "''") for bn in bill_nos]
        in_clause = ",".join(f"'{bn}'" for bn in escaped)
        filter_string = f"{field} IN ({in_clause})"

        raw_records = await self.client.query_all(
            form_id=self.form_id,
            field_keys=self.field_keys,
            filter_string=filter_string,
        )
        return [self.to_model(record) for record in raw_records]

    async def fetch_by_mtos(
        self, mto_numbers: list[str], mto_field: Optional[str] = None
    ) -> list[T]:
        """Query by multiple MTO numbers in a single batched query.

        This is much more efficient than calling fetch_by_mto repeatedly
        as it uses a single API call with an IN clause.

        Note: For SAL_SaleOrder, MTO can be stored in two fields:
        - FMtoNo (entry-level, newer orders)
        - F_QWJI_JHGZH (header-level, older orders)
        We query both to ensure all records are returned.

        Args:
            mto_numbers: List of MTO numbers to query
            mto_field: Optional override for MTO field name (uses config default)

        Returns:
            List of models matching any of the MTO numbers
        """
        if not mto_numbers:
            return []

        field = mto_field or self.config.mto_field
        # Build filter with IN clause and optional extra conditions
        escaped = [mto.replace("'", "''") for mto in mto_numbers]
        in_clause = ",".join(f"'{mto}'" for mto in escaped)

        # Special case for SAL_SaleOrder: query both entry and header MTO fields
        if self.form_id == "SAL_SaleOrder":
            filter_string = (
                f"(FMtoNo IN ({in_clause}) OR F_QWJI_JHGZH IN ({in_clause}))"
            )
        else:
            filter_string = f"{field} IN ({in_clause})"

        if self.config.extra_filter:
            filter_string = f"{filter_string} AND {self.config.extra_filter}"

        raw_records = await self.client.query_all(
            form_id=self.form_id,
            field_keys=self.field_keys,
            filter_string=filter_string,
        )
        return [self.to_model(record) for record in raw_records]


# =============================================================================
# Reader Configurations
# =============================================================================

PRODUCTION_ORDER_CONFIG = ReaderConfig(
    form_id="PRD_MO",
    mto_field="FMTONo",
    model_class=ProductionOrderModel,
    date_field="FCreateDate",
    field_mappings={
        "bill_no": FieldMapping("FBillNo"),
        "mto_number": FieldMapping("FMTONo"),
        "workshop": FieldMapping("FWorkShopID.FName"),
        "material_code": FieldMapping("FMaterialId.FNumber"),
        "material_name": FieldMapping("FMaterialId.FName"),
        "specification": FieldMapping("FMaterialId.FSpecification"),
        # Note: FAuxPropId.FName doesn't exist in this form, aux_attributes defaults to ""
        "aux_prop_id": FieldMapping("FAuxPropId", _int),  # For multi-material orders
        "qty": FieldMapping("FQty", _decimal),
        "status": FieldMapping("FStatus"),
        "create_date": FieldMapping("FCreateDate", _optional_str),
    },
)

PRODUCTION_BOM_CONFIG = ReaderConfig(
    form_id="PRD_PPBOM",
    mto_field="FMTONO",  # Corrected: no FPPBomEntry_ prefix
    model_class=ProductionBOMModel,
    bill_field="FMOBillNO",
    field_mappings={
        "mo_bill_no": FieldMapping("FMOBillNO"),
        "mto_number": FieldMapping("FMTONO"),  # Corrected: no prefix
        "material_code": FieldMapping("FMaterialId.FNumber"),  # Corrected: no prefix
        "material_name": FieldMapping("FMaterialId.FName"),
        "specification": FieldMapping("FMaterialId.FSpecification"),
        "aux_prop_id": FieldMapping("FAuxPropId", _int),  # Reference to BD_FLEXSITEMDETAILV
        "material_type": FieldMapping("FMaterialType", _int),  # Corrected: no prefix
        "need_qty": FieldMapping("FMustQty", _decimal),  # FNeedQty doesn't exist, use FMustQty
        "picked_qty": FieldMapping("FPickedQty", _decimal),  # Corrected: no prefix
        "no_picked_qty": FieldMapping("FNoPickedQty", _decimal),  # Corrected: no prefix
    },
)

PRODUCTION_RECEIPT_CONFIG = ReaderConfig(
    form_id="PRD_INSTOCK",
    mto_field="FMtoNo",  # Corrected: no FEntity_ prefix
    model_class=ProductionReceiptModel,
    field_mappings={
        "bill_no": FieldMapping("FBillNo"),
        "mto_number": FieldMapping("FMtoNo"),
        "material_code": FieldMapping("FMaterialId.FNumber"),
        "material_name": FieldMapping("FMaterialId.FName"),  # For variant-level display
        "specification": FieldMapping("FMaterialId.FSpecification"),  # For variant-level display
        "real_qty": FieldMapping("FRealQty", _decimal),
        "must_qty": FieldMapping("FMustQty", _decimal),
        "aux_prop_id": FieldMapping("FAuxPropId", _int),
        "mo_bill_no": FieldMapping("FMoBillNo"),
    },
    # Include approved/confirmed/completed docs (B=已审核, C=已确认, D=重新审核)
    extra_filter="FDocumentStatus IN ('B', 'C', 'D')",
)

PURCHASE_ORDER_CONFIG = ReaderConfig(
    form_id="PUR_PurchaseOrder",
    mto_field="FMtoNo",  # Corrected: no FPOOrderEntry_ prefix
    model_class=PurchaseOrderModel,
    field_mappings={
        "bill_no": FieldMapping("FBillNo"),
        "mto_number": FieldMapping("FMtoNo"),
        "material_code": FieldMapping("FMaterialId.FNumber"),
        "material_name": FieldMapping("FMaterialId.FName"),
        "specification": FieldMapping("FMaterialId.FSpecification"),
        "aux_prop_id": FieldMapping("FAuxPropId", _int),  # Reference to BD_FLEXSITEMDETAILV
        "order_qty": FieldMapping("FQty", _decimal),
        "stock_in_qty": FieldMapping("FStockInQty", _decimal),
        "remain_stock_in_qty": FieldMapping("FRemainStockInQty", _decimal),
    },
)

PURCHASE_RECEIPT_CONFIG = ReaderConfig(
    form_id="STK_InStock",
    mto_field="FMtoNo",  # Corrected: no FInStockEntry_ prefix
    model_class=PurchaseReceiptModel,
    field_mappings={
        "bill_no": FieldMapping("FBillNo"),
        "mto_number": FieldMapping("FMtoNo"),
        "material_code": FieldMapping("FMaterialId.FNumber"),
        "real_qty": FieldMapping("FRealQty", _decimal),
        "must_qty": FieldMapping("FMustQty", _decimal),
        "bill_type_number": FieldMapping("FBillTypeID.FNumber"),
    },
    # Include approved/confirmed docs, exclude drafts (A)
    extra_filter="FDocumentStatus IN ('B', 'C', 'D')",
)

SUBCONTRACTING_ORDER_CONFIG = ReaderConfig(
    form_id="SUB_SUBREQORDER",
    mto_field="FMtoNo",  # Corrected: no FTreeEntity_ prefix
    model_class=SubcontractingOrderModel,
    field_mappings={
        "bill_no": FieldMapping("FBillNo"),
        "mto_number": FieldMapping("FMtoNo"),
        "material_code": FieldMapping("FMaterialId.FNumber"),
        "order_qty": FieldMapping("FQty", _decimal),
        "stock_in_qty": FieldMapping("FStockInQty", _decimal),
        "no_stock_in_qty": FieldMapping("FNoStockInQty", _decimal),
    },
)

MATERIAL_PICKING_CONFIG = ReaderConfig(
    form_id="PRD_PickMtrl",
    mto_field="FMTONO",  # Corrected: no FEntity_ prefix
    model_class=MaterialPickingModel,
    field_mappings={
        "bill_no": FieldMapping("FBillNo"),
        "mto_number": FieldMapping("FMTONO"),
        "material_code": FieldMapping("FMaterialId.FNumber"),
        "app_qty": FieldMapping("FAppQty", _decimal),
        "actual_qty": FieldMapping("FActualQty", _decimal),
        "ppbom_bill_no": FieldMapping("FPPBomBillNo"),
        "aux_prop_id": FieldMapping("FAuxPropId", _int),  # 辅助属性ID，用于按颜色/尺寸汇总
    },
    # Include approved/confirmed documents (B=审核, C=确认), exclude drafts (A)
    extra_filter="FDocumentStatus IN ('B', 'C')",
)

SALES_DELIVERY_CONFIG = ReaderConfig(
    form_id="SAL_OUTSTOCK",
    mto_field="FMTONO",  # Corrected: no FSAL_OUTSTOCKENTRY_ prefix
    model_class=SalesDeliveryModel,
    field_mappings={
        "bill_no": FieldMapping("FBillNo"),
        "mto_number": FieldMapping("FMTONO"),
        "material_code": FieldMapping("FMaterialId.FNumber"),
        "real_qty": FieldMapping("FRealQty", _decimal),
        "must_qty": FieldMapping("FMustQty", _decimal),
        "aux_prop_id": FieldMapping("FAuxPropId", _int),
    },
    # Include approved/confirmed docs, exclude drafts (A)
    extra_filter="FDocumentStatus IN ('B', 'C', 'D')",
)

SALES_ORDER_CONFIG = ReaderConfig(
    form_id="SAL_SaleOrder",
    # Note: MTO can be in FMtoNo (entry-level) or F_QWJI_JHGZH (header-level)
    # The fetch_by_mto/fetch_by_mtos methods handle querying both fields
    mto_field="FMtoNo",
    model_class=SalesOrderModel,
    field_mappings={
        "bill_no": FieldMapping("FBillNo"),
        "mto_number": FieldMapping("FMtoNo"),
        "material_code": FieldMapping("FMaterialId.FNumber"),
        "material_name": FieldMapping("FMaterialId.FName"),
        "specification": FieldMapping("FMaterialId.FSpecification"),
        "aux_prop_id": FieldMapping("FAuxPropId", _int),
        "customer_name": FieldMapping("FCustId.FName"),
        "delivery_date": FieldMapping("FDeliveryDate", _optional_str),
        "qty": FieldMapping("FQty", _decimal),
        "bom_short_name": FieldMapping("FBomId.FName", _str),  # BOM简称
    },
)


# =============================================================================
# Typed Reader Classes (for backwards compatibility with type hints)
# =============================================================================


class ProductionOrderReader(GenericReader[ProductionOrderModel]):
    """Production Order Reader (PRD_MO)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, PRODUCTION_ORDER_CONFIG)


class ProductionBOMReader(GenericReader[ProductionBOMModel]):
    """Production BOM Reader (PRD_PPBOM)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, PRODUCTION_BOM_CONFIG)


class ProductionReceiptReader(GenericReader[ProductionReceiptModel]):
    """Production Receipt Reader (PRD_INSTOCK)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, PRODUCTION_RECEIPT_CONFIG)


class PurchaseOrderReader(GenericReader[PurchaseOrderModel]):
    """Purchase Order Reader (PUR_PurchaseOrder)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, PURCHASE_ORDER_CONFIG)


class PurchaseReceiptReader(GenericReader[PurchaseReceiptModel]):
    """Purchase Receipt Reader (STK_InStock)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, PURCHASE_RECEIPT_CONFIG)


class SubcontractingOrderReader(GenericReader[SubcontractingOrderModel]):
    """Subcontracting Order Reader (SUB_POORDER)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, SUBCONTRACTING_ORDER_CONFIG)


class MaterialPickingReader(GenericReader[MaterialPickingModel]):
    """Material Picking Reader (PRD_PickMtrl)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, MATERIAL_PICKING_CONFIG)


class SalesDeliveryReader(GenericReader[SalesDeliveryModel]):
    """Sales Delivery Reader (SAL_OUTSTOCK)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, SALES_DELIVERY_CONFIG)


class SalesOrderReader(GenericReader[SalesOrderModel]):
    """Sales Order Reader (SAL_SaleOrder)."""

    def __init__(self, client: KingdeeClient):
        super().__init__(client, SALES_ORDER_CONFIG)
