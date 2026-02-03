-- Migration 003: Add bom_short_name column to cached_sales_orders
--
-- Problem: The cached_sales_orders table was missing bom_short_name (BOM简称),
-- preventing the dashboard from displaying this field for finished goods (成品).
--
-- NOTE: This migration is handled specially in connection.py because:
-- 1. Fresh databases already have the column from schema.sql
-- 2. SQLite doesn't support "IF NOT EXISTS" for ALTER TABLE
--
-- The Python code checks if the column exists before running this SQL.

ALTER TABLE cached_sales_orders ADD COLUMN bom_short_name TEXT DEFAULT '';
