-- Migration 008: Drop stale unique indexes from migration 001
--
-- Migration 001 created unique indexes with fewer columns than
-- schema.sql's table-level UNIQUE constraints. On fresh databases,
-- both run, creating TWO conflicting unique constraints.
-- schema.sql is the source of truth; these old indexes must go.

DROP INDEX IF EXISTS idx_bom_unique;
DROP INDEX IF EXISTS idx_puro_unique;
DROP INDEX IF EXISTS idx_subo_unique;
DROP INDEX IF EXISTS idx_prdr_unique;
DROP INDEX IF EXISTS idx_purr_unique;
DROP INDEX IF EXISTS idx_pick_unique;
DROP INDEX IF EXISTS idx_sald_unique;
DROP INDEX IF EXISTS idx_salo_unique;
