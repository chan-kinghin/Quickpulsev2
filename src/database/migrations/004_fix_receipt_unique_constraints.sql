-- Migration 004: Fix receipt unique constraints that collapse multiple receipt documents
--
-- Problem: The UNIQUE indexes on receipt tables used (mto_number, material_code, aux_prop_id)
-- as the key, which collapses multiple receipt documents for the same variant into one row.
-- The ON CONFLICT ... DO UPDATE SET real_qty=excluded.real_qty OVERWRITES instead of
-- accumulating, causing dramatic undercount (e.g., 5,820 instead of 21,540).
--
-- Fix: Add bill_no column and include it in the UNIQUE constraint so each receipt
-- document gets its own row. The aggregation layer (_sum_by_material_and_aux) already
-- correctly accumulates multiple records with +=.
--
-- Affected tables:
--   cached_production_receipts  (PRD_INSTOCK)
--   cached_sales_delivery       (SAL_OUTSTOCK)
--   cached_purchase_receipts    (STK_InStock)

-- Step 1: Add bill_no column to each affected table
ALTER TABLE cached_production_receipts ADD COLUMN bill_no TEXT DEFAULT '';
ALTER TABLE cached_sales_delivery ADD COLUMN bill_no TEXT DEFAULT '';
ALTER TABLE cached_purchase_receipts ADD COLUMN bill_no TEXT DEFAULT '';

-- Step 2: Drop the harmful UNIQUE indexes
DROP INDEX IF EXISTS idx_prdr_unique;
DROP INDEX IF EXISTS idx_sald_unique;
DROP INDEX IF EXISTS idx_purr_unique;

-- Step 3: Create new UNIQUE indexes that include bill_no
-- This allows multiple receipt documents per variant while preventing true duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_prdr_unique
ON cached_production_receipts(bill_no, mto_number, material_code, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sald_unique
ON cached_sales_delivery(bill_no, mto_number, material_code, aux_prop_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_purr_unique
ON cached_purchase_receipts(bill_no, mto_number, material_code, bill_type_number);
