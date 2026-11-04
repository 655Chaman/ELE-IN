-- Migration 112: Cold Email Reputation, Multi-ESP Webhooks & Deliverability Hardening
-- Pillar 4: ESP Webhooks, Peer Warmup Swarm, Tracking SSL, & Domain Burnout Circuit Breaker

CREATE TABLE IF NOT EXISTS esp_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,
    event_id TEXT,
    message_id TEXT,
    event_type TEXT NOT NULL,
    email TEXT,
    workspace_id TEXT,
    payload JSONB,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_esp_event UNIQUE (provider, event_id)
);

CREATE INDEX IF NOT EXISTS idx_esp_webhook_events_email 
    ON esp_webhook_events(email);

CREATE INDEX IF NOT EXISTS idx_esp_webhook_events_msg 
    ON esp_webhook_events(provider, message_id);

CREATE TABLE IF NOT EXISTS warmup_swarm_exchanges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    sender_inbox_id TEXT NOT NULL,
    recipient_inbox_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    subject TEXT,
    stage TEXT NOT NULL DEFAULT 'SENT',
    simulated_deliverability_status TEXT DEFAULT 'INBOX',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_warmup_swarm_sender 
    ON warmup_swarm_exchanges(sender_inbox_id);

CREATE INDEX IF NOT EXISTS idx_warmup_swarm_recipient 
    ON warmup_swarm_exchanges(recipient_inbox_id);

-- Add domain burnout and tracking SSL columns to sender_inboxes / mailboxes if not exists
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sender_inboxes') THEN
        ALTER TABLE sender_inboxes ADD COLUMN IF NOT EXISTS tracking_domain TEXT;
        ALTER TABLE sender_inboxes ADD COLUMN IF NOT EXISTS ssl_verified BOOLEAN DEFAULT FALSE;
        ALTER TABLE sender_inboxes ADD COLUMN IF NOT EXISTS ssl_verified_at TIMESTAMPTZ;
        ALTER TABLE sender_inboxes ADD COLUMN IF NOT EXISTS domain_burnout_status TEXT DEFAULT 'HEALTHY';
        ALTER TABLE sender_inboxes ADD COLUMN IF NOT EXISTS domain_burnout_until TIMESTAMPTZ;
    END IF;
END $$;
