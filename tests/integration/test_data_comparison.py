"""Integration tests for QuickPulse vs Kingdee data comparison.

These tests validate that QuickPulse aggregation logic produces results
that match raw Kingdee API data.

For CI: Uses mocked readers with deterministic test data.
For local integration: Can use real API with KINGDEE_* env vars.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.models.mto_status import ChildItem
from src.query.mto_handler import MTOQueryHandler
from src.readers.models import (
    ProductionReceiptModel,
    SalesDeliveryModel,
    SalesOrderModel,
)


# ============================================================================
# Test Data Fixtures
# ============================================================================


@pytest.fixture
def sales_orders_single_material():
    """Sales orders for a single material code."""
    return [
        SalesOrderModel(
            bill_no="SO001",
            mto_number="TEST001",
            customer_name="Customer A",
            delivery_date="2025-02-01",
            material_code="07.02.001",
            material_name="Product A",
            specification="Spec A",
            aux_attributes="Red-M",
            aux_prop_id=1001,
            qty=Decimal("100"),
        ),
    ]


@pytest.fixture
def sales_orders_multiple_lines():
    """Sales orders with multiple lines for same material (different aux)."""
    return [
        SalesOrderModel(
            bill_no="SO001",
            mto_number="TEST002",
            customer_name="Customer A",
            delivery_date="2025-02-01",
            material_code="07.02.001",
            material_name="Product A",
            specification="Spec A",
            aux_attributes="Red-M",
            aux_prop_id=1001,
            qty=Decimal("100"),
        ),
        SalesOrderModel(
            bill_no="SO001",
            mto_number="TEST002",
            customer_name="Customer A",
            delivery_date="2025-02-01",
            material_code="07.02.001",
            material_name="Product A",
            specification="Spec A",
            aux_attributes="Red-L",
            aux_prop_id=1002,
            qty=Decimal("50"),
        ),
        SalesOrderModel(
            bill_no="SO002",
            mto_number="TEST002",
            customer_name="Customer A",
            delivery_date="2025-02-01",
            material_code="07.02.001",
            material_name="Product A",
            specification="Spec A",
            aux_attributes="Red-M",
            aux_prop_id=1001,
            qty=Decimal("30"),
        ),
    ]


@pytest.fixture
def receipts_matching_sales():
    """Production receipts matching sales orders."""
    return [
        ProductionReceiptModel(
            bill_no="RK001",
            mto_number="TEST002",
            material_code="07.02.001",
            aux_prop_id=1001,
            real_qty=Decimal("80"),
            must_qty=Decimal("130"),
            mo_bill_no="MO001",
        ),
        ProductionReceiptModel(
            bill_no="RK002",
            mto_number="TEST002",
            material_code="07.02.001",
            aux_prop_id=1002,
            real_qty=Decimal("50"),
            must_qty=Decimal("50"),
            mo_bill_no="MO001",
        ),
    ]


@pytest.fixture
def deliveries_matching_sales():
    """Sales deliveries matching sales orders."""
    return [
        SalesDeliveryModel(
            bill_no="DL001",
            mto_number="TEST002",
            material_code="07.02.001",
            aux_prop_id=1001,
            real_qty=Decimal("60"),
            must_qty=Decimal("130"),
        ),
        SalesDeliveryModel(
            bill_no="DL002",
            mto_number="TEST002",
            material_code="07.02.001",
            aux_prop_id=1002,
            real_qty=Decimal("40"),
            must_qty=Decimal("50"),
        ),
    ]


# ============================================================================
# Helper Functions
# ============================================================================


def create_test_handler(mock_readers):
    """Create MTOQueryHandler with mock readers."""
    return MTOQueryHandler(
        production_order_reader=mock_readers["production_order"],
        production_bom_reader=mock_readers["production_bom"],
        production_receipt_reader=mock_readers["production_receipt"],
        purchase_order_reader=mock_readers["purchase_order"],
        purchase_receipt_reader=mock_readers["purchase_receipt"],
        subcontracting_order_reader=mock_readers["subcontracting_order"],
        material_picking_reader=mock_readers["material_picking"],
        sales_delivery_reader=mock_readers["sales_delivery"],
        sales_order_reader=mock_readers["sales_order"],
        memory_cache_enabled=False,
    )


def sum_qty_by_material(children: list[ChildItem], field: str) -> dict[str, Decimal]:
    """Sum a quantity field by material_code from ChildItems."""
    result = {}
    for child in children:
        if child.material_code not in result:
            result[child.material_code] = Decimal(0)
        result[child.material_code] += getattr(child, field, Decimal(0))
    return result


# ============================================================================
# Test Cases
# ============================================================================


class TestSalesOrderAggregation:
    """Tests for sales order (07.xx) aggregation."""

    @pytest.mark.asyncio
    async def test_single_sales_order_required_qty(
        self, mock_readers, sales_orders_single_material
    ):
        """Test sales_order_qty equals sum of sales order FQty."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sales_orders_single_material
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST001", use_cache=False)

        # Filter 07.xx materials
        children_07 = [c for c in result.children if c.material_code.startswith("07.")]
        assert len(children_07) == 1

        child = children_07[0]
        raw_qty = sum(so.qty for so in sales_orders_single_material)

        assert child.sales_order_qty == raw_qty
        assert child.sales_order_qty == Decimal("100")

    @pytest.mark.asyncio
    async def test_multiple_lines_aggregation(
        self, mock_readers, sales_orders_multiple_lines
    ):
        """Test multiple sales order lines aggregate correctly by aux_prop_id."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sales_orders_multiple_lines
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST002", use_cache=False)

        children_07 = [c for c in result.children if c.material_code.startswith("07.")]

        # Should have 2 ChildItems: one for aux 1001, one for aux 1002
        assert len(children_07) == 2

        # Total sales order qty should match raw total
        qp_total = sum(c.sales_order_qty for c in children_07)
        raw_total = sum(so.qty for so in sales_orders_multiple_lines)
        assert qp_total == raw_total
        assert qp_total == Decimal("180")  # 100 + 50 + 30

    @pytest.mark.asyncio
    async def test_receipt_qty_matches_instock(
        self, mock_readers, sales_orders_multiple_lines, receipts_matching_sales
    ):
        """Test prod_instock_real_qty equals sum of PRD_INSTOCK FRealQty."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sales_orders_multiple_lines
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=receipts_matching_sales
        )
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST002", use_cache=False)

        children_07 = [c for c in result.children if c.material_code.startswith("07.")]

        # Total receipt should match raw total
        qp_total = sum(c.prod_instock_real_qty for c in children_07)
        raw_total = sum(r.real_qty for r in receipts_matching_sales)
        assert qp_total == raw_total
        assert qp_total == Decimal("130")  # 80 + 50

    @pytest.mark.asyncio
    async def test_pick_actual_qty_ignored_for_finished_goods(
        self,
        mock_readers,
        sales_orders_multiple_lines,
        receipts_matching_sales,
        deliveries_matching_sales,
    ):
        """Test pick_actual_qty remains zero for finished goods."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sales_orders_multiple_lines
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=receipts_matching_sales
        )
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(
            return_value=deliveries_matching_sales
        )

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST002", use_cache=False)

        children_07 = [c for c in result.children if c.material_code.startswith("07.")]

        # Total picked should match raw total
        qp_total = sum(c.pick_actual_qty for c in children_07)
        assert qp_total == Decimal("0")


class TestAuxPropertyGrouping:
    """Tests for aux_prop_id based grouping."""

    @pytest.mark.asyncio
    async def test_same_material_different_aux_creates_separate_items(
        self, mock_readers, sales_orders_multiple_lines
    ):
        """Test that same material with different aux_prop_id creates separate ChildItems."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sales_orders_multiple_lines
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST002", use_cache=False)

        children_07 = [c for c in result.children if c.material_code.startswith("07.")]

        # Two unique aux_prop_ids: 1001 and 1002
        assert len(children_07) == 2

        # Check each has correct aux_attributes
        aux_attrs = {c.aux_attributes for c in children_07}
        assert aux_attrs == {"Red-M", "Red-L"}

    @pytest.mark.asyncio
    async def test_aux_aggregation_per_variant(
        self, mock_readers, sales_orders_multiple_lines
    ):
        """Test quantities aggregate correctly per aux variant."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sales_orders_multiple_lines
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST002", use_cache=False)

        children_07 = [c for c in result.children if c.material_code.startswith("07.")]

        # Find each variant
        red_m = next((c for c in children_07 if c.aux_attributes == "Red-M"), None)
        red_l = next((c for c in children_07 if c.aux_attributes == "Red-L"), None)

        assert red_m is not None
        assert red_l is not None

        # Red-M: 100 + 30 = 130
        assert red_m.sales_order_qty == Decimal("130")
        # Red-L: 50
        assert red_l.sales_order_qty == Decimal("50")


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_zero_quantities(self, mock_readers):
        """Test handling of zero quantities."""
        sales_orders = [
            SalesOrderModel(
                bill_no="SO001",
                mto_number="TEST003",
                customer_name="Customer A",
                delivery_date="2025-02-01",
                material_code="07.02.001",
                material_name="Product A",
                specification="Spec A",
                aux_attributes="",
                aux_prop_id=0,
                qty=Decimal("0"),
            ),
        ]
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=sales_orders)
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST003", use_cache=False)

        children_07 = [c for c in result.children if c.material_code.startswith("07.")]
        assert len(children_07) == 1
        assert children_07[0].sales_order_qty == Decimal("0")

    @pytest.mark.asyncio
    async def test_no_receipts_no_deliveries(
        self, mock_readers, sales_orders_single_material
    ):
        """Test MTO with only sales orders (no receipts/deliveries)."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sales_orders_single_material
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST001", use_cache=False)

        children_07 = [c for c in result.children if c.material_code.startswith("07.")]
        assert len(children_07) == 1

        child = children_07[0]
        assert child.sales_order_qty == Decimal("100")
        assert child.prod_instock_real_qty == Decimal("0")
        assert child.pick_actual_qty == Decimal("0")

    @pytest.mark.asyncio
    async def test_receipts_exceed_required(self, mock_readers):
        """Test when receipt_qty exceeds required_qty (over-receipt)."""
        sales_orders = [
            SalesOrderModel(
                bill_no="SO001",
                mto_number="TEST004",
                customer_name="Customer A",
                delivery_date="2025-02-01",
                material_code="07.02.001",
                material_name="Product A",
                specification="Spec A",
                aux_attributes="",
                aux_prop_id=0,
                qty=Decimal("100"),
            ),
        ]
        receipts = [
            ProductionReceiptModel(
                bill_no="RK001",
                mto_number="TEST004",
                material_code="07.02.001",
                aux_prop_id=0,
                real_qty=Decimal("150"),  # More than required
                must_qty=Decimal("100"),
                mo_bill_no="MO001",
            ),
        ]
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=sales_orders)
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=receipts)
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])

        handler = create_test_handler(mock_readers)
        result = await handler.get_status("TEST004", use_cache=False)

        children_07 = [c for c in result.children if c.material_code.startswith("07.")]
        assert len(children_07) == 1

        child = children_07[0]
        assert child.sales_order_qty == Decimal("100")
        assert child.prod_instock_real_qty == Decimal("150")
        assert child.prod_instock_real_qty > child.sales_order_qty
