-- Migration 113: Inbound Webhook Buffer & CRM Sync Dead Letter Queue Hardening
-- Pillar 6: Unified Omnichannel Inbox & CRM Sync Engine

CREATE TABLE IF NOT EXISTS inbound_webhook_buffer (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    platform_message_id TEXT NOT NULL,
    thread_id TEXT,
    lead_id TEXT,
    sender_name TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'staged',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    CONSTRAINT uq_inbound_buffer UNIQUE (platform, platform_message_id, workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_inbound_buffer_workspace_status 
    ON inbound_webhook_buffer(workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_inbound_buffer_thread 
    ON inbound_webhook_buffer(workspace_id, thread_id);

CREATE INDEX IF NOT EXISTS idx_inbound_buffer_lead 
    ON inbound_webhook_buffer(workspace_id, lead_id);

CREATE TABLE IF NOT EXISTS crm_sync_dead_letter_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    status_code INT,
    retry_count INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    next_retry_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crm_dlq_pending_retry 
    ON crm_sync_dead_letter_queue(status, next_retry_at) 
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_crm_dlq_workspace_provider 
    ON crm_sync_dead_letter_queue(workspace_id, provider, entity_id);
