-- 014: Heal legacy DBs that lost their unique constraint after migration 008.
--
-- Background: schema.sql first added inline `UNIQUE(...)` to the cached_* tables
-- in commit d2d9172 (2026-03-16). Migration 008 (2026-03-20) then DROPPED the
-- now-redundant unique INDEXES created by migration 001/004, assuming the new
-- inline UNIQUE in schema.sql would carry the constraint.
--
-- That assumption only holds for DBs created AFTER 2026-03-16. SQLite does NOT
-- retroactively add table-level UNIQUE to a CREATE TABLE that was executed
-- before that constraint was added. Result: any DB created before 2026-03-16
-- and later upgraded past migration 008 lost ALL unique constraints on these
-- tables, silently breaking every `INSERT … ON CONFLICT … DO UPDATE` upsert
-- the sync writer relies on.
--
-- The error is ugly but predictable:
--   "ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint"
--
-- Symptoms users see: stale cache (last successful sync stuck) while the
-- dashboard happily serves old data and the auto-sync scheduler logs WARNINGs
-- nobody reads.
--
-- This migration restores the matching unique INDEXES idempotently. On modern
-- DBs (CREATE TABLE already carries the inline UNIQUE) the `IF NOT EXISTS`
-- skips them — SQLite collapses to the implicit autoindex. On legacy DBs the
-- indexes are recreated. Either way: upsert recovers.
--
-- All `_v2` suffixes avoid colliding with the index names migration 008 dropped
-- (in case anyone re-runs 008 in the future).

CREATE UNIQUE INDEX IF NOT EXISTS idx_po_unique_v2
    ON cached_production_orders(bill_no, mto_number, material_code, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bom_unique_v2
    ON cached_production_bom(mo_bill_no, material_code, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_puro_unique_v2
    ON cached_purchase_orders(bill_no, mto_number, material_code, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subo_unique_v2
    ON cached_subcontracting_orders(bill_no, mto_number, material_code, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prdr_unique_v2
    ON cached_production_receipts(bill_no, mto_number, material_code, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_purr_unique_v2
    ON cached_purchase_receipts(bill_no, mto_number, material_code, bill_type_number, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pick_unique_v2
    ON cached_material_picking(mto_number, material_code, ppbom_bill_no, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sald_unique_v2
    ON cached_sales_delivery(bill_no, mto_number, material_code, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_salo_unique_v2
    ON cached_sales_orders(bill_no, mto_number, material_code, aux_prop_id);
