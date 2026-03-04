"""Tests for BOMJoinedRow and get_mto_bom_joined in cache_reader.py"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.query.cache_reader import BOMJoinedRow, CacheReader


class TestBOMJoinedRowConstruction:
    """Tests for BOMJoinedRow dataclass."""

    def test_basic_construction(self):
        """Test BOMJoinedRow can be constructed with all fields."""
        row = BOMJoinedRow(
            mo_bill_no="MO0001",
            mto_number="AK2510034",
            material_code="C001",
            material_name="Part A",
            specification="Spec A",
            aux_attributes="Blue",
            aux_prop_id=1001,
            material_type=1,
            need_qty=Decimal("50"),
            picked_qty=Decimal("30"),
            no_picked_qty=Decimal("20"),
            prod_receipt_real_qty=Decimal("25"),
            prod_receipt_must_qty=Decimal("50"),
            pick_actual_qty=Decimal("30"),
            pick_app_qty=Decimal("35"),
            purchase_order_qty=Decimal("100"),
            purchase_stock_in_qty=Decimal("80"),
            purchase_receipt_real_qty=Decimal("75"),
            subcontract_order_qty=Decimal("40"),
            subcontract_stock_in_qty=Decimal("35"),
            delivery_real_qty=Decimal("90"),
        )

        assert row.mo_bill_no == "MO0001"
        assert row.mto_number == "AK2510034"
        assert row.material_code == "C001"
        assert row.material_name == "Part A"
        assert row.specification == "Spec A"
        assert row.aux_attributes == "Blue"
        assert row.aux_prop_id == 1001
        assert row.material_type == 1
        assert row.need_qty == Decimal("50")
        assert row.picked_qty == Decimal("30")
        assert row.no_picked_qty == Decimal("20")
        assert row.prod_receipt_real_qty == Decimal("25")
        assert row.prod_receipt_must_qty == Decimal("50")
        assert row.pick_actual_qty == Decimal("30")
        assert row.pick_app_qty == Decimal("35")
        assert row.purchase_order_qty == Decimal("100")
        assert row.purchase_stock_in_qty == Decimal("80")
        assert row.purchase_receipt_real_qty == Decimal("75")
        assert row.subcontract_order_qty == Decimal("40")
        assert row.subcontract_stock_in_qty == Decimal("35")
        assert row.delivery_real_qty == Decimal("90")

    def test_zero_aggregated_fields(self):
        """Test BOMJoinedRow with all aggregated fields at zero (no receipts)."""
        row = BOMJoinedRow(
            mo_bill_no="MO0001",
            mto_number="AK2510034",
            material_code="C002",
            material_name="Part B",
            specification="",
            aux_attributes="",
            aux_prop_id=0,
            material_type=2,
            need_qty=Decimal("100"),
            picked_qty=Decimal("0"),
            no_picked_qty=Decimal("100"),
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
        )

        assert row.prod_receipt_real_qty == Decimal("0")
        assert row.purchase_order_qty == Decimal("0")
        assert row.delivery_real_qty == Decimal("0")


class TestRowToBomJoined:
    """Tests for CacheReader._row_to_bom_joined method."""

    def test_happy_path(self):
        """Test _row_to_bom_joined with all fields populated."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0001",        # 0: mo_bill_no
            "AK2510034",     # 1: mto_number
            "C001",          # 2: material_code
            "Part A",        # 3: material_name
            "Spec A",        # 4: specification
            "Blue",          # 5: aux_attributes
            1001,            # 6: aux_prop_id
            1,               # 7: material_type
            50.0,            # 8: need_qty
            30.0,            # 9: picked_qty
            20.0,            # 10: no_picked_qty
            25.0,            # 11: prod_receipt_real_qty
            50.0,            # 12: prod_receipt_must_qty
            30.0,            # 13: pick_actual_qty
            35.0,            # 14: pick_app_qty
            100.0,           # 15: purchase_order_qty
            80.0,            # 16: purchase_stock_in_qty
            75.0,            # 17: purchase_receipt_real_qty
            40.0,            # 18: subcontract_order_qty
            35.0,            # 19: subcontract_stock_in_qty
            90.0,            # 20: delivery_real_qty
            "2026-01-15 12:00:00",  # 21: synced_at
        )

        result = reader._row_to_bom_joined(row)

        assert isinstance(result, BOMJoinedRow)
        assert result.mo_bill_no == "MO0001"
        assert result.mto_number == "AK2510034"
        assert result.material_code == "C001"
        assert result.material_name == "Part A"
        assert result.specification == "Spec A"
        assert result.aux_attributes == "Blue"
        assert result.aux_prop_id == 1001
        assert result.material_type == 1
        assert result.need_qty == Decimal("50.0")
        assert result.picked_qty == Decimal("30.0")
        assert result.no_picked_qty == Decimal("20.0")
        assert result.prod_receipt_real_qty == Decimal("25.0")
        assert result.prod_receipt_must_qty == Decimal("50.0")
        assert result.pick_actual_qty == Decimal("30.0")
        assert result.pick_app_qty == Decimal("35.0")
        assert result.purchase_order_qty == Decimal("100.0")
        assert result.purchase_stock_in_qty == Decimal("80.0")
        assert result.purchase_receipt_real_qty == Decimal("75.0")
        assert result.subcontract_order_qty == Decimal("40.0")
        assert result.subcontract_stock_in_qty == Decimal("35.0")
        assert result.delivery_real_qty == Decimal("90.0")

    def test_with_null_values(self):
        """Test _row_to_bom_joined with None/null values from COALESCE fallback."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO0001",   # 0: mo_bill_no
            None,        # 1: mto_number
            "C002",      # 2: material_code
            None,        # 3: material_name
            None,        # 4: specification
            None,        # 5: aux_attributes
            None,        # 6: aux_prop_id
            2,           # 7: material_type
            100.0,       # 8: need_qty
            None,        # 9: picked_qty
            None,        # 10: no_picked_qty
            0,           # 11: prod_receipt_real_qty (COALESCE default)
            0,           # 12: prod_receipt_must_qty
            0,           # 13: pick_actual_qty
            0,           # 14: pick_app_qty
            0,           # 15: purchase_order_qty
            0,           # 16: purchase_stock_in_qty
            0,           # 17: purchase_receipt_real_qty
            0,           # 18: subcontract_order_qty
            0,           # 19: subcontract_stock_in_qty
            0,           # 20: delivery_real_qty
            None,        # 21: synced_at
        )

        result = reader._row_to_bom_joined(row)

        assert result.mo_bill_no == "MO0001"
        assert result.mto_number == ""
        assert result.material_name == ""
        assert result.specification == ""
        assert result.aux_attributes == ""
        assert result.aux_prop_id == 0
        assert result.picked_qty == Decimal("0")
        assert result.no_picked_qty == Decimal("0")
        assert result.prod_receipt_real_qty == Decimal("0")
        assert result.purchase_order_qty == Decimal("0")
        assert result.delivery_real_qty == Decimal("0")

    def test_with_chinese_data(self):
        """Test _row_to_bom_joined with Chinese material names."""
        mock_db = MagicMock()
        reader = CacheReader(mock_db, ttl_minutes=60)

        row = (
            "MO20260115-001",  # 0: mo_bill_no
            "AK2610001",       # 1: mto_number
            "07.01.003",       # 2: material_code
            "成品外壳",         # 3: material_name
            "ABS 200x150mm",   # 4: specification
            "红色/大号",        # 5: aux_attributes
            9001,              # 6: aux_prop_id
            1,                 # 7: material_type
            Decimal("500"),    # 8: need_qty
            Decimal("400"),    # 9: picked_qty
            Decimal("100"),    # 10: no_picked_qty
            Decimal("350"),    # 11: prod_receipt_real_qty
            Decimal("500"),    # 12: prod_receipt_must_qty
            Decimal("400"),    # 13: pick_actual_qty
            Decimal("450"),    # 14: pick_app_qty
            Decimal("0"),      # 15: purchase_order_qty
            Decimal("0"),      # 16: purchase_stock_in_qty
            Decimal("0"),      # 17: purchase_receipt_real_qty
            Decimal("0"),      # 18: subcontract_order_qty
            Decimal("0"),      # 19: subcontract_stock_in_qty
            Decimal("300"),    # 20: delivery_real_qty
            "2026-01-15 10:00:00",  # 21: synced_at
        )

        result = reader._row_to_bom_joined(row)

        assert result.material_name == "成品外壳"
        assert result.specification == "ABS 200x150mm"
        assert result.aux_attributes == "红色/大号"
        assert result.need_qty == Decimal("500")
        assert result.prod_receipt_real_qty == Decimal("350")
        assert result.delivery_real_qty == Decimal("300")


class TestGetMtoBomJoined:
    """Tests for CacheReader.get_mto_bom_joined with actual SQLite database."""

    @pytest.mark.asyncio
    async def test_cache_miss_returns_empty(self, test_database):
        """Test get_mto_bom_joined returns empty result for unknown MTO."""
        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_mto_bom_joined("NONEXISTENT")

        assert result.data == []
        assert result.synced_at is None
        assert result.is_fresh is False

    @pytest.mark.asyncio
    async def test_bom_only_no_receipts(self, test_database):
        """Test BOM row with no matching receipts returns zeroes for aggregated fields."""
        await test_database.execute_write(
            """
            INSERT INTO cached_production_bom
            (mo_bill_no, mto_number, material_code, material_name,
             specification, aux_attributes, aux_prop_id, material_type,
             need_qty, picked_qty, no_picked_qty, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                "MO0001", "AK2510034", "C001", "Part A",
                "Spec A", "Blue", 1001, 1,
                50, 30, 20,
            ],
        )

        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_mto_bom_joined("AK2510034")

        assert len(result.data) == 1
        assert result.is_fresh is True
        row = result.data[0]
        assert isinstance(row, BOMJoinedRow)
        assert row.material_code == "C001"
        assert row.need_qty == Decimal("50")
        assert row.prod_receipt_real_qty == Decimal("0")
        assert row.pick_actual_qty == Decimal("0")
        assert row.purchase_order_qty == Decimal("0")
        assert row.purchase_receipt_real_qty == Decimal("0")
        assert row.subcontract_order_qty == Decimal("0")
        assert row.delivery_real_qty == Decimal("0")

    @pytest.mark.asyncio
    async def test_bom_with_production_receipts(self, test_database):
        """Test BOM row correctly joins production receipt aggregation."""
        # Insert BOM
        await test_database.execute_write(
            """
            INSERT INTO cached_production_bom
            (mo_bill_no, mto_number, material_code, material_name,
             specification, aux_attributes, aux_prop_id, material_type,
             need_qty, picked_qty, no_picked_qty, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["MO0001", "AK2510034", "C001", "Self-made Part", "Spec", "", 0, 1, 100, 80, 20],
        )

        # Insert two production receipt rows for same material (should be summed)
        for real_qty, must_qty in [(30, 50), (20, 50)]:
            await test_database.execute_write(
                """
                INSERT INTO cached_production_receipts
                (bill_no, mto_number, material_code, real_qty, must_qty,
                 aux_prop_id, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [f"RK{real_qty}", "AK2510034", "C001", real_qty, must_qty, 0],
            )

        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_mto_bom_joined("AK2510034")

        assert len(result.data) == 1
        row = result.data[0]
        assert row.prod_receipt_real_qty == Decimal("50")  # 30 + 20
        assert row.prod_receipt_must_qty == Decimal("100")  # 50 + 50

    @pytest.mark.asyncio
    async def test_bom_with_all_joins(self, test_database):
        """Test BOM row joins data from all source tables."""
        mto = "AK2510034"
        mat_code = "C002"
        aux_id = 1001

        # BOM
        await test_database.execute_write(
            """
            INSERT INTO cached_production_bom
            (mo_bill_no, mto_number, material_code, material_name,
             specification, aux_attributes, aux_prop_id, material_type,
             need_qty, picked_qty, no_picked_qty, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["MO0001", mto, mat_code, "Purchased Part", "Spec", "Blue", aux_id, 2, 200, 0, 200],
        )

        # Production receipt
        await test_database.execute_write(
            """
            INSERT INTO cached_production_receipts
            (bill_no, mto_number, material_code, real_qty, must_qty, aux_prop_id, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["RK001", mto, mat_code, 10, 20, aux_id],
        )

        # Material picking
        await test_database.execute_write(
            """
            INSERT INTO cached_material_picking
            (mto_number, material_code, app_qty, actual_qty, ppbom_bill_no, aux_prop_id, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [mto, mat_code, 50, 45, "PPBOM001", aux_id],
        )

        # Purchase order
        await test_database.execute_write(
            """
            INSERT INTO cached_purchase_orders
            (bill_no, mto_number, material_code, material_name, specification,
             aux_attributes, aux_prop_id, order_qty, stock_in_qty,
             remain_stock_in_qty, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["PO001", mto, mat_code, "Part", "Spec", "Blue", aux_id, 200, 150, 50],
        )

        # Purchase receipt
        await test_database.execute_write(
            """
            INSERT INTO cached_purchase_receipts
            (bill_no, mto_number, material_code, real_qty, must_qty,
             bill_type_number, aux_prop_id, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["RKD001", mto, mat_code, 140, 200, "RKD01_SYS", aux_id],
        )

        # Subcontracting order
        await test_database.execute_write(
            """
            INSERT INTO cached_subcontracting_orders
            (bill_no, mto_number, material_code, order_qty, stock_in_qty,
             no_stock_in_qty, aux_prop_id, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["SUB001", mto, mat_code, 60, 55, 5, aux_id],
        )

        # Sales delivery
        await test_database.execute_write(
            """
            INSERT INTO cached_sales_delivery
            (bill_no, mto_number, material_code, real_qty, must_qty, aux_prop_id, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            ["SD001", mto, mat_code, 90, 100, aux_id],
        )

        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_mto_bom_joined(mto)

        assert len(result.data) == 1
        row = result.data[0]
        assert row.material_code == mat_code
        assert row.aux_prop_id == aux_id
        assert row.need_qty == Decimal("200")
        assert row.prod_receipt_real_qty == Decimal("10")
        assert row.prod_receipt_must_qty == Decimal("20")
        assert row.pick_actual_qty == Decimal("45")
        assert row.pick_app_qty == Decimal("50")
        assert row.purchase_order_qty == Decimal("200")
        assert row.purchase_stock_in_qty == Decimal("150")
        assert row.purchase_receipt_real_qty == Decimal("140")
        assert row.subcontract_order_qty == Decimal("60")
        assert row.subcontract_stock_in_qty == Decimal("55")
        assert row.delivery_real_qty == Decimal("90")

    @pytest.mark.asyncio
    async def test_prefix_matching(self, test_database):
        """Test get_mto_bom_joined uses prefix matching (LIKE 'MTO%')."""
        # Insert BOM with sub-MTO suffix
        for suffix in ["", "-01", "-02"]:
            await test_database.execute_write(
                """
                INSERT INTO cached_production_bom
                (mo_bill_no, mto_number, material_code, material_name,
                 specification, aux_attributes, aux_prop_id, material_type,
                 need_qty, picked_qty, no_picked_qty, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [f"MO{suffix}", f"AK2510034{suffix}", f"C00{suffix or '0'}",
                 "Part", "", "", 0, 1, 10, 0, 10],
            )

        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_mto_bom_joined("AK2510034")

        # Should match all three: AK2510034, AK2510034-01, AK2510034-02
        assert len(result.data) == 3

    @pytest.mark.asyncio
    async def test_multiple_bom_rows_different_materials(self, test_database):
        """Test multiple BOM rows with different material codes are all returned."""
        mto = "AK2510034"
        materials = [
            ("C001", 1, 0),   # self-made, no aux
            ("C002", 2, 1001),  # purchased, with aux
            ("C003", 3, 0),   # subcontracted, no aux
        ]

        for mat_code, mat_type, aux_id in materials:
            await test_database.execute_write(
                """
                INSERT INTO cached_production_bom
                (mo_bill_no, mto_number, material_code, material_name,
                 specification, aux_attributes, aux_prop_id, material_type,
                 need_qty, picked_qty, no_picked_qty, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                ["MO0001", mto, mat_code, f"Part {mat_code}", "", "", aux_id, mat_type, 100, 0, 100],
            )

        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_mto_bom_joined(mto)

        assert len(result.data) == 3
        codes = [r.material_code for r in result.data]
        assert "C001" in codes
        assert "C002" in codes
        assert "C003" in codes

    @pytest.mark.asyncio
    async def test_no_multiplicative_join(self, test_database):
        """Test that subquery approach avoids multiplicative join inflation.

        If BOM has 2 rows for the same material, and there are 2 receipt rows,
        a naive join would produce 4 cross-product rows and inflate the SUM.
        The subquery approach should avoid this.
        """
        mto = "AK2510034"
        mat_code = "C001"
        aux_id = 0

        # Insert 2 BOM rows for same material (different mo_bill_no)
        for mo_no in ["MO0001", "MO0002"]:
            await test_database.execute_write(
                """
                INSERT INTO cached_production_bom
                (mo_bill_no, mto_number, material_code, material_name,
                 specification, aux_attributes, aux_prop_id, material_type,
                 need_qty, picked_qty, no_picked_qty, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [mo_no, mto, mat_code, "Part", "", "", aux_id, 1, 50, 0, 50],
            )

        # Insert 2 production receipt rows
        for bill_no, real_qty in [("RK001", 10), ("RK002", 15)]:
            await test_database.execute_write(
                """
                INSERT INTO cached_production_receipts
                (bill_no, mto_number, material_code, real_qty, must_qty,
                 aux_prop_id, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [bill_no, mto, mat_code, real_qty, real_qty, aux_id],
            )

        reader = CacheReader(test_database, ttl_minutes=60)
        result = await reader.get_mto_bom_joined(mto)

        # GROUP BY material_code, aux_prop_id -> 1 result row
        assert len(result.data) == 1
        row = result.data[0]
        # Receipts should be 10 + 15 = 25 (NOT 50 from multiplicative join)
        assert row.prod_receipt_real_qty == Decimal("25")
        # BOM need_qty is grouped: 50 + 50 is ambiguous, but it doesn't matter
        # because the GROUP BY aggregates BOM rows. What matters is receipt accuracy.
