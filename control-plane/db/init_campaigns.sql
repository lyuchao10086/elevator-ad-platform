-- Campaign core tables for strategy storage / versioning / publish logs.

CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    name TEXT,
    creator_id TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    schedule_json JSONB NOT NULL,
    target_device_groups JSONB,
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaigns_status
ON campaigns(status);

CREATE INDEX IF NOT EXISTS idx_campaigns_updated_at
ON campaigns(updated_at DESC);

CREATE TABLE IF NOT EXISTS campaign_versions (
    id BIGSERIAL PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    version TEXT NOT NULL,
    schedule_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, version)
);

CREATE INDEX IF NOT EXISTS idx_campaign_versions_campaign
ON campaign_versions(campaign_id, created_at DESC);

CREATE TABLE IF NOT EXISTS campaign_publish_logs (
    id BIGSERIAL PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    batch_id TEXT,
    version TEXT,
    device_id TEXT NOT NULL,
    ok BOOLEAN NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_publish_logs_campaign_time
ON campaign_publish_logs(campaign_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_publish_logs_batch
ON campaign_publish_logs(campaign_id, batch_id);
