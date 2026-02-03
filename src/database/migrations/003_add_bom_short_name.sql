-- Migration 003: Add bom_short_name column to cached_sales_orders
--
-- Problem: The cached_sales_orders table was missing bom_short_name (BOM简称),
-- preventing the dashboard from displaying this field for finished goods (成品).
--
-- NOTE: If running on a fresh database, schema.sql already includes this column.
-- This migration handles upgrading existing databases.

-- Add bom_short_name column for BOM简称
ALTER TABLE cached_sales_orders ADD COLUMN bom_short_name TEXT DEFAULT '';
