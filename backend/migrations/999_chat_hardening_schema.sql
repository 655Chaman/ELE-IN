-- =========================================================================================
-- ELE-IN PLATFORM DEEP HARDENING: COMPLETE CHAT SCHEMA MIGRATION
-- Generated strictly from the 40 hardening steps executed in this session.
-- Safe, idempotent execution: uses IF NOT EXISTS and ADD COLUMN IF NOT EXISTS throughout.
-- =========================================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------------------
-- 1. WORKSPACES: TIER, CREDITS, AUTO-RECHARGE & LIMITS
-- -----------------------------------------------------------------------------------------
ALTER TABLE IF EXISTS workspaces
    ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'FREE',
    ADD COLUMN IF NOT EXISTS data_cleaning_credits BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS billing_status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS auto_recharge_settings JSONB DEFAULT '{
        "enabled": false,
        "threshold_credits": 100,
        "recharge_package_id": "credits_1000",
        "max_monthly_recharges": 5,
        "recharges_this_month": 0,
        "last_recharged_at": null
    }'::jsonb,
    ADD COLUMN IF NOT EXISTS webhook_signing_secret TEXT,
    ADD COLUMN IF NOT EXISTS sending_window JSONB DEFAULT '{
        "start": "09:00",
        "end": "18:00",
        "timezone": "UTC",
        "days": ["mon", "tue", "wed", "thu", "fri"]
    }'::jsonb;

-- -----------------------------------------------------------------------------------------
-- 2. BILLING TRANSACTIONS & CREDIT LEDGER
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS billing_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    provider TEXT NOT NULL, -- 'stripe', 'razorpay', 'lemonsqueezy', 'admin_grant', 'auto_recharge', 'reconciliation'
    provider_order_id TEXT,
    provider_payment_id TEXT,
    package_id TEXT,
    amount_cents BIGINT DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    credits_added BIGINT DEFAULT 0,
    status TEXT DEFAULT 'pending', -- 'pending', 'paid', 'failed', 'refunded', 'reconciled'
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS billing_transactions
    ADD COLUMN IF NOT EXISTS provider_order_id TEXT,
    ADD COLUMN IF NOT EXISTS provider_payment_id TEXT,
    ADD COLUMN IF NOT EXISTS package_id TEXT,
    ADD COLUMN IF NOT EXISTS amount_cents BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS credits_added BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_billing_txns_workspace_id ON billing_transactions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_billing_txns_provider_order ON billing_transactions(provider, provider_order_id);
CREATE INDEX IF NOT EXISTS idx_billing_txns_status ON billing_transactions(status);

-- -----------------------------------------------------------------------------------------
-- 3. OUTBOX NOTIFICATION QUEUE (EXPONENTIAL BACKOFF & DLQ)
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- 'notification.email', 'notification.slack', 'notification.in_app', 'notification.webhook'
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'pending', -- 'pending', 'sent', 'failed', 'suspended'
    deliver_at TIMESTAMPTZ DEFAULT NOW(),
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outbox_events_poll ON outbox_events(status, deliver_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_outbox_events_workspace ON outbox_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_events_dlq ON outbox_events(workspace_id, status) WHERE status IN ('failed', 'suspended');

-- -----------------------------------------------------------------------------------------
-- 4. SUPPRESSION LIST (DO-NOT-CONTACT / DNC ENGINE)
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppression_list (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    linkedin_url TEXT,
    email TEXT,
    domain TEXT,
    value TEXT, -- Canonical indexed lookup string
    reason TEXT DEFAULT 'manual_dnc',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_suppression_workspace ON suppression_list(workspace_id);
CREATE INDEX IF NOT EXISTS idx_suppression_li_url ON suppression_list(workspace_id, linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_suppression_email ON suppression_list(workspace_id, email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_suppression_domain ON suppression_list(workspace_id, domain) WHERE domain IS NOT NULL;

-- -----------------------------------------------------------------------------------------
-- 5. SENDER PODS & WORKSPACE LOAD BALANCING
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sender_pods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active', -- 'active', 'paused', 'depleted'
    rotation_strategy TEXT DEFAULT 'round_robin', -- 'round_robin', 'weighted', 'lowest_load'
    max_daily_invites_per_pod INTEGER DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sender_pod_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pod_id UUID NOT NULL REFERENCES sender_pods(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    weight INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_pod_account UNIQUE(pod_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_sender_pods_workspace ON sender_pods(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sender_pod_acc_lookup ON sender_pod_accounts(workspace_id, pod_id, is_active);

-- -----------------------------------------------------------------------------------------
-- 6. RESIDENTIAL PROXIES & SSRF /24 SUBNET ISOLATION
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS proxies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT,
    password TEXT,
    protocol TEXT DEFAULT 'http',
    country TEXT,
    exit_ip TEXT,
    latency_ms INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active', -- 'active', 'quarantined', 'failed'
    quarantined_until TIMESTAMPTZ,
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proxies_workspace ON proxies(workspace_id);
CREATE INDEX IF NOT EXISTS idx_proxies_active ON proxies(workspace_id, status) WHERE status = 'active';

-- Add proxy affiliation columns to accounts if missing
ALTER TABLE IF EXISTS accounts
    ADD COLUMN IF NOT EXISTS proxy_id UUID REFERENCES proxies(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS proxy_country TEXT,
    ADD COLUMN IF NOT EXISTS health_score NUMERIC DEFAULT 100,
    ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ;

-- -----------------------------------------------------------------------------------------
-- 7. WORKER HEARTBEAT & ACTION AUDIT LOG
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS worker_heartbeat (
    worker_id TEXT PRIMARY KEY,
    last_beat_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'alive',
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS action_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    execution_state_id TEXT,
    action_type TEXT NOT NULL, -- 'extension_execution', 'message_send', 'invite_send', 'enrichment'
    result TEXT NOT NULL, -- 'success', 'failed'
    error_detail TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_action_log_workspace ON action_log(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_log_exec_state ON action_log(execution_state_id);

-- -----------------------------------------------------------------------------------------
-- 8. SOCIAL SIGNAL RADAR & INTENT CACHE
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_signal_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    linkedin_url TEXT NOT NULL,
    signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_social_signal_lead UNIQUE(workspace_id, linkedin_url)
);

CREATE INDEX IF NOT EXISTS idx_social_signal_lookup ON social_signal_cache(workspace_id, linkedin_url, expires_at);

-- -----------------------------------------------------------------------------------------
-- 9. OUTBOUND WEBHOOKS & ROTATION SYSTEM
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    url TEXT NOT NULL,
    events TEXT[] NOT NULL DEFAULT '{}',
    signing_secret TEXT NOT NULL,
    status TEXT DEFAULT 'active', -- 'active', 'paused', 'disabled'
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    endpoint_id UUID REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'pending', -- 'pending', 'success', 'failed', 'dead_letter'
    attempts INTEGER DEFAULT 0,
    next_retry_at TIMESTAMPTZ DEFAULT NOW(),
    response_status INTEGER,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_poll ON webhook_deliveries(status, next_retry_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_endpoint ON webhook_deliveries(endpoint_id, created_at DESC);

-- -----------------------------------------------------------------------------------------
-- 10. AI REPLY APPROVAL QUEUE
-- -----------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    lead_id TEXT,
    account_id TEXT,
    exec_state_id TEXT,
    generated_reply TEXT,
    ai_draft TEXT,
    sender_name TEXT,
    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected', 'skipped'
    token TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_approval_queue_workspace ON approval_queue(workspace_id, status);

-- -----------------------------------------------------------------------------------------
-- 11. CAMPAIGN EXECUTION STATES: LEASE TOKENS & ORPHAN GUARDS
-- -----------------------------------------------------------------------------------------
ALTER TABLE IF EXISTS campaign_execution_states
    ADD COLUMN IF NOT EXISTS lease_token TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS error_reason TEXT,
    ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_ces_lease_token ON campaign_execution_states(lease_token) WHERE lease_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ces_next_run ON campaign_execution_states(workspace_id, status, next_run_at) WHERE status = 'pending';

-- -----------------------------------------------------------------------------------------
-- 12. LEADS: UNSUBSCRIBE & SUPPRESSION FLAGS
-- -----------------------------------------------------------------------------------------
ALTER TABLE IF EXISTS leads
    ADD COLUMN IF NOT EXISTS is_unsubscribed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS unsubscribed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_leads_workspace_email ON leads(workspace_id, email);
CREATE INDEX IF NOT EXISTS idx_leads_workspace_li ON leads(workspace_id, linkedin_url);

-- -----------------------------------------------------------------------------------------
-- 13. ATOMIC STORED PROCEDURES (RPC)
-- -----------------------------------------------------------------------------------------

-- Procedure: Atomically Grant Credits
CREATE OR REPLACE FUNCTION add_credits_safely(
    p_workspace_id TEXT,
    p_credits BIGINT,
    p_event_id TEXT DEFAULT NULL,
    p_provider TEXT DEFAULT 'manual'
) RETURNS BIGINT AS $$
DECLARE
    v_new_balance BIGINT;
BEGIN
    UPDATE workspaces
    SET data_cleaning_credits = COALESCE(data_cleaning_credits, 0) + p_credits
    WHERE id = p_workspace_id
    RETURNING data_cleaning_credits INTO v_new_balance;

    -- Log transaction if event_id provided
    IF p_event_id IS NOT NULL THEN
        INSERT INTO billing_transactions (
            workspace_id,
            provider,
            provider_order_id,
            credits_added,
            status
        ) VALUES (
            p_workspace_id,
            p_provider,
            p_event_id,
            p_credits,
            'paid'
        )
        ON CONFLICT DO NOTHING;
    END IF;

    RETURN COALESCE(v_new_balance, 0);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- Procedure: Atomically Deduct Credits with Overdraft Defense
CREATE OR REPLACE FUNCTION deduct_credits_safely(
    p_workspace_id TEXT,
    p_credits BIGINT,
    p_action_type TEXT DEFAULT 'action_deduction'
) RETURNS BOOLEAN AS $$
DECLARE
    v_current_balance BIGINT;
BEGIN
    SELECT COALESCE(data_cleaning_credits, 0) INTO v_current_balance
    FROM workspaces
    WHERE id = p_workspace_id
    FOR UPDATE;

    IF v_current_balance < p_credits THEN
        RETURN FALSE;
    END IF;

    UPDATE workspaces
    SET data_cleaning_credits = data_cleaning_credits - p_credits
    WHERE id = p_workspace_id;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- -----------------------------------------------------------------------------------------
-- 14. ROW-LEVEL SECURITY (RLS) POLICIES FOR MULTI-TENANT ISOLATION
-- -----------------------------------------------------------------------------------------
ALTER TABLE IF EXISTS billing_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS suppression_list ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS sender_pods ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS sender_pod_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS proxies ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS action_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS social_signal_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS approval_queue ENABLE ROW LEVEL SECURITY;

-- Note: In Supabase, service_role bypasses RLS automatically, while authenticated
-- users filter via auth.uid() matching workspace members.
