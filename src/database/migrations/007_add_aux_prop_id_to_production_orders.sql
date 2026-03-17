-- Migration 007: Add aux_prop_id to cached_production_orders
--
-- This table was missing aux_prop_id on existing databases, causing
-- cache-path queries to fail with "no such column: aux_prop_id".
--
-- NOTE: This migration is handled specially in connection.py because
-- SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS.
-- On fresh databases, schema.sql already includes this column.

ALTER TABLE cached_production_orders ADD COLUMN aux_prop_id INTEGER DEFAULT 0;
