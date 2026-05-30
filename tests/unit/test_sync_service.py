"""Tests for src/sync/sync_service.py"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.exceptions import SyncError
from src.readers.models import (
    MaterialPickingModel,
    ProductionOrderModel,
    SubcontractingOrderModel,
)
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
    async def test_subcontract_upsert_preserves_distinct_mtos(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Bug 7 / bug-patterns.md #5 (Pattern 5 recurrence) regression guard.

        Two subcontract orders sharing (bill_no, material_code, aux_prop_id)
        but belonging to DIFFERENT MTOs of the same customer must both persist
        through the upsert. This was the contamination shape that produced
        DS256203S / 07.25.80 ghost rows on prod 2026-04-26: a supplier's
        subcontract order legitimately spans multiple MTOs of customer
        瑞弧WeaArCo, and the old upsert silently rewrote the first row's
        mto_number to the second's, then DELETE-by-mto removed the survivor
        on subsequent syncs.
        """
        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        # Same supplier subcontract bill_no, same material, same aux — different MTOs.
        # Both rows must coexist after the upsert.
        records = [
            SubcontractingOrderModel(
                bill_no="SUB_SHARED_001",
                mto_number="DS242022S-A2",
                material_code="07.25.80",
                order_qty=Decimal("100"),
                stock_in_qty=Decimal("0"),
                no_stock_in_qty=Decimal("100"),
                aux_prop_id=0,
            ),
            SubcontractingOrderModel(
                bill_no="SUB_SHARED_001",
                mto_number="DS256203S",
                material_code="07.25.80",
                order_qty=Decimal("780"),
                stock_in_qty=Decimal("0"),
                no_stock_in_qty=Decimal("780"),
                aux_prop_id=0,
            ),
        ]

        await service._upsert_subcontracting_orders_no_commit(records)
        await test_database._connection.commit()

        async with test_database._connection.execute(
            "SELECT mto_number, order_qty FROM cached_subcontracting_orders "
            "WHERE bill_no = ? AND material_code = ? ORDER BY mto_number",
            ("SUB_SHARED_001", "07.25.80"),
        ) as cursor:
            rows = await cursor.fetchall()

        assert len(rows) == 2, (
            f"Expected 2 rows (one per MTO); got {len(rows)}. "
            "If 1 row, the contamination bug is back: the upsert collapsed two "
            "distinct MTOs into one because mto_number is missing from the "
            "UNIQUE / ON CONFLICT key set. See bug-patterns.md #5."
        )
        mtos = {r[0] for r in rows}
        assert mtos == {"DS242022S-A2", "DS256203S"}
        # And the qty for each MTO must match what was inserted (no overwrite).
        qty_by_mto = {r[0]: float(r[1]) for r in rows}
        assert qty_by_mto["DS242022S-A2"] == 100.0
        assert qty_by_mto["DS256203S"] == 780.0

    @pytest.mark.asyncio
    async def test_subcontract_upsert_dedups_within_same_mto(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Idempotent within an MTO: two records with identical UNIQUE key
        for the same MTO collapse to one, with the later qty winning."""
        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        records = [
            SubcontractingOrderModel(
                bill_no="SUB_DUP",
                mto_number="DS256203S",
                material_code="07.25.80",
                order_qty=Decimal("100"),
                stock_in_qty=Decimal("0"),
                no_stock_in_qty=Decimal("100"),
                aux_prop_id=0,
            ),
            SubcontractingOrderModel(
                bill_no="SUB_DUP",
                mto_number="DS256203S",
                material_code="07.25.80",
                order_qty=Decimal("780"),
                stock_in_qty=Decimal("0"),
                no_stock_in_qty=Decimal("780"),
                aux_prop_id=0,
            ),
        ]

        await service._upsert_subcontracting_orders_no_commit(records)
        await test_database._connection.commit()

        async with test_database._connection.execute(
            "SELECT order_qty FROM cached_subcontracting_orders "
            "WHERE bill_no = ? AND mto_number = ?",
            ("SUB_DUP", "DS256203S"),
        ) as cursor:
            rows = await cursor.fetchall()

        assert len(rows) == 1
        # In-memory dedup retains the LAST record per (bill_no, mto_number,
        # material_code, aux_prop_id), so qty=780 wins.
        assert float(rows[0][0]) == 780.0

    @pytest.mark.asyncio
    async def test_picking_upsert_preserves_distinct_bills(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """bug-patterns.md #5 (Pattern 5) regression guard for cached_material_picking
        (migration 018).

        One (mto, material, ppbom, aux) picked across TWO 领料单 (different
        bill_no) must persist as TWO rows so SUM(actual_qty) is complete. Before
        018 the UNIQUE omitted bill_no, collapsing them to the last document and
        silently UNDER-counting actual_qty — live proof: DK261025S / 03.11.002
        cache over=43,280 vs live over=81,360 (3 rows, 2 bills)."""
        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        records = [
            MaterialPickingModel(
                bill_no="LL_A", mto_number="DK261025S", material_code="03.11.002",
                app_qty=Decimal("1920"), actual_qty=Decimal("45200"),
                ppbom_bill_no="PPBOM_X", aux_prop_id=0,
            ),
            MaterialPickingModel(
                bill_no="LL_B", mto_number="DK261025S", material_code="03.11.002",
                app_qty=Decimal("1920"), actual_qty=Decimal("40000"),
                ppbom_bill_no="PPBOM_X", aux_prop_id=0,
            ),
        ]

        await service._upsert_material_picking_no_commit(records)
        await test_database._connection.commit()

        async with test_database._connection.execute(
            "SELECT bill_no, actual_qty FROM cached_material_picking "
            "WHERE mto_number = ? AND material_code = ? ORDER BY bill_no",
            ("DK261025S", "03.11.002"),
        ) as cursor:
            rows = await cursor.fetchall()

        assert len(rows) == 2, (
            f"Expected 2 rows (one per 领料单); got {len(rows)}. If 1, the collapse "
            "bug is back: bill_no missing from the UNIQUE / ON CONFLICT key set, so "
            "actual_qty under-counts. See bug-patterns.md #5 / migration 018."
        )
        assert {r[0] for r in rows} == {"LL_A", "LL_B"}
        # SUM across both bills is now complete (was only the last bill before fix).
        assert sum(float(r[1]) for r in rows) == 85200.0

    @pytest.mark.asyncio
    async def test_picking_upsert_dedups_within_same_bill(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Idempotent within a 领料单: two records with identical UNIQUE key
        (same bill_no, mto, material, ppbom, aux) collapse to one, later qty wins."""
        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        records = [
            MaterialPickingModel(
                bill_no="LL_DUP", mto_number="DK261025S", material_code="03.11.002",
                app_qty=Decimal("100"), actual_qty=Decimal("200"),
                ppbom_bill_no="PPBOM_X", aux_prop_id=0,
            ),
            MaterialPickingModel(
                bill_no="LL_DUP", mto_number="DK261025S", material_code="03.11.002",
                app_qty=Decimal("100"), actual_qty=Decimal("350"),
                ppbom_bill_no="PPBOM_X", aux_prop_id=0,
            ),
        ]

        await service._upsert_material_picking_no_commit(records)
        await test_database._connection.commit()

        async with test_database._connection.execute(
            "SELECT actual_qty FROM cached_material_picking "
            "WHERE bill_no = ? AND mto_number = ?",
            ("LL_DUP", "DK261025S"),
        ) as cursor:
            rows = await cursor.fetchall()

        assert len(rows) == 1
        assert float(rows[0][0]) == 350.0

    @pytest.mark.asyncio
    async def test_production_orders_upsert_preserves_distinct_mtos(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Bug 7 / bug-patterns.md #5 (Wave 4A) regression guard.

        Two production orders sharing (bill_no, material_code, aux_prop_id)
        but belonging to DIFFERENT MTOs of the same customer must both
        persist through the upsert. This was the contamination shape that
        produced DS256203S's 18 ghost 07.xx rows on prod 2026-04-26 (07.01.06,
        07.01.07, 07.01.78, 07.01.80=941, 07.02.022, etc.): a production
        order legitimately spans multiple MTOs of customer 瑞弧WeaArCo
        (DS256203S / DS242022S-A2 / WS2510003), and the old upsert silently
        rewrote the first row's mto_number to the second's, then the next
        sync's DELETE-by-mto removed the survivor. Mirror of the Wave 2
        subcontract test above.
        """
        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        # Same production-order bill_no, same material, same aux —
        # different MTOs. Both rows must coexist after the upsert.
        records = [
            ProductionOrderModel(
                bill_no="PRDMO_SHARED_001",
                mto_number="DS242022S-A2",
                workshop="生产车间",
                material_code="07.01.80",
                material_name="样品A",
                specification="规格A",
                aux_attributes="",
                aux_prop_id=0,
                qty=Decimal("100"),
                status="B",
                create_date="2026-01-01",
            ),
            ProductionOrderModel(
                bill_no="PRDMO_SHARED_001",
                mto_number="DS256203S",
                workshop="生产车间",
                material_code="07.01.80",
                material_name="样品A",
                specification="规格A",
                aux_attributes="",
                aux_prop_id=0,
                qty=Decimal("941"),
                status="B",
                create_date="2026-01-02",
            ),
        ]

        await service._upsert_production_orders(records)
        await test_database._connection.commit()

        async with test_database._connection.execute(
            "SELECT mto_number, qty FROM cached_production_orders "
            "WHERE bill_no = ? AND material_code = ? ORDER BY mto_number",
            ("PRDMO_SHARED_001", "07.01.80"),
        ) as cursor:
            rows = await cursor.fetchall()

        assert len(rows) == 2, (
            f"Expected 2 rows (one per MTO); got {len(rows)}. "
            "If 1 row, the contamination bug is back: the upsert collapsed two "
            "distinct MTOs into one because mto_number is missing from the "
            "UNIQUE / ON CONFLICT key set. See bug-patterns.md #5 (Wave 4A) "
            "and DS256203S 07.01.80=941 ghost row from 2026-04-26."
        )
        mtos = {r[0] for r in rows}
        assert mtos == {"DS242022S-A2", "DS256203S"}
        # And the qty for each MTO must match what was inserted (no overwrite).
        qty_by_mto = {r[0]: float(r[1]) for r in rows}
        assert qty_by_mto["DS242022S-A2"] == 100.0
        assert qty_by_mto["DS256203S"] == 941.0

    @pytest.mark.asyncio
    async def test_production_orders_upsert_dedups_within_same_mto(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Idempotent within an MTO: two records with identical UNIQUE key
        for the same MTO collapse to one, with the later qty winning."""
        service = self.create_service(mock_readers, test_database, mock_sync_progress)

        records = [
            ProductionOrderModel(
                bill_no="PRDMO_DUP",
                mto_number="DS256203S",
                workshop="生产车间",
                material_code="07.01.80",
                material_name="样品A",
                specification="规格A",
                aux_attributes="",
                aux_prop_id=0,
                qty=Decimal("100"),
                status="B",
                create_date="2026-01-01",
            ),
            ProductionOrderModel(
                bill_no="PRDMO_DUP",
                mto_number="DS256203S",
                workshop="生产车间",
                material_code="07.01.80",
                material_name="样品A",
                specification="规格A",
                aux_attributes="",
                aux_prop_id=0,
                qty=Decimal("941"),
                status="B",
                create_date="2026-01-02",
            ),
        ]

        await service._upsert_production_orders(records)
        await test_database._connection.commit()

        async with test_database._connection.execute(
            "SELECT qty FROM cached_production_orders "
            "WHERE bill_no = ? AND mto_number = ?",
            ("PRDMO_DUP", "DS256203S"),
        ) as cursor:
            rows = await cursor.fetchall()

        assert len(rows) == 1
        # In-memory dedup retains the LAST record per (bill_no, mto_number,
        # material_code, aux_prop_id), so qty=941 wins.
        assert float(rows[0][0]) == 941.0

    # Tests for _sync_orders, _sync_orders_with_data, _sync_bom_for_orders_empty
    # removed — those methods were dead code and have been deleted

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


class TestPartialSyncReporting:
    """A sync with <=50% failed chunks must be recorded as 'partial', not 'success'.

    Before 2026-05-29 partial failures were logged then recorded as success
    (run_sync hard-coded status='success'); a silently-stalled table looked
    healthy. See PLAN_freshness_and_alerts_2026-05-29.md.
    """

    def _service(self, mock_readers, test_database, mock_sync_progress):
        return SyncService(
            readers=mock_readers, db=test_database, progress=mock_sync_progress
        )

    @pytest.mark.asyncio
    async def test_run_sync_records_partial(
        self, mock_readers, test_database, mock_sync_progress
    ):
        service = self._service(mock_readers, test_database, mock_sync_progress)
        # 1 of 5 chunks failed (<=50%): completes, but incomplete.
        service._sync_date_range = AsyncMock(return_value=(100, [2], 5))

        result = await service.run_sync(days_back=10, chunk_days=2)

        assert result.status == "partial"
        assert result.failed_chunks == 1
        assert result.total_chunks == 5
        # Must be persisted as partial, not success.
        rows = await test_database.execute_read(
            "SELECT status, error_message FROM sync_history ORDER BY id DESC LIMIT 1"
        )
        assert rows[0][0] == "partial"
        assert "1/5" in (rows[0][1] or "")

    @pytest.mark.asyncio
    async def test_run_sync_clean_success_unaffected(
        self, mock_readers, test_database, mock_sync_progress
    ):
        service = self._service(mock_readers, test_database, mock_sync_progress)
        service._sync_date_range = AsyncMock(return_value=(100, [], 5))

        result = await service.run_sync(days_back=10, chunk_days=2)

        assert result.status == "success"
        assert result.failed_chunks == 0

    @pytest.mark.asyncio
    async def test_sync_date_range_warns_and_returns_failures(
        self, mock_readers, test_database, mock_sync_progress, caplog
    ):
        service = self._service(mock_readers, test_database, mock_sync_progress)
        service._parallel_chunks = 1  # deterministic chunk order
        # 4 daily chunks; the 2nd raises → 1/4 = 25% (<=50%): warn, don't raise.
        service._sync_chunk = AsyncMock(side_effect=[5, SyncError("boom"), 5, 5])

        with caplog.at_level("WARNING", logger="src.sync.sync_service"):
            records, failed_indices, total = await service._sync_date_range(
                days_back=3, chunk_days=1
            )

        assert total == 4
        assert len(failed_indices) == 1
        assert records == 15  # 5+5+5; failed chunk contributes 0
        assert any("sync_partial" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_sync_date_range_aborts_above_50pct(
        self, mock_readers, test_database, mock_sync_progress
    ):
        service = self._service(mock_readers, test_database, mock_sync_progress)
        service._parallel_chunks = 1
        # 3 of 4 chunks fail → 75% > 50% → must still abort (raise).
        service._sync_chunk = AsyncMock(
            side_effect=[SyncError("a"), SyncError("b"), SyncError("c"), 5]
        )
        with pytest.raises(SyncError, match="aborted"):
            await service._sync_date_range(days_back=3, chunk_days=1)
