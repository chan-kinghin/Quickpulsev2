-- Migration 010: Add mto_number to UNIQUE on cached_production_orders
--
-- Problem (Bug 7 / bug-patterns.md #5 recurrence — Wave 4A): the table-level
-- UNIQUE constraint was (bill_no, material_code, aux_prop_id), excluding
-- mto_number, but the upsert in sync_service.py:_upsert_production_orders
-- did `ON CONFLICT(bill_no, material_code, aux_prop_id) DO UPDATE SET
-- mto_number=excluded.mto_number, ...`. When two MTOs of the same customer
-- share a production-order bill_no (legitimate — one PRD_MO can be
-- referenced from multiple MTO planning chains), the second sync's INSERT
-- collided on the existing row and silently rewrote its mto_number to the
-- new MTO. The first MTO's row was effectively migrated to the second MTO;
-- querying the first returned no rows, querying the second returned ghost
-- data that didn't belong to it.
--
-- Real-world contamination found 2026-04-26: customer 瑞弧WeaArCo MTO
-- DS256203S returned 18 ghost 07.xx rows (07.01.06, 07.01.07, 07.01.78,
-- 07.01.80=941, 07.02.022, 07.02.121, 07.04.078, 07.05.16.01..06,
-- 07.08.001..003, 07.23.007, 07.23.034, 07.25.84, 07.33.010, 07.37.001).
-- None of those exist in any Kingdee form for DS256203S — they were
-- migrated from sibling MTOs DS242022S-A2 / WS2510003 (same customer).
--
-- Template: this migration mirrors 009 (cached_subcontracting_orders), the
-- earlier instance of the same Pattern 5 bug fixed in commit cc9ab22. The
-- shape and data-preservation tradeoffs are identical; only the table name
-- and the recreated index list differ.
--
-- Fix: rebuild cached_production_orders with UNIQUE
-- (bill_no, mto_number, material_code, aux_prop_id). The 12-step recipe is
-- required because SQLite does not support ALTER TABLE DROP CONSTRAINT.
--
-- Data preservation: rows that pre-existed under wrong mto_numbers cannot
-- be recovered (the contamination already overwrote the original values).
-- The accompanying scripts/cleanup_production_orders_contamination.py
-- re-syncs from Kingdee for the affected customer cluster after the
-- migration applies.

-- Step 1: Create new table with corrected UNIQUE constraint. Schema must
-- match the post-migration shape in schema.sql exactly (column order, types,
-- defaults).
CREATE TABLE cached_production_orders_new (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    bill_no TEXT NOT NULL,
    workshop TEXT,
    material_code TEXT,
    material_name TEXT,
    specification TEXT,
    aux_attributes TEXT,
    aux_prop_id INTEGER DEFAULT 0,
    qty REAL,
    status TEXT,
    create_date TEXT,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
);

-- Step 2: Copy data. INSERT OR IGNORE: if any pre-existing duplicates somehow
-- exist under the same (bill_no, mto_number, material_code, aux_prop_id),
-- keep the first one (the new constraint is strictly tighter than the old,
-- so this is purely a safety net — under the old constraint, duplicates
-- with same mto_number were already impossible).
INSERT OR IGNORE INTO cached_production_orders_new
    (id, mto_number, bill_no, workshop, material_code, material_name,
     specification, aux_attributes, aux_prop_id, qty, status, create_date,
     raw_data, synced_at)
SELECT id, mto_number, bill_no, workshop, material_code, material_name,
       specification, aux_attributes, aux_prop_id, qty, status, create_date,
       raw_data, synced_at
FROM cached_production_orders;

-- Step 3: Drop old table (cascades indexes auto-attached to the table)
DROP TABLE cached_production_orders;

-- Step 4: Rename new → final
ALTER TABLE cached_production_orders_new RENAME TO cached_production_orders;

-- Step 5: Recreate the secondary indexes that the original CREATE TABLE
-- statement in schema.sql defined. Without these, queries that filter by
-- mto_number / material_code / synced_at lose their index path. Mirror the
-- complete set from schema.sql:23-29.
CREATE INDEX IF NOT EXISTS idx_po_mto
    ON cached_production_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_po_synced
    ON cached_production_orders(synced_at);
CREATE INDEX IF NOT EXISTS idx_po_material
    ON cached_production_orders(material_code);
CREATE INDEX IF NOT EXISTS idx_po_mto_synced
    ON cached_production_orders(mto_number, synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_mto_material
    ON cached_production_orders(mto_number, material_name, synced_at DESC);
