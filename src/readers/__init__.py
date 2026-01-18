"""Data readers for Kingdee forms.

This module provides readers for querying Kingdee K3Cloud forms.
All readers are generated from declarative configurations in factory.py.
"""

from src.readers.factory import (
    GenericReader,
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

__all__ = [
    # Reader classes
    "GenericReader",
    "ProductionOrderReader",
    "ProductionBOMReader",
    "ProductionReceiptReader",
    "PurchaseOrderReader",
    "PurchaseReceiptReader",
    "SubcontractingOrderReader",
    "MaterialPickingReader",
    "SalesDeliveryReader",
    "SalesOrderReader",
    # Model classes
    "ProductionOrderModel",
    "ProductionBOMModel",
    "ProductionReceiptModel",
    "PurchaseOrderModel",
    "PurchaseReceiptModel",
    "SubcontractingOrderModel",
    "MaterialPickingModel",
    "SalesDeliveryModel",
    "SalesOrderModel",
]
