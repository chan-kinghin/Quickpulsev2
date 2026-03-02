-- Migration 005: Add aux_prop_id to cached_purchase_receipts and cached_subcontracting_orders
--
-- These tables were missing aux_prop_id, causing variant-aware matching
-- to silently fall back to defaults (aux_prop_id=0) on the cache path.
--
-- NOTE: This migration is handled specially in connection.py because
-- SQLite doesn't support ALTER TABLE ADD COLUMN IF NOT EXISTS.
-- On fresh databases, schema.sql already includes these columns.

ALTER TABLE cached_purchase_receipts ADD COLUMN aux_prop_id INTEGER DEFAULT 0;
ALTER TABLE cached_subcontracting_orders ADD COLUMN aux_prop_id INTEGER DEFAULT 0;
