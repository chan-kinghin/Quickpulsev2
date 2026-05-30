-- Migration 018: Add bill_no to UNIQUE on cached_material_picking
--
-- Problem (bug-patterns.md #5 recurrence): cached_material_picking was the only
-- document cache table whose UNIQUE key omitted the document bill_no. The key was
-- (mto_number, material_code, ppbom_bill_no, aux_prop_id) and the upsert in
-- sync_service.py:_upsert_material_picking_no_commit did DELETE-by-mto then
-- `ON CONFLICT(... same 4 ...) DO UPDATE`. When one (mto, material, ppbom, aux) is
-- picked across MULTIPLE 领料单 (PRD_PickMtrl FBillNo) — common for high-volume
-- packaging materials — the in-memory dedup + ON CONFLICT kept only the LAST
-- document's row, so SUM(actual_qty) silently UNDER-counted vs live Kingdee.
--
-- Live proof (probed 2026-05-30): DK261025S / 03.11.002 = 3 live pick rows across
-- 2 bills, over = 81,360; the cache held over = 43,280. The 3 rows are distinct
-- under (bill_no, ppbom_bill_no, aux_prop_id) with ZERO residual collisions, so
-- adding bill_no fully un-collapses them (no entry-seq column needed).
--
-- Template: mirrors migration 010 (cached_production_orders) / 009
-- (cached_subcontracting_orders) — same Pattern 5 shape. The 12-step rebuild is
-- required because SQLite cannot DROP an inline-UNIQUE autoindex; a rebuild is the
-- only way to replace the table-level UNIQUE that fresh DBs get from schema.sql.
-- Runs AFTER migration 014 (which creates the narrow idx_pick_unique_v2): the
-- DROP TABLE below removes that narrow index, and 014 is already recorded so it
-- never re-runs.
--
-- Data preservation: rows already collapsed under the old key cannot be recovered
-- here (only the last bill survived each group). bill_no is backfilled from
-- raw_data for the surviving rows; a re-sync re-populates the full grain.

-- Step 1: Create new table with corrected UNIQUE constraint. Column order, types,
-- and defaults match the post-migration shape in schema.sql exactly.
CREATE TABLE cached_material_picking_new (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    bill_no TEXT,
    app_qty REAL,
    actual_qty REAL,
    ppbom_bill_no TEXT,
    aux_prop_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, ppbom_bill_no, aux_prop_id)
);

-- Step 2: Copy data, backfilling bill_no from raw_data JSON (works on legacy DBs
-- that lack a bill_no column AND on fresh DBs that already have one — the
-- json_extract re-derives the same value). COALESCE to '' to match the sync
-- writer (getattr(r,'bill_no','') or ''). INSERT OR IGNORE is a safety net: the
-- new key is strictly tighter than the old, so existing rows (already unique
-- under the old key) stay unique under the new one — no rows dropped here.
INSERT OR IGNORE INTO cached_material_picking_new
    (id, mto_number, material_code, bill_no, app_qty, actual_qty,
     ppbom_bill_no, aux_prop_id, raw_data, synced_at)
SELECT id, mto_number, material_code,
       COALESCE(json_extract(raw_data, '$.bill_no'), ''),
       app_qty, actual_qty, ppbom_bill_no, aux_prop_id, raw_data, synced_at
FROM cached_material_picking;

-- Step 3: Drop old table (cascades its indexes, including the legacy narrow
-- idx_pick_unique_v2 from migration 014).
DROP TABLE cached_material_picking;

-- Step 4: Rename new -> final.
ALTER TABLE cached_material_picking_new RENAME TO cached_material_picking;

-- Step 5: Recreate the secondary indexes from schema.sql:156-158. The unique
-- constraint is carried by the inline UNIQUE above (autoindex) — do NOT recreate
-- any narrow unique index here.
CREATE INDEX IF NOT EXISTS idx_pick_mto
    ON cached_material_picking(mto_number);
CREATE INDEX IF NOT EXISTS idx_pick_mto_synced
    ON cached_material_picking(mto_number, synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_pick_material_aux
    ON cached_material_picking(material_code, aux_prop_id);
