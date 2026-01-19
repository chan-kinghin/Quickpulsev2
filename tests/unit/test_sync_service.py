"""Tests for src/sync/sync_service.py"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.exceptions import SyncError
from src.sync.sync_service import SyncResult, SyncService, date_chunks, model_to_json


class TestDateChunks:
    """Tests for date_chunks helper."""

    def test_date_chunks_basic(self):
        """Test basic date chunking."""
        start = date(2025, 1, 1)
        end = date(2025, 1, 21)
        chunks = list(date_chunks(start, end, chunk_days=7))

        assert len(chunks) == 3
        assert chunks[0] == (date(2025, 1, 1), date(2025, 1, 7))
        assert chunks[1] == (date(2025, 1, 8), date(2025, 1, 14))
        assert chunks[2] == (date(2025, 1, 15), date(2025, 1, 21))

    def test_date_chunks_single(self):
        """Test when range fits in one chunk."""
        start = date(2025, 1, 1)
        end = date(2025, 1, 5)
        chunks = list(date_chunks(start, end, chunk_days=7))

        assert len(chunks) == 1
        assert chunks[0] == (date(2025, 1, 1), date(2025, 1, 5))

    def test_date_chunks_exact_boundary(self):
        """Test exact boundary (14 days = 2 x 7-day chunks)."""
        start = date(2025, 1, 1)
        end = date(2025, 1, 14)
        chunks = list(date_chunks(start, end, chunk_days=7))

        assert len(chunks) == 2

    def test_date_chunks_same_day(self):
        """Test single day range."""
        start = date(2025, 1, 1)
        end = date(2025, 1, 1)
        chunks = list(date_chunks(start, end, chunk_days=7))

        assert len(chunks) == 1
        assert chunks[0] == (date(2025, 1, 1), date(2025, 1, 1))

    def test_date_chunks_custom_size(self):
        """Test custom chunk size."""
        start = date(2025, 1, 1)
        end = date(2025, 1, 30)
        chunks = list(date_chunks(start, end, chunk_days=10))

        assert len(chunks) == 3
        assert chunks[0] == (date(2025, 1, 1), date(2025, 1, 10))
        assert chunks[1] == (date(2025, 1, 11), date(2025, 1, 20))
        assert chunks[2] == (date(2025, 1, 21), date(2025, 1, 30))


class TestModelToJson:
    """Tests for model_to_json helper."""

    def test_model_to_json_production_order(self, sample_production_order):
        """Test serializing ProductionOrderModel."""
        import json

        result = model_to_json(sample_production_order)

        # Should be valid JSON
        data = json.loads(result)
        assert data["bill_no"] == "MO0001"
        assert data["mto_number"] == "AK2510034"

    def test_model_to_json_with_decimal(self, sample_production_order):
        """Test Decimal is properly serialized."""
        import json

        result = model_to_json(sample_production_order)
        data = json.loads(result)

        # Decimal should be serialized (as number or string depending on mode)
        assert "qty" in data


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_sync_result_creation(self):
        """Test creating SyncResult."""
        from datetime import datetime

        result = SyncResult(
            status="success",
            days_back=90,
            records_synced=1000,
            started_at=datetime(2025, 1, 15, 10, 0),
            finished_at=datetime(2025, 1, 15, 10, 30),
        )

        assert result.status == "success"
        assert result.days_back == 90
        assert result.records_synced == 1000

    def test_sync_result_error(self):
        """Test creating error SyncResult."""
        from datetime import datetime

        result = SyncResult(
            status="error",
            days_back=90,
            records_synced=500,
            started_at=datetime(2025, 1, 15, 10, 0),
            finished_at=datetime(2025, 1, 15, 10, 5),
        )

        assert result.status == "error"


class TestSyncService:
    """Tests for SyncService class."""

    def create_service(self, mock_readers, test_database, mock_sync_progress):
        """Create SyncService with mocks."""
        return SyncService(
            readers=mock_readers,
            db=test_database,
            progress=mock_sync_progress,
        )

    @pytest.mark.asyncio
    async def test_is_running_initially_false(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Test is_running is False initially."""
        service = self.create_service(mock_readers, test_database, mock_sync_progress)
        assert service.is_running() is False

    @pytest.mark.asyncio
    async def test_run_sync_already_running(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Test SyncError when sync already running."""
        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        # Simulate running state
        service._running = True

        with pytest.raises(SyncError, match="already running"):
            await service.run_sync(days_back=7)

    @pytest.mark.asyncio
    async def test_sync_orders_empty(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Test sync with no orders returns empty list."""
        # Mock reader to return empty
        mock_readers["production_order"].fetch_by_date_range = AsyncMock(
            return_value=[]
        )

        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        orders = await service._sync_orders(date(2025, 1, 1), date(2025, 1, 7))
        assert orders == []

    @pytest.mark.asyncio
    async def test_sync_orders_with_data(
        self, mock_readers, test_database, mock_sync_progress, sample_production_orders
    ):
        """Test sync with production orders."""
        mock_readers["production_order"].fetch_by_date_range = AsyncMock(
            return_value=sample_production_orders
        )

        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        orders = await service._sync_orders(date(2025, 1, 1), date(2025, 1, 7))

        assert len(orders) == 2

    @pytest.mark.asyncio
    async def test_sync_bom_for_orders_empty(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Test BOM sync with no orders."""
        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        count = await service._sync_bom_for_orders([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_run_sync_success(
        self,
        mock_readers,
        test_database,
        mock_sync_progress,
        sample_production_orders,
        sample_bom_entries,
    ):
        """Test successful sync run."""
        mock_readers["production_order"].fetch_by_date_range = AsyncMock(
            return_value=sample_production_orders
        )
        mock_readers["production_bom"].fetch_by_bill_nos = AsyncMock(
            return_value=sample_bom_entries
        )

        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        result = await service.run_sync(days_back=7, chunk_days=7)

        assert result.status == "success"
        assert result.days_back == 7
        assert result.records_synced > 0

    @pytest.mark.asyncio
    async def test_clear_cache(self, mock_readers, test_database, mock_sync_progress):
        """Test _clear_cache removes data."""
        # Insert some data first
        await test_database.execute_write(
            """
            INSERT INTO cached_production_orders
            (mto_number, bill_no, workshop, material_code, material_name,
             specification, aux_attributes, qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ["AK001", "MO001", "", "M001", "", "", "", 100],
        )

        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        # Verify data exists
        rows = await test_database.execute_read(
            "SELECT COUNT(*) FROM cached_production_orders"
        )
        assert rows[0][0] > 0

        # Clear cache
        await service._clear_cache()

        # Verify data is gone
        rows = await test_database.execute_read(
            "SELECT COUNT(*) FROM cached_production_orders"
        )
        assert rows[0][0] == 0


class TestSyncServiceBatching:
    """Tests for sync service batching logic."""

    def create_service(self, mock_readers, test_database, mock_sync_progress):
        """Create SyncService with mocks."""
        return SyncService(
            readers=mock_readers,
            db=test_database,
            progress=mock_sync_progress,
        )

    @pytest.mark.asyncio
    async def test_fetch_bom_batch_with_retry_success(
        self, mock_readers, test_database, mock_sync_progress, sample_bom_entries
    ):
        """Test successful BOM batch fetch."""
        mock_readers["production_bom"].fetch_by_bill_nos = AsyncMock(
            return_value=sample_bom_entries
        )

        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        result = await service._fetch_bom_batch_with_retry(["MO001", "MO002"])

        assert result is not None
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_fetch_bom_batch_with_retry_timeout(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Test BOM batch fetch with timeout."""
        import asyncio

        async def slow_fetch(bill_nos):
            await asyncio.sleep(100)  # Longer than timeout
            return []

        mock_readers["production_bom"].fetch_by_bill_nos = slow_fetch

        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        # Override timeout for test
        import src.sync.sync_service as sync_module

        original_timeout = sync_module.BOM_QUERY_TIMEOUT
        sync_module.BOM_QUERY_TIMEOUT = 0.1  # Very short timeout

        try:
            result = await service._fetch_bom_batch_with_retry(["MO001"])
            assert result is None  # Should return None after retries
        finally:
            sync_module.BOM_QUERY_TIMEOUT = original_timeout

    @pytest.mark.asyncio
    async def test_fetch_bom_batch_with_retry_error(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Test BOM batch fetch with error."""
        mock_readers["production_bom"].fetch_by_bill_nos = AsyncMock(
            side_effect=Exception("API error")
        )

        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        # Override max retries for faster test
        import src.sync.sync_service as sync_module

        original_retries = sync_module.BOM_MAX_RETRIES
        sync_module.BOM_MAX_RETRIES = 0

        try:
            result = await service._fetch_bom_batch_with_retry(["MO001"])
            assert result is None
        finally:
            sync_module.BOM_MAX_RETRIES = original_retries
