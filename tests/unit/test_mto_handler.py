"""Tests for src/query/mto_handler.py - Config-driven MTO query logic."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.query.mto_handler import (
    MaterialType,
    MTOQueryHandler,
    _sum_by_material,
    _sum_by_material_and_aux,
)
from src.readers.models import (
    ProductionOrderModel,
    PurchaseOrderModel,
    SalesOrderModel,
    ProductionReceiptModel,
    SalesDeliveryModel,
)


class TestMaterialType:
    """Tests for MaterialType enum."""

    def test_material_type_values(self):
        """Test MaterialType enum values."""
        assert MaterialType.SELF_MADE == 1
        assert MaterialType.PURCHASED == 2
        assert MaterialType.SUBCONTRACTED == 3

    def test_display_names(self):
        """Test display name properties."""
        assert MaterialType.SELF_MADE.display_name == "自制"
        assert MaterialType.PURCHASED.display_name == "外购"
        assert MaterialType.SUBCONTRACTED.display_name == "委外"


class TestSumByMaterial:
    """Tests for _sum_by_material helper."""

    def test_sum_by_material_basic(self):
        """Test summing quantities by material code."""
        records = [
            MagicMock(material_code="M001", real_qty=Decimal("10")),
            MagicMock(material_code="M001", real_qty=Decimal("20")),
            MagicMock(material_code="M002", real_qty=Decimal("5")),
        ]

        result = _sum_by_material(records, "real_qty")

        assert result["M001"] == Decimal("30")
        assert result["M002"] == Decimal("5")

    def test_sum_by_material_empty(self):
        """Test with empty records."""
        result = _sum_by_material([], "real_qty")
        assert result == {}

    def test_sum_by_material_single_record(self):
        """Test with single record."""
        records = [MagicMock(material_code="M001", order_qty=Decimal("100"))]

        result = _sum_by_material(records, "order_qty")

        assert result["M001"] == Decimal("100")

    def test_sum_by_material_missing_material_code(self):
        """Test records with empty material code are skipped."""
        records = [
            MagicMock(material_code="M001", qty=Decimal("10")),
            MagicMock(material_code="", qty=Decimal("5")),
            MagicMock(material_code="M001", qty=Decimal("10")),
        ]

        result = _sum_by_material(records, "qty")

        assert result["M001"] == Decimal("20")
        assert "" not in result


class TestSumByMaterialAndAux:
    """Tests for _sum_by_material_and_aux helper."""

    def test_sum_by_material_and_aux_basic(self):
        """Test summing quantities by (material_code, aux_prop_id) tuple."""
        records = [
            MagicMock(material_code="M001", aux_prop_id=1, real_qty=Decimal("10")),
            MagicMock(material_code="M001", aux_prop_id=1, real_qty=Decimal("20")),
            MagicMock(material_code="M001", aux_prop_id=2, real_qty=Decimal("5")),  # Different aux
            MagicMock(material_code="M002", aux_prop_id=1, real_qty=Decimal("15")),
        ]

        result = _sum_by_material_and_aux(records, "real_qty")

        assert result[("M001", 1)] == Decimal("30")
        assert result[("M001", 2)] == Decimal("5")
        assert result[("M002", 1)] == Decimal("15")

    def test_sum_by_material_and_aux_zero_aux(self):
        """Test with aux_prop_id=0 (no variant)."""
        records = [
            MagicMock(material_code="M001", aux_prop_id=0, real_qty=Decimal("10")),
            MagicMock(material_code="M001", aux_prop_id=0, real_qty=Decimal("5")),
        ]

        result = _sum_by_material_and_aux(records, "real_qty")

        assert result[("M001", 0)] == Decimal("15")


class TestMTOQueryHandler:
    """Tests for MTOQueryHandler.get_status method with config-driven logic."""

    def create_handler(self, mock_readers, cache_reader=None):
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
            cache_reader=cache_reader,
        )

    @pytest.mark.asyncio
    async def test_get_status_no_data_raises(self, mock_readers):
        """Test ValueError when no data found for MTO."""
        # Mock all source forms to return empty
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers)

        with pytest.raises(ValueError, match="No data found for MTO"):
            await handler.get_status("NONEXISTENT", use_cache=False)

    @pytest.mark.asyncio
    async def test_get_status_sales_order_07_class(
        self, mock_readers, sample_sales_orders, sample_production_receipts, sample_sales_deliveries
    ):
        """Test get_status with 07.xx.xxx items from SAL_SaleOrder."""
        # Setup mocks
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sample_sales_orders
        )
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=sample_production_receipts
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(
            return_value=sample_sales_deliveries
        )
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={1001: "蓝色款", 1002: "红色款"}
        )

        handler = self.create_handler(mock_readers)

        result = await handler.get_status("AS2509076", use_cache=False)

        assert result.mto_number == "AS2509076"
        assert result.data_source == "live"
        # Should have 2 children (2 separate sales order rows, no aggregation)
        assert len(result.children) == 2
        # First child
        assert result.children[0].material_code == "07.02.037"
        assert result.children[0].required_qty == Decimal("2016")
        assert result.children[0].material_type_name == "成品"
        # Second child (different order)
        assert result.children[1].material_code == "07.02.037"
        assert result.children[1].required_qty == Decimal("1")

    @pytest.mark.asyncio
    async def test_get_status_purchase_order_03_class(
        self, mock_readers, sample_purchase_orders
    ):
        """Test get_status with 03.xx.xxx items from PUR_PurchaseOrder."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(
            return_value=sample_purchase_orders
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers)

        result = await handler.get_status("AS2509076", use_cache=False)

        assert result.mto_number == "AS2509076"
        # Should have children from purchase orders
        assert len(result.children) >= 1
        for child in result.children:
            assert child.material_code.startswith("03.")
            assert child.material_type_name == "外购"
            # Purchase orders use their own stock_in_qty for receipt
            assert child.receipt_source == "PUR_PurchaseOrder"

    @pytest.mark.asyncio
    async def test_get_status_production_order_05_class(
        self, mock_readers, sample_production_order_05
    ):
        """Test get_status with 05.xx.xxx items from PRD_MO."""
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[sample_production_order_05]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers)

        result = await handler.get_status("AS2509076", use_cache=False)

        assert len(result.children) == 1
        child = result.children[0]
        assert child.material_code == "05.01.001"
        assert child.material_type_name == "自制"
        assert child.receipt_source == "PRD_INSTOCK"

    @pytest.mark.asyncio
    async def test_get_status_cache_miss_fallback_to_live(
        self, mock_readers, sample_sales_orders
    ):
        """Test cache miss falls back to live API."""
        from src.query.cache_reader import CacheResult

        mock_cache = MagicMock()
        # Mock all cache methods to return empty (cache miss)
        mock_cache.get_sales_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )
        mock_cache.get_production_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )
        mock_cache.get_purchase_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )
        mock_cache.get_production_receipts = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )
        mock_cache.get_purchase_receipts = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )
        mock_cache.get_material_picking = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )
        mock_cache.get_sales_delivery = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )

        # Setup live API mocks
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sample_sales_orders
        )
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)

        result = await handler.get_status("AS2509076", use_cache=True)

        assert result.data_source == "live"

    @pytest.mark.asyncio
    async def test_get_status_cache_hit(
        self, mock_readers, sample_sales_orders
    ):
        """Test cache hit returns cached data."""
        from datetime import datetime
        from src.query.cache_reader import CacheResult

        mock_cache = MagicMock()
        synced_at = datetime.utcnow()

        # Mock cache to return sales orders (cache hit)
        mock_cache.get_sales_orders = AsyncMock(
            return_value=CacheResult(
                data=sample_sales_orders,
                synced_at=synced_at,
                is_fresh=True,
            )
        )
        mock_cache.get_production_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_purchase_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_production_receipts = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_purchase_receipts = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_material_picking = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_sales_delivery = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)

        result = await handler.get_status("AS2509076", use_cache=True)

        assert result.data_source == "cache"
        assert result.cache_age_seconds is not None

    @pytest.mark.asyncio
    async def test_get_status_use_cache_false_skips_cache(
        self, mock_readers, sample_sales_orders
    ):
        """Test use_cache=False skips cache lookup."""
        from datetime import datetime
        from src.query.cache_reader import CacheResult

        mock_cache = MagicMock()
        mock_cache.get_sales_orders = AsyncMock(
            return_value=CacheResult(
                data=sample_sales_orders,
                synced_at=datetime.utcnow(),
                is_fresh=True,
            )
        )

        # Setup live API mocks
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=sample_sales_orders
        )
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)

        result = await handler.get_status("AS2509076", use_cache=False)

        assert result.data_source == "live"
        mock_cache.get_sales_orders.assert_not_called()


# Test fixtures
@pytest.fixture
def mock_readers():
    """Create mock reader instances."""
    readers = {}
    for name in [
        "production_order",
        "production_bom",
        "production_receipt",
        "purchase_order",
        "purchase_receipt",
        "subcontracting_order",
        "material_picking",
        "sales_delivery",
        "sales_order",
    ]:
        mock = MagicMock()
        mock.client = MagicMock()
        mock.client.lookup_aux_properties = AsyncMock(return_value={})
        readers[name] = mock
    return readers


@pytest.fixture
def sample_sales_orders():
    """Sample sales orders for 07.xx.xxx (成品) testing."""
    return [
        SalesOrderModel(
            bill_no="SO001",
            mto_number="AS2509076",
            material_code="07.02.037",
            material_name="成品A",
            specification="规格1",
            aux_attributes="",
            aux_prop_id=1001,
            customer_name="客户A",
            delivery_date="2025-03-01",
            qty=Decimal("2016"),
        ),
        SalesOrderModel(
            bill_no="SO002",
            mto_number="AS2509076",
            material_code="07.02.037",
            material_name="成品A",
            specification="规格1",
            aux_attributes="",
            aux_prop_id=1001,  # Same variant, different order
            customer_name="客户A",
            delivery_date="2025-03-01",
            qty=Decimal("1"),
        ),
    ]


@pytest.fixture
def sample_production_receipts():
    """Sample production receipts for matching."""
    return [
        ProductionReceiptModel(
            mto_number="AS2509076",
            material_code="07.02.037",
            real_qty=Decimal("2016"),
            must_qty=Decimal("2016"),
            aux_prop_id=1001,
            mo_bill_no="MO001",
        ),
        ProductionReceiptModel(
            mto_number="AS2509076",
            material_code="07.02.037",
            real_qty=Decimal("1"),
            must_qty=Decimal("1"),
            aux_prop_id=1001,
            mo_bill_no="MO002",
        ),
    ]


@pytest.fixture
def sample_sales_deliveries():
    """Sample sales deliveries for matching."""
    return [
        SalesDeliveryModel(
            mto_number="AS2509076",
            material_code="07.02.037",
            real_qty=Decimal("2016"),
            must_qty=Decimal("2016"),
            aux_prop_id=1001,
        ),
    ]


@pytest.fixture
def sample_purchase_orders():
    """Sample purchase orders for 03.xx.xxx (外购) testing."""
    return [
        PurchaseOrderModel(
            bill_no="PO001",
            mto_number="AS2509076",
            material_code="03.01.001",
            material_name="外购件A",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            order_qty=Decimal("100"),
            stock_in_qty=Decimal("80"),
            remain_stock_in_qty=Decimal("20"),
        ),
    ]


@pytest.fixture
def sample_production_order_05():
    """Sample production order for 05.xx.xxx (自制) testing."""
    return ProductionOrderModel(
        bill_no="MO003",
        mto_number="AS2509076",
        workshop="车间A",
        material_code="05.01.001",
        material_name="自制件A",
        specification="",
        aux_attributes="",
        qty=Decimal("50"),
        status="审核",
        create_date="2025-01-15",
    )
