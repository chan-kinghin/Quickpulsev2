"""Tests for src/models/inventory.py"""

from decimal import Decimal

import pytest

from src.models.inventory import (
    ERP_CLASS_LABELS,
    InventoryDetail,
    InventorySearchResponse,
    MaterialMatch,
    WarehouseRow,
)


class TestMaterialMatch:
    """Tests for MaterialMatch model."""

    def test_minimal_construction(self):
        """Only required fields: material_code and material_name."""
        match = MaterialMatch(material_code="07.01.001", material_name="潜水镜")
        assert match.material_code == "07.01.001"
        assert match.material_name == "潜水镜"

    def test_full_construction(self):
        """All fields explicitly set."""
        match = MaterialMatch(
            material_code="07.01.001",
            material_name="潜水镜",
            specification="GT38-BLK",
            erp_class="9",
            erp_class_label="成品",
        )
        assert match.material_code == "07.01.001"
        assert match.material_name == "潜水镜"
        assert match.specification == "GT38-BLK"
        assert match.erp_class == "9"
        assert match.erp_class_label == "成品"

    def test_default_empty_erp_class(self):
        """erp_class and erp_class_label default to empty string."""
        match = MaterialMatch(material_code="03.01.001", material_name="外购件")
        assert match.erp_class == ""
        assert match.erp_class_label == ""
        assert match.specification == ""

    def test_material_match_matched_via_default_empty_list(self):
        """matched_via defaults to an empty list — not None, not missing."""
        m = MaterialMatch(material_code="X", material_name="Y")
        assert m.matched_via == []
        assert isinstance(m.matched_via, list)


class TestInventorySearchResponse:
    """Tests for InventorySearchResponse model."""

    def test_empty_items_list(self):
        """Zero results is a valid response."""
        response = InventorySearchResponse(query="NONEXISTENT", total=0, items=[])
        assert response.query == "NONEXISTENT"
        assert response.total == 0
        assert response.items == []

    def test_total_matches_items_length_on_populated(self):
        """total field reflects the number of items returned."""
        items = [
            MaterialMatch(material_code="07.01.001", material_name="潜水镜", specification="GT38-BLK"),
            MaterialMatch(material_code="07.01.002", material_name="潜水镜 Pro", specification="GT38-CLR"),
        ]
        response = InventorySearchResponse(query="GT38", total=len(items), items=items)
        assert response.total == 2
        assert len(response.items) == 2
        assert response.items[0].material_code == "07.01.001"
        assert response.items[1].specification == "GT38-CLR"

    def test_query_string_preserved(self):
        """Original query string is echoed back unchanged."""
        response = InventorySearchResponse(query="潜水镜", total=0, items=[])
        assert response.query == "潜水镜"


class TestWarehouseRow:
    """Tests for WarehouseRow model."""

    def test_minimal_construction(self):
        """Only warehouse_code and warehouse_name are required."""
        row = WarehouseRow(warehouse_code="01.01", warehouse_name="外销成品仓")
        assert row.warehouse_code == "01.01"
        assert row.warehouse_name == "外销成品仓"

    def test_defaults_for_lot_aux_qty(self):
        """lot_number, aux_id, aux_desc, base_qty, stock_org all have sensible defaults."""
        row = WarehouseRow(warehouse_code="01.01", warehouse_name="外销成品仓")
        assert row.lot_number == ""
        assert row.aux_id == 0
        assert row.aux_desc == ""
        assert row.base_qty == Decimal(0)
        assert row.stock_org == ""

    def test_full_construction(self):
        """All fields explicitly provided."""
        row = WarehouseRow(
            warehouse_code="01.01",
            warehouse_name="外销成品仓",
            lot_number="L20260512",
            aux_id=12345,
            aux_desc="GT38 / 黑色",
            base_qty=Decimal("800"),
            stock_org="福伦特",
        )
        assert row.lot_number == "L20260512"
        assert row.aux_id == 12345
        assert row.aux_desc == "GT38 / 黑色"
        assert row.base_qty == Decimal("800")
        assert row.stock_org == "福伦特"


class TestInventoryDetail:
    """Tests for InventoryDetail model."""

    def test_empty_rows_default(self):
        """rows defaults to an empty list, not None."""
        detail = InventoryDetail(material_code="07.01.001", material_name="潜水镜")
        assert detail.rows == []
        assert isinstance(detail.rows, list)

    def test_total_qty_decimal_preserved(self):
        """Decimal precision is not lost during construction."""
        detail = InventoryDetail(
            material_code="07.01.001",
            material_name="潜水镜",
            total_qty=Decimal("1234.50"),
        )
        assert detail.total_qty == Decimal("1234.50")
        assert isinstance(detail.total_qty, Decimal)

    def test_warehouse_count_default(self):
        """warehouse_count defaults to 0."""
        detail = InventoryDetail(material_code="07.01.001", material_name="潜水镜")
        assert detail.warehouse_count == 0

    def test_full_construction_with_rows(self):
        """InventoryDetail with rows populated."""
        rows = [
            WarehouseRow(
                warehouse_code="01.01",
                warehouse_name="外销成品仓",
                base_qty=Decimal("800"),
            ),
            WarehouseRow(
                warehouse_code="01.02",
                warehouse_name="原料仓",
                base_qty=Decimal("434.50"),
            ),
        ]
        detail = InventoryDetail(
            material_code="07.01.001",
            material_name="潜水镜",
            specification="GT38-BLK",
            erp_class="9",
            erp_class_label="成品",
            total_qty=Decimal("1234.50"),
            warehouse_count=2,
            rows=rows,
        )
        assert len(detail.rows) == 2
        assert detail.total_qty == Decimal("1234.50")
        assert detail.warehouse_count == 2


class TestErpClassLabels:
    """Tests for ERP_CLASS_LABELS constant."""

    def test_has_exactly_five_keys(self):
        """Mapping must cover exactly the 5 documented ErpClsID values."""
        assert len(ERP_CLASS_LABELS) == 5

    def test_expected_keys(self):
        """Keys are the string codes 1, 2, 3, 4, 9."""
        assert set(ERP_CLASS_LABELS.keys()) == {"1", "2", "3", "4", "9"}

    def test_expected_values(self):
        """Each code maps to the correct Chinese label."""
        assert ERP_CLASS_LABELS["1"] == "外购"
        assert ERP_CLASS_LABELS["2"] == "自制"
        assert ERP_CLASS_LABELS["3"] == "委外"
        assert ERP_CLASS_LABELS["4"] == "虚拟件"
        assert ERP_CLASS_LABELS["9"] == "成品"
