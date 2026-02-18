-- Schema mapping agent — persists mapping suggestions for review.

CREATE TABLE IF NOT EXISTS agent_mapping_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kingdee_field TEXT NOT NULL,
    semantic_role TEXT NOT NULL,
    material_class TEXT NOT NULL,
    confidence REAL NOT NULL,
    reasoning TEXT,
    match_signals TEXT,  -- JSON dict of signal_name -> score
    status TEXT DEFAULT 'pending',  -- pending / accepted / rejected
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ams_class
ON agent_mapping_suggestions(material_class);

CREATE INDEX IF NOT EXISTS idx_ams_status
ON agent_mapping_suggestions(status);
