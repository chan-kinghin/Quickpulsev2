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
    MaterialPickingModel,
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
        assert MaterialType.PURCHASED.display_name == "包材"
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
        # Aggregated by (material_code, aux_prop_id)
        assert len(result.children) == 1
        child = result.children[0]
        assert child.material_code == "07.02.037"
        assert child.sales_order_qty == Decimal("2017")
        assert child.prod_instock_real_qty == Decimal("2017")
        assert child.material_type_name == "成品"

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
            assert child.material_type_name == "包材"
            assert child.purchase_order_qty == Decimal("100")
            assert child.purchase_stock_in_qty == Decimal("80")

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
        assert child.prod_instock_must_qty == Decimal("50")
        assert child.prod_instock_real_qty == Decimal("0")
        assert child.pick_actual_qty == Decimal("0")

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
        mock_cache.get_production_bom_by_mto = AsyncMock(
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
        mock_cache.get_production_bom_by_mto = AsyncMock(
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

    @pytest.mark.asyncio
    async def test_selfmade_uses_prd_mo_qty_not_receipt_sum(
        self, mock_readers, sample_selfmade_receipts_overlapping, sample_production_order_for_receipts
    ):
        """Test that self-made 应收数量 uses PRD_MO.FQty, not sum of receipt FMustQty.

        Regression test: summing FMustQty across partial receipts gives inflated values
        (e.g., 2219 instead of 1008) because each receipt carries full/remaining expected qty.
        """
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[sample_production_order_for_receipts]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=sample_selfmade_receipts_overlapping
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={2001: "镜圈镜带实色红潘通230C"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2511034", use_cache=False)

        assert len(result.children) == 1
        child = result.children[0]
        assert child.material_code == "05.01.001"
        assert child.material_type_name == "自制"
        # KEY ASSERTION: must use PRD_MO.FQty (1008), NOT receipt sum (1211 + 1008 = 2219)
        assert child.prod_instock_must_qty == Decimal("1008")
        # Real qty should be correct sum (additive)
        assert child.prod_instock_real_qty == Decimal("1008")

    @pytest.mark.asyncio
    async def test_03_with_prd_mo_routes_as_selfmade(self, mock_readers):
        """03.xx material with PRD_MO (工段) routes through self-made path.

        纸箱工段等 03.xx 包材如果有生产订单, 应按自制处理:
        - prod_instock_real_qty 来自 PRD_INSTOCK.FRealQty
        - prod_instock_must_qty 来自 PRD_MO.FQty
        - material_type_name 显示 "自制"
        """
        prod_order_03 = ProductionOrderModel(
            bill_no="MO200",
            mto_number="AS2512032",
            workshop="纸箱工段",
            material_code="03.05.001",
            material_name="纸箱A",
            specification="",
            aux_prop_id=0,
            qty=Decimal("500"),
            status="已审核",
            create_date="2025-12-01",
        )
        receipt_03 = ProductionReceiptModel(
            bill_no="RK200",
            mto_number="AS2512032",
            material_code="03.05.001",
            material_name="纸箱A",
            specification="",
            real_qty=Decimal("300"),
            must_qty=Decimal("500"),
            aux_prop_id=0,
            mo_bill_no="MO200",
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order_03]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt_03]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512032", use_cache=False)

        assert len(result.children) == 1
        child = result.children[0]
        assert child.material_code == "03.05.001"
        assert child.material_type_name == "自制"
        assert child.prod_instock_must_qty == Decimal("500")
        assert child.prod_instock_real_qty == Decimal("300")

    @pytest.mark.asyncio
    async def test_03_without_prd_mo_stays_purchased(self, mock_readers):
        """03.xx material without PRD_MO stays on purchased path.

        无工段的 03.xx 物料保持外购路径, purchase_order_qty 正常显示。
        """
        purchase_03 = PurchaseOrderModel(
            bill_no="PO200",
            mto_number="AS2512032",
            material_code="03.01.010",
            material_name="外购包材B",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            order_qty=Decimal("200"),
            stock_in_qty=Decimal("150"),
            remain_stock_in_qty=Decimal("50"),
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(
            return_value=[purchase_03]
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512032", use_cache=False)

        assert len(result.children) >= 1
        child = result.children[0]
        assert child.material_code == "03.01.010"
        assert child.material_type_name == "包材"
        assert child.purchase_order_qty == Decimal("200")
        assert child.purchase_stock_in_qty == Decimal("150")

    @pytest.mark.asyncio
    async def test_03_with_prd_mo_no_receipt_shows_planned(self, mock_readers):
        """03.xx with PRD_MO but no PRD_INSTOCK shows as self-made with zero receipt.

        有工段但还没入库的 03.xx 物料, 应收数量 = PRD_MO.FQty, 实收数量 = 0。
        """
        prod_order_03 = ProductionOrderModel(
            bill_no="MO300",
            mto_number="AS2512032",
            workshop="吸塑工段",
            material_code="03.06.002",
            material_name="吸塑托盘",
            specification="",
            aux_prop_id=0,
            qty=Decimal("1000"),
            status="计划确认",
            create_date="2025-12-05",
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order_03]
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
        result = await handler.get_status("AS2512032", use_cache=False)

        assert len(result.children) == 1
        child = result.children[0]
        assert child.material_code == "03.06.002"
        assert child.material_type_name == "自制"
        assert child.prod_instock_must_qty == Decimal("1000")
        assert child.prod_instock_real_qty == Decimal("0")

    @pytest.mark.asyncio
    async def test_mixed_03_with_and_without_prd_mo(self, mock_readers):
        """Same MTO with 03.xx materials: one with 工段 (self-made), one without (purchased).

        同一 MTO 中混合: 有工段的 03.xx → 自制, 无工段的 03.xx → 外购。
        """
        # 03.05.001 has PRD_MO → self-made
        prod_order_03 = ProductionOrderModel(
            bill_no="MO400",
            mto_number="AS2512032",
            workshop="纸箱工段",
            material_code="03.05.001",
            material_name="纸箱A",
            specification="",
            aux_prop_id=0,
            qty=Decimal("500"),
            status="已审核",
            create_date="2025-12-01",
        )
        receipt_03 = ProductionReceiptModel(
            bill_no="RK400",
            mto_number="AS2512032",
            material_code="03.05.001",
            real_qty=Decimal("300"),
            must_qty=Decimal("500"),
            aux_prop_id=0,
            mo_bill_no="MO400",
        )
        # 03.01.010 has PUR only → purchased
        purchase_03 = PurchaseOrderModel(
            bill_no="PO400",
            mto_number="AS2512032",
            material_code="03.01.010",
            material_name="外购包材B",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            order_qty=Decimal("200"),
            stock_in_qty=Decimal("150"),
            remain_stock_in_qty=Decimal("50"),
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order_03]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(
            return_value=[purchase_03]
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt_03]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512032", use_cache=False)

        selfmade = [c for c in result.children if c.material_type_name == "自制"]
        purchased = [c for c in result.children if c.material_type_name == "包材"]

        assert len(selfmade) == 1
        assert selfmade[0].material_code == "03.05.001"
        assert selfmade[0].prod_instock_real_qty == Decimal("300")

        assert len(purchased) >= 1
        pur_child = [c for c in purchased if c.material_code == "03.01.010"]
        assert len(pur_child) == 1
        assert pur_child[0].purchase_order_qty == Decimal("200")

    @pytest.mark.asyncio
    async def test_03_with_prd_mo_not_duplicated_in_purchased(self, mock_readers):
        """03.xx with 工段 must NOT appear in both self-made and purchased paths.

        有工段的 03.xx 不应同时出现在自制和外购中, 避免重复计数。
        PPBOM 和 PickMtrl 外购分桶应排除有工段的物料。
        """
        from src.readers.models import ProductionBOMModel

        prod_order_03 = ProductionOrderModel(
            bill_no="MO500",
            mto_number="AS2512032",
            workshop="纸箱工段",
            material_code="03.05.001",
            material_name="纸箱A",
            specification="",
            aux_prop_id=0,
            qty=Decimal("500"),
            status="已审核",
            create_date="2025-12-01",
        )
        receipt_03 = ProductionReceiptModel(
            bill_no="RK500",
            mto_number="AS2512032",
            material_code="03.05.001",
            real_qty=Decimal("300"),
            must_qty=Decimal("500"),
            aux_prop_id=0,
            mo_bill_no="MO500",
        )
        # Same material also appears in PPBOM and PickMtrl — should be excluded from purchased
        bom_03 = ProductionBOMModel(
            mo_bill_no="MO500",
            mto_number="AS2512032",
            material_code="03.05.001",
            material_name="纸箱A",
            specification="",
            aux_prop_id=0,
            material_type=2,
            need_qty=Decimal("500"),
            picked_qty=Decimal("300"),
            no_picked_qty=Decimal("200"),
        )
        pick_03 = MaterialPickingModel(
            bill_no="PM500",
            mto_number="AS2512032",
            material_code="03.05.001",
            app_qty=Decimal("500"),
            actual_qty=Decimal("300"),
            ppbom_bill_no="MO500",
            aux_prop_id=0,
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order_03]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt_03]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(
            return_value=[pick_03]
        )
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )
        # Also mock production_bom reader (used in live path)
        mock_readers["production_bom"].fetch_by_mto = AsyncMock(
            return_value=[bom_03]
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512032", use_cache=False)

        # Should only appear once as self-made, NOT duplicated in purchased
        selfmade = [c for c in result.children if c.material_code == "03.05.001" and c.material_type_name == "自制"]
        purchased = [c for c in result.children if c.material_code == "03.05.001" and c.material_type_name == "包材"]

        assert len(selfmade) == 1
        assert len(purchased) == 0


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
        mock.fetch_by_mto = AsyncMock(return_value=[])
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


@pytest.fixture
def sample_selfmade_receipts_overlapping():
    """Receipts with overlapping FMustQty — each batch carries full/remaining expected qty."""
    return [
        ProductionReceiptModel(
            bill_no="RK001",
            mto_number="AS2511034",
            material_code="05.01.001",
            material_name="硅胶镜圈",
            specification="GST-GS53",
            real_qty=Decimal("500"),
            must_qty=Decimal("1211"),
            aux_prop_id=2001,
            mo_bill_no="MO100",
        ),
        ProductionReceiptModel(
            bill_no="RK002",
            mto_number="AS2511034",
            material_code="05.01.001",
            material_name="硅胶镜圈",
            specification="GST-GS53",
            real_qty=Decimal("508"),
            must_qty=Decimal("1008"),
            aux_prop_id=2001,
            mo_bill_no="MO100",
        ),
    ]


@pytest.fixture
def sample_production_order_for_receipts():
    """PRD_MO record with the correct order quantity."""
    return ProductionOrderModel(
        bill_no="MO100",
        mto_number="AS2511034",
        workshop="成型工段",
        material_code="05.01.001",
        material_name="硅胶镜圈",
        specification="GST-GS53",
        aux_prop_id=2001,
        qty=Decimal("1008"),
        status="已审核",
        create_date="2025-11-27",
    )
