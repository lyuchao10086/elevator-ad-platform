-- SQL: create materials table for control-plane
CREATE TABLE IF NOT EXISTS materials (
    material_id TEXT PRIMARY KEY,
    ad_id TEXT,
    file_name TEXT,
    oss_url TEXT,
    md5 TEXT,
    type TEXT,
    duration_sec INTEGER,
    size_bytes BIGINT,
    uploader_id TEXT,
    status TEXT,
    versions JSONB,
    tags JSONB,
    extra JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_materials_status ON materials(status);
CREATE INDEX IF NOT EXISTS idx_materials_ad_id ON materials(ad_id);
