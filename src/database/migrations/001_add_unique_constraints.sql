-- Migration 001: Add unique constraints for UPSERT support
-- These constraints enable ON CONFLICT ... DO UPDATE patterns
-- to replace delete-then-insert, reducing database I/O by ~50%

-- cached_production_bom: Unique on (mo_bill_no, material_code, aux_prop_id)
-- Same material can appear multiple times with different aux properties
CREATE UNIQUE INDEX IF NOT EXISTS idx_bom_unique
ON cached_production_bom(mo_bill_no, material_code, aux_prop_id);

-- cached_purchase_orders: Unique on bill line
CREATE UNIQUE INDEX IF NOT EXISTS idx_puro_unique
ON cached_purchase_orders(bill_no, material_code, aux_prop_id);

-- cached_subcontracting_orders: Unique on bill line
CREATE UNIQUE INDEX IF NOT EXISTS idx_subo_unique
ON cached_subcontracting_orders(bill_no, material_code);

-- cached_production_receipts: Aggregated by MTO + material
CREATE UNIQUE INDEX IF NOT EXISTS idx_prdr_unique
ON cached_production_receipts(mto_number, material_code);

-- cached_purchase_receipts: Aggregated by MTO + material + type
CREATE UNIQUE INDEX IF NOT EXISTS idx_purr_unique
ON cached_purchase_receipts(mto_number, material_code, bill_type_number);

-- cached_material_picking: Unique on picking line
CREATE UNIQUE INDEX IF NOT EXISTS idx_pick_unique
ON cached_material_picking(mto_number, material_code, ppbom_bill_no);

-- cached_sales_delivery: Aggregated by MTO + material
CREATE UNIQUE INDEX IF NOT EXISTS idx_sald_unique
ON cached_sales_delivery(mto_number, material_code);

-- cached_sales_orders: Unique on bill + MTO + material + aux variant
-- Multiple lines per sales order can have same MTO but different materials/variants
CREATE UNIQUE INDEX IF NOT EXISTS idx_salo_unique
ON cached_sales_orders(bill_no, mto_number, material_code, aux_prop_id);
