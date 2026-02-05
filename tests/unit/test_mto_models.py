"""Tests for src/models/mto_status.py"""

from datetime import datetime
from decimal import Decimal

import pytest

from src.models.mto_status import ChildItem, MTOStatusResponse, MTOSummary, ParentItem


class TestParentItem:
    """Tests for ParentItem model."""

    def test_minimal_parent(self):
        """Test creating minimal ParentItem."""
        parent = ParentItem(mto_number="AK2510034")
        assert parent.mto_number == "AK2510034"
        assert parent.customer_name == ""
        assert parent.delivery_date is None

    def test_full_parent(self):
        """Test creating ParentItem with all fields."""
        parent = ParentItem(
            mto_number="AK2510034",
            customer_name="Customer A",
            delivery_date="2025-02-01",
        )
        assert parent.mto_number == "AK2510034"
        assert parent.customer_name == "Customer A"
        assert parent.delivery_date == "2025-02-01"


class TestChildItem:
    """Tests for ChildItem model."""

    def test_valid_child(self):
        """Test creating valid ChildItem."""
        child = ChildItem(
            material_code="M001",
            material_name="Material",
            specification="Spec",
            aux_attributes="Blue",
            material_type=1,
            material_type_name="Self-made",
            sales_order_qty=Decimal("0"),
            prod_instock_must_qty=Decimal("100"),
            purchase_order_qty=Decimal("0"),
            pick_actual_qty=Decimal("8"),
            prod_instock_real_qty=Decimal("30"),
            purchase_stock_in_qty=Decimal("0"),
        )
        assert child.material_code == "M001"
        assert child.material_type == 1
        assert child.prod_instock_must_qty == Decimal("100")

    def test_serialization_aliases(self):
        """Test serialization aliases are applied."""
        child = ChildItem(
            material_code="M001",
            material_name="Material",
            specification="Spec",
            aux_attributes="",
            material_type=2,
            material_type_name="Purchased",
            sales_order_qty=Decimal("0"),
            prod_instock_must_qty=Decimal("0"),
            purchase_order_qty=Decimal("100"),
            pick_actual_qty=Decimal("0"),
            prod_instock_real_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("80"),
        )

        # Serialize with aliases
        data = child.model_dump(by_alias=True)

        # Check aliases are used
        assert "material_type_code" in data
        assert "material_type" in data  # This is material_type_name aliased
        assert "sales_order_qty" in data
        assert "prod_instock_real_qty" in data

        # Check values
        assert data["material_type_code"] == 2
        assert data["material_type"] == "Purchased"
        assert data["purchase_stock_in_qty"] == Decimal("80")

    def test_zero_decimal_values(self):
        """Test ChildItem with all zero decimal values."""
        child = ChildItem(
            material_code="M001",
            material_name="Material",
            specification="",
            aux_attributes="",
            material_type=1,
            material_type_name="Self-made",
            sales_order_qty=Decimal("0"),
            prod_instock_must_qty=Decimal("0"),
            purchase_order_qty=Decimal("0"),
            pick_actual_qty=Decimal("0"),
            prod_instock_real_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("0"),
        )
        assert child.prod_instock_must_qty == Decimal("0")


class TestMTOStatusResponse:
    """Tests for MTOStatusResponse model."""

    def test_minimal_response(self):
        """Test creating minimal response."""
        response = MTOStatusResponse(
            mto_number="AK2510034",
            parent=ParentItem(mto_number="AK2510034"),
            children=[],
            query_time=datetime(2025, 1, 15, 10, 30),
        )
        assert response.mto_number == "AK2510034"
        assert response.data_source == "live"  # Default
        assert response.cache_age_seconds is None

    def test_cache_response(self):
        """Test response from cache."""
        response = MTOStatusResponse(
            mto_number="AK2510034",
            parent=ParentItem(mto_number="AK2510034"),
            children=[],
            query_time=datetime(2025, 1, 15, 10, 30),
            data_source="cache",
            cache_age_seconds=300,
        )
        assert response.data_source == "cache"
        assert response.cache_age_seconds == 300

    def test_response_with_children(self, sample_mto_response):
        """Test response with children."""
        assert len(sample_mto_response.children) == 1
        assert sample_mto_response.children[0].material_code == "C001"

    def test_serialization_aliases(self):
        """Test serialization aliases in response."""
        response = MTOStatusResponse(
            mto_number="AK2510034",
            parent=ParentItem(mto_number="AK2510034"),
            children=[],
            query_time=datetime(2025, 1, 15, 10, 30),
        )

        data = response.model_dump(by_alias=True)

        # Check aliases
        assert "parent_item" in data
        assert "child_items" in data


class TestMTOSummary:
    """Tests for MTOSummary model."""

    def test_valid_summary(self):
        """Test creating valid summary."""
        summary = MTOSummary(
            mto_number="AK2510034",
            material_name="Finished Product",
            order_qty=Decimal("100"),
            status="Approved",
        )
        assert summary.mto_number == "AK2510034"
        assert summary.material_name == "Finished Product"
        assert summary.order_qty == Decimal("100")
        assert summary.status == "Approved"
