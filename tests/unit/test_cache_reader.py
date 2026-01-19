"""Tests for src/query/cache_reader.py"""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.query.cache_reader import CacheReader, CacheResult


class TestCacheResult:
    """Tests for CacheResult dataclass."""

    def test_cache_result_fresh(self):
        """Test fresh cache result."""
        result = CacheResult(
            data=[1, 2, 3],
            synced_at=datetime.now(),
            is_fresh=True,
        )
        assert result.is_fresh is True
        assert len(result.data) == 3

    def test_cache_result_stale(self):
        """Test stale cache result."""
        result = CacheResult(
            data=[1],
            synced_at=datetime.now() - timedelta(hours=2),
            is_fresh=False,
        )
        assert result.is_fresh is False

    def test_cache_result_empty(self):
        """Test empty cache result."""
        result = CacheResult(
            data=[],
            synced_at=None,
            is_fresh=False,
        )
        assert result.data == []
        assert result.synced_at is None


class TestCacheReaderIsFresh:
    """Tests for CacheReader._is_fresh method."""

    def test_is_fresh_within_ttl(self):
        """Test freshness check within TTL."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        # Within TTL (30 minutes ago in UTC)
        recent = datetime.utcnow() - timedelta(minutes=30)
        assert reader._is_fresh(recent) is True

    def test_is_fresh_outside_ttl(self):
        """Test freshness check outside TTL."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        # Outside TTL (90 minutes ago in UTC)
        old = datetime.utcnow() - timedelta(minutes=90)
        assert reader._is_fresh(old) is False

    def test_is_fresh_exactly_at_ttl(self):
        """Test freshness check at exact TTL boundary."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        # Exactly at TTL boundary (should be stale)
        at_boundary = datetime.utcnow() - timedelta(minutes=60)
        assert reader._is_fresh(at_boundary) is False

    def test_is_fresh_with_none(self):
        """Test freshness check with None timestamp."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        assert reader._is_fresh(None) is False

    def test_is_fresh_custom_ttl(self):
        """Test freshness with custom TTL."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=120)  # 2 hours

        # 90 minutes ago - should be fresh with 2 hour TTL
        time_90min_ago = datetime.utcnow() - timedelta(minutes=90)
        assert reader._is_fresh(time_90min_ago) is True


class TestCacheReaderParseTimestamp:
    """Tests for CacheReader._parse_timestamp method."""

    def test_parse_timestamp_iso_format(self):
        """Test parsing ISO format string."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        result = reader._parse_timestamp("2025-01-15T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_timestamp_datetime_passthrough(self):
        """Test datetime passthrough."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        dt = datetime(2025, 1, 15, 10, 30)
        assert reader._parse_timestamp(dt) == dt

    def test_parse_timestamp_none(self):
        """Test parsing None."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        assert reader._parse_timestamp(None) is None

    def test_parse_timestamp_invalid(self):
        """Test parsing invalid format."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        assert reader._parse_timestamp("invalid") is None
        assert reader._parse_timestamp("not-a-date") is None

    def test_parse_timestamp_sqlite_format(self):
        """Test parsing SQLite timestamp format."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        # SQLite CURRENT_TIMESTAMP format
        result = reader._parse_timestamp("2025-01-15 10:30:00")
        assert isinstance(result, datetime)


class TestCacheReaderGetProductionOrders:
    """Tests for CacheReader.get_production_orders method."""

    @pytest.mark.asyncio
    async def test_get_production_orders_cache_miss(self, test_database):
        """Test cache miss returns empty result."""
        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_production_orders("NONEXISTENT")

        assert result.data == []
        assert result.synced_at is None
        assert result.is_fresh is False

    @pytest.mark.asyncio
    async def test_get_production_orders_with_data(self, test_database):
        """Test get_production_orders with cached data."""
        # Insert test data
        await test_database.execute_write(
            """
            INSERT INTO cached_production_orders
            (mto_number, bill_no, workshop, material_code, material_name,
             specification, aux_attributes, qty, raw_data, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                "AK2510034",
                "MO0001",
                "Workshop",
                "M001",
                "Material",
                "Spec",
                "",
                100,
                '{"status": "Approved", "create_date": "2025-01-15"}',
            ],
        )

        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_production_orders("AK2510034")

        assert len(result.data) == 1
        assert result.data[0].mto_number == "AK2510034"
        assert result.data[0].bill_no == "MO0001"
        assert result.data[0].qty == Decimal("100")
        assert result.synced_at is not None
        assert result.is_fresh is True  # Just inserted


class TestCacheReaderGetProductionBom:
    """Tests for CacheReader.get_production_bom method."""

    @pytest.mark.asyncio
    async def test_get_production_bom_empty_input(self, test_database):
        """Test empty bill_nos returns empty result."""
        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_production_bom([])

        assert result.data == []
        assert result.synced_at is None
        assert result.is_fresh is False

    @pytest.mark.asyncio
    async def test_get_production_bom_no_matches(self, test_database):
        """Test no matching records."""
        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_production_bom(["NONEXISTENT"])

        assert result.data == []
        assert result.is_fresh is False

    @pytest.mark.asyncio
    async def test_get_production_bom_with_data(self, test_database):
        """Test get_production_bom with cached data."""
        # Insert test data
        await test_database.execute_write(
            """
            INSERT INTO cached_production_bom
            (mo_bill_no, material_code, material_name, material_type,
             need_qty, picked_qty, no_picked_qty, raw_data, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                "MO0001",
                "C001",
                "Part",
                1,
                50,
                30,
                20,
                '{"mto_number": "AK2510034", "specification": "Spec", "aux_attributes": ""}',
            ],
        )

        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_production_bom(["MO0001"])

        assert len(result.data) == 1
        assert result.data[0].mo_bill_no == "MO0001"
        assert result.data[0].material_code == "C001"
        assert result.data[0].need_qty == Decimal("50")
        assert result.is_fresh is True


class TestCacheReaderCheckFreshness:
    """Tests for CacheReader.check_freshness method."""

    @pytest.mark.asyncio
    async def test_check_freshness_no_data(self, test_database):
        """Test freshness check with no data."""
        reader = CacheReader(test_database, ttl_minutes=60)
        is_fresh, synced_at = await reader.check_freshness("NONEXISTENT")

        assert is_fresh is False
        assert synced_at is None

    @pytest.mark.asyncio
    async def test_check_freshness_with_fresh_data(self, test_database):
        """Test freshness check with fresh data."""
        # Insert recent data
        await test_database.execute_write(
            """
            INSERT INTO cached_production_orders
            (mto_number, bill_no, workshop, material_code, material_name,
             specification, aux_attributes, qty, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["AK2510034", "MO0001", "", "M001", "", "", "", 100],
        )

        reader = CacheReader(test_database, ttl_minutes=60)
        is_fresh, synced_at = await reader.check_freshness("AK2510034")

        assert is_fresh is True
        assert synced_at is not None


class TestCacheReaderRowConversion:
    """Tests for row-to-model conversion methods."""

    def test_row_to_order_basic(self):
        """Test _row_to_order with basic data."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0001",  # bill_no
            "AK2510034",  # mto_number
            "Workshop",  # workshop
            "M001",  # material_code
            "Material",  # material_name
            "Spec",  # specification
            "Blue",  # aux_attributes
            100,  # qty
            '{"status": "Approved", "create_date": "2025-01-15"}',  # raw_data
            "2025-01-15T10:00:00",  # synced_at
        )

        model = reader._row_to_order(row)

        assert model.bill_no == "MO0001"
        assert model.mto_number == "AK2510034"
        assert model.qty == Decimal("100")
        assert model.status == "Approved"
        assert model.create_date == "2025-01-15"

    def test_row_to_order_null_values(self):
        """Test _row_to_order with null values."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0001",
            "AK001",
            None,  # workshop
            "M001",
            None,  # material_name
            None,  # specification
            None,  # aux_attributes
            None,  # qty
            None,  # raw_data
            None,  # synced_at
        )

        model = reader._row_to_order(row)

        assert model.workshop == ""
        assert model.material_name == ""
        assert model.qty == Decimal("0")

    def test_row_to_bom_basic(self):
        """Test _row_to_bom with basic data."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0001",  # mo_bill_no
            "C001",  # material_code
            "Part",  # material_name
            1,  # material_type
            50,  # need_qty
            30,  # picked_qty
            20,  # no_picked_qty
            '{"mto_number": "AK001", "specification": "Spec", "aux_attributes": "Blue", "aux_prop_id": 1001}',  # raw_data
            "2025-01-15T10:00:00",  # synced_at
        )

        model = reader._row_to_bom(row)

        assert model.mo_bill_no == "MO0001"
        assert model.material_code == "C001"
        assert model.material_type == 1
        assert model.need_qty == Decimal("50")
        assert model.mto_number == "AK001"
        assert model.aux_attributes == "Blue"
        assert model.aux_prop_id == 1001

    def test_row_to_bom_invalid_json(self):
        """Test _row_to_bom with invalid JSON in raw_data."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0001",
            "C001",
            "Part",
            1,
            50,
            30,
            20,
            "invalid json",  # Invalid JSON
            "2025-01-15T10:00:00",
        )

        model = reader._row_to_bom(row)

        # Should not crash, use defaults
        assert model.mto_number == ""
        assert model.specification == ""
        assert model.aux_prop_id == 0
