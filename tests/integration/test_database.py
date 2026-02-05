"""Integration tests for database operations."""

from decimal import Decimal

import pytest


class TestDatabaseConnection:
    """Tests for Database class connection and schema."""

    @pytest.mark.asyncio
    async def test_connect_creates_tables(self, temp_db_path):
        """Test connect() creates schema tables."""
        from src.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()

        # Check tables exist
        rows = await db.execute_read(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        table_names = [row[0] for row in rows]

        assert "cached_production_orders" in table_names
        assert "cached_production_bom" in table_names
        assert "sync_history" in table_names

        await db.close()

    @pytest.mark.asyncio
    async def test_connect_is_idempotent(self, temp_db_path):
        """Test connect() can be called multiple times."""
        from src.database.connection import Database

        db = Database(temp_db_path)
        await db.connect()
        await db.connect()  # Should not raise

        rows = await db.execute_read("SELECT 1")
        assert rows[0][0] == 1

        await db.close()


class TestDatabaseReadWrite:
    """Tests for Database read/write operations."""

    @pytest.mark.asyncio
    async def test_execute_read(self, test_database):
        """Test read operations."""
        rows = await test_database.execute_read("SELECT 1 + 1 as result")
        assert rows[0][0] == 2

    @pytest.mark.asyncio
    async def test_execute_read_with_params(self, test_database):
        """Test read with parameters."""
        rows = await test_database.execute_read(
            "SELECT ? + ? as result", [5, 10]
        )
        assert rows[0][0] == 15

    @pytest.mark.asyncio
    async def test_execute_write(self, test_database):
        """Test write operation."""
        await test_database.execute_write(
            """
            INSERT INTO cached_production_orders
            (mto_number, bill_no, workshop, material_code, material_name,
             specification, aux_attributes, qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ["AK001", "MO001", "Workshop", "M001", "Material", "Spec", "", 100],
        )

        rows = await test_database.execute_read(
            "SELECT mto_number, bill_no FROM cached_production_orders WHERE mto_number = ?",
            ["AK001"],
        )

        assert len(rows) == 1
        assert rows[0][0] == "AK001"
        assert rows[0][1] == "MO001"

    @pytest.mark.asyncio
    async def test_executemany(self, test_database):
        """Test batch insert."""
        data = [
            ("AK001", "MO001", "Workshop", "M001", "Material1", "", "", 100),
            ("AK002", "MO002", "Workshop", "M002", "Material2", "", "", 200),
            ("AK003", "MO003", "Workshop", "M003", "Material3", "", "", 300),
        ]

        await test_database.executemany(
            """
            INSERT INTO cached_production_orders
            (mto_number, bill_no, workshop, material_code, material_name,
             specification, aux_attributes, qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data,
        )

        rows = await test_database.execute_read(
            "SELECT COUNT(*) FROM cached_production_orders"
        )
        assert rows[0][0] == 3


class TestCacheOperations:
    """Tests for cache table operations."""

    @pytest.mark.asyncio
    async def test_insert_production_order(self, test_database):
        """Test inserting production order into cache."""
        await test_database.execute_write(
            """
            INSERT INTO cached_production_orders
            (mto_number, bill_no, workshop, material_code, material_name,
             specification, aux_attributes, qty, raw_data, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["AK2510034", "MO0001", "Workshop A", "P001", "Product",
             "Spec", "Blue", 100, '{"status": "Approved"}'],
        )

        rows = await test_database.execute_read(
            """
            SELECT mto_number, bill_no, qty, synced_at
            FROM cached_production_orders
            WHERE bill_no = ?
            """,
            ["MO0001"],
        )

        assert len(rows) == 1
        assert rows[0][0] == "AK2510034"
        assert rows[0][2] == 100
        assert rows[0][3] is not None  # synced_at should be set

    @pytest.mark.asyncio
    async def test_upsert_on_conflict(self, test_database):
        """Test upsert updates existing records."""
        # Insert initial
        await test_database.execute_write(
            """
            INSERT INTO cached_production_orders
            (mto_number, bill_no, workshop, material_code, material_name,
             specification, aux_attributes, qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ["AK001", "MO001", "Workshop A", "M001", "Material1", "", "", 100],
        )

        # Upsert with same bill_no (unique constraint)
        await test_database.execute_write(
            """
            INSERT INTO cached_production_orders
            (mto_number, bill_no, workshop, material_code, material_name,
             specification, aux_attributes, qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(bill_no, material_code, aux_prop_id) DO UPDATE SET
                qty = excluded.qty,
                material_name = excluded.material_name
            """,
            ["AK001", "MO001", "Workshop A", "M001", "Updated Material", "", "", 200],
        )

        rows = await test_database.execute_read(
            "SELECT qty, material_name FROM cached_production_orders WHERE bill_no = ?",
            ["MO001"],
        )

        assert len(rows) == 1
        assert rows[0][0] == 200  # Updated qty
        assert rows[0][1] == "Updated Material"

    @pytest.mark.asyncio
    async def test_insert_production_bom(self, test_database):
        """Test inserting BOM entry into cache."""
        await test_database.execute_write(
            """
            INSERT INTO cached_production_bom
            (mo_bill_no, material_code, material_name, material_type,
             need_qty, picked_qty, no_picked_qty, raw_data, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["MO0001", "C001", "Part 1", 1, 50, 30, 20, '{"mto_number": "AK001"}'],
        )

        rows = await test_database.execute_read(
            """
            SELECT mo_bill_no, material_code, material_type, need_qty
            FROM cached_production_bom
            WHERE mo_bill_no = ?
            """,
            ["MO0001"],
        )

        assert len(rows) == 1
        assert rows[0][1] == "C001"
        assert rows[0][2] == 1
        assert rows[0][3] == 50

    @pytest.mark.asyncio
    async def test_delete_bom_for_bill(self, test_database):
        """Test deleting BOM entries for a bill number."""
        # Insert multiple BOM entries
        data = [
            ("MO0001", "C001", "Part 1", 1, 50, 30, 20, "{}"),
            ("MO0001", "C002", "Part 2", 2, 100, 0, 100, "{}"),
            ("MO0002", "C003", "Part 3", 1, 25, 25, 0, "{}"),
        ]

        await test_database.executemany(
            """
            INSERT INTO cached_production_bom
            (mo_bill_no, material_code, material_name, material_type,
             need_qty, picked_qty, no_picked_qty, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data,
        )

        # Delete for MO0001
        await test_database.execute_write(
            "DELETE FROM cached_production_bom WHERE mo_bill_no = ?",
            ["MO0001"],
        )

        # Only MO0002 should remain
        rows = await test_database.execute_read(
            "SELECT mo_bill_no FROM cached_production_bom"
        )
        assert len(rows) == 1
        assert rows[0][0] == "MO0002"


class TestSyncHistory:
    """Tests for sync_history table operations."""

    @pytest.mark.asyncio
    async def test_insert_sync_history(self, test_database):
        """Test inserting sync history record."""
        await test_database.execute_write(
            """
            INSERT INTO sync_history
            (started_at, finished_at, status, days_back, records_synced, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ["2025-01-15T10:00:00", "2025-01-15T10:30:00", "success", 90, 1500, None],
        )

        rows = await test_database.execute_read(
            "SELECT status, records_synced FROM sync_history ORDER BY id DESC LIMIT 1"
        )

        assert len(rows) == 1
        assert rows[0][0] == "success"
        assert rows[0][1] == 1500

    @pytest.mark.asyncio
    async def test_sync_history_with_error(self, test_database):
        """Test sync history with error message."""
        await test_database.execute_write(
            """
            INSERT INTO sync_history
            (started_at, finished_at, status, days_back, records_synced, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ["2025-01-15T10:00:00", "2025-01-15T10:05:00", "error", 90, 500,
             "Connection to Kingdee failed"],
        )

        rows = await test_database.execute_read(
            "SELECT status, error_message FROM sync_history ORDER BY id DESC LIMIT 1"
        )

        assert rows[0][0] == "error"
        assert "Connection" in rows[0][1]
