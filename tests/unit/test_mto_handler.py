"""Tests for src/query/mto_handler.py - Config-driven MTO query logic."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.query.cache_reader import BOMJoinedRow
from src.query.mto_handler import (
    MaterialType,
    MTOQueryHandler,
    _sum_by_material,
    _sum_by_material_and_aux,
)
from src.readers.models import (
    MaterialPickingModel,
    ProductionBOMModel,
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
        # prod_instock_must_qty comes from BOM need_qty (PRD_MO.FQty = 50)
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
        # Mock BOM-first cache methods to return empty (cache miss)
        mock_cache.get_sales_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )
        mock_cache.get_production_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )
        mock_cache.get_mto_bom_joined = AsyncMock(
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

        # Mock BOM-first cache to return sales orders (cache hit)
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
        mock_cache.get_mto_bom_joined = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_production_receipts = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_sales_delivery = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_material_picking = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_purchase_receipts = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_purchase_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)

        # raw SQLite cache is now opt-in via source="cache" (retired from the default path)
        result = await handler.get_status("AS2509076", source="cache")

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

    # ---------------------------------------------------------------
    # PUR-only synthetic child aux resolution (cache path)
    # ---------------------------------------------------------------
    # Regression for the bug fixed in docs/PLAN_pur_only_aux_lookup_2026-05-22.md.
    # The cache path collected aux_prop_ids only from SAL + BOM, never from
    # PUR. So synthetic-PUR children (packaging items like 03.23.009 贴纸 that
    # have no PPBOM line) silently showed "-" for 辅助属性 even though
    # BD_FLEXSITEMDETAILV had rich descriptions for those IDs.
    def _empty_cache_mock(self, synced_at, mto_number="AK2508006"):
        """Cache mock with empty BOM/SAL/receipts but ONE minimal PRD_MO so
        _try_cache doesn't bail early at the "need at least some source data"
        check (mto_handler.py line 388). Purchase orders are NOT preset — set
        them in the test for clarity."""
        from src.query.cache_reader import CacheResult
        mock_cache = MagicMock()
        empty = CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        mock_cache.get_sales_orders = AsyncMock(return_value=empty)
        mock_cache.get_production_orders = AsyncMock(
            return_value=CacheResult(
                data=[ProductionOrderModel(
                    bill_no="MO_STUB",
                    mto_number=mto_number,
                    workshop="",
                    material_code="05.99.999",
                    material_name="stub",
                    specification="",
                    aux_prop_id=0,
                    qty=Decimal("1"),
                    status="已审核",
                    create_date="2026-05-22",
                )],
                synced_at=synced_at,
                is_fresh=True,
            )
        )
        mock_cache.get_mto_bom_joined = AsyncMock(return_value=empty)
        mock_cache.get_production_receipts = AsyncMock(return_value=empty)
        mock_cache.get_sales_delivery = AsyncMock(return_value=empty)
        mock_cache.get_material_picking = AsyncMock(return_value=empty)
        mock_cache.get_purchase_receipts = AsyncMock(return_value=empty)
        return mock_cache

    @pytest.mark.asyncio
    async def test_cache_path_pur_only_child_resolves_aux_attributes(
        self, mock_readers
    ):
        from datetime import datetime
        from src.query.cache_reader import CacheResult

        synced_at = datetime.utcnow()
        mock_cache = self._empty_cache_mock(synced_at)
        mock_cache.get_purchase_orders = AsyncMock(
            return_value=CacheResult(
                data=[
                    PurchaseOrderModel(
                        bill_no="PO900",
                        mto_number="AK2508006",
                        material_code="03.23.009",
                        material_name="贴纸",
                        specification="",
                        aux_attributes="",
                        aux_prop_id=114367,
                        order_qty=Decimal("35456"),
                        stock_in_qty=Decimal("35456"),
                        remain_stock_in_qty=Decimal("0"),
                    )
                ],
                synced_at=synced_at,
                is_fresh=True,
            )
        )
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={
                114367: "JSC儿童款泳帽可移动价格贴纸,UK24×26MM/Pantone 485C,3.99",
            }
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)
        result = await handler.get_status("AK2508006", source="cache")

        assert result.data_source == "cache"
        stickers = [c for c in result.children if c.material_code == "03.23.009"]
        assert len(stickers) == 1
        assert (
            stickers[0].aux_attributes
            == "JSC儿童款泳帽可移动价格贴纸,UK24×26MM/Pantone 485C,3.99"
        )
        # Confirm purchase_orders aux IDs reached lookup_aux_properties
        called_with = mock_readers["production_order"].client.lookup_aux_properties.await_args
        assert 114367 in (called_with.args[0] if called_with.args else [])

    @pytest.mark.asyncio
    async def test_cache_path_pur_only_child_missing_description_falls_back_to_empty(
        self, mock_readers
    ):
        from datetime import datetime
        from src.query.cache_reader import CacheResult

        synced_at = datetime.utcnow()
        mock_cache = self._empty_cache_mock(synced_at)
        mock_cache.get_purchase_orders = AsyncMock(
            return_value=CacheResult(
                data=[
                    PurchaseOrderModel(
                        bill_no="PO901",
                        mto_number="AK2508006",
                        material_code="03.23.009",
                        material_name="贴纸",
                        specification="",
                        aux_attributes="",
                        aux_prop_id=999999,
                        order_qty=Decimal("100"),
                        stock_in_qty=Decimal("0"),
                        remain_stock_in_qty=Decimal("100"),
                    )
                ],
                synced_at=synced_at,
                is_fresh=True,
            )
        )
        # Kingdee has no description for this ID
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)
        result = await handler.get_status("AK2508006", source="cache")

        stickers = [c for c in result.children if c.material_code == "03.23.009"]
        assert len(stickers) == 1
        assert stickers[0].aux_attributes == ""

    @pytest.mark.asyncio
    async def test_cache_path_pur_only_child_aux_zero_not_in_lookup(
        self, mock_readers
    ):
        from datetime import datetime
        from src.query.cache_reader import CacheResult

        synced_at = datetime.utcnow()
        mock_cache = self._empty_cache_mock(synced_at, mto_number="AS2509001")
        mock_cache.get_purchase_orders = AsyncMock(
            return_value=CacheResult(
                data=[
                    PurchaseOrderModel(
                        bill_no="PO902",
                        mto_number="AS2509001",
                        material_code="03.01.010",
                        material_name="包材",
                        specification="",
                        aux_attributes="",
                        aux_prop_id=0,
                        order_qty=Decimal("200"),
                        stock_in_qty=Decimal("0"),
                        remain_stock_in_qty=Decimal("200"),
                    )
                ],
                synced_at=synced_at,
                is_fresh=True,
            )
        )
        lookup_mock = AsyncMock(return_value={})
        mock_readers["production_order"].client.lookup_aux_properties = lookup_mock

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)
        result = await handler.get_status("AS2509001", source="cache")

        children = [c for c in result.children if c.material_code == "03.01.010"]
        assert len(children) == 1
        assert children[0].aux_attributes == ""
        # aux_prop_id=0 must NOT be added to the lookup set
        called_with = lookup_mock.await_args.args[0] if lookup_mock.await_args.args else []
        assert 0 not in called_with

    @pytest.mark.asyncio
    async def test_selfmade_uses_bom_need_qty_not_receipt_sum(
        self, mock_readers, sample_selfmade_receipts_overlapping, sample_production_order_for_receipts
    ):
        """Test that self-made 应收数量 uses BOM need_qty, not summed receipt FMustQty.

        PRD_INSTOCK.FMustQty per receipt carries the full/remaining expected qty —
        these overlap and are NOT additive. Summing them produces inflated values
        (e.g., 1211 + 1008 = 2219 instead of actual demand 1008).
        Correct source: PPBOM.FMustQty or PRD_MO.FQty.
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
        # prod_instock_must_qty = PRD_MO.FQty (BOM demand), NOT sum of receipt FMustQty
        assert child.prod_instock_must_qty == Decimal("1008")
        # Real qty should be correct sum (additive)
        assert child.prod_instock_real_qty == Decimal("1008")

    @pytest.mark.asyncio
    async def test_regression_must_qty_never_from_receipt_sum(
        self, mock_readers, sample_selfmade_receipts_overlapping, sample_production_order_for_receipts
    ):
        """REGRESSION GUARD (bug-patterns.md #10): prod_instock_must_qty must NEVER
        equal the sum of PRD_INSTOCK.FMustQty (1211 + 1008 = 2219).

        Receipt FMustQty values overlap across batches — they are NOT additive.
        If this test fails, someone changed the data source back to
        row.prod_receipt_must_qty. Revert that change.

        History: fixed b8e6fc7, regressed 265303a, re-fixed 2026-03-30.
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

        child = result.children[0]
        inflated_sum = Decimal("2219")  # 1211 + 1008 — the WRONG value
        assert child.prod_instock_must_qty != inflated_sum, (
            "prod_instock_must_qty equals summed receipt FMustQty (2219). "
            "This is a known regression — receipt FMustQty values overlap across "
            "batches and must NOT be summed. Use row.need_qty instead. "
            "See bug-patterns.md #10."
        )
        assert child.prod_instock_must_qty == Decimal("1008")  # PRD_MO.FQty

    @pytest.mark.asyncio
    async def test_regression_must_qty_never_from_bom_rollup_sum(self, mock_readers):
        """REGRESSION GUARD (bug-patterns.md #10, BOM-rollup variant): when the
        SAME self-made (code, aux) appears in N parent PPBOM lines within one MTO,
        the resulting need_qty MUST be the production target (PRD_MO.FQty), NOT
        the sum across the N parent lines.

        Concrete scenario (mirrors AK2510034 / 05.02.08.027 in dev):
        - Self-made component appears in 3 parent BOMs, each with need_qty=100
        - PRD_MO has one row for this component with qty=100
        - Old (buggy) live builder: SUM(100, 100, 100) = 300
        - Correct: PRD_MO.FQty = 100

        If this test fails with prod_instock_must_qty == 300, the bug has
        regressed: someone reverted the self-made branch in
        _build_bom_joined_rows_from_live (Step 1) back to
        `sum(b.need_qty for b in bom_list)`. The summation is correct ONLY for
        purchased/subcontracted (material_type ∈ {2,3}) — see the
        REGRESSION GUARD comment block at the call site.

        Introduced 2026-04-26. Companion to
        test_regression_must_qty_never_from_receipt_sum.
        """
        from src.readers.models import ProductionBOMModel

        mto = "BOMR0001"
        # 3 parent BOMs all consuming the same self-made component, each line
        # carrying the full demand for THAT parent (3 × 100 = 300 inflated).
        bom_lines = [
            ProductionBOMModel(
                mo_bill_no=f"MO{i:03d}",
                mto_number=mto,
                material_code="05.02.08.027",
                material_name="盒子",
                specification="",
                aux_prop_id=0,
                material_type=1,  # 自制
                need_qty=Decimal("100"),
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("100"),
            )
            for i in range(3)
        ]
        # Single PRD_MO row carrying the team's actual production target.
        prod_order = ProductionOrderModel(
            bill_no="MO_TARGET",
            mto_number=mto,
            workshop="组装工段",
            material_code="05.02.08.027",
            material_name="盒子",
            specification="",
            aux_prop_id=0,
            qty=Decimal("100"),  # actual production target
            status="已审核",
            create_date="2026-04-20",
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order]
        )
        mock_readers["production_bom"].fetch_by_mto = AsyncMock(
            return_value=bom_lines
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
        result = await handler.get_status(mto, use_cache=False)

        assert len(result.children) == 1
        child = result.children[0]
        assert child.material_code == "05.02.08.027"
        assert child.material_type_name == "自制"
        inflated_sum = Decimal("300")  # 3 × 100 — the WRONG value
        assert child.prod_instock_must_qty != inflated_sum, (
            "prod_instock_must_qty equals SUM(need_qty) across BOM lines (300). "
            "This is a known regression — when a self-made component appears in "
            "N parent BOMs within one MTO, summing inflates by N×. Use "
            "PRD_MO.FQty (or MAX(need_qty) fallback) for self-made. "
            "See bug-patterns.md #10."
        )
        assert child.prod_instock_must_qty == Decimal("100"), (
            "Expected need_qty = PRD_MO.FQty (100), got "
            f"{child.prod_instock_must_qty}"
        )

    @pytest.mark.asyncio
    async def test_bom_rollup_falls_back_to_max_when_no_prd_mo(self, mock_readers):
        """When self-made component has BOM lines but no matching PRD_MO row,
        fall back to MAX(need_qty), not SUM. The largest single parent demand
        is closer to the truth than the cumulative sum across parents.

        Companion to test_regression_must_qty_never_from_bom_rollup_sum: covers
        the COALESCE fallback path for self-made when PRD_MO data is absent
        (e.g., partial sync, or component fabricated without an explicit MO).
        """
        from src.readers.models import ProductionBOMModel

        mto = "BOMR0002"
        bom_lines = [
            ProductionBOMModel(
                mo_bill_no="MO_A",
                mto_number=mto,
                material_code="05.02.08.099",
                material_name="盖子",
                specification="",
                aux_prop_id=0,
                material_type=1,
                need_qty=Decimal("80"),
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("80"),
            ),
            ProductionBOMModel(
                mo_bill_no="MO_B",
                mto_number=mto,
                material_code="05.02.08.099",
                material_name="盖子",
                specification="",
                aux_prop_id=0,
                material_type=1,
                need_qty=Decimal("120"),  # largest
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("120"),
            ),
        ]

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        # No PRD_MO row for this component
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_bom"].fetch_by_mto = AsyncMock(
            return_value=bom_lines
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
        # No PRD_MO and no other source means get_status will raise (no parent).
        # Drive the live builder directly instead.
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=bom_lines,
            prod_orders=[],
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "05.02.08.099"
        # MAX(80, 120) = 120, not SUM(80, 120) = 200
        assert row.need_qty == Decimal("120"), (
            f"Expected MAX(need_qty)=120 fallback, got {row.need_qty}"
        )

    @pytest.mark.asyncio
    async def test_purchased_still_sums_across_bom_lines(self, mock_readers):
        """Purchased materials (material_type=2) MUST keep summing across BOM
        lines — the fix in test_regression_must_qty_never_from_bom_rollup_sum
        applies ONLY to self-made (material_type=1).

        For purchased materials, demand legitimately accumulates across parents
        (you place one combined order). Reverting the sum for purchased would
        under-count purchase demand.
        """
        from src.readers.models import ProductionBOMModel

        bom_lines = [
            ProductionBOMModel(
                mo_bill_no="MO_A",
                mto_number="BOMR0003",
                material_code="03.01.001",
                material_name="包材",
                specification="",
                aux_prop_id=0,
                material_type=2,  # 外购
                need_qty=Decimal("50"),
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("50"),
            ),
            ProductionBOMModel(
                mo_bill_no="MO_B",
                mto_number="BOMR0003",
                material_code="03.01.001",
                material_name="包材",
                specification="",
                aux_prop_id=0,
                material_type=2,
                need_qty=Decimal("70"),
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("70"),
            ),
        ]

        handler = self.create_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=bom_lines,
            prod_orders=[],
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "03.01.001"
        assert row.material_type == 2
        # SUM(50, 70) = 120 — purchased materials accumulate across BOM lines
        assert row.need_qty == Decimal("120"), (
            f"Expected SUM(need_qty)=120 for purchased, got {row.need_qty}"
        )

    @pytest.mark.asyncio
    async def test_bom_aux_zero_rolls_up_prd_mo_across_all_aux(self, mock_readers):
        """Tier-3 fallback: PPBOM has aux=0 (generic), PRD_MO is at one or more
        specific aux values. _lookup_mo_qty must roll up ALL PRD_MO rows for
        the material code, NOT just _mo_qty[(code, 0)].

        Real-data scenario from AS2603009 / 05.07.02.01 鞋撑:
        - PPBOM: 1 line, aux=0, FMustQty=1,130,160 (50× inflated by upstream)
        - PRD_MO: 1 row, aux=105814, FQty=1,662
        - Old _lookup_mo_qty(code, 0): exact miss + (code, 0) miss → ZERO
          → falls through to MAX(b.need_qty) = 1,130,160 (still inflated)
        - Fixed: Tier-3 sums PRD_MO across all aux → 1,662

        This test uses TWO PRD_MO rows at different specific aux to also
        catch the case where production was split across variants and the
        team's total target is the sum (e.g., 1000 + 662 = 1662).
        """
        from src.readers.models import ProductionBOMModel

        mto = "AS2603009"
        # PPBOM: aux=0, generic line carrying inflated demand from upstream
        bom_lines = [
            ProductionBOMModel(
                mo_bill_no="MO260400029",
                mto_number=mto,
                material_code="05.07.02.01",
                material_name="鞋撑",
                specification="",
                aux_prop_id=0,
                material_type=1,
                need_qty=Decimal("1130160"),
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("1130160"),
            ),
        ]
        # PRD_MO: two rows at SPECIFIC aux (none at 0).
        # Total target = 1000 + 662 = 1662.
        prod_orders = [
            ProductionOrderModel(
                bill_no="MO_A",
                mto_number=mto,
                workshop="鞋撑工段",
                material_code="05.07.02.01",
                material_name="鞋撑",
                specification="",
                aux_prop_id=105814,
                qty=Decimal("1000"),
                status="已审核",
                create_date="2026-04-01",
            ),
            ProductionOrderModel(
                bill_no="MO_B",
                mto_number=mto,
                workshop="鞋撑工段",
                material_code="05.07.02.01",
                material_name="鞋撑",
                specification="",
                aux_prop_id=105815,
                qty=Decimal("662"),
                status="已审核",
                create_date="2026-04-01",
            ),
        ]

        handler = self.create_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=bom_lines,
            prod_orders=prod_orders,
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "05.07.02.01"
        # Tier-3: sum PRD_MO across all aux when PPBOM aux=0 → 1000 + 662 = 1662
        assert row.need_qty == Decimal("1662"), (
            f"Expected Tier-3 PRD_MO all-aux rollup = 1662, got {row.need_qty}. "
            "Old behavior would return MAX(b.need_qty) = 1,130,160 (inflated). "
            "See bug-patterns.md #10 — Tier-3 fallback must mirror the "
            "all_aux_rollup tier already present in the receipt-side _get()."
        )
        # And specifically NOT the inflated upstream BOM value:
        assert row.need_qty != Decimal("1130160"), (
            "need_qty fell through to MAX(b.need_qty) — Tier-3 PRD_MO rollup "
            "is missing or returning ZERO. This is the AS2603009/AS2602037 "
            "real-data regression. Inspect _lookup_mo_qty's Tier-3 branch."
        )

    @pytest.mark.asyncio
    async def test_bom_aux_zero_single_specific_prd_mo(self, mock_readers):
        """Tier-3 simpler case: PPBOM aux=0, single PRD_MO at non-zero aux.
        Real-data scenario AS2602037 / 05.06.02.21 水阀 (KD truth = 20,130,
        post-fix-without-Tier-3 = 120,780, ratio 6×)."""
        from src.readers.models import ProductionBOMModel

        mto = "AS2602037"
        bom_lines = [
            ProductionBOMModel(
                mo_bill_no="MO260202221",
                mto_number=mto,
                material_code="05.06.02.21",
                material_name="水阀",
                specification="",
                aux_prop_id=0,
                material_type=1,
                need_qty=Decimal("120780"),  # 6× inflated upstream
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("120780"),
            ),
        ]
        prod_orders = [
            ProductionOrderModel(
                bill_no="MO_TARGET",
                mto_number=mto,
                workshop="组装工段",
                material_code="05.06.02.21",
                material_name="水阀",
                specification="",
                aux_prop_id=107962,  # specific aux, not 0
                qty=Decimal("20130"),
                status="已审核",
                create_date="2026-03-15",
            ),
        ]

        handler = self.create_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=bom_lines,
            prod_orders=prod_orders,
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )
        assert rows[0].need_qty == Decimal("20130"), (
            f"Expected Tier-3 PRD_MO rollup = 20130, got {rows[0].need_qty}. "
            "AS2602037 / 05.06.02.21 regression — see bug-patterns.md #10."
        )

    @pytest.mark.asyncio
    async def test_bom_specific_aux_with_disjoint_prd_mo_aux_falls_back_to_rollup(
        self, mock_readers
    ):
        """Tier 2.5 (Wave 4C): BOM at aux=A (specific) + PRD_MO at aux=B,C
        (different specific) — Tier 1 and Tier 2 both miss; the fallback
        rolls up PRD_MO across all aux for the code so the demand matches
        the team's production target.

        Real-data scenario: AS2602033 / 05.02.12.44 had PPBOM at aux=
        105726/197964/206684/106447/106237 and PRD_MO at aux=221031/221032/
        221033 (FQty 2880 each, total 8640). Pre-Tier-2.5 the BOM-specific-
        aux rows fell to MAX(b.need_qty) and over-counted ~2.7× (~23040
        instead of 8640).

        This test uses a single BOM line at aux=999 (specific) and two
        PRD_MO rows at aux=1000 and aux=1001 (also specific, fully
        disjoint from BOM aux). Expected need_qty = 1000 + 662 = 1662
        (sum of all PRD_MO), NOT MAX(b.need_qty)=2880, NOT ZERO.
        """
        from src.readers.models import ProductionBOMModel

        mto = "AS2602033"
        # PPBOM: single line at SPECIFIC aux=999 with inflated upstream demand.
        bom_lines = [
            ProductionBOMModel(
                mo_bill_no="MO260400099",
                mto_number=mto,
                material_code="05.02.12.44",
                material_name="测试件",
                specification="",
                aux_prop_id=999,
                material_type=1,
                need_qty=Decimal("2880"),
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("2880"),
            ),
        ]
        # PRD_MO: two rows at SPECIFIC aux values, NEITHER matching BOM's 999
        # AND no row at aux=0. Tier 1 (exact 999) misses; Tier 2 ((code,0))
        # misses; Tier 2.5 must roll up all PRD_MO → 1000 + 662 = 1662.
        prod_orders = [
            ProductionOrderModel(
                bill_no="MO_X",
                mto_number=mto,
                workshop="组装工段",
                material_code="05.02.12.44",
                material_name="测试件",
                specification="",
                aux_prop_id=1000,
                qty=Decimal("1000"),
                status="已审核",
                create_date="2026-04-01",
            ),
            ProductionOrderModel(
                bill_no="MO_Y",
                mto_number=mto,
                workshop="组装工段",
                material_code="05.02.12.44",
                material_name="测试件",
                specification="",
                aux_prop_id=1001,
                qty=Decimal("662"),
                status="已审核",
                create_date="2026-04-01",
            ),
        ]

        handler = self.create_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=bom_lines,
            prod_orders=prod_orders,
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "05.02.12.44"
        # Tier 2.5: BOM specific-aux + PRD_MO disjoint specific-aux →
        # all-aux rollup = 1000 + 662 = 1662.
        assert row.need_qty == Decimal("1662"), (
            f"Expected Tier-2.5 PRD_MO all-aux rollup = 1662, got "
            f"{row.need_qty}. Tier 1 (exact aux=999) and Tier 2 ((code,0)) "
            "both miss; without Tier 2.5 the caller drops to MAX(b.need_qty)"
            " = 2880 (inflated) or returns ZERO. AS2602033 / 05.02.12.44 "
            "real-data regression — see bug-patterns.md #10 + Wave 4C plan."
        )
        # And specifically NOT the BOM upstream value:
        assert row.need_qty != Decimal("2880"), (
            "need_qty fell through to MAX(b.need_qty) — Tier-2.5 PRD_MO "
            "rollup is missing or returning ZERO. Inspect _lookup_mo_qty's "
            "Tier-2.5 branch (the post-Tier-2 fallback to _mo_qty_by_code)."
        )

    @pytest.mark.asyncio
    async def test_bom_multi_specific_aux_disjoint_prd_mo_dedups_rollup(
        self, mock_readers
    ):
        """Tier 2.5 multi-row dedup (Wave 4C): when N BOM-aux groups all
        miss Tier 1+2 (disjoint aux numbering), exactly ONE row carries the
        all-aux PRD_MO rollup; the others get ZERO (no MAX fallback).

        Without this dedup, every BOM-aux row would carry the full team
        target → SUM(must_qty) by code = N × team-target instead of 1 ×
        team-target. Real-data scenario: AS2602033 / 05.02.12.44 had 5 BOM
        groups at specific aux + 1 BOM group at aux=0; with naive Tier 2.5
        every group returned 8640 → SUM 51840 = 6× target.

        This test uses 3 BOM groups at distinct specific aux + 2 PRD_MO
        rows at completely different specific aux. Total target = 1000+
        662 = 1662. Expected: SUM(need_qty across rows) == 1662.
        """
        from src.readers.models import ProductionBOMModel

        mto = "AS2602033_MULTI"
        # 3 BOM groups at distinct specific aux, all with FMustQty=2880.
        bom_lines = [
            ProductionBOMModel(
                mo_bill_no="MO_AAA",
                mto_number=mto,
                material_code="05.02.12.44",
                material_name="测试件",
                specification="",
                aux_prop_id=900 + i,  # 900, 901, 902
                material_type=1,
                need_qty=Decimal("2880"),
                picked_qty=Decimal("0"),
                no_picked_qty=Decimal("2880"),
            )
            for i in range(3)
        ]
        # 2 PRD_MO rows at completely different specific aux (no overlap
        # with BOM, no aux=0 entry).
        prod_orders = [
            ProductionOrderModel(
                bill_no="MO_X",
                mto_number=mto,
                workshop="组装工段",
                material_code="05.02.12.44",
                material_name="测试件",
                specification="",
                aux_prop_id=2000,
                qty=Decimal("1000"),
                status="已审核",
                create_date="2026-04-01",
            ),
            ProductionOrderModel(
                bill_no="MO_Y",
                mto_number=mto,
                workshop="组装工段",
                material_code="05.02.12.44",
                material_name="测试件",
                specification="",
                aux_prop_id=2001,
                qty=Decimal("662"),
                status="已审核",
                create_date="2026-04-01",
            ),
        ]

        handler = self.create_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=bom_lines,
            prod_orders=prod_orders,
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )
        # Three rows preserved (one per BOM-aux group), but exactly one
        # carries the team total — the others are ZERO.
        assert len(rows) == 3, f"Expected 3 BOM-aux rows, got {len(rows)}"
        # SUM across all rows for this code must equal the team target,
        # NOT 3 × team-target.
        sum_need = sum((r.need_qty for r in rows), Decimal(0))
        assert sum_need == Decimal("1662"), (
            f"Expected SUM(need_qty) across {len(rows)} disjoint-aux rows "
            f"to equal team target = 1662, got {sum_need}. Without per-code "
            "Tier-2.5 dedup, every row would carry the full rollup and "
            "SUM = N × target. AS2602033 / 05.02.12.44 real-data regression."
        )
        # Verify the elected row carries the full rollup and the others
        # are zero.
        non_zero_rows = [r for r in rows if r.need_qty > 0]
        assert len(non_zero_rows) == 1, (
            f"Expected exactly 1 row with need_qty>0 (Tier-2.5 dedup); "
            f"got {len(non_zero_rows)}: {[(r.aux_prop_id, r.need_qty) for r in rows]}"
        )
        assert non_zero_rows[0].need_qty == Decimal("1662")

    @pytest.mark.asyncio
    async def test_03_with_prd_mo_routes_as_selfmade(self, mock_readers):
        """03.xx material with PRD_MO (工段) routes through self-made path.

        纸箱工段等 03.xx 包材如果有生产订单, 应按自制处理:
        - prod_instock_real_qty 来自 PRD_INSTOCK.FRealQty
        - prod_instock_must_qty 来自 PRD_INSTOCK.FMustQty
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
        # prod_instock_must_qty = PRD_MO.FQty (demand), even without receipts
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
    async def test_03_in_ppbom_with_material_type_1_routes_selfmade(self, mock_readers):
        """03.xx in PPBOM with FMaterialType=1 routes as self-made.

        FMaterialType is the authoritative source from Kingdee PPBOM.
        A 03.xx item with material_type=1 should route as self-made,
        with prod_instock_must_qty populated from PRD_INSTOCK.FMustQty.
        """
        bom_03_selfmade = ProductionBOMModel(
            mo_bill_no="MO600",
            mto_number="AS2512059",
            material_code="03.01.010",
            material_name="自制包材B",
            specification="",
            aux_prop_id=0,
            material_type=1,  # FMaterialType=1 → self-made
            need_qty=Decimal("200"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("200"),
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_bom"].fetch_by_mto = AsyncMock(
            return_value=[bom_03_selfmade]
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
        result = await handler.get_status("AS2512059", use_cache=False)

        assert len(result.children) >= 1
        child = [c for c in result.children if c.material_code == "03.01.010"][0]
        assert child.material_type_name == "自制"
        # prod_instock_must_qty = PPBOM.need_qty (demand), even without receipts
        assert child.prod_instock_must_qty == Decimal("200")
        assert child.prod_instock_real_qty == Decimal("0")

    @pytest.mark.asyncio
    async def test_03_with_prd_mo_not_duplicated_in_purchased(self, mock_readers):
        """03.xx with FMaterialType=1 must NOT appear in both self-made and purchased paths.

        有 FMaterialType=1 的 03.xx 不应同时出现在自制和外购中, 避免重复计数。
        """
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
        # PPBOM with FMaterialType=1 (self-made) — should only appear as self-made, not duplicated
        bom_03 = ProductionBOMModel(
            mo_bill_no="MO500",
            mto_number="AS2512032",
            material_code="03.05.001",
            material_name="纸箱A",
            specification="",
            aux_prop_id=0,
            material_type=1,
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


class TestBomRowToChild:
    """Direct unit tests for _bom_row_to_child() routing logic."""

    def _make_handler(self):
        """Create a minimal handler for calling _bom_row_to_child()."""
        mock_readers = {}
        for name in [
            "production_order", "production_bom", "production_receipt",
            "purchase_order", "purchase_receipt", "subcontracting_order",
            "material_picking", "sales_delivery", "sales_order",
        ]:
            mock_readers[name] = MagicMock()
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
        )

    def test_03_with_material_type_1_routes_as_selfmade(self):
        """BOMJoinedRow with material_code=03.xx and material_type=1 → self-made.

        FMaterialType is the authoritative source; 03.xx with material_type=1
        routes as self-made with prod_instock_must_qty populated.
        """
        row = BOMJoinedRow(
            mo_bill_no="MO700",
            mto_number="AS2512059",
            material_code="03.02.005",
            material_name="自制包材",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,  # FMaterialType=1 → self-made
            need_qty=Decimal("100"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("100"),
            prod_receipt_real_qty=Decimal("60"),
            prod_receipt_must_qty=Decimal("100"),
            pick_actual_qty=Decimal("0"),
            pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("0"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"),
            subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
        )
        handler = self._make_handler()
        child = handler._bom_row_to_child(
            row=row,
            aux_descriptions={},
        )

        assert child.material_type == MaterialType.SELF_MADE
        assert child.material_type_name == "自制"
        assert child.prod_instock_must_qty == Decimal("100")
        assert child.prod_instock_real_qty == Decimal("60")

    def test_03_with_material_type_2_routes_as_purchased(self):
        """BOMJoinedRow with material_code=03.xx and material_type=2 → purchased.

        FMaterialType=2 is trusted directly, routing as purchased.
        """
        row = BOMJoinedRow(
            mo_bill_no="MO800",
            mto_number="AS2512059",
            material_code="03.06.002",
            material_name="外购包材",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=2,  # FMaterialType=2 → purchased
            need_qty=Decimal("500"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("500"),
            prod_receipt_real_qty=Decimal("0"),
            prod_receipt_must_qty=Decimal("0"),
            pick_actual_qty=Decimal("0"),
            pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("500"),
            purchase_stock_in_qty=Decimal("300"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"),
            subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
        )
        handler = self._make_handler()
        child = handler._bom_row_to_child(
            row=row,
            aux_descriptions={},
        )

        assert child.material_type == MaterialType.PURCHASED
        assert child.material_type_name == "包材"
        assert child.purchase_order_qty == Decimal("500")
        assert child.purchase_stock_in_qty == Decimal("300")

    def test_05_with_material_type_1_stays_selfmade(self):
        """Non-03 material (05.xx) with material_type=1 stays self-made (no override)."""
        row = BOMJoinedRow(
            mo_bill_no="MO900",
            mto_number="AS2512059",
            material_code="05.01.001",
            material_name="自制半成品",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("200"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("200"),
            prod_receipt_real_qty=Decimal("100"),
            prod_receipt_must_qty=Decimal("200"),
            pick_actual_qty=Decimal("0"),
            pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("0"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"),
            subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
        )
        handler = self._make_handler()
        child = handler._bom_row_to_child(
            row=row,
            aux_descriptions={},
        )

        assert child.material_type == MaterialType.SELF_MADE
        assert child.material_type_name == "自制"

    def test_category_baocai_with_is_purchase_true_routes_as_purchased(self):
        """外销包材 + IsPurchase=True → 包材 (外箱/内盒/纸卡)."""
        row = BOMJoinedRow(
            mo_bill_no="MO_BAOCAI",
            mto_number="AS2510999",
            material_code="03.03.001",
            material_name="外箱",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("100"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("100"),
            prod_receipt_real_qty=Decimal("0"),
            prod_receipt_must_qty=Decimal("0"),
            pick_actual_qty=Decimal("0"),
            pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("100"),
            purchase_stock_in_qty=Decimal("60"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"),
            subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
            category_name="外销包材",
            is_purchase=True,
        )
        child = self._make_handler()._bom_row_to_child(row=row, aux_descriptions={})

        assert child.material_type == MaterialType.PURCHASED
        assert child.material_type_name == "包材"
        assert child.purchase_order_qty == Decimal("100")
        assert child.purchase_stock_in_qty == Decimal("60")

    def test_category_baocai_with_is_purchase_false_still_routes_as_baocai(self):
        """外销包材 + IsPurchase=False → 包材 CHIP, but 自制 (生产入库) 口径.

        Two orthogonal axes that an earlier revert (e3d12a2, 2026-05-22)
        accidentally welded together, dropping the order quantity for
        self-made packaging (吸塑/跟型件) — the regression this test now locks:

        - CHIP / filter axis  → `material_type_name` == "包材". Per the
          colleague's clarification, 包材 is a CATEGORY: self-made plastic
          packaging sits in the 包材 chip alongside purchased 外箱/纸卡.
        - DATA 口径 axis      → `material_type` code == SELF_MADE(1). A
          self-made part has NO purchase order, so its demand must come
          from BOM `need_qty` (生产入库.应收) and fulfilment from
          `prod_receipt_real_qty` (生产入库.实收), exactly like a 05.xx
          self-made item. This restores the pre-BOM-first behaviour
          (工段 routing, commit e493de8). The frontend keys columns off
          the code and the chip/filter off the name, so this single split
          gives 包材 chip + 生产入库 columns with no frontend change.
        """
        row = BOMJoinedRow(
            mo_bill_no="MO_XISU",
            mto_number="AS2603021-3",
            material_code="03.02.02.176",
            material_name="2CLG316 对折吸塑",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("200"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("200"),
            prod_receipt_real_qty=Decimal("150"),
            prod_receipt_must_qty=Decimal("200"),
            pick_actual_qty=Decimal("30"),
            pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("0"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"),
            subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
            category_name="外销包材",
            is_purchase=False,
        )
        child = self._make_handler()._bom_row_to_child(row=row, aux_descriptions={})

        # CHIP / filter axis — stays 包材 (colleague's requirement).
        assert child.material_type_name == "包材"
        # DATA 口径 axis — self-made, so the demand/fulfilment columns are
        # populated from production, NOT from a (non-existent) purchase order.
        assert child.material_type == MaterialType.SELF_MADE
        assert child.prod_instock_must_qty == Decimal("200"), "需求应来自 BOM need_qty"
        assert child.prod_instock_real_qty == Decimal("150"), "齐套应来自生产入库.实收"
        assert child.pick_actual_qty == Decimal("30")
        # The purchase-order demand column must NOT carry a value — a
        # self-made part has no PO; leaking 0 here is what showed "0 订单数量".
        assert not child.purchase_order_qty
        # is_purchase stays on the child for downstream filtering.
        assert child.is_purchase is False

    def test_self_made_baocai_gets_meaningful_fulfillment_rate(self):
        """End-to-end: a self-made 外销包材 child must resolve to a real
        fulfillment_rate via the self_made semantic config (实收/need_qty),
        not collapse to 0/None the way the 包材→采购 口径 did.

        Locks the full chain through the REAL config: 包材 chip (name) +
        SELF_MADE code → engine.detect_class_id_by_type(1, is_finished_goods
        =False) → self_made → rate = prod_instock_real_qty /
        prod_instock_must_qty. Uses build_metric_engine() so config drift
        (e.g. someone flipping self_made's material_type_id) breaks here.
        """
        from src.mto_config import MTOConfig

        row = BOMJoinedRow(
            mo_bill_no="MO_XISU2",
            mto_number="AS2603021-4",
            material_code="03.02.02.089",
            material_name="GS56泳镜 PET 跟型内衬",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("200"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("0"),
            prod_receipt_real_qty=Decimal("150"),
            prod_receipt_must_qty=Decimal("200"),
            pick_actual_qty=Decimal("0"),
            pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("0"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"),
            subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
            category_name="外销包材",
            is_purchase=False,
        )
        child = self._make_handler()._bom_row_to_child(row=row, aux_descriptions={})
        engine = MTOConfig("config/mto_config.json").build_metric_engine()

        # The chip says 包材, but the engine must see a self-made item.
        class_id = engine.detect_class_id_by_type(
            child.material_type, getattr(child, "is_finished_goods", False)
        )
        assert class_id == "self_made"

        metrics = engine.compute_for_item(child, class_id)
        assert metrics["fulfillment_rate"].value == Decimal("0.75"), (
            "150/200 — self-made 口径, not 0/0"
        )

    def test_category_weiwai_routes_as_subcontracted(self):
        """category_name=委外加工 → 委外, regardless of FMaterialType.

        Regression guard: 08.xx materials all carry material_type=1 in this
        tenant. The 委外 chip was permanently empty before the fix.
        """
        row = BOMJoinedRow(
            mo_bill_no="MO_WEIWAI",
            mto_number="AS2510888",
            material_code="08.01.045",
            material_name="成人PU帽",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("500"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("500"),
            prod_receipt_real_qty=Decimal("0"),
            prod_receipt_must_qty=Decimal("0"),
            pick_actual_qty=Decimal("0"),
            pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("0"),
            purchase_stock_in_qty=Decimal("0"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("500"),
            subcontract_stock_in_qty=Decimal("300"),
            delivery_real_qty=Decimal("0"),
            category_name="委外加工",
        )
        child = self._make_handler()._bom_row_to_child(row=row, aux_descriptions={})

        assert child.material_type == MaterialType.SUBCONTRACTED
        assert child.material_type_name == "委外"
        assert child.purchase_order_qty == Decimal("500")
        assert child.purchase_stock_in_qty == Decimal("300")

    def test_category_zhuliao_routes_as_selfmade(self):
        """category_name=主料 → 自制 (raw materials, FMaterialType=1 happens to agree)."""
        row = BOMJoinedRow(
            mo_bill_no="MO_ZHU",
            mto_number="AS001",
            material_code="01.22.002",
            material_name="固态硅胶",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("50"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("50"),
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
            category_name="主料",
        )
        child = self._make_handler()._bom_row_to_child(row=row, aux_descriptions={})

        assert child.material_type == MaterialType.SELF_MADE
        assert child.material_type_name == "自制"

    def test_missing_category_falls_back_to_material_type_and_warns(self, caplog):
        """Empty category_name falls back to material_type with a warning log.

        Covers old cache rows that don't yet have category_name populated, plus
        any future Kingdee category we haven't mapped.
        """
        row = BOMJoinedRow(
            mo_bill_no="MO_OLD",
            mto_number="AS001",
            material_code="05.01.001",
            material_name="半成品",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=1,
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
            # category_name defaults to ""
        )
        with caplog.at_level("WARNING", logger="src.query.mto_handler"):
            child = self._make_handler()._bom_row_to_child(row=row, aux_descriptions={})

        # Routed by legacy material_type=1 → 自制
        assert child.material_type == MaterialType.SELF_MADE
        assert child.material_type_name == "自制"
        # Sync gap is surfaced
        assert any("bom_row_category_fallback" in r.message for r in caplog.records)


class TestAggregatedSalesChildCloseStatus:
    """Tests for the OR-merge of close_status in _build_aggregated_sales_child.

    Verifies that if ANY sales order in the grouped list is closed ('B'),
    the resulting ChildItem.close_status is also 'B'.
    """

    def _make_handler(self):
        """Build a minimal MTOQueryHandler with all-MagicMock readers."""
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

    def _so(self, close_status="A") -> SalesOrderModel:
        return SalesOrderModel(
            bill_no="SO_TEST",
            mto_number="AS_TEST",
            material_code="07.02.037",
            material_name="成品A",
            specification="",
            customer_name="客户A",
            close_status=close_status,
        )

    def test_aggregated_sales_child_all_open_close_status_a(self):
        """Three sales orders all open → ChildItem.close_status == 'A'."""
        handler = self._make_handler()
        sales_orders = [self._so("A"), self._so("A"), self._so("A")]
        child = handler._build_aggregated_sales_child(
            sales_orders=sales_orders,
            receipt_by_material={},
            delivered_by_material={},
            aux_descriptions={},
        )
        assert child.close_status == "A"

    def test_aggregated_sales_child_one_closed_close_status_b(self):
        """Three sales orders, middle one closed → ChildItem.close_status == 'B'."""
        handler = self._make_handler()
        sales_orders = [self._so("A"), self._so("B"), self._so("A")]
        child = handler._build_aggregated_sales_child(
            sales_orders=sales_orders,
            receipt_by_material={},
            delivered_by_material={},
            aux_descriptions={},
        )
        assert child.close_status == "B"


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
        # _fetch_live also looks up BD_MATERIAL categories for synthetic-row routing
        # (Phase 2a). Default to an awaitable no-op; tests needing real values override.
        mock.client.lookup_material_categories = AsyncMock(return_value={})
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


class TestAuxPropIdMismatchRouting(TestMTOQueryHandler):
    """Tests for 03.xx routing when PRD_MO and PRD_INSTOCK have different aux_prop_id values.

    Bug: PRD_MO has aux_prop_id=0, PRD_INSTOCK has aux_prop_id=12345.
    The old code used (material_code, aux_prop_id) tuple matching, which silently failed.
    Fix: Use material_code-only matching for routing decisions.
    """

    @pytest.mark.asyncio
    async def test_03_aux_mismatch_routes_receipt_as_selfmade(self, mock_readers):
        """03.xx receipt with different aux_prop_id from PRD_MO still routes as self-made.

        PRD_MO has aux_prop_id=0, PRD_INSTOCK has aux_prop_id=5001 (box dimension).
        Receipt should still be routed to self-made path based on material_code alone.
        """
        prod_order = ProductionOrderModel(
            bill_no="MO600",
            mto_number="AS2512042-2",
            workshop="外箱工段",
            material_code="03.05.010",
            material_name="外箱",
            specification="500x400x300",
            aux_prop_id=0,  # PRD_MO has no aux variant
            qty=Decimal("800"),
            status="已审核",
            create_date="2025-12-10",
        )
        receipt = ProductionReceiptModel(
            bill_no="RK600",
            mto_number="AS2512042-2",
            material_code="03.05.010",
            material_name="外箱",
            specification="500x400x300",
            real_qty=Decimal("600"),
            must_qty=Decimal("800"),
            aux_prop_id=5001,  # Different aux_prop_id from PRD_MO!
            mo_bill_no="MO600",
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={5001: "500x400x300mm"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512042-2", use_cache=False)

        assert len(result.children) == 1
        child = result.children[0]
        assert child.material_code == "03.05.010"
        assert child.material_type_name == "自制"
        assert child.prod_instock_real_qty == Decimal("600")
        # PRD_MO qty found via (code, 0) fallback
        assert child.prod_instock_must_qty == Decimal("800")

    @pytest.mark.asyncio
    async def test_03_aux_mismatch_excludes_from_purchase(self, mock_readers):
        """03.xx with PRD_MO must not appear in purchased path even when PUR order exists.

        Same material has both PRD_MO (self-made routing) and PUR order.
        The PUR order row should be excluded since the material is routed to self-made.
        """
        prod_order = ProductionOrderModel(
            bill_no="MO700",
            mto_number="AS2512042-2",
            workshop="外箱工段",
            material_code="03.05.010",
            material_name="外箱",
            specification="500x400x300",
            aux_prop_id=0,
            qty=Decimal("800"),
            status="已审核",
            create_date="2025-12-10",
        )
        receipt = ProductionReceiptModel(
            bill_no="RK700",
            mto_number="AS2512042-2",
            material_code="03.05.010",
            material_name="外箱",
            specification="500x400x300",
            real_qty=Decimal("600"),
            must_qty=Decimal("800"),
            aux_prop_id=5001,
            mo_bill_no="MO700",
        )
        # Same material also has a purchase order — should be excluded
        purchase = PurchaseOrderModel(
            bill_no="PO700",
            mto_number="AS2512042-2",
            material_code="03.05.010",
            material_name="外箱",
            specification="500x400x300",
            aux_attributes="500x400x300mm",
            aux_prop_id=5001,
            order_qty=Decimal("800"),
            stock_in_qty=Decimal("0"),
            remain_stock_in_qty=Decimal("800"),
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(
            return_value=[purchase]
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={5001: "500x400x300mm"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512042-2", use_cache=False)

        selfmade = [c for c in result.children if c.material_type_name == "自制"]
        purchased = [c for c in result.children if c.material_code == "03.05.010" and c.material_type_name == "包材"]

        assert len(selfmade) == 1
        assert selfmade[0].material_code == "03.05.010"
        assert selfmade[0].prod_instock_real_qty == Decimal("600")
        # No duplicate in purchased path
        assert len(purchased) == 0

    @pytest.mark.asyncio
    async def test_03_aux_mismatch_mixed_with_normal_purchase(self, mock_readers):
        """MTO with both routed 03.xx (aux mismatch) and normal 03.xx purchased.

        03.05.010 has PRD_MO → self-made (despite aux mismatch).
        03.01.020 has PUR only → normal purchased.
        Both should appear correctly without interference.
        """
        prod_order = ProductionOrderModel(
            bill_no="MO800",
            mto_number="AS2512042-2",
            workshop="外箱工段",
            material_code="03.05.010",
            material_name="外箱",
            specification="500x400x300",
            aux_prop_id=0,
            qty=Decimal("800"),
            status="已审核",
            create_date="2025-12-10",
        )
        receipt = ProductionReceiptModel(
            bill_no="RK800",
            mto_number="AS2512042-2",
            material_code="03.05.010",
            material_name="外箱",
            specification="500x400x300",
            real_qty=Decimal("600"),
            must_qty=Decimal("800"),
            aux_prop_id=5001,
            mo_bill_no="MO800",
        )
        # Different 03.xx material with only PUR → should stay purchased
        normal_purchase = PurchaseOrderModel(
            bill_no="PO800",
            mto_number="AS2512042-2",
            material_code="03.01.020",
            material_name="标签",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            order_qty=Decimal("1000"),
            stock_in_qty=Decimal("1000"),
            remain_stock_in_qty=Decimal("0"),
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(
            return_value=[normal_purchase]
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={5001: "500x400x300mm"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512042-2", use_cache=False)

        selfmade = [c for c in result.children if c.material_type_name == "自制"]
        purchased = [c for c in result.children if c.material_type_name == "包材"]

        # 03.05.010 → self-made (routed via PRD_MO)
        assert len(selfmade) == 1
        assert selfmade[0].material_code == "03.05.010"
        assert selfmade[0].prod_instock_real_qty == Decimal("600")

        # 03.01.020 → normal purchased
        pur_children = [c for c in purchased if c.material_code == "03.01.020"]
        assert len(pur_children) == 1
        assert pur_children[0].purchase_order_qty == Decimal("1000")
        assert pur_children[0].purchase_stock_in_qty == Decimal("1000")


class TestAuxMismatch05xx(TestMTOQueryHandler):
    """Tests for 05.xx aux_prop_id mismatch between PRD_MO and PRD_INSTOCK.

    Bug #1/#2: PRD_MO has aux_prop_id=0, PRD_INSTOCK has aux_prop_id=N.
    Dedup checks used exact tuple keys, creating duplicate self-made rows.
    Fix: Code-only dedup for all self-made materials, not just 03.xx.
    """

    @pytest.mark.asyncio
    async def test_05_aux_mismatch_no_duplicate_prd_mo_row(self, mock_readers):
        """05.xx with PRD_MO aux=0 and receipt aux=2001 must NOT create duplicate row.

        PRD_MO has aux_prop_id=0, PRD_INSTOCK has aux_prop_id=2001.
        Only one self-made row should appear (from the receipt), not two.
        """
        prod_order = ProductionOrderModel(
            bill_no="MO900",
            mto_number="AS2512050",
            workshop="成型工段",
            material_code="05.01.001",
            material_name="硅胶镜圈",
            specification="GST-GS53",
            aux_prop_id=0,  # PRD_MO has no aux variant
            qty=Decimal("1000"),
            status="已审核",
            create_date="2025-12-15",
        )
        receipt = ProductionReceiptModel(
            bill_no="RK900",
            mto_number="AS2512050",
            material_code="05.01.001",
            material_name="硅胶镜圈",
            specification="GST-GS53",
            real_qty=Decimal("800"),
            must_qty=Decimal("1000"),
            aux_prop_id=2001,  # Different from PRD_MO!
            mo_bill_no="MO900",
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={2001: "GST-GS53"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512050", use_cache=False)

        selfmade = [c for c in result.children if c.material_code == "05.01.001"]
        assert len(selfmade) == 1, f"Expected 1 row, got {len(selfmade)}: {selfmade}"
        assert selfmade[0].material_type_name == "自制"
        assert selfmade[0].prod_instock_real_qty == Decimal("800")
        assert selfmade[0].prod_instock_must_qty == Decimal("1000")

    @pytest.mark.asyncio
    async def test_05_aux_mismatch_pickmtrl_no_duplicate(self, mock_readers):
        """05.xx with pick aux=0 and receipt aux=2001 must NOT create duplicate row.

        PRD_PickMtrl has aux_prop_id=0, PRD_INSTOCK has aux_prop_id=2001.
        Only the receipt-based row should appear, not an extra pickmtrl row.
        """
        prod_order = ProductionOrderModel(
            bill_no="MO950",
            mto_number="AS2512050",
            workshop="成型工段",
            material_code="05.01.001",
            material_name="硅胶镜圈",
            specification="GST-GS53",
            aux_prop_id=0,
            qty=Decimal("1000"),
            status="已审核",
            create_date="2025-12-15",
        )
        receipt = ProductionReceiptModel(
            bill_no="RK950",
            mto_number="AS2512050",
            material_code="05.01.001",
            material_name="硅胶镜圈",
            specification="GST-GS53",
            real_qty=Decimal("800"),
            must_qty=Decimal("1000"),
            aux_prop_id=2001,
            mo_bill_no="MO950",
        )
        pick = MaterialPickingModel(
            bill_no="PM950",
            mto_number="AS2512050",
            material_code="05.01.001",
            app_qty=Decimal("1000"),
            actual_qty=Decimal("900"),
            ppbom_bill_no="MO950",
            aux_prop_id=0,  # Different from receipt!
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[prod_order]
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(
            return_value=[pick]
        )
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={2001: "GST-GS53"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512050", use_cache=False)

        selfmade = [c for c in result.children if c.material_code == "05.01.001"]
        assert len(selfmade) == 1, f"Expected 1 row, got {len(selfmade)}: {selfmade}"
        assert selfmade[0].prod_instock_real_qty == Decimal("800")


class TestSalesReceiptFallback(TestMTOQueryHandler):
    """Tests for Bug #3: sales child receipt lookup fallback.

    When SAL_SaleOrder has aux_prop_id=N but PRD_INSTOCK has aux_prop_id=0,
    the receipt lookup should fall back to (code, 0) instead of returning 0.
    """

    @pytest.mark.asyncio
    async def test_sales_receipt_aux_mismatch_uses_fallback(self, mock_readers):
        """07.xx finished goods: receipt lookup falls back when aux differs."""
        sales_order = SalesOrderModel(
            bill_no="SO900",
            mto_number="AS2512060",
            material_code="07.02.037",
            material_name="成品A",
            specification="规格1",
            aux_attributes="蓝色",
            aux_prop_id=3001,
            customer_name="客户A",
            delivery_date="2025-12-20",
            qty=Decimal("500"),
        )
        receipt = ProductionReceiptModel(
            bill_no="RK960",
            mto_number="AS2512060",
            material_code="07.02.037",
            material_name="成品A",
            specification="规格1",
            real_qty=Decimal("500"),
            must_qty=Decimal("500"),
            aux_prop_id=0,  # Different from sales order!
            mo_bill_no="MO960",
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=[sales_order]
        )
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=[receipt]
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={3001: "蓝色"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("AS2512060", use_cache=False)

        assert len(result.children) == 1
        child = result.children[0]
        assert child.material_code == "07.02.037"
        assert child.material_type_name == "成品"
        assert child.sales_order_qty == Decimal("500")
        # Should find receipt via (code, 0) fallback, NOT show 0
        assert child.prod_instock_real_qty == Decimal("500")

    @pytest.mark.asyncio
    async def test_finished_goods_receipt_via_purchase_receipt(self, mock_readers):
        """Wave 6B: 07.xx finished goods receipt via STK_InStock (purchase_receipts).

        Pre-fix: _build_aggregated_sales_child only consulted prod_receipts
        (PRD_INSTOCK). When a 07.xx finished good is bought-in from a sister
        plant / OEM partner, the receipt lands in STK_InStock with
        bill_type_number=RKD01_SYS, and prod_instock_real_qty was 0 with no
        sign of the inbound quantity.

        Post-fix: same Tier 1 → Tier 3 rollup logic applied to
        purchase_receipts and surfaced as purchase_stock_in_qty on the child.

        Reproduces DK251003S 07.02.151/154 (BOM aux=A specific for 07.xx with
        STK_InStock receipt at the same aux) — KD demand=242, fulfilled=242
        but PRD_INSTOCK is empty.
        """
        from src.readers.models import PurchaseReceiptModel

        sales_order = SalesOrderModel(
            bill_no="SO_W6B",
            mto_number="DK_W6B",
            material_code="07.02.151",
            material_name="泳镜",
            specification="规格X",
            aux_attributes="蓝色",
            aux_prop_id=205453,
            customer_name="客户W6B",
            delivery_date="2026-01-30",
            qty=Decimal("242"),
        )
        # NOTE: PRD_INSTOCK is intentionally empty for this scenario.
        purchase_receipt = PurchaseReceiptModel(
            bill_no="CG_W6B",
            mto_number="DK_W6B",
            material_code="07.02.151",
            material_name="泳镜",
            specification="规格X",
            real_qty=Decimal("242"),
            must_qty=Decimal("242"),
            bill_type_number="RKD01_SYS",
            aux_prop_id=205453,  # exact aux match with sales order
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=[sales_order]
        )
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(
            return_value=[purchase_receipt]
        )
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["subcontracting_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_bom"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={205453: "蓝色"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("DK_W6B", use_cache=False)

        finished = [c for c in result.children if c.material_code == "07.02.151"]
        assert len(finished) == 1
        child = finished[0]
        assert child.material_type_name == "成品"
        assert child.sales_order_qty == Decimal("242")
        # Pre-fix: prod_instock_real_qty=0 AND purchase_stock_in_qty=0.
        # Post-fix: STK_InStock receipt is surfaced via purchase_stock_in_qty.
        assert child.prod_instock_real_qty == Decimal("0")
        assert child.purchase_stock_in_qty == Decimal("242"), (
            "Wave 6B: STK_InStock receipt for 07.xx finished good must be "
            "surfaced as purchase_stock_in_qty when PRD_INSTOCK is empty"
        )

    @pytest.mark.asyncio
    async def test_finished_goods_multi_aux_no_double_attribution(self, mock_readers):
        """Wave 6 followup: 3 SAL aux groups + 1 PRD_INSTOCK aux must NOT cause
        the same receipt to be attributed to all 3 children.

        Real-data case: DK251003S 07.01.07 had 3 SAL aux groups
        (153245/100398/100238) but PRD_INSTOCK only at aux=153245 with
        FRealQty=17280. Pre-dedup, all 3 children got prod_instock_real_qty
        =17280 (Tier 3 rollup) → SUM = 51840 (3× the actual receipt).
        Post-dedup, only the Tier-1-matched child gets 17280; the other 2
        get 0.
        """
        sales_orders = [
            SalesOrderModel(
                bill_no="SO_X1", mto_number="DK_X",
                material_code="07.01.07", aux_prop_id=153245,
                customer_name="A", delivery_date="2026-01-01",
                qty=Decimal("17000"),
            ),
            SalesOrderModel(
                bill_no="SO_X2", mto_number="DK_X",
                material_code="07.01.07", aux_prop_id=100398,
                customer_name="A", delivery_date="2026-01-01",
                qty=Decimal("24"),
            ),
            SalesOrderModel(
                bill_no="SO_X3", mto_number="DK_X",
                material_code="07.01.07", aux_prop_id=100238,
                customer_name="A", delivery_date="2026-01-01",
                qty=Decimal("24"),
            ),
        ]
        receipt = ProductionReceiptModel(
            bill_no="RK_X", mto_number="DK_X",
            material_code="07.01.07",
            real_qty=Decimal("17280"),
            must_qty=Decimal("17280"),
            aux_prop_id=153245,  # exact match with first SAL
            mo_bill_no="MO_X",
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=sales_orders)
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[receipt])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["subcontracting_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_bom"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={153245: "A", 100398: "B", 100238: "C"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("DK_X", use_cache=False)
        children = [c for c in result.children if c.material_code == "07.01.07"]
        assert len(children) == 3
        # Exactly ONE child should have prod_instock_real_qty=17280 (the one
        # whose aux Tier-1 matched). The other two must have 0.
        instock_values = sorted([int(c.prod_instock_real_qty) for c in children])
        assert instock_values == [0, 0, 17280], (
            f"Expected [0, 0, 17280], got {instock_values}. Pre-dedup all 3 "
            f"children received the all-aux rollup (3× double-attribution) — "
            f"DK251003S 07.01.07 saw QP=51840 vs KD=17280."
        )
        # Tier-1 match should land on the largest SAL aux group (153245).
        for c in children:
            if c.prod_instock_real_qty > 0:
                assert c.aux_attributes == "A"

    @pytest.mark.asyncio
    async def test_finished_goods_purchase_receipt_aux_mismatch_fallback(self, mock_readers):
        """Wave 6B: aux mismatch between SAL and STK_InStock falls through to rollup.

        SAL has aux=A specific, STK_InStock has aux=B specific (different).
        Tier 3 (all_aux_rollup) should kick in and surface the receipt qty.
        """
        from src.readers.models import PurchaseReceiptModel

        sales_order = SalesOrderModel(
            bill_no="SO_W6B2",
            mto_number="DK_W6B2",
            material_code="07.02.147",
            material_name="泳镜",
            specification="",
            aux_prop_id=111,  # SAL aux
            customer_name="客户",
            delivery_date="2026-02-01",
            qty=Decimal("100"),
        )
        purchase_receipt = PurchaseReceiptModel(
            bill_no="CG_W6B2",
            mto_number="DK_W6B2",
            material_code="07.02.147",
            real_qty=Decimal("100"),
            must_qty=Decimal("100"),
            bill_type_number="RKD01_SYS",
            aux_prop_id=222,  # different aux
        )

        mock_readers["sales_order"].fetch_by_mto = AsyncMock(
            return_value=[sales_order]
        )
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(
            return_value=[purchase_receipt]
        )
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["subcontracting_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_bom"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={111: "A", 222: "B"}
        )

        handler = self.create_handler(mock_readers)
        result = await handler.get_status("DK_W6B2", use_cache=False)

        finished = [c for c in result.children if c.material_code == "07.02.147"]
        assert len(finished) == 1
        # Tier 3 rollup: SAL aux=111 doesn't match STK aux=222, so fall through
        # to the all-aux sum.
        assert finished[0].purchase_stock_in_qty == Decimal("100")


class TestBuildBomJoinedRowsFromLive:
    """Tests for _build_bom_joined_rows_from_live synthetic entries.

    This method converts live Kingdee API data into BOMJoinedRow objects.
    Step 1 builds rows from PPBOM (primary source).
    Step 2 creates SYNTHETIC rows for items found in receipts/picks/orders
    but NOT in PPBOM.
    """

    def _make_handler(self, mock_readers):
        """Create handler for direct method testing."""
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
        )

    def test_all_items_in_ppbom_no_synthetic(self, mock_readers):
        """When PPBOM covers all items, no synthetic rows are created."""
        bom = ProductionBOMModel(
            mo_bill_no="MO001",
            mto_number="AS001",
            material_code="05.01.001",
            material_name="自制件A",
            specification="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("100"),
            picked_qty=Decimal("50"),
            no_picked_qty=Decimal("50"),
        )
        receipt = ProductionReceiptModel(
            bill_no="RK001",
            mto_number="AS001",
            material_code="05.01.001",
            material_name="自制件A",
            specification="",
            real_qty=Decimal("80"),
            must_qty=Decimal("100"),
            aux_prop_id=0,
            mo_bill_no="MO001",
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[bom],
            prod_orders=[],
            prod_receipts=[receipt],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        assert rows[0].material_code == "05.01.001"
        assert rows[0].need_qty == Decimal("100")
        # Receipt data aggregated into the BOM row
        assert rows[0].prod_receipt_real_qty == Decimal("80")

    def test_receipt_not_in_ppbom_creates_synthetic(self, mock_readers):
        """PRD_INSTOCK item not in PPBOM gets a synthetic row."""
        receipt = ProductionReceiptModel(
            bill_no="RK100",
            mto_number="AS100",
            material_code="05.02.001",
            material_name="自制件B",
            specification="规格X",
            real_qty=Decimal("50"),
            must_qty=Decimal("50"),
            aux_prop_id=0,
            mo_bill_no="MO100",
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],  # No PPBOM
            prod_orders=[],
            prod_receipts=[receipt],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "05.02.001"
        assert row.material_type == 1  # self-made
        assert row.need_qty == Decimal("0")  # synthetic has no BOM demand
        assert row.prod_receipt_real_qty == Decimal("50")

    def test_purchase_order_not_in_ppbom_creates_synthetic(self, mock_readers):
        """PUR order not in PPBOM gets a synthetic row with type=2."""
        purchase = PurchaseOrderModel(
            bill_no="PO100",
            mto_number="AS100",
            material_code="03.01.001",
            material_name="包材A",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            order_qty=Decimal("200"),
            stock_in_qty=Decimal("100"),
            remain_stock_in_qty=Decimal("100"),
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[],
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[purchase],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "03.01.001"
        assert row.material_type == 2  # purchased
        assert row.purchase_order_qty == Decimal("200")
        assert row.purchase_stock_in_qty == Decimal("100")

    def test_finished_goods_never_get_synthetic(self, mock_readers):
        """07.xx items are never created as synthetic rows."""
        receipt_07 = ProductionReceiptModel(
            bill_no="RK200",
            mto_number="AS200",
            material_code="07.02.037",
            material_name="成品A",
            specification="",
            real_qty=Decimal("100"),
            must_qty=Decimal("100"),
            aux_prop_id=0,
            mo_bill_no="MO200",
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[],
            prod_receipts=[receipt_07],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        # 07.xx is finished_goods — handled via _build_aggregated_sales_child, not synthetic
        assert len(rows) == 0

    def test_dedup_prevents_duplicate_synthetic(self, mock_readers):
        """Item in both receipts and picks only gets one synthetic row."""
        receipt = ProductionReceiptModel(
            bill_no="RK300",
            mto_number="AS300",
            material_code="05.01.005",
            material_name="自制件C",
            specification="",
            real_qty=Decimal("40"),
            must_qty=Decimal("50"),
            aux_prop_id=0,
            mo_bill_no="MO300",
        )
        pick = MaterialPickingModel(
            bill_no="PM300",
            mto_number="AS300",
            material_code="05.01.005",
            app_qty=Decimal("50"),
            actual_qty=Decimal("40"),
            ppbom_bill_no="MO300",
            aux_prop_id=0,
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[],
            prod_receipts=[receipt],
            material_picks=[pick],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        # Only one row despite appearing in both receipts and picks
        assert len(rows) == 1
        assert rows[0].material_code == "05.01.005"
        # Pick data should still be aggregated into the row
        assert rows[0].pick_actual_qty == Decimal("40")

    def test_ppbom_item_enriched_with_receipt_data(self, mock_readers):
        """PPBOM item gets receipt/pick data via pre-aggregation in _make_row."""
        bom = ProductionBOMModel(
            mo_bill_no="MO400",
            mto_number="AS400",
            material_code="05.01.010",
            material_name="自制件D",
            specification="",
            aux_prop_id=0,
            material_type=1,
            need_qty=Decimal("200"),
            picked_qty=Decimal("100"),
            no_picked_qty=Decimal("100"),
        )
        receipt = ProductionReceiptModel(
            bill_no="RK400",
            mto_number="AS400",
            material_code="05.01.010",
            material_name="自制件D",
            specification="",
            real_qty=Decimal("150"),
            must_qty=Decimal("200"),
            aux_prop_id=0,
            mo_bill_no="MO400",
        )
        pick = MaterialPickingModel(
            bill_no="PM400",
            mto_number="AS400",
            material_code="05.01.010",
            app_qty=Decimal("200"),
            actual_qty=Decimal("180"),
            ppbom_bill_no="MO400",
            aux_prop_id=0,
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[bom],
            prod_orders=[],
            prod_receipts=[receipt],
            material_picks=[pick],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "05.01.010"
        assert row.need_qty == Decimal("200")
        assert row.prod_receipt_real_qty == Decimal("150")
        assert row.pick_actual_qty == Decimal("180")
        assert row.pick_app_qty == Decimal("200")

    def test_03_receipt_without_prd_mo_gets_type_1(self, mock_readers):
        """03.xx in PRD_INSTOCK without PRD_MO gets synthetic row with type=1 (source-table: self-made).

        Bug fix: previously all synthetic PRD_INSTOCK rows got type=1 (self-made),
        even 03.xx items that have no production order and should be purchased.
        """
        receipt = ProductionReceiptModel(
            bill_no="RK500",
            mto_number="AS500",
            material_code="03.01.005",
            material_name="包材X",
            specification="",
            real_qty=Decimal("30"),
            must_qty=Decimal("30"),
            aux_prop_id=0,
            mo_bill_no="",
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[],  # No PRD_MO for this 03.xx
            prod_receipts=[receipt],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "03.01.005"
        assert row.material_type == 1  # source-table inference: PRD_INSTOCK → self-made

    def test_03_receipt_with_prd_mo_gets_type_1(self, mock_readers):
        """03.xx in PRD_INSTOCK with PRD_MO gets synthetic row with type=1 (self-made)."""
        receipt = ProductionReceiptModel(
            bill_no="RK600",
            mto_number="AS600",
            material_code="03.05.001",
            material_name="纸箱A",
            specification="",
            real_qty=Decimal("300"),
            must_qty=Decimal("500"),
            aux_prop_id=0,
            mo_bill_no="MO600",
        )
        prod_order = ProductionOrderModel(
            bill_no="MO600",
            mto_number="AS600",
            workshop="纸箱工段",
            material_code="03.05.001",
            material_name="纸箱A",
            specification="",
            aux_prop_id=0,
            qty=Decimal("500"),
            status="已审核",
            create_date="2025-12-01",
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[prod_order],  # Has PRD_MO → self-made
            prod_receipts=[receipt],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "03.05.001"
        assert row.material_type == 1  # self-made because PRD_MO exists

    def test_prd_mo_only_creates_synthetic_when_no_bom_or_receipt(self, mock_readers):
        """PRD_MO item not in PPBOM and not in receipts still gets a synthetic row."""
        prod_order = ProductionOrderModel(
            bill_no="MO700",
            mto_number="AS700",
            workshop="成型工段",
            material_code="05.03.001",
            material_name="自制件E",
            specification="",
            aux_prop_id=0,
            qty=Decimal("1000"),
            status="已审核",
            create_date="2025-12-01",
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[prod_order],
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "05.03.001"
        assert row.material_type == 1  # self-made (PRD_MO implies production)

    def test_synthetic_row_emits_all_aux_variants_no_bom(self, mock_readers):
        """Bug-patterns.md #11 (Bug 5b) regression guard.

        Three PUR aux variants of the same purchased material with NO PPBOM entry
        must produce 3 separate synthetic rows. The original code-only dedup
        emitted only the first.

        Real-world case: 03.23.009 贴纸 with 3 SKUs (3 colors), each its own
        purchase order, none in PPBOM → operator must see all 3, not just one.
        """
        pur_rows = [
            PurchaseOrderModel(
                bill_no=f"PO{i}",
                mto_number="AS900",
                material_code="03.23.009",
                material_name="贴纸",
                specification="",
                aux_prop_id=aux,
                order_qty=Decimal("100"),
                stock_in_qty=Decimal("100"),
                remain_stock_in_qty=Decimal("0"),
            )
            for i, aux in enumerate([211001, 199180, 211709], start=1)
        ]

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[],
            prod_receipts=[],
            material_picks=[],
            purchase_orders=pur_rows,
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 3, (
            "Expected 3 synthetic rows (one per aux variant). "
            "Got fewer → Pattern 11 regression: code-only dedup is back."
        )
        aux_ids = sorted(r.aux_prop_id for r in rows)
        assert aux_ids == [199180, 211001, 211709]
        for r in rows:
            assert r.material_code == "03.23.009"

    def test_prd_mo_multi_aux_no_bom_no_receipt_emits_all(self, mock_readers):
        """Wave 6C: 05.xx self-made code with multi-aux PRD_MO and no PPBOM.

        Pre-Wave-6C: only the first PRD_MO aux surfaced; the rest were silently
        dropped because block 2c added the code to covered_codes_synthetic and
        subsequent groups skipped.

        Real-data case: DK251003S / 05.20.01.07.011 PC镜片 had 3 PRD_MO rows
        at 3 distinct aux summing to 49440 (960 + 9600 + 38880). QP returned
        demand=960 (1/50 of Kingdee). Post-Wave-6C, all 3 rows emit so the
        sum matches Kingdee's PRD_MO total.

        The code-level gate is preserved when BOM exists (so 3-tier rollup
        attribution still works) and when 2a fired (so receipt rollup is
        only attributed once).
        """
        prod_orders = [
            ProductionOrderModel(
                bill_no=f"MO_W6C_{i}",
                mto_number="DK_W6C",
                workshop="测试",
                material_code="05.20.01.07.011",
                material_name="PC镜片(已印刷)",
                specification="",
                aux_prop_id=aux,
                qty=qty,
                status="已审核",
                create_date="2026-04-01",
            )
            for i, (aux, qty) in enumerate(
                [(105726, Decimal("960")),
                 (106250, Decimal("9600")),
                 (105980, Decimal("38880"))],
                start=1,
            )
        ]

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=prod_orders,
            prod_receipts=[],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 3, (
            f"Wave 6C: expected 3 synthetic rows from PRD_MO multi-aux, got "
            f"{len(rows)}. Pre-fix dropped all-but-first → demand 960 vs "
            f"Kingdee 49440 (50× shortfall on DK251003S 05.20.01.07.011)."
        )
        total_need = sum(r.need_qty for r in rows)
        assert total_need == Decimal("49440")
        aux_ids = sorted(r.aux_prop_id for r in rows)
        assert aux_ids == [105726, 105980, 106250]

    def test_prd_mo_multi_aux_with_prd_instock_keeps_old_dedup(self, mock_readers):
        """Wave 6C: when PRD_INSTOCK fired in 2a, 2c keeps the old code-level
        gate so the receipt rollup isn't attributed twice.

        Setup: PRD_INSTOCK at aux=A (1 emit in 2a), PRD_MO at aux=A and aux=B.
        Block 2a emits 1 row (aux=A) with _lookup_mo_qty(A) → exact match.
        Block 2c at aux=A: covered_keys hit → skip.
        Block 2c at aux=B: code already in covered_codes_synthetic AND
        codes_with_prd_instock_emit → skip (legacy behavior preserved).
        Result: 1 row total.
        """
        receipt = ProductionReceiptModel(
            bill_no="RK_W6C2",
            mto_number="DK_W6C2",
            material_code="05.20.01.07.012",
            material_name="自制件",
            specification="",
            real_qty=Decimal("100"),
            must_qty=Decimal("100"),
            aux_prop_id=900,  # aux=A
            mo_bill_no="MO_W6C2_A",
        )
        prod_orders = [
            ProductionOrderModel(
                bill_no="MO_W6C2_A",
                mto_number="DK_W6C2",
                workshop="测试",
                material_code="05.20.01.07.012",
                material_name="自制件",
                specification="",
                aux_prop_id=900,  # aux=A (matches receipt)
                qty=Decimal("100"),
                status="已审核",
                create_date="2026-04-01",
            ),
            ProductionOrderModel(
                bill_no="MO_W6C2_B",
                mto_number="DK_W6C2",
                workshop="测试",
                material_code="05.20.01.07.012",
                material_name="自制件",
                specification="",
                aux_prop_id=901,  # aux=B (no receipt at B)
                qty=Decimal("50"),
                status="已审核",
                create_date="2026-04-01",
            ),
        ]

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=prod_orders,
            prod_receipts=[receipt],
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        # 2a emits 1 (aux=A); 2c skips both A (covered_keys) and B (legacy
        # gate when 2a fired, prevents receipt rollup double attribution).
        assert len(rows) == 1
        assert rows[0].aux_prop_id == 900
        # need_qty comes from _lookup_mo_qty(A) = exact PRD_MO at A
        assert rows[0].need_qty == Decimal("100")

    def test_synthetic_row_dedup_within_source(self, mock_readers):
        """Composite-key dedup still prevents true duplicates.

        Two PRD_INSTOCK records with the same (material_code, aux_prop_id)
        must collapse to a single synthetic row. This was the legitimate
        purpose the original `covered_codes` set tried to serve; the
        composite (code, aux) key in `covered_keys` already handles it.
        """
        receipts = [
            ProductionReceiptModel(
                bill_no=bill,
                mto_number="AS950",
                material_code="03.05.001",
                material_name="纸箱A",
                specification="",
                real_qty=Decimal("50"),
                must_qty=Decimal("50"),
                aux_prop_id=0,
                mo_bill_no="MO950",
            )
            for bill in ("RK950A", "RK950B")
        ]

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[],
            prod_receipts=receipts,
            material_picks=[],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        assert rows[0].material_code == "03.05.001"
        assert rows[0].aux_prop_id == 0

    def test_pick_only_creates_synthetic_with_inferred_type(self, mock_readers):
        """Material pick without any other source creates synthetic row."""
        pick = MaterialPickingModel(
            bill_no="PM900",
            mto_number="AS900",
            material_code="03.02.001",
            app_qty=Decimal("100"),
            actual_qty=Decimal("80"),
            ppbom_bill_no="MO900",
            aux_prop_id=0,
        )

        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=[],
            prod_orders=[],
            prod_receipts=[],
            material_picks=[pick],
            purchase_orders=[],
            purchase_receipts=[],
            subcontracting_orders=[],
            sales_deliveries=[],
        )

        assert len(rows) == 1
        row = rows[0]
        assert row.material_code == "03.02.001"
        # source-table inference: pick with no other source → conservative default self-made
        assert row.material_type == 1
        assert row.pick_actual_qty == Decimal("80")

    # ------------------------------------------------------------------
    # Wave 5B regression pins (live path — both bugs share helpers).
    # ------------------------------------------------------------------
    def test_lookup_mo_qty_partial_exact_match_dedups_remainder(self, mock_readers):
        """Wave 5B Bug A — partial-exact-match dedup of PRD_MO Tier 2.5 rollup.

        Real-data: AS2602033 / 05.02.08.037 盒子. Kingdee says total demand
        = 32544 (sum of two PRD_MO rows). QP's BOM has 2 aux groups; ONE
        matches a PRD_MO aux exactly (32544), the OTHER misses. Pre-Wave-5B
        the matched row claimed Tier 1 (32544) AND the non-matched row
        claimed full Tier 2.5 rollup (32544) → SUM = 65088 = 2× truth.

        Post-Wave-5B partial-match dedup: matched row keeps 32544,
        non-matched row gets max(0, rollup - exact_matched) = 0. SUM =
        32544 = team's actual production target.

        Synthetic shape: BOM aux=A and aux=B (both same code). PRD_MO
        only at aux=A (qty=10000). _mo_qty_by_code total = 10000.
        Expected: aux=A row gets 10000 (Tier 1); aux=B row gets 0.
        """
        from src.readers.models import ProductionBOMModel

        mto = "AS2602033_W5B"
        bom_lines = [
            ProductionBOMModel(
                mo_bill_no="MO_AAA", mto_number=mto,
                material_code="05.02.08.037", material_name="盒子",
                specification="", aux_prop_id=900, material_type=1,
                need_qty=Decimal("8000"), picked_qty=Decimal("0"),
                no_picked_qty=Decimal("8000"),
            ),
            ProductionBOMModel(
                mo_bill_no="MO_BBB", mto_number=mto,
                material_code="05.02.08.037", material_name="盒子",
                specification="", aux_prop_id=901, material_type=1,
                need_qty=Decimal("8000"), picked_qty=Decimal("0"),
                no_picked_qty=Decimal("8000"),
            ),
        ]
        prod_orders = [
            # PRD_MO at aux=900 — Tier 1 exact match for the first BOM row.
            ProductionOrderModel(
                bill_no="MO_X", mto_number=mto, workshop="组装工段",
                material_code="05.02.08.037", material_name="盒子",
                specification="", aux_prop_id=900, qty=Decimal("10000"),
                status="已审核", create_date="2026-04-01",
            ),
        ]
        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=bom_lines, prod_orders=prod_orders,
            prod_receipts=[], material_picks=[], purchase_orders=[],
            purchase_receipts=[], subcontracting_orders=[], sales_deliveries=[],
        )
        assert len(rows) == 2
        by_aux = {r.aux_prop_id: r for r in rows}
        # Tier 1 row claims exact PRD_MO qty.
        assert by_aux[900].need_qty == Decimal("10000")
        # Non-matched row gets max(0, rollup - exact_matched) =
        # max(0, 10000 - 10000) = 0. NOT the full rollup (10000) and
        # NOT MAX(b.need_qty) = 8000.
        assert by_aux[901].need_qty == Decimal("0"), (
            f"Wave 5B partial-match dedup regressed. Got "
            f"{by_aux[901].need_qty}. Pre-fix this row would claim full "
            "rollup = 10000 (Tier 2.5 over-application); post-fix the "
            "remainder is max(0, 10000 - 10000) = 0. AS2602033 / "
            "05.02.08.037 real-data regression."
        )
        # SUM matches the team's PRD_MO target.
        assert sum((r.need_qty for r in rows), Decimal(0)) == Decimal("10000")

    def test_get_receipt_partial_exact_match_dedups_remainder(self, mock_readers):
        """Wave 5B Bug B — receipt-side partial-match dedup.

        Real-data: AK2510034 / 05.02.15.62 电镀镜片. Kingdee says
        prod_instock_real_qty=1444. QP's BOM has multiple aux groups;
        receipts are at completely different aux. Pre-Wave-5B QP returns
        0/0/0 for fulfilled/pick (Tier 1+2 miss; Tier 3 only fired for
        BOM aux=0). Post-fix the elected non-matched BOM-aux claims the
        rollup (1444); siblings stay 0; SUM matches Kingdee.

        Synthetic shape: BOM aux=A and aux=B; receipt at aux=B (Tier 1
        match for B) and aux=C (disjoint). _by_code_all total = 1444.
        Expected: aux=B row gets exact value; aux=A row gets remainder
        (1444 - exact_amount).
        """
        from src.readers.models import ProductionBOMModel

        mto = "AK2510034_W5B"
        bom_lines = [
            # BOM at aux=A (no receipt match) and aux=B (Tier 1 match).
            ProductionBOMModel(
                mo_bill_no="MO_R1", mto_number=mto,
                material_code="05.02.15.62", material_name="电镀镜片",
                specification="", aux_prop_id=900, material_type=1,
                need_qty=Decimal("722"), picked_qty=Decimal("0"),
                no_picked_qty=Decimal("722"),
            ),
            ProductionBOMModel(
                mo_bill_no="MO_R2", mto_number=mto,
                material_code="05.02.15.62", material_name="电镀镜片",
                specification="", aux_prop_id=901, material_type=1,
                need_qty=Decimal("722"), picked_qty=Decimal("0"),
                no_picked_qty=Decimal("722"),
            ),
        ]
        # Receipts: Tier 1 hit at aux=901 (=500), and disjoint aux=999 (=944).
        # Total all-aux rollup = 500 + 944 = 1444.
        receipts = [
            ProductionReceiptModel(
                bill_no="RK1", mto_number=mto, material_code="05.02.15.62",
                material_name="电镀镜片", specification="",
                real_qty=Decimal("500"), must_qty=Decimal("500"),
                aux_prop_id=901, mo_bill_no="MO_R2",
            ),
            ProductionReceiptModel(
                bill_no="RK2", mto_number=mto, material_code="05.02.15.62",
                material_name="电镀镜片", specification="",
                real_qty=Decimal("944"), must_qty=Decimal("944"),
                aux_prop_id=999, mo_bill_no="MO_DISJOINT",
            ),
        ]
        handler = self._make_handler(mock_readers)
        rows = handler._build_bom_joined_rows_from_live(
            production_bom=bom_lines, prod_orders=[], prod_receipts=receipts,
            material_picks=[], purchase_orders=[], purchase_receipts=[],
            subcontracting_orders=[], sales_deliveries=[],
        )
        assert len(rows) == 2
        by_aux = {r.aux_prop_id: r for r in rows}
        # Tier 1 match: receipt at aux=901 → exact 500.
        assert by_aux[901].prod_receipt_real_qty == Decimal("500")
        # Non-matched (aux=900): elected (only one non-matched, smallest
        # aux). Claims max(0, rollup - exact_sum) = 1444 - 500 = 944.
        assert by_aux[900].prod_receipt_real_qty == Decimal("944"), (
            f"Wave 5B receipt-side Tier 2.5 fall-through + dedup regressed. "
            f"Got {by_aux[900].prod_receipt_real_qty}. Pre-fix this row "
            "returned 0 (Tier 1+2 miss; Tier 3 only fired for BOM aux=0). "
            "Post-fix _get falls through to _by_code_all rollup with "
            "partial-match dedup. AK2510034 / 05.02.15.62 real-data "
            "regression."
        )
        # SUM across BOM-aux rows matches Kingdee total.
        total = sum(
            (r.prod_receipt_real_qty for r in rows), Decimal(0)
        )
        assert total == Decimal("1444"), (
            f"SUM(prod_receipt_real_qty) across {len(rows)} BOM-aux rows "
            f"= {total}, expected 1444. Without Wave 5B receipt-side "
            "dedup, both BOM-aux rows could attribute the rollup → "
            "SUM = 2× actual."
        )


class TestLiveMatchQualityParity:
    """Stage 4 of PLAN_aux_match_visibility: live-path match_quality_breakdown
    must mirror the same tier semantics as the cache SQL CASE expressions.
    """

    def _make_handler(self, mock_readers):
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
        )

    def test_live_emits_exact_when_aux_matches(self, mock_readers):
        bom = ProductionBOMModel(
            mo_bill_no="MO001", mto_number="AS001",
            material_code="05.01.001", material_name="自制件",
            specification="", aux_prop_id=5001, material_type=1,
            need_qty=Decimal("100"), picked_qty=Decimal("0"), no_picked_qty=Decimal("100"),
        )
        receipt = ProductionReceiptModel(
            bill_no="RK001", mto_number="AS001", material_code="05.01.001",
            real_qty=Decimal("80"), must_qty=Decimal("100"), aux_prop_id=5001,
        )
        rows = self._make_handler(mock_readers)._build_bom_joined_rows_from_live(
            production_bom=[bom], prod_orders=[], prod_receipts=[receipt],
            material_picks=[], purchase_orders=[], purchase_receipts=[],
            subcontracting_orders=[], sales_deliveries=[],
        )
        assert len(rows) == 1
        assert rows[0].match_quality_breakdown["prod_receipt"] == "exact"

    def test_live_emits_aux_zero_fallback_when_bom_aux_unmatched(self, mock_readers):
        bom = ProductionBOMModel(
            mo_bill_no="MO001", mto_number="AS001",
            material_code="05.01.001", material_name="自制件",
            specification="", aux_prop_id=5001, material_type=1,
            need_qty=Decimal("100"), picked_qty=Decimal("0"), no_picked_qty=Decimal("100"),
        )
        receipt = ProductionReceiptModel(
            bill_no="RK001", mto_number="AS001", material_code="05.01.001",
            real_qty=Decimal("80"), must_qty=Decimal("100"), aux_prop_id=0,
        )
        rows = self._make_handler(mock_readers)._build_bom_joined_rows_from_live(
            production_bom=[bom], prod_orders=[], prod_receipts=[receipt],
            material_picks=[], purchase_orders=[], purchase_receipts=[],
            subcontracting_orders=[], sales_deliveries=[],
        )
        assert len(rows) == 1
        assert rows[0].match_quality_breakdown["prod_receipt"] == "aux_zero_fallback"
        assert rows[0].prod_receipt_real_qty == Decimal("80")  # tier-2 fallback resolved

    def test_live_emits_all_aux_rollup_when_bom_is_generic(self, mock_readers):
        bom = ProductionBOMModel(
            mo_bill_no="MO001", mto_number="AS001",
            material_code="05.01.001", material_name="自制件",
            specification="", aux_prop_id=0, material_type=1,
            need_qty=Decimal("100"), picked_qty=Decimal("0"), no_picked_qty=Decimal("100"),
        )
        receipts = [
            ProductionReceiptModel(
                bill_no="RK001", mto_number="AS001", material_code="05.01.001",
                real_qty=Decimal("30"), must_qty=Decimal("30"), aux_prop_id=5001,
            ),
            ProductionReceiptModel(
                bill_no="RK002", mto_number="AS001", material_code="05.01.001",
                real_qty=Decimal("20"), must_qty=Decimal("20"), aux_prop_id=5002,
            ),
        ]
        rows = self._make_handler(mock_readers)._build_bom_joined_rows_from_live(
            production_bom=[bom], prod_orders=[], prod_receipts=receipts,
            material_picks=[], purchase_orders=[], purchase_receipts=[],
            subcontracting_orders=[], sales_deliveries=[],
        )
        assert len(rows) == 1
        assert rows[0].match_quality_breakdown["prod_receipt"] == "all_aux_rollup"
        assert rows[0].prod_receipt_real_qty == Decimal("50")  # 30 + 20 summed

    def test_live_emits_no_match_when_no_receipts_anywhere(self, mock_readers):
        bom = ProductionBOMModel(
            mo_bill_no="MO001", mto_number="AS001",
            material_code="05.01.001", material_name="自制件",
            specification="", aux_prop_id=5001, material_type=1,
            need_qty=Decimal("100"), picked_qty=Decimal("0"), no_picked_qty=Decimal("100"),
        )
        rows = self._make_handler(mock_readers)._build_bom_joined_rows_from_live(
            production_bom=[bom], prod_orders=[], prod_receipts=[],
            material_picks=[], purchase_orders=[], purchase_receipts=[],
            subcontracting_orders=[], sales_deliveries=[],
        )
        assert len(rows) == 1
        for source in (
            "prod_receipt", "pick", "purchase_order", "purchase_receipt",
            "subcontract", "delivery",
        ):
            assert rows[0].match_quality_breakdown[source] == "no_match"


class TestStrictAuxFilter:
    """Stage 6 of PLAN_aux_match_visibility: strict mode zeros out non-exact qtys."""

    def test_filter_passes_through_exact_rows_unchanged(self):
        from src.query.cache_reader import BOMJoinedRow

        row = BOMJoinedRow(
            mo_bill_no="MO001", mto_number="AS001",
            material_code="C001", material_name="", specification="",
            aux_attributes="", aux_prop_id=5001, material_type=1,
            need_qty=Decimal("100"), picked_qty=Decimal("0"), no_picked_qty=Decimal("100"),
            prod_receipt_real_qty=Decimal("80"), prod_receipt_must_qty=Decimal("100"),
            pick_actual_qty=Decimal("70"), pick_app_qty=Decimal("75"),
            purchase_order_qty=Decimal("0"), purchase_stock_in_qty=Decimal("0"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"), subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
            match_quality_breakdown={
                "prod_receipt": "exact", "pick": "exact",
                "purchase_order": "no_match", "purchase_receipt": "no_match",
                "subcontract": "no_match", "delivery": "no_match",
            },
        )
        out = MTOQueryHandler._apply_strict_aux_filter([row])
        assert len(out) == 1
        # Exact rows pass through with original qtys.
        assert out[0].prod_receipt_real_qty == Decimal("80")
        assert out[0].pick_actual_qty == Decimal("70")

    def test_filter_zeros_aux_zero_fallback_and_marks_no_match(self):
        from src.query.cache_reader import BOMJoinedRow

        row = BOMJoinedRow(
            mo_bill_no="MO001", mto_number="AS001",
            material_code="C001", material_name="", specification="",
            aux_attributes="", aux_prop_id=5001, material_type=1,
            need_qty=Decimal("100"), picked_qty=Decimal("0"), no_picked_qty=Decimal("100"),
            prod_receipt_real_qty=Decimal("80"),  # came from aux=0 fallback
            prod_receipt_must_qty=Decimal("100"),
            pick_actual_qty=Decimal("0"), pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("0"), purchase_stock_in_qty=Decimal("0"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"), subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
            match_quality_breakdown={
                "prod_receipt": "aux_zero_fallback",
                "pick": "no_match", "purchase_order": "no_match",
                "purchase_receipt": "no_match", "subcontract": "no_match",
                "delivery": "no_match",
            },
        )
        out = MTOQueryHandler._apply_strict_aux_filter([row])
        assert len(out) == 1
        # qty zeroed out — strict mode exposes the data quality issue.
        assert out[0].prod_receipt_real_qty == Decimal("0")
        # match_quality flipped to no_match so the UI badge disappears for this source.
        assert out[0].match_quality_breakdown["prod_receipt"] == "no_match"
        # need_qty / BOM-sourced fields unchanged.
        assert out[0].need_qty == Decimal("100")

    def test_filter_zeros_all_aux_rollup(self):
        from src.query.cache_reader import BOMJoinedRow

        row = BOMJoinedRow(
            mo_bill_no="MO001", mto_number="AS001",
            material_code="C001", material_name="", specification="",
            aux_attributes="", aux_prop_id=0, material_type=2,
            need_qty=Decimal("100"), picked_qty=Decimal("0"), no_picked_qty=Decimal("100"),
            prod_receipt_real_qty=Decimal("0"), prod_receipt_must_qty=Decimal("0"),
            pick_actual_qty=Decimal("0"), pick_app_qty=Decimal("0"),
            purchase_order_qty=Decimal("200"),  # came from all-aux rollup
            purchase_stock_in_qty=Decimal("150"),
            purchase_receipt_real_qty=Decimal("0"),
            subcontract_order_qty=Decimal("0"), subcontract_stock_in_qty=Decimal("0"),
            delivery_real_qty=Decimal("0"),
            match_quality_breakdown={
                "prod_receipt": "no_match", "pick": "no_match",
                "purchase_order": "all_aux_rollup",
                "purchase_receipt": "no_match", "subcontract": "no_match",
                "delivery": "no_match",
            },
        )
        out = MTOQueryHandler._apply_strict_aux_filter([row])
        assert out[0].purchase_order_qty == Decimal("0")
        assert out[0].purchase_stock_in_qty == Decimal("0")
        assert out[0].match_quality_breakdown["purchase_order"] == "no_match"


class TestMTOClassificationFields:
    """The response carries business-line / order-type badges derived from the
    MTO number prefix via classify_mto(). Pure-additive: existing quantity and
    column logic is untouched. Uses the live path for determinism.
    """

    def create_handler(self, mock_readers):
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
            cache_reader=None,
        )

    def _wire_purchase_only(self, mock_readers, sample_purchase_orders):
        """Minimal live wiring: only purchase orders return data (03 class)."""
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

    @pytest.mark.asyncio
    async def test_as_full_order(self, mock_readers, sample_purchase_orders):
        """AS prefix -> 外销 · 完整订单, not a sample."""
        self._wire_purchase_only(mock_readers, sample_purchase_orders)
        handler = self.create_handler(mock_readers)

        result = await handler.get_status("AS2604001", use_cache=False)

        assert result.business_line_label == "外销"
        assert result.order_type_label == "完整订单"
        assert result.is_sample is False

    @pytest.mark.asyncio
    async def test_ak_stock_halffinished_order(self, mock_readers, sample_purchase_orders):
        """AK prefix -> 外销 · 备货半成品单, not a sample."""
        self._wire_purchase_only(mock_readers, sample_purchase_orders)
        handler = self.create_handler(mock_readers)

        result = await handler.get_status("AK2510034", use_cache=False)

        assert result.business_line_label == "外销"
        assert result.order_type_label == "备货半成品单"
        assert result.is_sample is False

    @pytest.mark.asyncio
    async def test_ay_sample_order(self, mock_readers, sample_purchase_orders):
        """AY prefix -> 外销 · 样品单, is_sample True."""
        self._wire_purchase_only(mock_readers, sample_purchase_orders)
        handler = self.create_handler(mock_readers)

        result = await handler.get_status("AY2604099", use_cache=False)

        assert result.business_line_label == "外销"
        assert result.order_type_label == "样品单"
        assert result.is_sample is True
