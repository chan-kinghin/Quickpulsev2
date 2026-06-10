"""Tests for src/sync/sync_service.py"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.exceptions import SyncError
from src.readers.models import (
    MaterialPickingModel,
    ProductionOrderModel,
    ProductionReceiptModel,
    PurchaseOrderModel,
    PurchaseReceiptModel,
    SalesDeliveryModel,
    SalesOrderModel,
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


class TestEntryGrainUpserts:
    """bug-patterns.md #5, SIXTH occurrence (audit 2026-06-10): one Kingdee
    document can carry MULTIPLE entry lines with the same (material, aux).
    Pre-entry_id, every document cache upsert kept exactly one line per key.
    Each test mirrors a live-verified collapse case: two same-document entry
    lines must BOTH survive so SUM() matches Kingdee.
    """

    def _service(self, mock_readers, test_database, mock_sync_progress):
        return SyncService(
            readers=mock_readers, db=test_database, progress=mock_sync_progress
        )

    async def _rows(self, db, table, where, params):
        async with db._connection.execute(
            f"SELECT entry_id FROM {table} WHERE {where} ORDER BY entry_id", params
        ) as cursor:
            return await cursor.fetchall()

    @pytest.mark.asyncio
    async def test_sales_delivery_same_doc_lines_both_survive(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Live case XS26050001: lines 186+55+54 on the same (material, aux)
        collapsed to one row (-61% of 481), hiding real 超发."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        records = [
            SalesDeliveryModel(
                bill_no="XS26050001", mto_number="AS2605001", material_code="03.03.001",
                real_qty=Decimal("186"), must_qty=Decimal("186"),
                aux_prop_id=196059, entry_id=226990,
            ),
            SalesDeliveryModel(
                bill_no="XS26050001", mto_number="AS2605001", material_code="03.03.001",
                real_qty=Decimal("55"), must_qty=Decimal("55"),
                aux_prop_id=196059, entry_id=226992,
            ),
        ]
        await service._upsert_sales_delivery_no_commit(records)
        await test_database._connection.commit()
        rows = await self._rows(
            test_database, "cached_sales_delivery",
            "bill_no=? AND material_code=? AND aux_prop_id=?",
            ("XS26050001", "03.03.001", 196059),
        )
        assert len(rows) == 2, (
            f"Expected 2 rows (one per entry line); got {len(rows)}. If 1, the "
            "entry-grain collapse is back: entry_id missing from the UNIQUE / "
            "ON CONFLICT / dedup key set. See migration 019."
        )

    @pytest.mark.asyncio
    async def test_sales_orders_same_doc_lines_both_survive(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Live case XSDD2605036: a qty=3 line next to a qty=300 line on the
        same (material, aux) was silently dropped → phantom 超发."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        records = [
            SalesOrderModel(
                bill_no="XSDD2605036", mto_number="DS2605036", material_code="07.32.001",
                customer_name="客户A", qty=Decimal("300"),
                aux_prop_id=227785, entry_id=322305,
            ),
            SalesOrderModel(
                bill_no="XSDD2605036", mto_number="DS2605036", material_code="07.32.001",
                customer_name="客户A", qty=Decimal("3"),
                aux_prop_id=227785, entry_id=322310,
            ),
        ]
        await service._upsert_sales_orders_no_commit(records)
        await test_database._connection.commit()
        rows = await self._rows(
            test_database, "cached_sales_orders",
            "bill_no=? AND material_code=? AND aux_prop_id=?",
            ("XSDD2605036", "07.32.001", 227785),
        )
        assert len(rows) == 2
        async with test_database._connection.execute(
            "SELECT SUM(qty) FROM cached_sales_orders WHERE bill_no=?",
            ("XSDD2605036",),
        ) as cursor:
            total = (await cursor.fetchone())[0]
        assert float(total) == 303.0

    @pytest.mark.asyncio
    async def test_material_picking_same_doc_lines_both_survive(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Live case LL26041108 / 05.02.04.033 / aux=106244: two lines 1021+579
        in ONE 领料单 — bill_no in the key (migration 018) is NOT sufficient;
        the cache kept 579. Migration 018's zero-residual-collision claim was
        empirically false."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        records = [
            MaterialPickingModel(
                bill_no="LL26041108", mto_number="AS2603026-8",
                material_code="05.02.04.033", app_qty=Decimal("1021"),
                actual_qty=Decimal("1021"), ppbom_bill_no="PPBOM260305746",
                aux_prop_id=106244, entry_id=199603,
            ),
            MaterialPickingModel(
                bill_no="LL26041108", mto_number="AS2603026-8",
                material_code="05.02.04.033", app_qty=Decimal("579"),
                actual_qty=Decimal("579"), ppbom_bill_no="PPBOM260305746",
                aux_prop_id=106244, entry_id=199604,
            ),
        ]
        await service._upsert_material_picking_no_commit(records)
        await test_database._connection.commit()
        async with test_database._connection.execute(
            "SELECT SUM(actual_qty) FROM cached_material_picking "
            "WHERE bill_no=? AND material_code=?",
            ("LL26041108", "05.02.04.033"),
        ) as cursor:
            total = (await cursor.fetchone())[0]
        assert float(total) == 1600.0, (
            f"SUM(actual_qty)={total}, expected 1600 (1021+579). If 579, the "
            "same-document entry collapse is back — see migration 019."
        )

    @pytest.mark.asyncio
    async def test_purchase_receipts_same_doc_lines_all_survive(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Live case CG26041724 / 23.12.01 / aux=0: cache kept 14 of
        39+1798+762+14=2613 — feeds the agent-chat SQL pipeline."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        qtys_ids = [(39, 211749), (1798, 211750), (762, 211751), (14, 211752)]
        records = [
            PurchaseReceiptModel(
                bill_no="CG26041724", mto_number="", material_code="23.12.01",
                real_qty=Decimal(q), must_qty=Decimal(q),
                bill_type_number="RKD01_SYS", aux_prop_id=0, entry_id=eid,
            )
            for q, eid in qtys_ids
        ]
        await service._upsert_purchase_receipts_no_commit(records)
        await test_database._connection.commit()
        async with test_database._connection.execute(
            "SELECT SUM(real_qty), COUNT(*) FROM cached_purchase_receipts WHERE bill_no=?",
            ("CG26041724",),
        ) as cursor:
            total, n = await cursor.fetchone()
        assert n == 4
        assert float(total) == 2613.0

    @pytest.mark.asyncio
    async def test_purchase_orders_same_doc_lines_both_survive(
        self, mock_readers, test_database, mock_sync_progress
    ):
        service = self._service(mock_readers, test_database, mock_sync_progress)
        records = [
            PurchaseOrderModel(
                bill_no="CG_PO_001", mto_number="AS2605001", material_code="03.23.008",
                order_qty=Decimal("100"), stock_in_qty=Decimal("0"),
                remain_stock_in_qty=Decimal("100"), aux_prop_id=0, entry_id=1001,
            ),
            PurchaseOrderModel(
                bill_no="CG_PO_001", mto_number="AS2605001", material_code="03.23.008",
                order_qty=Decimal("250"), stock_in_qty=Decimal("0"),
                remain_stock_in_qty=Decimal("250"), aux_prop_id=0, entry_id=1002,
            ),
        ]
        await service._upsert_purchase_orders_no_commit(records)
        await test_database._connection.commit()
        async with test_database._connection.execute(
            "SELECT SUM(order_qty) FROM cached_purchase_orders WHERE bill_no=?",
            ("CG_PO_001",),
        ) as cursor:
            total = (await cursor.fetchone())[0]
        assert float(total) == 350.0

    @pytest.mark.asyncio
    async def test_production_receipts_same_doc_lines_both_survive(
        self, mock_readers, test_database, mock_sync_progress
    ):
        service = self._service(mock_readers, test_database, mock_sync_progress)
        records = [
            ProductionReceiptModel(
                bill_no="CP_PR_001", mto_number="AS2605001", material_code="05.02.27.022",
                real_qty=Decimal("1365"), must_qty=Decimal("1365"),
                aux_prop_id=106022, entry_id=115473,
            ),
            ProductionReceiptModel(
                bill_no="CP_PR_001", mto_number="AS2605001", material_code="05.02.27.022",
                real_qty=Decimal("200"), must_qty=Decimal("200"),
                aux_prop_id=106022, entry_id=115499,
            ),
        ]
        await service._upsert_production_receipts_no_commit(records)
        await test_database._connection.commit()
        async with test_database._connection.execute(
            "SELECT SUM(real_qty) FROM cached_production_receipts WHERE bill_no=?",
            ("CP_PR_001",),
        ) as cursor:
            total = (await cursor.fetchone())[0]
        assert float(total) == 1565.0

    @pytest.mark.asyncio
    async def test_subcontracting_orders_same_doc_lines_both_survive(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Live case WW25100020 / 08.27.001 / aux=0 (probed 2026-06-10,
        /tmp/probe_subreqorder_entryid_20260610.py): two lines 1200+38800 in
        ONE 委外订单 — the 7th Pattern-5 table; pre-fix the upsert kept one
        line, under-counting 委外 订单数量. NOTE: this form's entry id is
        FTreeEntity_FEntryID (not FEntity_/FSubReqEntry_)."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        records = [
            SubcontractingOrderModel(
                bill_no="WW25100020", mto_number="踏板", material_code="08.27.001",
                order_qty=Decimal("1200"), stock_in_qty=Decimal("0"),
                no_stock_in_qty=Decimal("1200"), aux_prop_id=0, entry_id=100383,
            ),
            SubcontractingOrderModel(
                bill_no="WW25100020", mto_number="踏板", material_code="08.27.001",
                order_qty=Decimal("38800"), stock_in_qty=Decimal("0"),
                no_stock_in_qty=Decimal("38800"), aux_prop_id=0, entry_id=100867,
            ),
        ]
        await service._upsert_subcontracting_orders_no_commit(records)
        await test_database._connection.commit()
        rows = await self._rows(
            test_database, "cached_subcontracting_orders",
            "bill_no=? AND material_code=? AND aux_prop_id=?",
            ("WW25100020", "08.27.001", 0),
        )
        assert len(rows) == 2, (
            f"Expected 2 rows (one per entry line); got {len(rows)}. If 1, the "
            "entry-grain collapse is back on the SEVENTH table — entry_id "
            "missing from the UNIQUE / ON CONFLICT / dedup key. Migration 019."
        )
        async with test_database._connection.execute(
            "SELECT SUM(order_qty) FROM cached_subcontracting_orders WHERE bill_no=?",
            ("WW25100020",),
        ) as cursor:
            total = (await cursor.fetchone())[0]
        assert float(total) == 40000.0

    @pytest.mark.asyncio
    async def test_same_entry_id_still_dedups(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Idempotency unchanged: the SAME entry line twice (dual-field
        SAL_SaleOrder query repeat) collapses to one row."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        line = dict(
            bill_no="XSDD_DUP", mto_number="DS2605999", material_code="07.32.001",
            customer_name="客户A", qty=Decimal("300"), aux_prop_id=1, entry_id=900001,
        )
        records = [SalesOrderModel(**line), SalesOrderModel(**line)]
        await service._upsert_sales_orders_no_commit(records)
        await test_database._connection.commit()
        async with test_database._connection.execute(
            "SELECT COUNT(*) FROM cached_sales_orders WHERE bill_no=?",
            ("XSDD_DUP",),
        ) as cursor:
            n = (await cursor.fetchone())[0]
        assert n == 1


class TestStalePurge:
    """Audit 2026-06-10 Bug 2: ghost rows from documents deleted/反审核-ed in
    Kingdee. Per-MTO DELETE lists were derived from FETCHED records, so an MTO
    whose last document disappeared kept its dead cached rows forever; and
    cached_production_orders had no delete step at all.
    """

    def _service(self, mock_readers, test_database, mock_sync_progress):
        return SyncService(
            readers=mock_readers, db=test_database, progress=mock_sync_progress
        )

    async def _insert_delivery(self, db, mto, bill="XS_OLD", qty=100.0):
        await db.execute_write(
            "INSERT INTO cached_sales_delivery "
            "(bill_no, mto_number, material_code, real_qty, must_qty, aux_prop_id, entry_id) "
            "VALUES (?, ?, ?, ?, ?, 0, 0)",
            [bill, mto, "07.01.01", qty, qty],
        )

    @pytest.mark.asyncio
    async def test_purge_mtos_removes_rows_even_with_zero_fetched_records(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """The ghost case: sync fetched ZERO delivery rows for an MTO whose
        last 出库单 was deleted in Kingdee — the dead cached row must go."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        await self._insert_delivery(test_database, "AS_GHOST")

        await service._upsert_sales_delivery_no_commit([], purge_mtos=["AS_GHOST"])
        await test_database._connection.commit()

        rows = await test_database.execute_read(
            "SELECT COUNT(*) FROM cached_sales_delivery WHERE mto_number='AS_GHOST'"
        )
        assert rows[0][0] == 0, (
            "Ghost row survived: purge_mtos with zero fetched records must "
            "still delete — otherwise phantom 超发 alerts persist forever."
        )

    @pytest.mark.asyncio
    async def test_purge_spares_mtos_outside_purge_list(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """MTOs from failed fetch batches are NOT in purge_mtos — their cached
        data must survive (a transient API error must never wipe the cache)."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        await self._insert_delivery(test_database, "AS_FAILED_BATCH")
        await self._insert_delivery(test_database, "AS_OK")

        await service._upsert_sales_delivery_no_commit([], purge_mtos=["AS_OK"])
        await test_database._connection.commit()

        rows = await test_database.execute_read(
            "SELECT mto_number FROM cached_sales_delivery"
        )
        assert {r[0] for r in rows} == {"AS_FAILED_BATCH"}

    @pytest.mark.asyncio
    async def test_legacy_call_without_purge_list_derives_from_records(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """Direct callers (no purge_mtos) keep the old derive-from-records
        behavior: rows for unrelated MTOs are untouched."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        await self._insert_delivery(test_database, "AS_UNRELATED")

        records = [
            SalesDeliveryModel(
                bill_no="XS_NEW", mto_number="AS_TOUCHED", material_code="07.01.01",
                real_qty=Decimal("5"), must_qty=Decimal("5"), aux_prop_id=0, entry_id=1,
            )
        ]
        await service._upsert_sales_delivery_no_commit(records)
        await test_database._connection.commit()

        rows = await test_database.execute_read(
            "SELECT mto_number FROM cached_sales_delivery ORDER BY mto_number"
        )
        assert [r[0] for r in rows] == ["AS_TOUCHED", "AS_UNRELATED"]

    @pytest.mark.asyncio
    async def test_fetch_by_mto_numbers_excludes_failed_batches_from_purge(
        self, mock_readers, test_database, mock_sync_progress, monkeypatch
    ):
        """purge_mtos must cover only SUCCESSFUL batches."""
        import src.sync.sync_service as sync_module

        service = self._service(mock_readers, test_database, mock_sync_progress)
        monkeypatch.setattr(sync_module, "MTO_BATCH_SIZE", 2)

        # Batch 1 (A1, A2) succeeds with one record; batch 2 (B1, B2) fails.
        async def fake_batch(reader, mtos, data_type, batch_idx, total):
            if "B1" in mtos:
                return None
            return [
                SalesDeliveryModel(
                    bill_no="XS1", mto_number="A1", material_code="07.01.01",
                    real_qty=Decimal("1"), must_qty=Decimal("1"),
                )
            ]

        service._fetch_mto_batch_with_retry = fake_batch

        records, purge_mtos = await service._fetch_by_mto_numbers(
            "sales_delivery", ["A1", "A2", "B1", "B2"], "sales_delivery"
        )
        assert len(records) == 1
        assert sorted(purge_mtos) == ["A1", "A2"], (
            "Failed-batch MTOs must be excluded from the purge list; including "
            "them deletes cached data the fetch could not replace."
        )

    @pytest.mark.asyncio
    async def test_production_orders_window_purges_stale_rows(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """A cached order inside the synced window with no matching fetched
        record disappears; rows outside the window (and NULL create_date)
        survive. cached_production_orders previously had NO delete step."""
        service = self._service(mock_readers, test_database, mock_sync_progress)

        async def insert_order(mto, bill, create_date):
            await test_database.execute_write(
                "INSERT INTO cached_production_orders "
                "(mto_number, bill_no, material_code, qty, create_date) "
                "VALUES (?, ?, '07.01.01', 10, ?)",
                [mto, bill, create_date],
            )

        await insert_order("AS_IN_WINDOW", "MO_STALE", "2026-06-03T10:00:00")
        await insert_order("AS_OUTSIDE", "MO_KEEP", "2026-05-01T10:00:00")
        await insert_order("AS_NULL_DATE", "MO_NULL", None)

        fetched = [
            ProductionOrderModel(
                bill_no="MO_FRESH", mto_number="AS_FRESH", workshop="",
                material_code="07.01.02", material_name="", specification="",
                qty=Decimal("5"), status="B", create_date="2026-06-04",
            )
        ]
        await service._upsert_production_orders(
            fetched, window=(date(2026, 6, 1), date(2026, 6, 7))
        )
        await test_database._connection.commit()

        rows = await test_database.execute_read(
            "SELECT mto_number FROM cached_production_orders ORDER BY mto_number"
        )
        assert [r[0] for r in rows] == ["AS_FRESH", "AS_NULL_DATE", "AS_OUTSIDE"], (
            "Window-replace must purge in-window stale rows (deleted/反审核 in "
            "Kingdee) while keeping out-of-window and NULL-date rows."
        )

    @pytest.mark.asyncio
    async def test_production_orders_window_purge_runs_with_empty_fetch(
        self, mock_readers, test_database, mock_sync_progress
    ):
        """If Kingdee returns ZERO orders for the window (all deleted), the
        purge must still run — this was the early-return ghost path."""
        service = self._service(mock_readers, test_database, mock_sync_progress)
        await test_database.execute_write(
            "INSERT INTO cached_production_orders "
            "(mto_number, bill_no, material_code, qty, create_date) "
            "VALUES ('AS_DEAD', 'MO_DEAD', '07.01.01', 10, '2026-06-03')",
        )

        await service._upsert_production_orders(
            [], window=(date(2026, 6, 1), date(2026, 6, 7))
        )
        await test_database._connection.commit()

        rows = await test_database.execute_read(
            "SELECT COUNT(*) FROM cached_production_orders WHERE mto_number='AS_DEAD'"
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
