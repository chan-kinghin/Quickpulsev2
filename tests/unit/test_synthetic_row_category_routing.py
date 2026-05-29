"""Phase 2a: synthetic / PUR-only rows route by the authoritative BD_MATERIAL category
(passed in as category_by_code), NOT the unreliable legacy material_type.

Reproduces the live routing divergence found by the parity gate:
- 03.06.03.001 (外销包材) was mislabeled 自制 because the synthetic pick row had no category.
- 08.12.02.18 (委外加工) must route 委外 even though it enters via the PUR block (type=2).
"""
from decimal import Decimal
from unittest.mock import MagicMock

from src.mto_config import MTOConfig
from src.query.mto_handler import MTOQueryHandler
from src.readers.models import MaterialPickingModel, PurchaseOrderModel


def _handler():
    stub = MagicMock()  # readers unused here; data is passed directly to the builder
    return MTOQueryHandler(
        production_order_reader=stub, production_bom_reader=stub, production_receipt_reader=stub,
        purchase_order_reader=stub, purchase_receipt_reader=stub, subcontracting_order_reader=stub,
        material_picking_reader=stub, sales_delivery_reader=stub, sales_order_reader=stub,
        cache_reader=None, mto_config=MTOConfig("config/mto_config.json"),
        metric_engine=None, memory_cache_enabled=False,
    )


def _labels(h, rows):
    return [h._bom_row_to_child(r, {}).material_type_name for r in rows]


def _pick(code):
    return MaterialPickingModel(mto_number="AS2603016", material_code=code,
                                app_qty=Decimal(0), actual_qty=Decimal(1210),
                                ppbom_bill_no="", aux_prop_id=5)


def _po(code):
    return PurchaseOrderModel(bill_no="PO1", mto_number="AS2512042-2", material_code=code,
                              order_qty=Decimal(100), stock_in_qty=Decimal(0),
                              remain_stock_in_qty=Decimal(100), aux_prop_id=7)


def test_synthetic_pick_routes_by_category_not_legacy_type():
    """外销包材 pick-only row -> 包材 (was 自制 before the fix)."""
    h = _handler()
    rows = h._build_bom_joined_rows_from_live(
        [], [], [], [_pick("03.06.03.001")], [], [], [], [],
        category_by_code={"03.06.03.001": "外销包材"},
    )
    assert _labels(h, rows) == ["包材"]


def test_without_category_falls_back_to_legacy_type():
    """Control: no category -> legacy fallback reproduces the OLD buggy 自制 label."""
    h = _handler()
    rows = h._build_bom_joined_rows_from_live(
        [], [], [], [_pick("03.06.03.001")], [], [], [], [],
        category_by_code={},
    )
    assert _labels(h, rows) == ["自制"]


def test_purchase_block_category_overrides_block_type():
    """委外加工 material entering via the PUR block (hardcoded type=2) routes 委外 by category."""
    h = _handler()
    rows = h._build_bom_joined_rows_from_live(
        [], [], [], [], [_po("08.12.02.18")], [], [], [],
        category_by_code={"08.12.02.18": "委外加工"},
    )
    assert _labels(h, rows) == ["委外"]
