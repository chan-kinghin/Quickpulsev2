-- Migration 019: entry-line grain (entry_id) for the seven document cache tables
--
-- Problem (bug-patterns.md #5, SIXTH occurrence — audit 2026-06-10): every
-- document cache table keyed rows at document grain (bill_no, mto, material,
-- [bill_type/ppbom,] aux), but one Kingdee document can legitimately carry
-- MULTIPLE entry lines with the SAME (material, aux). The in-memory dedup +
-- ON CONFLICT then keeps exactly one line per key, silently under-counting.
--
-- Live proof (probed 2026-06-10, /tmp/probe_fentryid_variants_20260610.py):
--   cached_sales_delivery    XS26050001: aux=196059 lines 186+55+54 → cache kept one (real 超发 hidden)
--   cached_sales_orders      XSDD2605036: qty=300 + qty=3 same (material,aux) → 3-line dropped (phantom 超发)
--   cached_material_picking  LL26041108 / 05.02.04.033 / aux=106244: 1021+579 → kept 579
--                            (migration 018's "zero residual collisions" claim was empirically false:
--                            bill_no alone is not sufficient when ONE 领料单 repeats a key)
--   cached_purchase_receipts CG26041724 / 23.12.01: 39+1798+762+14(+12 more) → kept 14 of 2613
--   cached_purchase_orders / cached_production_receipts: same shape (feed agent-chat SQL).
--   cached_subcontracting_orders (probed 2026-06-10,
--                            /tmp/probe_subreqorder_entryid_20260610.py): 15 live
--                            colliding groups, e.g. WW25100020 / 08.27.001:
--                            lines 1200+38800 → cache kept one (委外订单 under-count).
--                            NOTE: this form's entry id is FTreeEntity_FEntryID
--                            (FEntity_/FSubReqEntry_ variants rejected: 字段不存在).
--
-- Fix: add entry_id (Kingdee FEntryID, requested via the entity-prefixed
-- FieldKey per form — see factory.py) and append it to each UNIQUE.
--
-- Template: migration 018. The table rebuild is required because SQLite cannot
-- alter an inline UNIQUE. DROP TABLE also removes the narrow idx_*_v2 unique
-- indexes from migration 014 for these tables (they enforce the OLD document
-- grain and would reject the second entry line); do NOT recreate them — the
-- inline UNIQUE below carries the constraint on both legacy and fresh DBs.
--
-- Data preservation: lines already collapsed under the old key cannot be
-- recovered here. entry_id is backfilled from raw_data JSON where present
-- (rows synced before this migration lack it → 0). Note the backfill is NOT
-- strictly lossless either: rows whose backfilled entry_id COALESCEs to the
-- same value (typically 0) under an identical old key collapse to one
-- (key, entry_id) and the extras are INSERT OR IGNOREd. Both gaps are
-- repaired by the FULL 365-day re-sync that is REQUIRED after deploy to
-- repopulate the entry grain (same flow as migration 018 / commit 9c5fe58).

-- ============================================================================
-- 1/7 cached_purchase_orders
-- ============================================================================
CREATE TABLE cached_purchase_orders_new (
    id INTEGER PRIMARY KEY,
    bill_no TEXT NOT NULL,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    material_name TEXT,
    specification TEXT,
    aux_attributes TEXT,
    aux_prop_id INTEGER DEFAULT 0,
    order_qty REAL,
    stock_in_qty REAL,
    remain_stock_in_qty REAL,
    entry_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id, entry_id)
);
-- INSERT OR IGNORE is mostly a safety net: the new key is strictly wider than
-- the old, so rows unique under the old key normally stay unique. The one
-- exception: rows whose old key already collided AND whose backfilled
-- entry_id COALESCEs to the same value (e.g. both 0, pre-019 raw_data) land
-- on the same (key, entry_id) and the extras ARE dropped here — see the
-- "Data preservation" note above; the mandatory full re-sync repairs them.
INSERT OR IGNORE INTO cached_purchase_orders_new
    (id, bill_no, mto_number, material_code, material_name, specification,
     aux_attributes, aux_prop_id, order_qty, stock_in_qty, remain_stock_in_qty,
     entry_id, raw_data, synced_at)
SELECT id, bill_no, mto_number, material_code, material_name, specification,
       aux_attributes, aux_prop_id, order_qty, stock_in_qty, remain_stock_in_qty,
       COALESCE(json_extract(raw_data, '$.entry_id'), 0),
       raw_data, synced_at
FROM cached_purchase_orders;
DROP TABLE cached_purchase_orders;
ALTER TABLE cached_purchase_orders_new RENAME TO cached_purchase_orders;
CREATE INDEX IF NOT EXISTS idx_puro_mto ON cached_purchase_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_puro_material ON cached_purchase_orders(material_code);
CREATE INDEX IF NOT EXISTS idx_puro_mto_synced ON cached_purchase_orders(mto_number, synced_at DESC);

-- ============================================================================
-- 2/7 cached_production_receipts
-- ============================================================================
CREATE TABLE cached_production_receipts_new (
    id INTEGER PRIMARY KEY,
    bill_no TEXT DEFAULT '',
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    real_qty REAL,
    must_qty REAL,
    aux_prop_id INTEGER DEFAULT 0,
    entry_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id, entry_id)
);
INSERT OR IGNORE INTO cached_production_receipts_new
    (id, bill_no, mto_number, material_code, real_qty, must_qty,
     aux_prop_id, entry_id, raw_data, synced_at)
SELECT id, bill_no, mto_number, material_code, real_qty, must_qty,
       aux_prop_id, COALESCE(json_extract(raw_data, '$.entry_id'), 0),
       raw_data, synced_at
FROM cached_production_receipts;
DROP TABLE cached_production_receipts;
ALTER TABLE cached_production_receipts_new RENAME TO cached_production_receipts;
CREATE INDEX IF NOT EXISTS idx_prdr_mto ON cached_production_receipts(mto_number);
CREATE INDEX IF NOT EXISTS idx_prdr_mto_synced ON cached_production_receipts(mto_number, synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_prdr_material_aux ON cached_production_receipts(material_code, aux_prop_id);

-- ============================================================================
-- 3/7 cached_purchase_receipts
-- ============================================================================
CREATE TABLE cached_purchase_receipts_new (
    id INTEGER PRIMARY KEY,
    bill_no TEXT DEFAULT '',
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    real_qty REAL,
    must_qty REAL,
    bill_type_number TEXT,
    aux_prop_id INTEGER DEFAULT 0,
    entry_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, bill_type_number, aux_prop_id, entry_id)
);
INSERT OR IGNORE INTO cached_purchase_receipts_new
    (id, bill_no, mto_number, material_code, real_qty, must_qty,
     bill_type_number, aux_prop_id, entry_id, raw_data, synced_at)
SELECT id, bill_no, mto_number, material_code, real_qty, must_qty,
       bill_type_number, aux_prop_id,
       COALESCE(json_extract(raw_data, '$.entry_id'), 0),
       raw_data, synced_at
FROM cached_purchase_receipts;
DROP TABLE cached_purchase_receipts;
ALTER TABLE cached_purchase_receipts_new RENAME TO cached_purchase_receipts;
CREATE INDEX IF NOT EXISTS idx_purr_mto ON cached_purchase_receipts(mto_number);
CREATE INDEX IF NOT EXISTS idx_purr_type ON cached_purchase_receipts(bill_type_number);
CREATE INDEX IF NOT EXISTS idx_purr_mto_synced ON cached_purchase_receipts(mto_number, synced_at DESC);

-- ============================================================================
-- 4/7 cached_material_picking
-- ============================================================================
CREATE TABLE cached_material_picking_new (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    bill_no TEXT,
    app_qty REAL,
    actual_qty REAL,
    ppbom_bill_no TEXT,
    aux_prop_id INTEGER DEFAULT 0,
    entry_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, ppbom_bill_no, aux_prop_id, entry_id)
);
INSERT OR IGNORE INTO cached_material_picking_new
    (id, mto_number, material_code, bill_no, app_qty, actual_qty,
     ppbom_bill_no, aux_prop_id, entry_id, raw_data, synced_at)
SELECT id, mto_number, material_code, bill_no, app_qty, actual_qty,
       ppbom_bill_no, aux_prop_id,
       COALESCE(json_extract(raw_data, '$.entry_id'), 0),
       raw_data, synced_at
FROM cached_material_picking;
DROP TABLE cached_material_picking;
ALTER TABLE cached_material_picking_new RENAME TO cached_material_picking;
CREATE INDEX IF NOT EXISTS idx_pick_mto ON cached_material_picking(mto_number);
CREATE INDEX IF NOT EXISTS idx_pick_mto_synced ON cached_material_picking(mto_number, synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_pick_material_aux ON cached_material_picking(material_code, aux_prop_id);

-- ============================================================================
-- 5/7 cached_sales_delivery
-- ============================================================================
CREATE TABLE cached_sales_delivery_new (
    id INTEGER PRIMARY KEY,
    bill_no TEXT DEFAULT '',
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    real_qty REAL,
    must_qty REAL,
    aux_prop_id INTEGER DEFAULT 0,
    entry_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id, entry_id)
);
INSERT OR IGNORE INTO cached_sales_delivery_new
    (id, bill_no, mto_number, material_code, real_qty, must_qty,
     aux_prop_id, entry_id, raw_data, synced_at)
SELECT id, bill_no, mto_number, material_code, real_qty, must_qty,
       aux_prop_id, COALESCE(json_extract(raw_data, '$.entry_id'), 0),
       raw_data, synced_at
FROM cached_sales_delivery;
DROP TABLE cached_sales_delivery;
ALTER TABLE cached_sales_delivery_new RENAME TO cached_sales_delivery;
CREATE INDEX IF NOT EXISTS idx_sald_mto ON cached_sales_delivery(mto_number);
CREATE INDEX IF NOT EXISTS idx_sald_mto_synced ON cached_sales_delivery(mto_number, synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_sald_material_aux ON cached_sales_delivery(material_code, aux_prop_id);

-- ============================================================================
-- 6/7 cached_sales_orders
-- ============================================================================
CREATE TABLE cached_sales_orders_new (
    id INTEGER PRIMARY KEY,
    bill_no TEXT NOT NULL,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    material_name TEXT,
    specification TEXT,
    aux_attributes TEXT,
    aux_prop_id INTEGER DEFAULT 0,
    customer_name TEXT,
    delivery_date TEXT,
    qty REAL DEFAULT 0,
    bom_short_name TEXT DEFAULT '',
    material_group_name TEXT DEFAULT '',
    close_status TEXT DEFAULT 'A',
    entry_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id, entry_id)
);
INSERT OR IGNORE INTO cached_sales_orders_new
    (id, bill_no, mto_number, material_code, material_name, specification,
     aux_attributes, aux_prop_id, customer_name, delivery_date, qty,
     bom_short_name, material_group_name, close_status, entry_id,
     raw_data, synced_at)
SELECT id, bill_no, mto_number, material_code, material_name, specification,
       aux_attributes, aux_prop_id, customer_name, delivery_date, qty,
       bom_short_name, material_group_name, close_status,
       COALESCE(json_extract(raw_data, '$.entry_id'), 0),
       raw_data, synced_at
FROM cached_sales_orders;
DROP TABLE cached_sales_orders;
ALTER TABLE cached_sales_orders_new RENAME TO cached_sales_orders;
CREATE INDEX IF NOT EXISTS idx_salo_mto ON cached_sales_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_salo_material ON cached_sales_orders(material_code);
CREATE INDEX IF NOT EXISTS idx_salo_mto_synced ON cached_sales_orders(mto_number, synced_at DESC);

-- ============================================================================
-- 7/7 cached_subcontracting_orders
-- ============================================================================
CREATE TABLE cached_subcontracting_orders_new (
    id INTEGER PRIMARY KEY,
    bill_no TEXT NOT NULL,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    order_qty REAL,
    stock_in_qty REAL,
    no_stock_in_qty REAL,
    aux_prop_id INTEGER DEFAULT 0,
    entry_id INTEGER DEFAULT 0,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- mto_number stays in the key (bug-patterns.md #5 Bug 7, 2026-04-26);
    -- entry_id appended for the entry-line grain (this migration).
    UNIQUE(bill_no, mto_number, material_code, aux_prop_id, entry_id)
);
INSERT OR IGNORE INTO cached_subcontracting_orders_new
    (id, bill_no, mto_number, material_code, order_qty, stock_in_qty,
     no_stock_in_qty, aux_prop_id, entry_id, raw_data, synced_at)
SELECT id, bill_no, mto_number, material_code, order_qty, stock_in_qty,
       no_stock_in_qty, aux_prop_id,
       COALESCE(json_extract(raw_data, '$.entry_id'), 0),
       raw_data, synced_at
FROM cached_subcontracting_orders;
DROP TABLE cached_subcontracting_orders;
ALTER TABLE cached_subcontracting_orders_new RENAME TO cached_subcontracting_orders;
CREATE INDEX IF NOT EXISTS idx_subo_mto ON cached_subcontracting_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_subo_material ON cached_subcontracting_orders(material_code);
CREATE INDEX IF NOT EXISTS idx_subo_mto_synced ON cached_subcontracting_orders(mto_number, synced_at DESC);
