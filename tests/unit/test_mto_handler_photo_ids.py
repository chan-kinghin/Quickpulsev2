"""Wave B2 tests for ``ChildItem.photo_file_ids`` plumbing.

Covers:
  * ``MTOQueryHandler._collect_photo_file_ids`` dedup + filter + order rules
  * ``MTOQueryHandler._bom_row_to_child`` threading the list onto every
    material-type branch
  * ``MTOQueryHandler._build_aggregated_sales_child`` threading the list onto
    the finished-goods (07.xx) ChildItem

Wave A surfaced ``photo_file_id_1/2/3`` on ``ProductionOrderModel``; this
wave's job is to collect those into ``ChildItem.photo_file_ids: list[str]``
(union across all PRD_MOs under one MTO, deduplicated, insertion-ordered)
and pass them through both join paths (cache + live).
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.query.cache_reader import BOMJoinedRow
from src.query.mto_handler import MTOQueryHandler, MaterialType
from src.readers.models import ProductionOrderModel, SalesOrderModel


def _make_handler() -> MTOQueryHandler:
    """Minimal handler instance for direct method calls (no readers exercised)."""
    readers = {}
    for name in [
        "production_order", "production_bom", "production_receipt",
        "purchase_order", "purchase_receipt", "subcontracting_order",
        "material_picking", "sales_delivery", "sales_order",
    ]:
        readers[name] = MagicMock()
    return MTOQueryHandler(
        production_order_reader=readers["production_order"],
        production_bom_reader=readers["production_bom"],
        production_receipt_reader=readers["production_receipt"],
        purchase_order_reader=readers["purchase_order"],
        purchase_receipt_reader=readers["purchase_receipt"],
        subcontracting_order_reader=readers["subcontracting_order"],
        material_picking_reader=readers["material_picking"],
        sales_delivery_reader=readers["sales_delivery"],
        sales_order_reader=readers["sales_order"],
    )


def _po(bill_no: str, p1=None, p2=None, p3=None) -> ProductionOrderModel:
    """Helper: build a minimal ProductionOrderModel with optional photo slots."""
    return ProductionOrderModel(
        bill_no=bill_no,
        mto_number="DS264102S",
        workshop="W1",
        material_code="05.02.001",
        material_name="parent",
        specification="",
        qty=Decimal("100"),
        status="B",
        photo_file_id_1=p1,
        photo_file_id_2=p2,
        photo_file_id_3=p3,
    )


def _bom_row(material_type: int = 1) -> BOMJoinedRow:
    """Helper: build a BOMJoinedRow that won't trip any 07.xx-related logic."""
    return BOMJoinedRow(
        mo_bill_no="MO260501414",
        mto_number="DS264102S",
        material_code="05.02.001",
        material_name="child",
        specification="",
        aux_attributes="",
        aux_prop_id=0,
        material_type=material_type,
        need_qty=Decimal("10"),
        picked_qty=Decimal("0"),
        no_picked_qty=Decimal("10"),
        prod_receipt_real_qty=Decimal("0"),
        prod_receipt_must_qty=Decimal("0"),
        pick_actual_qty=Decimal("0"),
        pick_app_qty=Decimal("0"),
        purchase_order_qty=Decimal("0"),
        purchase_stock_in_qty=Decimal("0"),
        purchase_receipt_real_qty=Decimal("0"),
        subcontract_order_qty=Decimal("0"),
        subcontract_stock_in_qty=Decimal("0"),
        delivery_real_qty=Decimal("0"),
    )


class TestCollectPhotoFileIds:
    """``_collect_photo_file_ids`` — pure helper."""

    def test_empty_list(self):
        assert MTOQueryHandler._collect_photo_file_ids([]) == []

    def test_none_input(self):
        assert MTOQueryHandler._collect_photo_file_ids(None) == []

    def test_all_none_slots_yields_empty(self):
        pos = [_po("MO1"), _po("MO2")]
        assert MTOQueryHandler._collect_photo_file_ids(pos) == []

    def test_empty_string_slots_filtered(self):
        # Kingdee can return '' for unused slots; treat same as None.
        pos = [_po("MO1", p1="", p2="abc", p3="")]
        assert MTOQueryHandler._collect_photo_file_ids(pos) == ["abc"]

    def test_dedup_across_prd_mos(self):
        # Two PRD_MOs both carry the same FileID — appears once in output.
        pos = [
            _po("MO1", p1="abc", p2="def"),
            _po("MO2", p1="abc", p2="ghi"),
        ]
        assert MTOQueryHandler._collect_photo_file_ids(pos) == ["abc", "def", "ghi"]

    def test_dedup_within_one_prd_mo(self):
        # Same ID repeated across slots on a single PRD_MO — appears once.
        pos = [_po("MO1", p1="abc", p2="abc", p3="abc")]
        assert MTOQueryHandler._collect_photo_file_ids(pos) == ["abc"]

    def test_insertion_order_preserved(self):
        # Iteration is (PRD_MO order) × (slot 1 → 2 → 3). Verify exact sequence.
        pos = [
            _po("MO1", p1="a", p2="b", p3="c"),
            _po("MO2", p1="d", p2="e", p3="f"),
        ]
        assert MTOQueryHandler._collect_photo_file_ids(pos) == [
            "a", "b", "c", "d", "e", "f",
        ]

    def test_real_world_three_photos(self):
        # Real FileID shape from docs/PLAN: 32-char hex.
        ids = [
            "8978cffd01404da595bdc8be907fbcce",
            "d8b7e9b6fed143efae647b77c742cd67",
            "4ec577b82824455c9cb7a1aed25c85f8",
        ]
        pos = [_po("MO260501414", p1=ids[0], p2=ids[1], p3=ids[2])]
        assert MTOQueryHandler._collect_photo_file_ids(pos) == ids


class TestBomRowToChildPhotoIds:
    """``_bom_row_to_child`` must thread ``photo_file_ids`` onto every branch."""

    @pytest.mark.parametrize("material_type", [1, 2, 3])
    def test_photo_ids_threaded_on_known_types(self, material_type):
        handler = _make_handler()
        row = _bom_row(material_type=material_type)
        photos = ["abc", "def"]

        child = handler._bom_row_to_child(row, aux_descriptions={}, photo_file_ids=photos)

        assert child.photo_file_ids == ["abc", "def"]

    def test_photo_ids_threaded_on_unknown_type(self):
        handler = _make_handler()
        row = _bom_row(material_type=99)  # falls through to "未知" branch
        child = handler._bom_row_to_child(row, aux_descriptions={}, photo_file_ids=["xyz"])
        assert child.material_type_name == "未知"
        assert child.photo_file_ids == ["xyz"]

    def test_default_empty_list_when_omitted(self):
        # The kwarg is optional; default is no photos. Critical so the
        # existing _make_handler test paths (which don't pass photo_file_ids)
        # don't crash.
        handler = _make_handler()
        row = _bom_row(material_type=1)
        child = handler._bom_row_to_child(row, aux_descriptions={})
        assert child.photo_file_ids == []

    def test_default_empty_list_when_none(self):
        handler = _make_handler()
        row = _bom_row(material_type=1)
        child = handler._bom_row_to_child(row, aux_descriptions={}, photo_file_ids=None)
        assert child.photo_file_ids == []

    def test_caller_list_not_mutated_by_handler(self):
        # The handler should defensively copy the list so mutations to the
        # ChildItem's list don't leak into the caller-side photo_file_ids.
        handler = _make_handler()
        row = _bom_row(material_type=1)
        photos = ["abc"]
        child = handler._bom_row_to_child(row, aux_descriptions={}, photo_file_ids=photos)
        child.photo_file_ids.append("mutated")
        assert photos == ["abc"]


class TestBuildAggregatedSalesChildPhotoIds:
    """``_build_aggregated_sales_child`` (07.xx path) must thread the list too."""

    def _so(self, code="07.02.001", aux=1001, qty=Decimal("10")) -> SalesOrderModel:
        return SalesOrderModel(
            bill_no="SO1",
            mto_number="DS264102S",
            material_code=code,
            material_name="finished",
            specification="",
            aux_attributes="",
            aux_prop_id=aux,
            customer_name="C",
            delivery_date=None,
            qty=qty,
        )

    def test_photos_threaded_through(self):
        handler = _make_handler()
        child = handler._build_aggregated_sales_child(
            [self._so()],
            receipt_by_material={},
            delivered_by_material={},
            aux_descriptions={},
            photo_file_ids=["abc", "def"],
        )
        assert child.is_finished_goods is True
        assert child.photo_file_ids == ["abc", "def"]

    def test_default_empty_when_omitted(self):
        handler = _make_handler()
        child = handler._build_aggregated_sales_child(
            [self._so()],
            receipt_by_material={},
            delivered_by_material={},
            aux_descriptions={},
        )
        assert child.photo_file_ids == []
