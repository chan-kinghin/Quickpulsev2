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
            "Approved",  # status
            "2025-01-15",  # create_date
            12345,  # aux_prop_id
            None,  # photo_file_id_1
            None,  # photo_file_id_2
            None,  # photo_file_id_3
            "2025-01-15 12:00:00",  # synced_at
        )

        model = reader._row_to_order(row)

        assert model.bill_no == "MO0001"
        assert model.mto_number == "AK2510034"
        assert model.qty == Decimal("100")
        assert model.status == "Approved"
        assert model.create_date == "2025-01-15"
        assert model.aux_prop_id == 12345
        assert model.photo_file_id_1 is None
        assert model.photo_file_id_2 is None
        assert model.photo_file_id_3 is None

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
            None,  # status
            None,  # create_date
            None,  # aux_prop_id
            None,  # photo_file_id_1
            None,  # photo_file_id_2
            None,  # photo_file_id_3
            None,  # synced_at
        )

        model = reader._row_to_order(row)

        assert model.workshop == ""
        assert model.material_name == ""
        assert model.qty == Decimal("0")
        assert model.aux_prop_id == 0
        assert model.photo_file_id_1 is None
        assert model.photo_file_id_2 is None
        assert model.photo_file_id_3 is None

    def test_row_to_order_with_photo_file_ids(self):
        """Test _row_to_order surfaces photo FileIDs from the cache row."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0002",  # bill_no
            "AK2510099",  # mto_number
            "WS",  # workshop
            "M999",  # material_code
            "Name",  # material_name
            "Spec",  # specification
            "",  # aux_attributes
            42,  # qty
            "B",  # status
            "2026-05-11",  # create_date
            0,  # aux_prop_id
            "a" * 32,  # photo_file_id_1
            "",  # photo_file_id_2 (empty slot — preserved as-is)
            "c" * 32,  # photo_file_id_3
            "2026-05-11 12:00:00",  # synced_at
        )

        model = reader._row_to_order(row)

        assert model.photo_file_id_1 == "a" * 32
        assert model.photo_file_id_2 == ""
        assert model.photo_file_id_3 == "c" * 32

    def test_row_to_bom_basic(self):
        """Test _row_to_bom with basic data."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0001",  # mo_bill_no
            "AK001",  # mto_number
            "C001",  # material_code
            "Part",  # material_name
            "Spec",  # specification
            "Blue",  # aux_attributes
            1001,  # aux_prop_id
            1,  # material_type
            50,  # need_qty
            30,  # picked_qty
            20,  # no_picked_qty
            "硅胶防水袋",  # material_group_name (column 11)
            "外销包材",  # category_name (column 12)
            1,  # is_purchase (column 13)
        )

        model = reader._row_to_bom(row)

        assert model.mo_bill_no == "MO0001"
        assert model.material_code == "C001"
        assert model.material_type == 1
        assert model.need_qty == Decimal("50")
        assert model.mto_number == "AK001"
        assert model.aux_attributes == "Blue"
        assert model.aux_prop_id == 1001
        assert model.material_group_name == "硅胶防水袋"
        assert model.category_name == "外销包材"
        assert model.is_purchase is True

    def test_row_to_bom_with_null_values(self):
        """Test _row_to_bom with null values."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0001",  # mo_bill_no
            None,  # mto_number
            "C001",  # material_code
            None,  # material_name
            None,  # specification
            None,  # aux_attributes
            None,  # aux_prop_id
            1,  # material_type
            50,  # need_qty
            30,  # picked_qty
            20,  # no_picked_qty
            None,  # material_group_name (column 11)
            None,  # category_name (column 12)
            None,  # is_purchase (column 13)
        )

        model = reader._row_to_bom(row)

        # Should handle nulls gracefully
        assert model.mto_number == ""
        assert model.specification == ""
        assert model.aux_prop_id == 0
        assert model.material_group_name == ""
        assert model.category_name == ""
        assert model.is_purchase is False

    def test_row_to_purchase_order_happy_path(self):
        """Test _row_to_purchase_order with all fields populated."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "PO20260115-001",  # 0: bill_no
            "AK2510034",       # 1: mto_number
            "03.01.002",       # 2: material_code
            "铝合金板",         # 3: material_name
            "500x300x2mm",     # 4: specification
            "银色",            # 5: aux_attributes
            2001,              # 6: aux_prop_id
            Decimal("200.00"), # 7: order_qty
            Decimal("150.00"), # 8: stock_in_qty
            Decimal("50.00"),  # 9: remain_stock_in_qty
            '{"some": "raw"}', # 10: raw_data
            "2026-01-15 10:00:00",  # 11: synced_at
        )

        model = reader._row_to_purchase_order(row)

        assert model.bill_no == "PO20260115-001"
        assert model.mto_number == "AK2510034"
        assert model.material_code == "03.01.002"
        assert model.material_name == "铝合金板"
        assert model.specification == "500x300x2mm"
        assert model.aux_attributes == "银色"
        assert model.aux_prop_id == 2001
        assert model.order_qty == Decimal("200.00")
        assert model.stock_in_qty == Decimal("150.00")
        assert model.remain_stock_in_qty == Decimal("50.00")

    def test_row_to_purchase_order_with_nones(self):
        """Test _row_to_purchase_order with None/edge-case values."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "PO001",   # 0: bill_no
            "AK001",   # 1: mto_number
            "03.02.001",  # 2: material_code
            None,      # 3: material_name
            None,      # 4: specification
            None,      # 5: aux_attributes
            None,      # 6: aux_prop_id
            None,      # 7: order_qty
            Decimal("0"),  # 8: stock_in_qty
            None,      # 9: remain_stock_in_qty
            None,      # 10: raw_data
            None,      # 11: synced_at
        )

        model = reader._row_to_purchase_order(row)

        assert model.bill_no == "PO001"
        assert model.material_name == ""
        assert model.specification == ""
        assert model.aux_attributes == ""
        assert model.aux_prop_id == 0
        assert model.order_qty == Decimal("0")
        assert model.stock_in_qty == Decimal("0")
        assert model.remain_stock_in_qty == Decimal("0")

    def test_row_to_subcontracting_order_happy_path(self):
        """Test _row_to_subcontracting_order with all fields populated."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        raw_data = '{"material_name": "委外加工件", "specification": "CNC精加工"}'
        row = (
            "SUB20260120-003",  # 0: bill_no
            "AK2510034",        # 1: mto_number
            "05.03.001",        # 2: material_code
            Decimal("500.00"),  # 3: order_qty
            Decimal("300.00"),  # 4: stock_in_qty
            Decimal("200.00"),  # 5: no_stock_in_qty
            3001,               # 6: aux_prop_id
            raw_data,           # 7: raw_data
            "2026-01-20 08:00:00",  # 8: synced_at
        )

        model = reader._row_to_subcontracting_order(row)

        assert model.bill_no == "SUB20260120-003"
        assert model.mto_number == "AK2510034"
        assert model.material_code == "05.03.001"
        assert model.order_qty == Decimal("500.00")
        assert model.stock_in_qty == Decimal("300.00")
        assert model.no_stock_in_qty == Decimal("200.00")
        assert model.aux_prop_id == 3001
        # material_name and specification extracted from raw_data JSON
        assert model.material_name == "委外加工件"
        assert model.specification == "CNC精加工"

    def test_row_to_subcontracting_order_with_nones(self):
        """Test _row_to_subcontracting_order with None/zero values."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            None,          # 0: bill_no
            "AK001",       # 1: mto_number
            "05.03.002",   # 2: material_code
            None,          # 3: order_qty
            Decimal("0"),  # 4: stock_in_qty
            None,          # 5: no_stock_in_qty
            None,          # 6: aux_prop_id
            None,          # 7: raw_data
            None,          # 8: synced_at
        )

        model = reader._row_to_subcontracting_order(row)

        assert model.bill_no == ""
        assert model.material_code == "05.03.002"
        assert model.order_qty == Decimal("0")
        assert model.stock_in_qty == Decimal("0")
        assert model.no_stock_in_qty == Decimal("0")
        assert model.aux_prop_id == 0
        # No raw_data means defaults
        assert model.material_name == ""
        assert model.specification == ""

    def test_row_to_production_receipt_happy_path(self):
        """Test _row_to_production_receipt with all fields populated."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        raw_data = '{"material_name": "成品外壳", "specification": "ABS 200x150mm"}'
        row = (
            "RK20260110-001",   # 0: bill_no
            "AK2510034",        # 1: mto_number
            "07.01.003",        # 2: material_code
            Decimal("80.00"),   # 3: real_qty
            Decimal("100.00"),  # 4: must_qty
            4001,               # 5: aux_prop_id
            raw_data,           # 6: raw_data
            "2026-01-10 14:30:00",  # 7: synced_at
        )

        model = reader._row_to_production_receipt(row)

        assert model.bill_no == "RK20260110-001"
        assert model.mto_number == "AK2510034"
        assert model.material_code == "07.01.003"
        assert model.real_qty == Decimal("80.00")
        assert model.must_qty == Decimal("100.00")
        assert model.aux_prop_id == 4001
        # material_name and specification extracted from raw_data JSON
        assert model.material_name == "成品外壳"
        assert model.specification == "ABS 200x150mm"

    def test_row_to_production_receipt_with_nones(self):
        """Test _row_to_production_receipt with None values and no raw_data."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            None,          # 0: bill_no
            "AK001",       # 1: mto_number
            "07.01.001",   # 2: material_code
            None,          # 3: real_qty
            None,          # 4: must_qty
            None,          # 5: aux_prop_id
            None,          # 6: raw_data (no raw data)
            None,          # 7: synced_at
        )

        model = reader._row_to_production_receipt(row)

        assert model.bill_no == ""
        assert model.real_qty == Decimal("0")
        assert model.must_qty == Decimal("0")
        assert model.aux_prop_id == 0
        # No raw_data means defaults
        assert model.material_name == ""
        assert model.specification == ""

    def test_row_to_production_receipt_invalid_raw_data(self):
        """Test _row_to_production_receipt with malformed raw_data JSON."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "RK001",           # 0: bill_no
            "AK001",           # 1: mto_number
            "07.01.001",       # 2: material_code
            Decimal("10.00"),  # 3: real_qty
            Decimal("10.00"),  # 4: must_qty
            0,                 # 5: aux_prop_id
            "not valid json",  # 6: raw_data (invalid)
            "2026-01-10 10:00:00",  # 7: synced_at
        )

        model = reader._row_to_production_receipt(row)

        # Should fall back to defaults on invalid JSON
        assert model.material_name == ""
        assert model.specification == ""
        assert model.real_qty == Decimal("10.00")

    def test_row_to_purchase_receipt_happy_path(self):
        """Test _row_to_purchase_receipt with all fields populated."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        raw_data = '{"material_name": "铝合金螺丝", "specification": "M6x20mm"}'
        row = (
            "RKD20260118-005",  # 0: bill_no
            "AK2510034",        # 1: mto_number
            "03.02.005",        # 2: material_code
            Decimal("250.00"),  # 3: real_qty
            Decimal("300.00"),  # 4: must_qty
            "RKD01_SYS",        # 5: bill_type_number
            5001,               # 6: aux_prop_id
            raw_data,           # 7: raw_data
            "2026-01-18 09:00:00",  # 8: synced_at
        )

        model = reader._row_to_purchase_receipt(row)

        assert model.bill_no == "RKD20260118-005"
        assert model.mto_number == "AK2510034"
        assert model.material_code == "03.02.005"
        assert model.real_qty == Decimal("250.00")
        assert model.must_qty == Decimal("300.00")
        assert model.bill_type_number == "RKD01_SYS"
        assert model.aux_prop_id == 5001
        # material_name and specification extracted from raw_data JSON
        assert model.material_name == "铝合金螺丝"
        assert model.specification == "M6x20mm"

    def test_row_to_purchase_receipt_with_nones(self):
        """Test _row_to_purchase_receipt with None values."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            None,          # 0: bill_no
            "AK001",       # 1: mto_number
            "03.01.001",   # 2: material_code
            None,          # 3: real_qty
            Decimal("0"),  # 4: must_qty
            None,          # 5: bill_type_number
            None,          # 6: aux_prop_id
            None,          # 7: raw_data
            None,          # 8: synced_at
        )

        model = reader._row_to_purchase_receipt(row)

        assert model.bill_no == ""
        assert model.real_qty == Decimal("0")
        assert model.must_qty == Decimal("0")
        assert model.bill_type_number == ""
        assert model.aux_prop_id == 0
        # No raw_data means defaults
        assert model.material_name == ""
        assert model.specification == ""

    def test_row_to_purchase_receipt_subcontracting_type(self):
        """Test _row_to_purchase_receipt with RKD03_SYS (subcontracting receipt)."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "RKD20260120-010",  # 0: bill_no
            "AK2510034",        # 1: mto_number
            "05.02.001",        # 2: material_code
            Decimal("100.00"),  # 3: real_qty
            Decimal("100.00"),  # 4: must_qty
            "RKD03_SYS",        # 5: bill_type_number (subcontracting)
            6001,               # 6: aux_prop_id
            None,               # 7: raw_data
            "2026-01-20 16:00:00",  # 8: synced_at
        )

        model = reader._row_to_purchase_receipt(row)

        assert model.bill_type_number == "RKD03_SYS"
        assert model.real_qty == Decimal("100.00")

    def test_row_to_material_picking_happy_path(self):
        """Test _row_to_material_picking with all fields populated."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        raw_data = '{"material_name": "包装纸板", "specification": "A4 350g"}'
        row = (
            "AK2510034",        # 0: mto_number
            "03.01.008",        # 1: material_code
            Decimal("120.00"),  # 2: app_qty
            Decimal("115.50"),  # 3: actual_qty
            "PPBOM20260105-001",  # 4: ppbom_bill_no
            7001,               # 5: aux_prop_id
            raw_data,           # 6: raw_data
            "2026-01-22 11:00:00",  # 7: synced_at
        )

        model = reader._row_to_material_picking(row)

        assert model.mto_number == "AK2510034"
        assert model.material_code == "03.01.008"
        assert model.app_qty == Decimal("120.00")
        assert model.actual_qty == Decimal("115.50")
        assert model.ppbom_bill_no == "PPBOM20260105-001"
        assert model.aux_prop_id == 7001
        # material_name and specification extracted from raw_data JSON
        assert model.material_name == "包装纸板"
        assert model.specification == "A4 350g"

    def test_row_to_material_picking_with_nones(self):
        """Test _row_to_material_picking with None values."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "AK001",       # 0: mto_number
            "03.01.001",   # 1: material_code
            None,          # 2: app_qty
            None,          # 3: actual_qty
            None,          # 4: ppbom_bill_no
            None,          # 5: aux_prop_id
            None,          # 6: raw_data
            None,          # 7: synced_at
        )

        model = reader._row_to_material_picking(row)

        assert model.mto_number == "AK001"
        assert model.material_code == "03.01.001"
        assert model.app_qty == Decimal("0")
        assert model.actual_qty == Decimal("0")
        assert model.ppbom_bill_no == ""
        assert model.aux_prop_id == 0
        # No raw_data means defaults
        assert model.material_name == ""
        assert model.specification == ""

    def test_row_to_sales_delivery_happy_path(self):
        """Test _row_to_sales_delivery with all fields populated."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        raw_data = '{"material_name": "成品组装件", "specification": "标准型号B"}'
        row = (
            "SD20260125-002",   # 0: bill_no
            "AK2510034",        # 1: mto_number
            "07.01.001",        # 2: material_code
            Decimal("90.00"),   # 3: real_qty
            Decimal("100.00"),  # 4: must_qty
            8001,               # 5: aux_prop_id
            raw_data,           # 6: raw_data
            "2026-01-25 15:00:00",  # 7: synced_at
        )

        model = reader._row_to_sales_delivery(row)

        assert model.bill_no == "SD20260125-002"
        assert model.mto_number == "AK2510034"
        assert model.material_code == "07.01.001"
        assert model.real_qty == Decimal("90.00")
        assert model.must_qty == Decimal("100.00")
        assert model.aux_prop_id == 8001
        # material_name and specification extracted from raw_data JSON
        assert model.material_name == "成品组装件"
        assert model.specification == "标准型号B"

    def test_row_to_sales_delivery_with_nones(self):
        """Test _row_to_sales_delivery with None values."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            None,          # 0: bill_no
            "AK001",       # 1: mto_number
            "07.01.001",   # 2: material_code
            None,          # 3: real_qty
            None,          # 4: must_qty
            None,          # 5: aux_prop_id
            None,          # 6: raw_data
            None,          # 7: synced_at
        )

        model = reader._row_to_sales_delivery(row)

        assert model.bill_no == ""
        assert model.real_qty == Decimal("0")
        assert model.must_qty == Decimal("0")
        assert model.aux_prop_id == 0
        # No raw_data means defaults
        assert model.material_name == ""
        assert model.specification == ""

    def test_row_to_sales_order_happy_path(self):
        """Test _row_to_sales_order with all fields populated."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "SO20260101-001",   # 0: bill_no
            "AK2510034",        # 1: mto_number
            "07.01.001",        # 2: material_code
            "成品组装件",        # 3: material_name
            "标准型号A",        # 4: specification
            "红色/大号",        # 5: aux_attributes
            9001,               # 6: aux_prop_id
            "深圳市流利科技",    # 7: customer_name
            "2026-02-28",       # 8: delivery_date
            Decimal("1000.00"), # 9: qty
            "BOM-A1",           # 10: bom_short_name
            "护目镜",            # 11: material_group_name
            "A",                # 12: close_status
            '{"raw": "data"}',  # 13: raw_data
            "2026-01-01 08:00:00",  # 14: synced_at
        )

        model = reader._row_to_sales_order(row)

        assert model.bill_no == "SO20260101-001"
        assert model.mto_number == "AK2510034"
        assert model.material_code == "07.01.001"
        assert model.material_name == "成品组装件"
        assert model.specification == "标准型号A"
        assert model.aux_attributes == "红色/大号"
        assert model.aux_prop_id == 9001
        assert model.customer_name == "深圳市流利科技"
        assert model.delivery_date == "2026-02-28"
        assert model.qty == Decimal("1000.00")
        assert model.bom_short_name == "BOM-A1"
        assert model.material_group_name == "护目镜"

    def test_row_to_sales_order_with_nones(self):
        """Test _row_to_sales_order with None values."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "SO001",       # 0: bill_no
            "AK001",       # 1: mto_number
            "07.01.001",   # 2: material_code
            None,          # 3: material_name
            None,          # 4: specification
            None,          # 5: aux_attributes
            None,          # 6: aux_prop_id
            None,          # 7: customer_name
            None,          # 8: delivery_date
            None,          # 9: qty
            None,          # 10: bom_short_name
            None,          # 11: material_group_name
            None,          # 12: close_status
            None,          # 13: raw_data
            None,          # 14: synced_at
        )

        model = reader._row_to_sales_order(row)

        assert model.bill_no == "SO001"
        assert model.material_name == ""
        assert model.specification == ""
        assert model.aux_attributes == ""
        assert model.aux_prop_id == 0
        assert model.customer_name == ""
        assert model.delivery_date is None
        assert model.qty == Decimal("0")
        assert model.bom_short_name == ""
        assert model.material_group_name == ""


class TestFallbackTelemetry:
    """Stage 1 of PLAN_aux_match_visibility: verify fallback tier counts are logged.

    The cache reader's BOM JOIN computes match_quality labels per source via SQL CASE.
    `_log_fallback_telemetry` aggregates them and emits one structured log per MTO query
    so Loki can chart the fallback rate before any code change ships.
    """

    @staticmethod
    def _row(quality_per_source: tuple[str, ...]) -> tuple:
        """Build a minimal 28-column BOM JOIN row with given match_quality labels.

        Columns 0-20 are placeholders (not consulted by the telemetry path);
        columns 21-26 are the per-source labels; column 27 is synced_at.
        """
        assert len(quality_per_source) == 6, "must provide 6 source labels"
        return (
            "MO001", "AK001", "M001", "name", "spec", "", 0, 1,  # 0-7
            Decimal("0"), Decimal("0"), Decimal("0"),             # 8-10 qtys
            Decimal("0"), Decimal("0"),                           # 11-12 prod_receipt
            Decimal("0"), Decimal("0"),                           # 13-14 pick
            Decimal("0"), Decimal("0"),                           # 15-16 purchase_order
            Decimal("0"),                                         # 17 purchase_receipt
            Decimal("0"), Decimal("0"),                           # 18-19 subcontract
            Decimal("0"),                                         # 20 delivery
            *quality_per_source,                                  # 21-26 match_quality
            "2026-04-25 12:00:00",                                # 27 synced_at
        )

    def test_telemetry_logs_all_exact_when_perfectly_matched(self, caplog):
        rows = [
            self._row(("exact", "exact", "exact", "exact", "exact", "exact")),
            self._row(("exact", "exact", "exact", "exact", "exact", "exact")),
        ]
        with caplog.at_level("INFO", logger="src.query.cache_reader"):
            CacheReader._log_fallback_telemetry("AK2510034", rows)

        record = next(r for r in caplog.records if "mto_fallback_telemetry" in r.message)
        assert "non_exact_hits=0" in record.message
        assert '"exact": 2' in record.message  # each source shows 2 exact matches

    def test_telemetry_counts_aux_zero_fallback(self, caplog):
        rows = [
            self._row(("aux_zero_fallback", "exact", "exact", "exact", "exact", "exact")),
            self._row(("exact", "aux_zero_fallback", "exact", "exact", "exact", "exact")),
        ]
        with caplog.at_level("INFO", logger="src.query.cache_reader"):
            CacheReader._log_fallback_telemetry("AK2510034", rows)

        record = next(r for r in caplog.records if "mto_fallback_telemetry" in r.message)
        assert "non_exact_hits=2" in record.message
        assert '"aux_zero_fallback": 1' in record.message

    def test_telemetry_counts_all_aux_rollup(self, caplog):
        rows = [
            self._row(("all_aux_rollup", "all_aux_rollup", "exact", "exact", "exact", "exact")),
        ]
        with caplog.at_level("INFO", logger="src.query.cache_reader"):
            CacheReader._log_fallback_telemetry("AK2510034", rows)

        record = next(r for r in caplog.records if "mto_fallback_telemetry" in r.message)
        assert "non_exact_hits=2" in record.message
        assert '"all_aux_rollup": 1' in record.message

    def test_telemetry_no_match_does_not_inflate_non_exact_hits(self, caplog):
        # `no_match` means the row genuinely has no receipt anywhere — that's a data
        # state, not a fallback. The telemetry counter should not flag it as a fallback.
        rows = [
            self._row(("no_match", "no_match", "no_match", "no_match", "no_match", "no_match")),
        ]
        with caplog.at_level("INFO", logger="src.query.cache_reader"):
            CacheReader._log_fallback_telemetry("AK2510034", rows)

        record = next(r for r in caplog.records if "mto_fallback_telemetry" in r.message)
        assert "non_exact_hits=0" in record.message

    def test_telemetry_includes_mto_number_and_row_count(self, caplog):
        rows = [
            self._row(("exact",) * 6),
            self._row(("exact",) * 6),
            self._row(("exact",) * 6),
        ]
        with caplog.at_level("INFO", logger="src.query.cache_reader"):
            CacheReader._log_fallback_telemetry("AK9999999", rows)

        record = next(r for r in caplog.records if "mto_fallback_telemetry" in r.message)
        assert "mto=AK9999999" in record.message
        assert "bom_rows=3" in record.message


class TestTableFreshness:
    """Tests for CacheReader.table_freshness (data-freshness health card)."""

    @pytest.mark.asyncio
    async def test_no_like_or_mto_filter(self):
        """Regression guard: table-level freshness must NOT reuse per-MTO LIKE matching.

        check_freshness() is per-MTO with `WHERE mto_number LIKE ?`; table_freshness()
        is whole-table. If this ever regresses to a LIKE/mto query the staleness card
        silently stops reflecting actual table state.
        """
        mock_db = MagicMock()
        captured = []

        async def fake_read(query, params=None):
            captured.append(query)
            return [(None, 0)]

        mock_db.execute_read = fake_read
        reader = CacheReader(mock_db, ttl_minutes=60)
        await reader.table_freshness()

        assert len(captured) == 9  # all 9 cache tables probed
        assert all("LIKE" not in q.upper() for q in captured), captured
        assert all("MTO_NUMBER" not in q.upper() for q in captured), captured

    @pytest.mark.asyncio
    async def test_empty_then_populated(self, test_database):
        reader = CacheReader(test_database, ttl_minutes=60)

        facts = await reader.table_freshness()
        by_table = {f["table"]: f for f in facts}
        assert len(facts) == 9
        assert by_table["cached_sales_orders"]["row_count"] == 0
        assert by_table["cached_sales_orders"]["last_synced_at"] is None

        await test_database.execute_write(
            """
            INSERT INTO cached_sales_orders
            (bill_no, mto_number, material_code, customer_name, delivery_date, qty, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["SO1", "AK2510034", "07.01.001", "刀刀", "2026-03-05T00:00:00", 100],
        )

        facts = await reader.table_freshness()
        by_table = {f["table"]: f for f in facts}
        assert by_table["cached_sales_orders"]["row_count"] == 1
        assert by_table["cached_sales_orders"]["last_synced_at"] is not None


class TestOverPickAlerts:
    """Tests for CacheReader.get_over_pick_alerts (超领预警)."""

    @staticmethod
    async def _pick(db, mto, mat, app, actual, bill, aux=0):
        await db.execute_write(
            """
            INSERT INTO cached_material_picking
            (mto_number, material_code, app_qty, actual_qty, ppbom_bill_no, aux_prop_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [mto, mat, app, actual, bill, aux],
        )

    @pytest.mark.asyncio
    async def test_over_pick_summed_across_picking_docs(self, test_database):
        """Same mto+material across two picking docs: sum first, then compare."""
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._pick(test_database, "AK1", "05.01.001", 10, 12, "P1")
        await self._pick(test_database, "AK1", "05.01.001", 10, 15, "P2")  # 27 vs 20 → 7
        result = await reader.get_over_pick_alerts()
        assert result["skipped_incomplete"] == 0
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["over_amount"] == 7
        assert result["alerts"][0]["severe"] is False

    @pytest.mark.asyncio
    async def test_app_zero_actual_positive_is_severe(self, test_database):
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._pick(test_database, "AK2", "05.01.002", 0, 50, "P3")
        result = await reader.get_over_pick_alerts()
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["severe"] is True

    @pytest.mark.asyncio
    async def test_sample_rows_not_filtered_in_cache_reader(self, test_database):
        """Cache reader stays pure: sample (AY/DY) rows are NOT dropped here.

        Sample exclusion lives in the alerts router so it can report
        excluded_sample_count. Filtering inside the SQL would make that count
        impossible and turn the filter into a silent failure. This guards the
        layering: a Y-prefix MTO must still appear in the raw cache-reader output.
        """
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._pick(test_database, "AY2510001", "05.01.001", 0, 50, "P-S")
        result = await reader.get_over_pick_alerts()
        mtos = {a["mto_number"] for a in result["alerts"]}
        assert "AY2510001" in mtos
        assert "excluded_sample_count" not in result  # not the reader's concern

    @pytest.mark.asyncio
    async def test_within_application_not_flagged(self, test_database):
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._pick(test_database, "AK3", "05.01.003", 100, 80, "P4")
        result = await reader.get_over_pick_alerts()
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_null_qty_skipped_not_zeroed(self, test_database, caplog):
        """NULL actual_qty must be skipped + counted, never coerced to 0."""
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._pick(test_database, "AK4", "05.01.004", 10, None, "P5")
        with caplog.at_level("WARNING", logger="src.query.cache_reader"):
            result = await reader.get_over_pick_alerts()
        assert result["skipped_incomplete"] == 1
        assert result["alerts"] == []
        assert any("overpick_null_skip" in r.message for r in caplog.records)


class TestOverShipAlerts:
    """Tests for CacheReader.get_over_ship_alerts (超发预警)."""

    @staticmethod
    async def _order(db, mto, mat, qty, close="A", cust="刀刀"):
        await db.execute_write(
            """
            INSERT INTO cached_sales_orders
            (bill_no, mto_number, material_code, customer_name, delivery_date,
             qty, close_status, aux_prop_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            [f"SO-{mto}-{mat}", mto, mat, cust, "2026-03-05T00:00:00", qty, close],
        )

    @staticmethod
    async def _delivery(db, mto, mat, real, bill):
        await db.execute_write(
            """
            INSERT INTO cached_sales_delivery
            (bill_no, mto_number, material_code, real_qty, aux_prop_id)
            VALUES (?, ?, ?, ?, 0)
            """,
            [bill, mto, mat, real],
        )

    @pytest.mark.asyncio
    async def test_over_ship_detected(self, test_database):
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._order(test_database, "AK1", "07.01.001", 100)
        await self._delivery(test_database, "AK1", "07.01.001", 70, "D1")
        await self._delivery(test_database, "AK1", "07.01.001", 50, "D2")  # 120 vs 100
        result = await reader.get_over_ship_alerts()
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["over_amount"] == 20

    @pytest.mark.asyncio
    async def test_within_order_not_flagged(self, test_database):
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._order(test_database, "AK2", "07.01.002", 100)
        await self._delivery(test_database, "AK2", "07.01.002", 80, "D3")
        result = await reader.get_over_ship_alerts()
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_sample_rows_not_filtered_in_cache_reader(self, test_database):
        """Cache reader stays pure: sample (DY/AY) rows are NOT dropped here.

        Sample exclusion + excluded_sample_count live in the alerts router. A
        Y-prefix MTO must still surface in the raw cache-reader output.
        """
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._order(test_database, "DY251002S", "07.01.001", 100)
        await self._delivery(test_database, "DY251002S", "07.01.001", 130, "D-S")
        result = await reader.get_over_ship_alerts()
        mtos = {a["mto_number"] for a in result["alerts"]}
        assert "DY251002S" in mtos
        assert "excluded_sample_count" not in result

    @pytest.mark.asyncio
    async def test_closed_order_excluded(self, test_database):
        """A closed order line (close_status='B') must not produce an over-ship alert."""
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._order(test_database, "AK3", "07.01.003", 100, close="B")
        await self._delivery(test_database, "AK3", "07.01.003", 130, "D4")
        result = await reader.get_over_ship_alerts()
        assert result["alerts"] == []

    @pytest.mark.asyncio
    async def test_null_real_qty_skipped(self, test_database, caplog):
        reader = CacheReader(test_database, ttl_minutes=60)
        await self._order(test_database, "AK4", "07.01.004", 10)
        await test_database.execute_write(
            """
            INSERT INTO cached_sales_delivery
            (bill_no, mto_number, material_code, real_qty, aux_prop_id)
            VALUES ('D5', 'AK4', '07.01.004', NULL, 0)
            """,
        )
        with caplog.at_level("WARNING", logger="src.query.cache_reader"):
            result = await reader.get_over_ship_alerts()
        assert result["skipped_incomplete"] == 1
        assert any("overship_null_skip" in r.message for r in caplog.records)
