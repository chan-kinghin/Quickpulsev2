"""Migration 019 (entry-line grain) — applies cleanly on fresh AND legacy DBs.

Fresh path: the standard test_database fixture runs schema.sql (already at
entry grain) and then all migrations including 019's rebuild — covered here by
asserting the end state.

Legacy path: simulate a pre-019 (current prod) database — seven document cache
tables WITHOUT entry_id, UNIQUE at document grain, migrations 001-018 marked
applied — then connect and assert 019 rebuilds with zero row loss, entry_id
backfilled to 0, and the widened UNIQUE accepting two same-document lines.
"""

import sqlite3
from pathlib import Path

import pytest
import pytest_asyncio

from src.database.connection import Database

ENTRY_GRAIN_TABLES = {
    "cached_purchase_orders": (
        "bill_no", "mto_number", "material_code", "aux_prop_id", "entry_id",
    ),
    "cached_production_receipts": (
        "bill_no", "mto_number", "material_code", "aux_prop_id", "entry_id",
    ),
    "cached_purchase_receipts": (
        "bill_no", "mto_number", "material_code", "bill_type_number",
        "aux_prop_id", "entry_id",
    ),
    "cached_material_picking": (
        "bill_no", "mto_number", "material_code", "ppbom_bill_no",
        "aux_prop_id", "entry_id",
    ),
    "cached_sales_delivery": (
        "bill_no", "mto_number", "material_code", "aux_prop_id", "entry_id",
    ),
    "cached_sales_orders": (
        "bill_no", "mto_number", "material_code", "aux_prop_id", "entry_id",
    ),
    "cached_subcontracting_orders": (
        "bill_no", "mto_number", "material_code", "aux_prop_id", "entry_id",
    ),
}

# Pre-019 table shapes (schema.sql as deployed before this migration).
LEGACY_DDL = """
CREATE TABLE cached_purchase_orders (
    id INTEGER PRIMARY KEY, bill_no TEXT NOT NULL, mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL, material_name TEXT, specification TEXT,
    aux_attributes TEXT, aux_prop_id INTEGER DEFAULT 0,
    order_qty REAL, stock_in_qty REAL, remain_stock_in_qty REAL,
    raw_data TEXT, synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
);
CREATE TABLE cached_production_receipts (
    id INTEGER PRIMARY KEY, bill_no TEXT DEFAULT '', mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL, real_qty REAL, must_qty REAL,
    aux_prop_id INTEGER DEFAULT 0,
    raw_data TEXT, synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
);
CREATE TABLE cached_purchase_receipts (
    id INTEGER PRIMARY KEY, bill_no TEXT DEFAULT '', mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL, real_qty REAL, must_qty REAL,
    bill_type_number TEXT, aux_prop_id INTEGER DEFAULT 0,
    raw_data TEXT, synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, bill_type_number, aux_prop_id)
);
CREATE TABLE cached_material_picking (
    id INTEGER PRIMARY KEY, mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL, bill_no TEXT, app_qty REAL, actual_qty REAL,
    ppbom_bill_no TEXT, aux_prop_id INTEGER DEFAULT 0,
    raw_data TEXT, synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, ppbom_bill_no, aux_prop_id)
);
CREATE TABLE cached_sales_delivery (
    id INTEGER PRIMARY KEY, bill_no TEXT DEFAULT '', mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL, real_qty REAL, must_qty REAL,
    aux_prop_id INTEGER DEFAULT 0,
    raw_data TEXT, synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
);
CREATE TABLE cached_sales_orders (
    id INTEGER PRIMARY KEY, bill_no TEXT NOT NULL, mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL, material_name TEXT, specification TEXT,
    aux_attributes TEXT, aux_prop_id INTEGER DEFAULT 0, customer_name TEXT,
    delivery_date TEXT, qty REAL DEFAULT 0, bom_short_name TEXT DEFAULT '',
    material_group_name TEXT DEFAULT '', close_status TEXT DEFAULT 'A',
    raw_data TEXT, synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
);
CREATE TABLE cached_subcontracting_orders (
    id INTEGER PRIMARY KEY, bill_no TEXT NOT NULL, mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL, order_qty REAL, stock_in_qty REAL,
    no_stock_in_qty REAL, aux_prop_id INTEGER DEFAULT 0,
    raw_data TEXT, synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
);
"""


def _unique_index_columns(con: sqlite3.Connection, table: str) -> set[tuple]:
    uniques = set()
    for _, name, is_unique, *_ in con.execute(f"PRAGMA index_list({table})"):
        if is_unique:
            cols = tuple(
                r[2] for r in con.execute(f"PRAGMA index_info({name})")
            )
            uniques.add(cols)
    return uniques


@pytest_asyncio.fixture
async def legacy_database(tmp_path: Path):
    """Pre-019 DB: legacy table shapes, migrations 001-018 marked applied,
    one representative row per table (with raw_data lacking entry_id, as on
    prod today)."""
    db_path = tmp_path / "legacy.db"
    con = sqlite3.connect(db_path)
    con.executescript(LEGACY_DDL)
    con.execute(
        "CREATE TABLE _migrations (name TEXT PRIMARY KEY, "
        "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    migrations_dir = (
        Path(__file__).resolve().parents[2] / "src" / "database" / "migrations"
    )
    for f in sorted(migrations_dir.glob("*.sql")):
        if f.name < "019":
            con.execute("INSERT INTO _migrations (name) VALUES (?)", (f.name,))
    # Representative legacy rows (raw_data WITHOUT entry_id).
    con.execute(
        "INSERT INTO cached_sales_delivery "
        "(bill_no, mto_number, material_code, real_qty, must_qty, aux_prop_id, raw_data) "
        "VALUES ('XS26050001', 'AS001', '03.03.001', 186, 186, 196059, "
        "'{\"bill_no\": \"XS26050001\"}')"
    )
    con.execute(
        "INSERT INTO cached_material_picking "
        "(mto_number, material_code, bill_no, app_qty, actual_qty, ppbom_bill_no, "
        "aux_prop_id, raw_data) "
        "VALUES ('AS001', '05.02.04.033', 'LL26041108', 579, 579, 'PPBOM1', 106244, '{}')"
    )
    con.execute(
        "INSERT INTO cached_purchase_orders "
        "(bill_no, mto_number, material_code, order_qty, stock_in_qty, "
        "remain_stock_in_qty, raw_data) VALUES ('PO1', 'AS001', '03.23.008', 10, 0, 10, '{}')"
    )
    con.execute(
        "INSERT INTO cached_production_receipts "
        "(bill_no, mto_number, material_code, real_qty, must_qty, raw_data) "
        "VALUES ('CP1', 'AS001', '05.01.01', 5, 5, '{}')"
    )
    con.execute(
        "INSERT INTO cached_purchase_receipts "
        "(bill_no, mto_number, material_code, real_qty, must_qty, bill_type_number, raw_data) "
        "VALUES ('CG26041724', 'AS001', '23.12.01', 14, 14, 'RKD01_SYS', '{}')"
    )
    con.execute(
        "INSERT INTO cached_sales_orders "
        "(bill_no, mto_number, material_code, customer_name, qty, raw_data) "
        "VALUES ('XSDD2605036', 'DS001', '07.32.001', '客户A', 300, '{}')"
    )
    con.execute(
        "INSERT INTO cached_subcontracting_orders "
        "(bill_no, mto_number, material_code, order_qty, stock_in_qty, "
        "no_stock_in_qty, raw_data) "
        "VALUES ('WW25100020', '踏板', '08.27.001', 1200, 0, 1200, '{}')"
    )
    con.commit()
    con.close()

    db = Database(db_path)
    await db.connect()  # runs schema.sql (IF NOT EXISTS no-ops) + migration 019
    yield db
    await db.close()


class TestFreshSchema:
    @pytest.mark.asyncio
    async def test_fresh_db_has_entry_grain_unique(self, test_database):
        """Fresh DB end state: every document cache table carries exactly the
        entry-grain UNIQUE; the narrow pre-019 indexes (001/004/014) are gone."""
        for table, expected in ENTRY_GRAIN_TABLES.items():
            rows = await test_database.execute(f"PRAGMA index_list({table})")
            uniques = []
            for r in rows:
                if r[2] == 1:  # is unique
                    info = await test_database.execute(f"PRAGMA index_info({r[1]})")
                    uniques.append(tuple(c[2] for c in info))
            assert uniques == [expected], (
                f"{table}: unique indexes {uniques} != [{expected}]. A narrow "
                "pre-entry-grain unique index would reject the second entry "
                "line of a document (Pattern 5 #6 regression)."
            )


class TestLegacyMigration:
    @pytest.mark.asyncio
    async def test_migration_applies_on_legacy_schema_without_row_loss(
        self, legacy_database
    ):
        for table in ENTRY_GRAIN_TABLES:
            rows = await legacy_database.execute(f"SELECT COUNT(*) FROM {table}")
            assert rows[0][0] == 1, f"{table} lost its row during migration 019"
            # entry_id exists and is backfilled to 0 (legacy raw_data lacks it)
            rows = await legacy_database.execute(
                f"SELECT entry_id FROM {table}"
            )
            assert rows[0][0] == 0

    @pytest.mark.asyncio
    async def test_migrated_unique_accepts_two_same_document_lines(
        self, legacy_database
    ):
        """The whole point: after 019, two lines of ONE document with the same
        (material, aux) coexist when their entry ids differ."""
        await legacy_database.execute_write(
            "INSERT INTO cached_sales_delivery "
            "(bill_no, mto_number, material_code, real_qty, must_qty, aux_prop_id, entry_id) "
            "VALUES ('XS26050001', 'AS001', '03.03.001', 55, 55, 196059, 226992)"
        )
        rows = await legacy_database.execute(
            "SELECT SUM(real_qty) FROM cached_sales_delivery "
            "WHERE bill_no='XS26050001' AND aux_prop_id=196059"
        )
        assert float(rows[0][0]) == 241.0  # 186 (migrated, entry_id=0) + 55

    @pytest.mark.asyncio
    async def test_migration_recorded(self, legacy_database):
        rows = await legacy_database.execute(
            "SELECT COUNT(*) FROM _migrations "
            "WHERE name = '019_entry_id_grain_for_document_caches.sql'"
        )
        assert rows[0][0] == 1
