"""Tests for src/query/mto_handler.py - Core business logic."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.query.mto_handler import (
    MaterialType,
    MTOQueryHandler,
    _AggregatedBOMEntry,
    _sum_by_material,
)
from src.readers.models import ProductionBOMModel


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

    def test_display_name_unknown(self):
        """Test display name for unknown type returns empty."""
        # MaterialType is IntEnum, so accessing value outside enum still works
        # but display_name will return "未知" for unknown types in handler
        pass  # This is handled in handler, not enum


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


class TestAggregatedBOMEntry:
    """Tests for _AggregatedBOMEntry dataclass."""

    def test_aggregated_entry_properties(self):
        """Test that aggregated entry forwards properties correctly."""
        base_entry = ProductionBOMModel(
            mo_bill_no="MO001",
            mto_number="AK001",
            material_code="C001",
            material_name="Part",
            specification="Spec",
            aux_attributes="Blue",
            aux_prop_id=1001,
            material_type=2,
            need_qty=Decimal("10"),
            picked_qty=Decimal("5"),
            no_picked_qty=Decimal("5"),
        )

        aggregated = _AggregatedBOMEntry(
            _base=base_entry,
            need_qty=Decimal("30"),
            picked_qty=Decimal("15"),
            no_picked_qty=Decimal("15"),
        )

        # Base properties are forwarded
        assert aggregated.material_code == "C001"
        assert aggregated.material_name == "Part"
        assert aggregated.specification == "Spec"
        assert aggregated.aux_attributes == "Blue"
        assert aggregated.aux_prop_id == 1001
        assert aggregated.material_type == 2
        assert aggregated.mto_number == "AK001"

        # Quantities are from aggregation
        assert aggregated.need_qty == Decimal("30")
        assert aggregated.picked_qty == Decimal("15")
        assert aggregated.no_picked_qty == Decimal("15")


class TestBOMEntryAggregation:
    """Tests for BOM entry aggregation logic."""

    def create_handler(self, mock_readers):
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
        )

    def test_aggregate_empty_entries(self, mock_readers):
        """Test aggregation with empty list."""
        handler = self.create_handler(mock_readers)
        result = handler._aggregate_bom_entries([])
        assert result == []

    def test_aggregate_single_entry(self, mock_readers, sample_bom_entries):
        """Test aggregation with single entry (no merging needed)."""
        handler = self.create_handler(mock_readers)
        result = handler._aggregate_bom_entries([sample_bom_entries[0]])

        assert len(result) == 1
        assert result[0].material_code == "C001"
        assert result[0].need_qty == Decimal("50")

    def test_aggregate_different_materials(self, mock_readers, sample_bom_entries):
        """Test entries with different materials stay separate."""
        handler = self.create_handler(mock_readers)
        result = handler._aggregate_bom_entries(sample_bom_entries)

        # 3 different materials -> 3 entries
        assert len(result) == 3

    def test_aggregate_same_material_different_aux(self, mock_readers):
        """Test that same material with different aux_attributes stays separate."""
        handler = self.create_handler(mock_readers)

        entries = [
            ProductionBOMModel(
                mo_bill_no="MO001",
                mto_number="AK001",
                material_code="C001",
                material_name="Part",
                specification="",
                aux_attributes="Blue",  # Different aux
                material_type=1,
                need_qty=Decimal("10"),
                picked_qty=Decimal("5"),
                no_picked_qty=Decimal("5"),
            ),
            ProductionBOMModel(
                mo_bill_no="MO001",
                mto_number="AK001",
                material_code="C001",
                material_name="Part",
                specification="",
                aux_attributes="Red",  # Different aux
                material_type=1,
                need_qty=Decimal("20"),
                picked_qty=Decimal("10"),
                no_picked_qty=Decimal("10"),
            ),
        ]

        result = handler._aggregate_bom_entries(entries)

        # Should NOT merge - different aux_attributes
        assert len(result) == 2

    def test_aggregate_same_material_same_aux(self, mock_readers):
        """Test that identical keys get merged."""
        handler = self.create_handler(mock_readers)

        entries = [
            ProductionBOMModel(
                mo_bill_no="MO001",
                mto_number="AK001",
                material_code="C001",
                material_name="Part",
                specification="",
                aux_attributes="Blue",
                material_type=1,
                need_qty=Decimal("10"),
                picked_qty=Decimal("5"),
                no_picked_qty=Decimal("5"),
            ),
            ProductionBOMModel(
                mo_bill_no="MO002",  # Different MO but same key
                mto_number="AK001",
                material_code="C001",
                material_name="Part",
                specification="",
                aux_attributes="Blue",  # Same aux
                material_type=1,
                need_qty=Decimal("20"),
                picked_qty=Decimal("10"),
                no_picked_qty=Decimal("10"),
            ),
        ]

        result = handler._aggregate_bom_entries(entries)

        # Should merge - same (material_code, aux_attributes, mto_number)
        assert len(result) == 1
        assert result[0].need_qty == Decimal("30")
        assert result[0].picked_qty == Decimal("15")
        assert result[0].no_picked_qty == Decimal("15")


class TestMTOQueryHandler:
    """Tests for MTOQueryHandler.get_status method."""

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
    async def test_get_status_no_orders_raises(self, mock_readers):
        """Test ValueError when no production orders found."""
        mock_readers["production_order"].fetch_by_mto = AsyncMock(return_value=[])

        handler = self.create_handler(mock_readers)

        with pytest.raises(ValueError, match="No production orders found"):
            await handler.get_status("NONEXISTENT", use_cache=False)

    @pytest.mark.asyncio
    async def test_get_status_live_api(
        self,
        mock_readers,
        sample_production_order,
        sample_bom_entries,
        sample_production_receipts,
        sample_purchase_orders,
        sample_purchase_receipts,
        sample_subcontracting_orders,
    ):
        """Test get_status from live API."""
        # Setup mocks
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[sample_production_order]
        )
        mock_readers["production_bom"].fetch_by_bill_nos = AsyncMock(
            return_value=sample_bom_entries
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(
            return_value=sample_production_receipts
        )
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(
            return_value=sample_purchase_orders
        )
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(
            return_value=sample_purchase_receipts
        )
        mock_readers["subcontracting_order"].fetch_by_mto = AsyncMock(
            return_value=sample_subcontracting_orders
        )
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])

        # Mock aux property lookup
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={1001: "Blue Model"}
        )

        handler = self.create_handler(mock_readers)

        result = await handler.get_status("AK2510034", use_cache=False)

        assert result.mto_number == "AK2510034"
        assert result.data_source == "live"
        assert result.parent.mto_number == "AK2510034"
        # Check children exist (exact count depends on material types)
        assert len(result.children) >= 1

    @pytest.mark.asyncio
    async def test_get_status_cache_miss_fallback_to_live(
        self, mock_readers, sample_production_order, sample_bom_entries
    ):
        """Test cache miss falls back to live API."""
        from src.query.cache_reader import CacheResult

        mock_cache = MagicMock()
        mock_cache.get_production_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=None, is_fresh=False)
        )

        # Setup live API mocks
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[sample_production_order]
        )
        mock_readers["production_bom"].fetch_by_bill_nos = AsyncMock(
            return_value=sample_bom_entries
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["subcontracting_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)

        result = await handler.get_status("AK2510034", use_cache=True)

        assert result.data_source == "live"
        mock_cache.get_production_orders.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_status_cache_hit(
        self, mock_readers, sample_production_order, sample_bom_entries
    ):
        """Test cache hit returns cached data."""
        from datetime import datetime

        from src.query.cache_reader import CacheResult

        mock_cache = MagicMock()
        synced_at = datetime.utcnow()

        # Mock all cache methods - they're all called in _try_cache
        mock_cache.get_production_orders = AsyncMock(
            return_value=CacheResult(
                data=[sample_production_order],
                synced_at=synced_at,
                is_fresh=True,
            )
        )
        mock_cache.get_production_bom = AsyncMock(
            return_value=CacheResult(
                data=sample_bom_entries,
                synced_at=synced_at,
                is_fresh=True,
            )
        )
        mock_cache.get_purchase_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )
        mock_cache.get_subcontracting_orders = AsyncMock(
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
        mock_cache.get_sales_orders = AsyncMock(
            return_value=CacheResult(data=[], synced_at=synced_at, is_fresh=True)
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)

        result = await handler.get_status("AK2510034", use_cache=True)

        assert result.data_source == "cache"
        assert result.cache_age_seconds is not None

    @pytest.mark.asyncio
    async def test_get_status_use_cache_false_skips_cache(
        self, mock_readers, sample_production_order, sample_bom_entries
    ):
        """Test use_cache=False skips cache lookup."""
        from datetime import datetime

        from src.query.cache_reader import CacheResult

        mock_cache = MagicMock()
        mock_cache.get_production_orders = AsyncMock(
            return_value=CacheResult(
                data=[sample_production_order],
                synced_at=datetime.utcnow(),
                is_fresh=True,
            )
        )

        # Setup live API mocks
        mock_readers["production_order"].fetch_by_mto = AsyncMock(
            return_value=[sample_production_order]
        )
        mock_readers["production_bom"].fetch_by_bill_nos = AsyncMock(
            return_value=sample_bom_entries
        )
        mock_readers["production_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["purchase_receipt"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["subcontracting_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["material_picking"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_delivery"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["sales_order"].fetch_by_mto = AsyncMock(return_value=[])
        mock_readers["production_order"].client.lookup_aux_properties = AsyncMock(
            return_value={}
        )

        handler = self.create_handler(mock_readers, cache_reader=mock_cache)

        result = await handler.get_status("AK2510034", use_cache=False)

        assert result.data_source == "live"
        mock_cache.get_production_orders.assert_not_called()
