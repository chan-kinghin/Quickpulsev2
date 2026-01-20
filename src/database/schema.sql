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
    status TEXT,       -- Denormalized from raw_data for faster access
    create_date TEXT,  -- Denormalized from raw_data for faster access
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_po_mto ON cached_production_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_po_synced ON cached_production_orders(synced_at);
CREATE INDEX IF NOT EXISTS idx_po_material ON cached_production_orders(material_code);
-- Compound index for common query pattern: filter by mto_number, sort by synced_at
CREATE INDEX IF NOT EXISTS idx_po_mto_synced ON cached_production_orders(mto_number, synced_at DESC);

-- Production BOM cache
CREATE TABLE IF NOT EXISTS cached_production_bom (
    id INTEGER PRIMARY KEY,
    mo_bill_no TEXT NOT NULL,
    mto_number TEXT,         -- Denormalized from raw_data for indexed lookups
    material_code TEXT NOT NULL,
    material_name TEXT,
    specification TEXT,      -- Denormalized from raw_data
    aux_attributes TEXT,     -- Denormalized from raw_data
    aux_prop_id INTEGER DEFAULT 0,  -- Denormalized from raw_data
    material_type INTEGER,   -- 1=自制, 2=外购, 3=委外
    need_qty REAL,
    picked_qty REAL,
    no_picked_qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bom_mo ON cached_production_bom(mo_bill_no);
CREATE INDEX IF NOT EXISTS idx_bom_mto ON cached_production_bom(mto_number);
CREATE INDEX IF NOT EXISTS idx_bom_material ON cached_production_bom(material_code);
CREATE INDEX IF NOT EXISTS idx_bom_type ON cached_production_bom(material_type);
-- Compound index for common query pattern
CREATE INDEX IF NOT EXISTS idx_bom_mo_synced ON cached_production_bom(mo_bill_no, synced_at DESC);

-- Purchase orders cache (外购件)
CREATE TABLE IF NOT EXISTS cached_purchase_orders (
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
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_puro_mto ON cached_purchase_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_puro_material ON cached_purchase_orders(material_code);
CREATE INDEX IF NOT EXISTS idx_puro_mto_synced ON cached_purchase_orders(mto_number, synced_at DESC);

-- Subcontracting orders cache (委外件)
CREATE TABLE IF NOT EXISTS cached_subcontracting_orders (
    id INTEGER PRIMARY KEY,
    bill_no TEXT NOT NULL,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    order_qty REAL,
    stock_in_qty REAL,
    no_stock_in_qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_subo_mto ON cached_subcontracting_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_subo_material ON cached_subcontracting_orders(material_code);
CREATE INDEX IF NOT EXISTS idx_subo_mto_synced ON cached_subcontracting_orders(mto_number, synced_at DESC);

-- Production receipts cache (自制件入库)
CREATE TABLE IF NOT EXISTS cached_production_receipts (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    real_qty REAL,
    must_qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_prdr_mto ON cached_production_receipts(mto_number);
CREATE INDEX IF NOT EXISTS idx_prdr_mto_synced ON cached_production_receipts(mto_number, synced_at DESC);

-- Purchase receipts cache (外购/委外入库)
CREATE TABLE IF NOT EXISTS cached_purchase_receipts (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    real_qty REAL,
    must_qty REAL,
    bill_type_number TEXT,  -- RKD01_SYS=外购, RKD02_SYS=委外
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_purr_mto ON cached_purchase_receipts(mto_number);
CREATE INDEX IF NOT EXISTS idx_purr_type ON cached_purchase_receipts(bill_type_number);
CREATE INDEX IF NOT EXISTS idx_purr_mto_synced ON cached_purchase_receipts(mto_number, synced_at DESC);

-- Material picking cache (生产领料)
CREATE TABLE IF NOT EXISTS cached_material_picking (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    app_qty REAL,
    actual_qty REAL,
    ppbom_bill_no TEXT,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pick_mto ON cached_material_picking(mto_number);
CREATE INDEX IF NOT EXISTS idx_pick_mto_synced ON cached_material_picking(mto_number, synced_at DESC);

-- Sales delivery cache (销售出库)
CREATE TABLE IF NOT EXISTS cached_sales_delivery (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    material_code TEXT NOT NULL,
    real_qty REAL,
    must_qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sald_mto ON cached_sales_delivery(mto_number);
CREATE INDEX IF NOT EXISTS idx_sald_mto_synced ON cached_sales_delivery(mto_number, synced_at DESC);

-- Sales orders cache (销售订单 - 客户/交期信息)
CREATE TABLE IF NOT EXISTS cached_sales_orders (
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
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_salo_mto ON cached_sales_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_salo_material ON cached_sales_orders(material_code);
CREATE INDEX IF NOT EXISTS idx_salo_mto_synced ON cached_sales_orders(mto_number, synced_at DESC);

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
