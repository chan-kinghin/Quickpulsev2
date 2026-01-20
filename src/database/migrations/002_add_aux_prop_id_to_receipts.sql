-- Migration 002: Add aux_prop_id to receipt tables for variant-aware matching
--
-- Problem: Cache tables for receipts and deliveries were missing aux_prop_id column,
-- causing variant-aware receipt matching to fail when using cached data.
--
-- The _sum_by_material_and_aux() function aggregates by (material_code, aux_prop_id),
-- but without aux_prop_id stored in cache, all records got aux_prop_id=0, breaking
-- lookups for sales orders with specific aux_prop_id values.

-- Add aux_prop_id to production receipts (PRD_INSTOCK cache)
ALTER TABLE cached_production_receipts ADD COLUMN aux_prop_id INTEGER DEFAULT 0;

-- Add aux_prop_id to sales delivery (SAL_OUTSTOCK cache)
ALTER TABLE cached_sales_delivery ADD COLUMN aux_prop_id INTEGER DEFAULT 0;

-- Create indexes for efficient variant-aware lookups
-- These support the (material_code, aux_prop_id) key used in _sum_by_material_and_aux()
CREATE INDEX IF NOT EXISTS idx_prdr_material_aux ON cached_production_receipts(material_code, aux_prop_id);
CREATE INDEX IF NOT EXISTS idx_sald_material_aux ON cached_sales_delivery(material_code, aux_prop_id);
