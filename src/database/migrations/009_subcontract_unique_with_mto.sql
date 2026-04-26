-- Migration 009: Add mto_number to UNIQUE on cached_subcontracting_orders
--
-- Problem (Bug 7 / bug-patterns.md #5 recurrence): the table-level UNIQUE
-- constraint was (bill_no, material_code, aux_prop_id), excluding mto_number,
-- but the upsert in sync_service.py:_upsert_subcontracting_orders_no_commit
-- did `ON CONFLICT(bill_no, material_code, aux_prop_id) DO UPDATE SET
-- mto_number=excluded.mto_number`. When two MTOs of the same customer share a
-- supplier subcontract order (legitimate — one supplier order can fulfill
-- multiple MTOs), the second sync's INSERT collided on the existing row and
-- silently rewrote its mto_number to the new MTO. The first MTO's row was
-- effectively migrated to the second MTO; querying the first returned no
-- rows, querying the second returned ghost data that didn't belong to it.
--
-- Real-world contamination found 2026-04-26: customer 瑞弧WeaArCo MTOs
-- DS256203S / DS242022S-A2 / WS2510003. Direct Kingdee query for DS256203S
-- material 07.25.80 returned zero rows; QP returned demand=780 (from a
-- different MTO of the same customer that contaminated the cache).
--
-- Fix: rebuild cached_subcontracting_orders with UNIQUE
-- (bill_no, mto_number, material_code, aux_prop_id). The 12-step recipe is
-- required because SQLite does not support ALTER TABLE DROP CONSTRAINT.
--
-- Data preservation: rows that pre-existed under wrong mto_numbers cannot be
-- recovered (the contamination already overwrote the original values). The
-- accompanying scripts/cleanup_subcontract_contamination.py re-syncs from
-- Kingdee for the affected customer cluster after the migration applies.

-- Step 1: Create new table with corrected UNIQUE constraint
CREATE TABLE cached_subcontracting_orders_new (
    id INTEGER PRIMARY KEY,
    bill_no TEXT NOT NULL,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    order_qty REAL,
    stock_in_qty REAL,
    no_stock_in_qty REAL,
    aux_prop_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id)
);

-- Step 2: Copy data. INSERT OR IGNORE: if any pre-existing duplicates somehow
-- exist under the same (bill_no, mto_number, material_code, aux_prop_id), keep
-- the first one (the new constraint is strictly tighter than the old, so this
-- is purely a safety net — under the old constraint, duplicates with same
-- mto_number were already impossible).
INSERT OR IGNORE INTO cached_subcontracting_orders_new
    (id, bill_no, mto_number, material_code, order_qty, stock_in_qty,
     no_stock_in_qty, aux_prop_id, raw_data, synced_at)
SELECT id, bill_no, mto_number, material_code, order_qty, stock_in_qty,
       no_stock_in_qty, aux_prop_id, raw_data, synced_at
FROM cached_subcontracting_orders;

-- Step 3: Drop old table (cascades indexes auto-attached to the table)
DROP TABLE cached_subcontracting_orders;

-- Step 4: Rename new → final
ALTER TABLE cached_subcontracting_orders_new RENAME TO cached_subcontracting_orders;

-- Step 5: Recreate the secondary indexes that the original CREATE TABLE
-- statement in schema.sql defined. Without these, queries that filter by
-- mto_number / material_code lose their index path.
CREATE INDEX IF NOT EXISTS idx_subo_mto
    ON cached_subcontracting_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_subo_material
    ON cached_subcontracting_orders(material_code);
CREATE INDEX IF NOT EXISTS idx_subo_mto_synced
    ON cached_subcontracting_orders(mto_number, synced_at DESC);
