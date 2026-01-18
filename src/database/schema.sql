-- Enable WAL mode for better concurrent read/write performance
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

-- Production orders cache
CREATE TABLE IF NOT EXISTS cached_production_orders (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    bill_no TEXT NOT NULL UNIQUE,
    workshop TEXT,
    material_code TEXT,
    material_name TEXT,
    specification TEXT,
    aux_attributes TEXT,
    qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_po_mto ON cached_production_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_po_synced ON cached_production_orders(synced_at);
CREATE INDEX IF NOT EXISTS idx_po_material ON cached_production_orders(material_code);

-- Production BOM cache
CREATE TABLE IF NOT EXISTS cached_production_bom (
    id INTEGER PRIMARY KEY,
    mo_bill_no TEXT NOT NULL,
    material_code TEXT NOT NULL,
    material_name TEXT,
    material_type INTEGER,  -- 1=自制, 2=外购, 3=委外
    need_qty REAL,
    picked_qty REAL,
    no_picked_qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bom_mo ON cached_production_bom(mo_bill_no);
CREATE INDEX IF NOT EXISTS idx_bom_material ON cached_production_bom(material_code);
CREATE INDEX IF NOT EXISTS idx_bom_type ON cached_production_bom(material_type);

-- Sync history
CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT NOT NULL,  -- success/error
    days_back INTEGER,
    records_synced INTEGER,
    error_message TEXT
);
