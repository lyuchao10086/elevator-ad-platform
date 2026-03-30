-- Campaign core tables for strategy storage / versioning / publish logs.
-- This script is backward compatible with existing API behavior.

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
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('draft', 'published', 'archived')),
    CHECK (end_at IS NULL OR start_at IS NULL OR end_at > start_at)
);

CREATE INDEX IF NOT EXISTS idx_campaigns_status
ON campaigns(status);

CREATE INDEX IF NOT EXISTS idx_campaigns_updated_at
ON campaigns(updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_campaigns_version
ON campaigns(version);

CREATE INDEX IF NOT EXISTS idx_campaigns_created_at
ON campaigns(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_campaigns_target_devices_gin
ON campaigns USING gin (target_device_groups);

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

CREATE INDEX IF NOT EXISTS idx_campaign_versions_created_at
ON campaign_versions(created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_publish_logs_failed
ON campaign_publish_logs(campaign_id, ok, created_at DESC);

CREATE TABLE IF NOT EXISTS campaign_retry_batches (
    id BIGSERIAL PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    source_batch_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, source_batch_id)
);

CREATE INDEX IF NOT EXISTS idx_retry_batches_campaign_time
ON campaign_retry_batches(campaign_id, created_at DESC);
