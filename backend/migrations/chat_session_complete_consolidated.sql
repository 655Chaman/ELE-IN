-- =========================================================================================
-- ELE-IN & ELESIUM CONSOLIDATED SESSION MIGRATION (SINGLE-CLICK SUPABASE DEPLOYMENT)
-- =========================================================================================
-- Strictly contains ONLY the tables, columns, RPCs, indexes, and RLS policies
-- designed, implemented, and hardened during this chat session.
-- 100% Idempotent & Self-Healing: Adds any missing columns to pre-existing tables
-- BEFORE creating indexes, constraints, or policies.
-- =========================================================================================

-- Safely extend pre-existing custom PostgreSQL ENUM types before DDL execution
ALTER TYPE public.outbox_event_status ADD VALUE IF NOT EXISTS 'suspended';
ALTER TYPE public.proxy_status ADD VALUE IF NOT EXISTS 'active';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'snoozed_ooo';
ALTER TYPE public.lead_status ADD VALUE IF NOT EXISTS 'Suppressed';
ALTER TYPE public.approval_status ADD VALUE IF NOT EXISTS 'rejected';

BEGIN;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Preserve or create Multi-Tenant Row-Level Security (RLS) helper
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'my_workspace_ids') THEN
        EXECUTE $func$
            CREATE FUNCTION public.my_workspace_ids()
            RETURNS SETOF UUID LANGUAGE sql STABLE SECURITY DEFINER AS $body$
                SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid();
            $body$;
        $func$;
    END IF;
END $$;

-- =========================================================================================
-- 1. WORKSPACES, CREDITS, TIER & AUTO-RECHARGE HARDENING
-- =========================================================================================
ALTER TABLE IF EXISTS public.workspaces
    ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'FREE',
    ADD COLUMN IF NOT EXISTS data_cleaning_credits BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS billing_status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS webhook_signing_secret TEXT,
    ADD COLUMN IF NOT EXISTS ai_provider TEXT DEFAULT 'nvidia',
    ADD COLUMN IF NOT EXISTS ai_model TEXT DEFAULT 'meta/llama-3.1-70b-instruct',
    ADD COLUMN IF NOT EXISTS custom_llm_api_key TEXT,
    ADD COLUMN IF NOT EXISTS ai_temperature NUMERIC(3,2) DEFAULT 0.70,
    ADD COLUMN IF NOT EXISTS agency_credit_quota INTEGER DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS agency_credits_allocated INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS auto_recharge_settings JSONB DEFAULT '{
        "enabled": false,
        "threshold_credits": 100,
        "recharge_package_id": "credits_1000",
        "max_monthly_recharges": 5,
        "recharges_this_month": 0,
        "last_recharged_at": null
    }'::jsonb,
    ADD COLUMN IF NOT EXISTS sending_window JSONB DEFAULT '{
        "start": "09:00",
        "end": "18:00",
        "timezone": "UTC",
        "days": ["mon", "tue", "wed", "thu", "fri"]
    }'::jsonb;

-- =========================================================================================
-- 2. BILLING TRANSACTIONS, CHECKOUT SESSIONS & CREDIT LEDGER
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.billing_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    amount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    amount_cents BIGINT DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'usd',
    status TEXT NOT NULL DEFAULT 'succeeded',
    provider TEXT NOT NULL,
    provider_tx_id TEXT UNIQUE,
    provider_order_id TEXT,
    provider_payment_id TEXT,
    package_id TEXT,
    credits_added BIGINT DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.billing_transactions
    ADD COLUMN IF NOT EXISTS amount NUMERIC(10, 2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS amount_cents BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'usd',
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'succeeded',
    ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'razorpay',
    ADD COLUMN IF NOT EXISTS provider_tx_id TEXT,
    ADD COLUMN IF NOT EXISTS provider_order_id TEXT,
    ADD COLUMN IF NOT EXISTS provider_payment_id TEXT,
    ADD COLUMN IF NOT EXISTS package_id TEXT,
    ADD COLUMN IF NOT EXISTS credits_added BIGINT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_billing_transactions_workspace ON public.billing_transactions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_billing_transactions_created ON public.billing_transactions(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_txns_provider_order ON public.billing_transactions(provider, provider_order_id);
CREATE INDEX IF NOT EXISTS idx_billing_txns_status ON public.billing_transactions(status);

CREATE TABLE IF NOT EXISTS public.checkout_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    user_id UUID,
    package_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'razorpay',
    provider_order_id TEXT UNIQUE,
    amount_cents INT NOT NULL DEFAULT 0,
    credits INT NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'created',
    metadata JSONB DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.checkout_sessions
    ADD COLUMN IF NOT EXISTS id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS user_id UUID,
    ADD COLUMN IF NOT EXISTS package_id TEXT,
    ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'razorpay',
    ADD COLUMN IF NOT EXISTS provider_order_id TEXT,
    ADD COLUMN IF NOT EXISTS amount_cents INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS credits INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD',
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'created',
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_checkout_sessions_workspace ON public.checkout_sessions(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkout_sessions_order ON public.checkout_sessions(provider_order_id);

CREATE TABLE IF NOT EXISTS public.credit_deductions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    amount INT NOT NULL,
    balance_after INT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.credit_deductions
    ADD COLUMN IF NOT EXISTS action_type TEXT,
    ADD COLUMN IF NOT EXISTS amount INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS balance_after INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_credit_deductions_workspace_created ON public.credit_deductions(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_credit_deductions_workspace_action ON public.credit_deductions(workspace_id, action_type);

CREATE TABLE IF NOT EXISTS public.credit_action_costs (
    action_type TEXT PRIMARY KEY,
    credits INT NOT NULL,
    description TEXT,
    category TEXT NOT NULL DEFAULT 'general',
    is_active BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO public.credit_action_costs (action_type, credits, description, category, is_active)
VALUES 
    ('lead_enrichment', 5, 'Full profile waterfall enrichment', 'enrichment', true),
    ('email_discovery', 3, 'Find and verify professional email', 'enrichment', true),
    ('phone_lookup', 10, 'Verified direct dial mobile lookup', 'enrichment', true),
    ('ai_personalization', 2, 'Elesium hyper-personalized icebreaker generation', 'ai', true),
    ('ai_reply_generation', 2, 'Elesium context-aware objection handling and reply', 'ai', true)
ON CONFLICT (action_type) DO NOTHING;

-- =========================================================================================
-- 3. OUTBOX NOTIFICATION QUEUE & DEAD-LETTER QUARANTINE (DLQ)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'pending',
    deliver_at TIMESTAMPTZ DEFAULT NOW(),
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.outbox_events
    ADD COLUMN IF NOT EXISTS event_type TEXT,
    ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS deliver_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_error TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_outbox_events_poll ON public.outbox_events(status, deliver_at);
CREATE INDEX IF NOT EXISTS idx_outbox_events_workspace ON public.outbox_events(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_events_dlq ON public.outbox_events(workspace_id, status);

-- =========================================================================================
-- 4. SUPPRESSION LIST (DO-NOT-CONTACT / DNC ENGINE)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.suppression_list (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    linkedin_url TEXT,
    email TEXT,
    domain TEXT,
    value TEXT,
    reason TEXT DEFAULT 'manual_dnc',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.suppression_list
    ADD COLUMN IF NOT EXISTS linkedin_url TEXT,
    ADD COLUMN IF NOT EXISTS email TEXT,
    ADD COLUMN IF NOT EXISTS domain TEXT,
    ADD COLUMN IF NOT EXISTS value TEXT,
    ADD COLUMN IF NOT EXISTS reason TEXT DEFAULT 'manual_dnc',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_suppression_workspace ON public.suppression_list(workspace_id);
CREATE INDEX IF NOT EXISTS idx_suppression_li_url ON public.suppression_list(workspace_id, linkedin_url) WHERE linkedin_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_suppression_email ON public.suppression_list(workspace_id, email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_suppression_domain ON public.suppression_list(workspace_id, domain) WHERE domain IS NOT NULL;

-- =========================================================================================
-- 5. SENDER PODS, FLEET FAILOVER & WORKSPACE LOAD BALANCING
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.sender_pods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    rotation_strategy TEXT DEFAULT 'round_robin',
    max_daily_invites_per_pod INTEGER DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.sender_pods
    ADD COLUMN IF NOT EXISTS name TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS rotation_strategy TEXT DEFAULT 'round_robin',
    ADD COLUMN IF NOT EXISTS max_daily_invites_per_pod INTEGER DEFAULT 100,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.sender_pod_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pod_id UUID NOT NULL REFERENCES public.sender_pods(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    weight INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_pod_account UNIQUE(pod_id, account_id)
);

ALTER TABLE IF EXISTS public.sender_pod_accounts
    ADD COLUMN IF NOT EXISTS pod_id UUID,
    ADD COLUMN IF NOT EXISTS account_id TEXT,
    ADD COLUMN IF NOT EXISTS workspace_id TEXT,
    ADD COLUMN IF NOT EXISTS weight INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_sender_pods_workspace ON public.sender_pods(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sender_pod_acc_lookup ON public.sender_pod_accounts(workspace_id, pod_id, is_active);

ALTER TABLE IF EXISTS public.accounts
    ADD COLUMN IF NOT EXISTS proxy_id UUID,
    ADD COLUMN IF NOT EXISTS preferred_proxy_id UUID,
    ADD COLUMN IF NOT EXISTS proxy_country TEXT,
    ADD COLUMN IF NOT EXISTS health_score NUMERIC DEFAULT 100,
    ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS quarantine_reason TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS is_pod_eligible BOOLEAN DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_accounts_quarantined_until ON public.accounts(quarantined_until);
CREATE INDEX IF NOT EXISTS idx_accounts_pod_eligible ON public.accounts(is_pod_eligible, status);

ALTER TABLE IF EXISTS public.campaigns
    ADD COLUMN IF NOT EXISTS pod_dispatch_strategy TEXT DEFAULT 'CAPACITY_WEIGHTED',
    ADD COLUMN IF NOT EXISTS pod_emergency_paused BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS pod_pause_reason TEXT DEFAULT NULL;

ALTER TABLE IF EXISTS public.campaign_accounts
    ADD COLUMN IF NOT EXISTS weight INTEGER DEFAULT 100,
    ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS failover_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_dispatched_at TIMESTAMPTZ DEFAULT NULL;

-- =========================================================================================
-- 6. RESIDENTIAL PROXIES & /24 SUBNET ISOLATION
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.proxies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT,
    password TEXT,
    password_encrypted TEXT,
    protocol TEXT DEFAULT 'http',
    country TEXT,
    country_code TEXT,
    label TEXT,
    source TEXT DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    exit_ip TEXT,
    latency_ms INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    quarantined_until TIMESTAMPTZ,
    failure_count INTEGER DEFAULT 0,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.proxies
    ADD COLUMN IF NOT EXISTS password TEXT,
    ADD COLUMN IF NOT EXISTS country TEXT,
    ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'user',
    ADD COLUMN IF NOT EXISTS country_code TEXT,
    ADD COLUMN IF NOT EXISTS label TEXT,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS latency_ms INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS exit_ip TEXT,
    ADD COLUMN IF NOT EXISTS password_encrypted TEXT,
    ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS failure_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_proxies_workspace ON public.proxies(workspace_id);
CREATE INDEX IF NOT EXISTS idx_proxies_active ON public.proxies(workspace_id, status, is_active);
CREATE INDEX IF NOT EXISTS idx_proxies_quarantined_until ON public.proxies(quarantined_until);

-- =========================================================================================
-- 7. WORKER HEARTBEAT, ACTION LOG, EXECUTION LEASES & APPROVAL QUEUE
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.worker_heartbeat (
    worker_id TEXT PRIMARY KEY,
    last_beat_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'alive',
    metadata JSONB DEFAULT '{}'::jsonb
);

ALTER TABLE IF EXISTS public.worker_heartbeat
    ADD COLUMN IF NOT EXISTS last_beat_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'alive',
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS public.action_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    execution_state_id TEXT,
    action_type TEXT NOT NULL,
    result TEXT NOT NULL,
    error_detail TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.action_log
    ADD COLUMN IF NOT EXISTS execution_state_id TEXT,
    ADD COLUMN IF NOT EXISTS action_type TEXT,
    ADD COLUMN IF NOT EXISTS result TEXT,
    ADD COLUMN IF NOT EXISTS error_detail TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_action_log_workspace ON public.action_log(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_log_exec_state ON public.action_log(execution_state_id);

CREATE TABLE IF NOT EXISTS public.approval_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    lead_id TEXT,
    account_id TEXT,
    exec_state_id TEXT,
    generated_reply TEXT,
    ai_draft TEXT,
    sender_name TEXT,
    thread_url TEXT,
    status TEXT DEFAULT 'pending',
    token TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.approval_queue
    ADD COLUMN IF NOT EXISTS lead_id TEXT,
    ADD COLUMN IF NOT EXISTS account_id TEXT,
    ADD COLUMN IF NOT EXISTS exec_state_id TEXT,
    ADD COLUMN IF NOT EXISTS generated_reply TEXT,
    ADD COLUMN IF NOT EXISTS ai_draft TEXT,
    ADD COLUMN IF NOT EXISTS sender_name TEXT,
    ADD COLUMN IF NOT EXISTS thread_url TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS token TEXT,
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE IF EXISTS public.messages ADD COLUMN IF NOT EXISTS thread_url TEXT;
CREATE INDEX IF NOT EXISTS idx_approval_queue_workspace ON public.approval_queue(workspace_id, status);

ALTER TABLE IF EXISTS public.campaign_execution_states
    ADD COLUMN IF NOT EXISTS lease_token TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS error_reason TEXT,
    ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_ces_lease_token ON public.campaign_execution_states(lease_token) WHERE lease_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ces_next_run ON public.campaign_execution_states(workspace_id, status, next_run_at);

ALTER TABLE IF EXISTS public.processing_jobs ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_processing_jobs_idempotency_key
    ON public.processing_jobs(workspace_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_campaign_lead_enrollment'
    ) THEN
        ALTER TABLE public.campaign_enrollments
            ADD CONSTRAINT uq_campaign_lead_enrollment UNIQUE (campaign_id, lead_id);
    END IF;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- =========================================================================================
-- 8. OUTBOUND WEBHOOK ENDPOINTS & RETRYING DELIVERIES
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.webhook_endpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    url TEXT NOT NULL,
    events TEXT[] NOT NULL DEFAULT '{}',
    signing_secret TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    failure_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.webhook_endpoints
    ADD COLUMN IF NOT EXISTS events TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS failure_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.webhook_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    endpoint_id UUID REFERENCES public.webhook_endpoints(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    next_retry_at TIMESTAMPTZ DEFAULT NOW(),
    response_status INTEGER,
    last_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.webhook_deliveries
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS response_status INTEGER,
    ADD COLUMN IF NOT EXISTS last_error TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_poll ON public.webhook_deliveries(status, next_retry_at);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_endpoint ON public.webhook_deliveries(endpoint_id, created_at DESC);

-- =========================================================================================
-- 9. LEADS, DYNAMIC SEGMENTATION & AI INBOX BATTLECARDS
-- =========================================================================================
ALTER TABLE IF EXISTS public.leads
    ADD COLUMN IF NOT EXISTS is_unsubscribed BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS unsubscribed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deal_stage TEXT DEFAULT 'new_lead',
    ADD COLUMN IF NOT EXISTS deal_stage_updated_at TIMESTAMPTZ DEFAULT now(),
    ADD COLUMN IF NOT EXISTS deal_estimated_value NUMERIC(12, 2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS last_objection_type TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_leads_workspace_email ON public.leads(workspace_id, email);
CREATE INDEX IF NOT EXISTS idx_leads_workspace_li ON public.leads(workspace_id, linkedin_url);
CREATE INDEX IF NOT EXISTS idx_leads_workspace_deal_stage ON public.leads(workspace_id, deal_stage);

ALTER TABLE IF EXISTS public.lead_lists
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_lead_lists_workspace_metadata
    ON public.lead_lists USING gin (metadata);

CREATE TABLE IF NOT EXISTS public.lead_objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    lead_id UUID NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    objection_type TEXT NOT NULL,
    confidence NUMERIC(4, 3) DEFAULT 0.850,
    prospect_message TEXT,
    suggested_rebuttal TEXT,
    chosen_framework TEXT,
    resolved BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.lead_objections
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS objection_type TEXT,
    ADD COLUMN IF NOT EXISTS confidence NUMERIC(4, 3) DEFAULT 0.850,
    ADD COLUMN IF NOT EXISTS prospect_message TEXT,
    ADD COLUMN IF NOT EXISTS suggested_rebuttal TEXT,
    ADD COLUMN IF NOT EXISTS chosen_framework TEXT,
    ADD COLUMN IF NOT EXISTS resolved BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_lead_objections_workspace_lead ON public.lead_objections(workspace_id, lead_id, created_at DESC);

-- =========================================================================================
-- 10. KNOWLEDGE BASE SYNTHESIS, PERSONAS & OBJECTIONS UNIFICATION
-- =========================================================================================
ALTER TABLE IF EXISTS public.personas
    ADD COLUMN IF NOT EXISTS value_prop TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS target_titles JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS tone_tweaks TEXT DEFAULT '';

ALTER TABLE IF EXISTS public.knowledge_assets
    ADD COLUMN IF NOT EXISTS raw_text TEXT;

CREATE TABLE IF NOT EXISTS public.knowledge_synthesis (
    workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    core_value_prop TEXT,
    identified_tone JSONB DEFAULT '[]'::jsonb,
    target_customer_profile TEXT,
    key_differentiators JSONB DEFAULT '[]'::jsonb,
    proof_points JSONB DEFAULT '[]'::jsonb,
    primary_pain_points_solved JSONB DEFAULT '[]'::jsonb,
    generated_from_vector_count INT DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.knowledge_synthesis
    ADD COLUMN IF NOT EXISTS core_value_prop TEXT,
    ADD COLUMN IF NOT EXISTS identified_tone JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS target_customer_profile TEXT,
    ADD COLUMN IF NOT EXISTS key_differentiators JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS proof_points JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS primary_pain_points_solved JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS generated_from_vector_count INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.knowledge_synthesis_drafts (
    workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    core_value_prop TEXT,
    identified_tone JSONB DEFAULT '[]'::jsonb,
    target_customer_profile TEXT,
    key_differentiators JSONB DEFAULT '[]'::jsonb,
    proof_points JSONB DEFAULT '[]'::jsonb,
    primary_pain_points_solved JSONB DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'draft',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.knowledge_synthesis_drafts
    ADD COLUMN IF NOT EXISTS core_value_prop TEXT,
    ADD COLUMN IF NOT EXISTS identified_tone JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS target_customer_profile TEXT,
    ADD COLUMN IF NOT EXISTS key_differentiators JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS proof_points JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS primary_pain_points_solved JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.knowledge_objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    objection_topic TEXT,
    rebuttal_strategy TEXT,
    trigger TEXT,
    playbook TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.knowledge_objections
    ADD COLUMN IF NOT EXISTS objection_topic TEXT,
    ADD COLUMN IF NOT EXISTS rebuttal_strategy TEXT,
    ADD COLUMN IF NOT EXISTS trigger TEXT,
    ADD COLUMN IF NOT EXISTS playbook TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_knowledge_objections_workspace ON public.knowledge_objections(workspace_id);

-- =========================================================================================
-- 11. BAYESIAN ICP CALIBRATION STUDIO & SIGNAL WEIGHTS
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.icp_signal_weights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    signal_name TEXT NOT NULL,
    prior_alpha INT NOT NULL DEFAULT 2,
    prior_beta INT NOT NULL DEFAULT 2,
    is_frozen BOOLEAN DEFAULT false,
    weight_multiplier NUMERIC(5,2) DEFAULT 1.00,
    category TEXT DEFAULT 'general',
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, signal_name)
);

ALTER TABLE IF EXISTS public.icp_signal_weights
    ADD COLUMN IF NOT EXISTS signal_name TEXT,
    ADD COLUMN IF NOT EXISTS prior_alpha INT DEFAULT 2,
    ADD COLUMN IF NOT EXISTS prior_beta INT DEFAULT 2,
    ADD COLUMN IF NOT EXISTS is_frozen BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS weight_multiplier NUMERIC(5,2) DEFAULT 1.00,
    ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_icp_signal_weights_workspace ON public.icp_signal_weights(workspace_id);

CREATE TABLE IF NOT EXISTS public.icp_feedback_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
    event_type TEXT,
    signal_key TEXT,
    outcome_type TEXT,
    signals_affected JSONB DEFAULT '[]'::jsonb,
    score_before INT,
    score_after INT,
    alpha_delta INTEGER DEFAULT 0,
    beta_delta INTEGER DEFAULT 0,
    source TEXT DEFAULT 'system',
    details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.icp_feedback_events
    ADD COLUMN IF NOT EXISTS campaign_id UUID,
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS event_type TEXT,
    ADD COLUMN IF NOT EXISTS signal_key TEXT,
    ADD COLUMN IF NOT EXISTS outcome_type TEXT,
    ADD COLUMN IF NOT EXISTS signals_affected JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS score_before INT,
    ADD COLUMN IF NOT EXISTS score_after INT,
    ADD COLUMN IF NOT EXISTS alpha_delta INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS beta_delta INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'system',
    ADD COLUMN IF NOT EXISTS details JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_icp_feedback_workspace_created ON public.icp_feedback_events(workspace_id, created_at DESC);

-- =========================================================================================
-- 12. PROSPECT SOCIAL SIGNAL RADAR & CACHE
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.social_signal_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    linkedin_url TEXT NOT NULL,
    signals JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_social_signal_lead UNIQUE(workspace_id, linkedin_url)
);

ALTER TABLE IF EXISTS public.social_signal_cache
    ADD COLUMN IF NOT EXISTS linkedin_url TEXT,
    ADD COLUMN IF NOT EXISTS signals JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_social_signal_lookup ON public.social_signal_cache(workspace_id, linkedin_url, expires_at);

CREATE TABLE IF NOT EXISTS public.lead_social_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    post_url TEXT,
    post_text TEXT NOT NULL,
    post_date TIMESTAMPTZ DEFAULT now(),
    engagement_count JSONB DEFAULT '{"likes": 0, "comments": 0, "reposts": 0}'::jsonb,
    media_type TEXT DEFAULT 'text',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.lead_social_posts
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS post_url TEXT,
    ADD COLUMN IF NOT EXISTS post_text TEXT,
    ADD COLUMN IF NOT EXISTS post_date TIMESTAMPTZ DEFAULT now(),
    ADD COLUMN IF NOT EXISTS engagement_count JSONB DEFAULT '{"likes": 0, "comments": 0, "reposts": 0}'::jsonb,
    ADD COLUMN IF NOT EXISTS media_type TEXT DEFAULT 'text',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.lead_social_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    post_id UUID REFERENCES public.lead_social_posts(id) ON DELETE SET NULL,
    signal_type TEXT NOT NULL DEFAULT 'general_activity',
    intent_score INTEGER NOT NULL DEFAULT 50,
    summary TEXT,
    recommended_hook TEXT,
    is_actioned BOOLEAN DEFAULT false,
    detected_at TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.lead_social_signals
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS post_id UUID,
    ADD COLUMN IF NOT EXISTS signal_type TEXT DEFAULT 'general_activity',
    ADD COLUMN IF NOT EXISTS intent_score INTEGER DEFAULT 50,
    ADD COLUMN IF NOT EXISTS summary TEXT,
    ADD COLUMN IF NOT EXISTS recommended_hook TEXT,
    ADD COLUMN IF NOT EXISTS is_actioned BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ DEFAULT now(),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_lead_social_posts_workspace_lead ON public.lead_social_posts(workspace_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_social_signals_workspace_score ON public.lead_social_signals(workspace_id, intent_score DESC, detected_at DESC);

-- =========================================================================================
-- 13. THOMPSON SAMPLING MULTI-ARMED BANDIT & TRIGGER RADAR (HORIZONS 31 & 32)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.bandit_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    step_type TEXT NOT NULL DEFAULT 'connection_note',
    status TEXT NOT NULL DEFAULT 'active',
    auto_mutate BOOLEAN DEFAULT true,
    min_trials_before_mutation INTEGER DEFAULT 25,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.bandit_experiments
    ADD COLUMN IF NOT EXISTS campaign_id UUID,
    ADD COLUMN IF NOT EXISTS name TEXT,
    ADD COLUMN IF NOT EXISTS step_type TEXT DEFAULT 'connection_note',
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS auto_mutate BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS min_trials_before_mutation INTEGER DEFAULT 25,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.copy_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES public.bandit_experiments(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    variant_label TEXT,
    template_text TEXT,
    angle_tag TEXT DEFAULT 'value_prop',
    alpha INTEGER NOT NULL DEFAULT 1,
    beta INTEGER NOT NULL DEFAULT 1,
    impressions INTEGER NOT NULL DEFAULT 0,
    positive_outcomes INTEGER NOT NULL DEFAULT 0,
    is_challenger BOOLEAN DEFAULT false,
    parent_variant_id UUID REFERENCES public.copy_variants(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.copy_variants
    ADD COLUMN IF NOT EXISTS experiment_id UUID,
    ADD COLUMN IF NOT EXISTS variant_label TEXT,
    ADD COLUMN IF NOT EXISTS template_text TEXT,
    ADD COLUMN IF NOT EXISTS angle_tag TEXT DEFAULT 'value_prop',
    ADD COLUMN IF NOT EXISTS alpha INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS beta INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS impressions INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS positive_outcomes INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_challenger BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS parent_variant_id UUID,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.trigger_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
    company_name TEXT,
    event_type TEXT,
    headline TEXT,
    source_url TEXT,
    urgency_score INTEGER DEFAULT 75,
    generated_hook TEXT,
    status TEXT NOT NULL DEFAULT 'detected',
    enrolled_campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    detected_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.trigger_events
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS company_name TEXT,
    ADD COLUMN IF NOT EXISTS event_type TEXT,
    ADD COLUMN IF NOT EXISTS headline TEXT,
    ADD COLUMN IF NOT EXISTS source_url TEXT,
    ADD COLUMN IF NOT EXISTS urgency_score INTEGER DEFAULT 75,
    ADD COLUMN IF NOT EXISTS generated_hook TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'detected',
    ADD COLUMN IF NOT EXISTS enrolled_campaign_id UUID,
    ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_bandit_experiments_workspace ON public.bandit_experiments(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_copy_variants_experiment ON public.copy_variants(experiment_id, status);
CREATE INDEX IF NOT EXISTS idx_trigger_events_workspace ON public.trigger_events(workspace_id, status, urgency_score DESC);

-- =========================================================================================
-- 14. SOCIAL FEED PRE-WARMER & OMNICHANNEL CASCADE (HORIZON 35B)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.lead_prewarm_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    lead_id UUID NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    action_type TEXT NOT NULL,
    target_url TEXT,
    generated_comment TEXT,
    warmth_points INTEGER DEFAULT 10,
    status TEXT NOT NULL DEFAULT 'completed',
    executed_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.lead_prewarm_events
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS campaign_id UUID,
    ADD COLUMN IF NOT EXISTS action_type TEXT,
    ADD COLUMN IF NOT EXISTS target_url TEXT,
    ADD COLUMN IF NOT EXISTS generated_comment TEXT,
    ADD COLUMN IF NOT EXISTS warmth_points INTEGER DEFAULT 10,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'completed',
    ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.omnichannel_fallback_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT true,
    linkedin_invite_timeout_hours INTEGER DEFAULT 72,
    fallback_channel TEXT DEFAULT 'email',
    provider TEXT DEFAULT 'smartlead',
    external_campaign_id TEXT,
    inmail_template TEXT,
    email_subject_template TEXT,
    email_body_template TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(workspace_id, campaign_id)
);

ALTER TABLE IF EXISTS public.omnichannel_fallback_configs
    ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS linkedin_invite_timeout_hours INTEGER DEFAULT 72,
    ADD COLUMN IF NOT EXISTS fallback_channel TEXT DEFAULT 'email',
    ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'smartlead',
    ADD COLUMN IF NOT EXISTS external_campaign_id TEXT,
    ADD COLUMN IF NOT EXISTS inmail_template TEXT,
    ADD COLUMN IF NOT EXISTS email_subject_template TEXT,
    ADD COLUMN IF NOT EXISTS email_body_template TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.omnichannel_cascade_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    lead_id UUID NOT NULL REFERENCES public.leads(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    from_channel TEXT NOT NULL DEFAULT 'linkedin_invite',
    to_channel TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'triggered',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.omnichannel_cascade_logs
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS campaign_id UUID,
    ADD COLUMN IF NOT EXISTS from_channel TEXT DEFAULT 'linkedin_invite',
    ADD COLUMN IF NOT EXISTS to_channel TEXT,
    ADD COLUMN IF NOT EXISTS reason TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'triggered',
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.thought_leadership_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    framework TEXT NOT NULL DEFAULT 'contrarian',
    hook_line TEXT,
    post_body TEXT,
    target_persona TEXT,
    viral_score INTEGER DEFAULT 80,
    status TEXT DEFAULT 'draft',
    scheduled_for TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.thought_leadership_posts
    ADD COLUMN IF NOT EXISTS topic TEXT,
    ADD COLUMN IF NOT EXISTS framework TEXT DEFAULT 'contrarian',
    ADD COLUMN IF NOT EXISTS hook_line TEXT,
    ADD COLUMN IF NOT EXISTS post_body TEXT,
    ADD COLUMN IF NOT EXISTS target_persona TEXT,
    ADD COLUMN IF NOT EXISTS viral_score INTEGER DEFAULT 80,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_prewarm_workspace_lead ON public.lead_prewarm_events(workspace_id, lead_id, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_cascade_logs_workspace ON public.omnichannel_cascade_logs(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_thought_posts_workspace ON public.thought_leadership_posts(workspace_id, created_at DESC);

-- =========================================================================================
-- 15. EVENT HARVESTER & MULTIMODAL VOICE/VIDEO STUDIO (HORIZON 35C)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.harvested_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL DEFAULT 'linkedin_event',
    source_url TEXT,
    title TEXT,
    organizer TEXT,
    topic_tags TEXT[] DEFAULT '{}',
    total_scraped INTEGER DEFAULT 0,
    icp_matched INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'completed',
    auto_campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    harvested_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.harvested_events
    ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'linkedin_event',
    ADD COLUMN IF NOT EXISTS source_url TEXT,
    ADD COLUMN IF NOT EXISTS title TEXT,
    ADD COLUMN IF NOT EXISTS organizer TEXT,
    ADD COLUMN IF NOT EXISTS topic_tags TEXT[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS total_scraped INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS icp_matched INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'completed',
    ADD COLUMN IF NOT EXISTS auto_campaign_id UUID,
    ADD COLUMN IF NOT EXISTS harvested_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.event_attendees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES public.harvested_events(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
    full_name TEXT,
    headline TEXT,
    company TEXT,
    linkedin_url TEXT,
    attendee_role TEXT DEFAULT 'attendee',
    icp_score INTEGER DEFAULT 75,
    contextual_opener TEXT,
    enrolled BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.event_attendees
    ADD COLUMN IF NOT EXISTS event_id UUID,
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS full_name TEXT,
    ADD COLUMN IF NOT EXISTS headline TEXT,
    ADD COLUMN IF NOT EXISTS company TEXT,
    ADD COLUMN IF NOT EXISTS linkedin_url TEXT,
    ADD COLUMN IF NOT EXISTS attendee_role TEXT DEFAULT 'attendee',
    ADD COLUMN IF NOT EXISTS icp_score INTEGER DEFAULT 75,
    ADD COLUMN IF NOT EXISTS contextual_opener TEXT,
    ADD COLUMN IF NOT EXISTS enrolled BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS public.multimodal_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES public.leads(id) ON DELETE SET NULL,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    media_type TEXT NOT NULL DEFAULT 'voice_note',
    voice_profile TEXT DEFAULT 'executive_warm',
    script_text TEXT,
    personalized_transcript TEXT,
    duration_seconds INTEGER DEFAULT 28,
    thumbnail_overlay_text TEXT,
    prospect_domain_bg TEXT,
    audio_waveform JSONB DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.multimodal_assets
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS campaign_id UUID,
    ADD COLUMN IF NOT EXISTS media_type TEXT DEFAULT 'voice_note',
    ADD COLUMN IF NOT EXISTS voice_profile TEXT DEFAULT 'executive_warm',
    ADD COLUMN IF NOT EXISTS script_text TEXT,
    ADD COLUMN IF NOT EXISTS personalized_transcript TEXT,
    ADD COLUMN IF NOT EXISTS duration_seconds INTEGER DEFAULT 28,
    ADD COLUMN IF NOT EXISTS thumbnail_overlay_text TEXT,
    ADD COLUMN IF NOT EXISTS prospect_domain_bg TEXT,
    ADD COLUMN IF NOT EXISTS audio_waveform JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ready',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_harvested_events_workspace ON public.harvested_events(workspace_id, harvested_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_attendees_event ON public.event_attendees(event_id, icp_score DESC);
CREATE INDEX IF NOT EXISTS idx_multimodal_assets_workspace ON public.multimodal_assets(workspace_id, created_at DESC);

-- =========================================================================================
-- 16. ABM BUYING COMMITTEES & MULTITHREADING (HORIZON 34A)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.target_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    company_name TEXT NOT NULL,
    domain TEXT,
    industry TEXT,
    employee_band TEXT DEFAULT '51-200',
    tier TEXT NOT NULL DEFAULT 'tier_1',
    heat_score INTEGER NOT NULL DEFAULT 50,
    intent_stage TEXT NOT NULL DEFAULT 'warming',
    ai_account_thesis TEXT,
    signals_json JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.target_accounts
    ADD COLUMN IF NOT EXISTS company_name TEXT,
    ADD COLUMN IF NOT EXISTS domain TEXT,
    ADD COLUMN IF NOT EXISTS industry TEXT,
    ADD COLUMN IF NOT EXISTS employee_band TEXT DEFAULT '51-200',
    ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'tier_1',
    ADD COLUMN IF NOT EXISTS heat_score INTEGER DEFAULT 50,
    ADD COLUMN IF NOT EXISTS intent_stage TEXT DEFAULT 'warming',
    ADD COLUMN IF NOT EXISTS ai_account_thesis TEXT,
    ADD COLUMN IF NOT EXISTS signals_json JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.account_committee_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES public.target_accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    lead_id UUID,
    full_name TEXT,
    title TEXT,
    linkedin_url TEXT,
    committee_role TEXT DEFAULT 'champion',
    influence_weight INTEGER DEFAULT 75,
    relationship_status TEXT DEFAULT 'untouched',
    assigned_sender_id UUID,
    personalized_angle TEXT,
    last_touched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.account_committee_members
    ADD COLUMN IF NOT EXISTS account_id UUID,
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS full_name TEXT,
    ADD COLUMN IF NOT EXISTS title TEXT,
    ADD COLUMN IF NOT EXISTS linkedin_url TEXT,
    ADD COLUMN IF NOT EXISTS committee_role TEXT DEFAULT 'champion',
    ADD COLUMN IF NOT EXISTS influence_weight INTEGER DEFAULT 75,
    ADD COLUMN IF NOT EXISTS relationship_status TEXT DEFAULT 'untouched',
    ADD COLUMN IF NOT EXISTS assigned_sender_id UUID,
    ADD COLUMN IF NOT EXISTS personalized_angle TEXT,
    ADD COLUMN IF NOT EXISTS last_touched_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.multithread_campaign_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID NOT NULL REFERENCES public.target_accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    campaign_id UUID,
    play_type TEXT DEFAULT 'pincer_multithread',
    status TEXT DEFAULT 'active',
    members_enrolled INTEGER DEFAULT 0,
    orchestration_plan JSONB DEFAULT '[]'::jsonb,
    launched_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.multithread_campaign_runs
    ADD COLUMN IF NOT EXISTS account_id UUID,
    ADD COLUMN IF NOT EXISTS campaign_id UUID,
    ADD COLUMN IF NOT EXISTS play_type TEXT DEFAULT 'pincer_multithread',
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS members_enrolled INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS orchestration_plan JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS launched_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_target_accounts_ws_heat ON public.target_accounts(workspace_id, heat_score DESC);
CREATE INDEX IF NOT EXISTS idx_committee_members_account ON public.account_committee_members(account_id, influence_weight DESC);
CREATE INDEX IF NOT EXISTS idx_committee_members_ws ON public.account_committee_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_multithread_runs_ws ON public.multithread_campaign_runs(workspace_id, launched_at DESC);

-- =========================================================================================
-- 17. CHAMPION BOOMERANG TRACKER & CLOSED-LOST REVIVAL (HORIZON 34B)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.champion_job_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    contact_name TEXT,
    linkedin_url TEXT,
    previous_company TEXT,
    previous_title TEXT,
    previous_relationship TEXT DEFAULT 'champion',
    new_company TEXT,
    new_title TEXT,
    new_company_domain TEXT,
    new_company_icp_fit INTEGER DEFAULT 85,
    days_in_new_role INTEGER DEFAULT 14,
    buying_window_status TEXT DEFAULT 'golden_90_days',
    congrats_hook TEXT,
    status TEXT DEFAULT 'detected',
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.champion_job_changes
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS contact_name TEXT,
    ADD COLUMN IF NOT EXISTS linkedin_url TEXT,
    ADD COLUMN IF NOT EXISTS previous_company TEXT,
    ADD COLUMN IF NOT EXISTS previous_title TEXT,
    ADD COLUMN IF NOT EXISTS previous_relationship TEXT DEFAULT 'champion',
    ADD COLUMN IF NOT EXISTS new_company TEXT,
    ADD COLUMN IF NOT EXISTS new_title TEXT,
    ADD COLUMN IF NOT EXISTS new_company_domain TEXT,
    ADD COLUMN IF NOT EXISTS new_company_icp_fit INTEGER DEFAULT 85,
    ADD COLUMN IF NOT EXISTS days_in_new_role INTEGER DEFAULT 14,
    ADD COLUMN IF NOT EXISTS buying_window_status TEXT DEFAULT 'golden_90_days',
    ADD COLUMN IF NOT EXISTS congrats_hook TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'detected',
    ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.warm_intro_paths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    target_lead_name TEXT,
    target_title TEXT,
    target_company TEXT,
    target_linkedin_url TEXT,
    connector_name TEXT,
    connector_type TEXT DEFAULT 'team_sender',
    shared_context TEXT,
    proximity_score INTEGER DEFAULT 88,
    intro_ask_script TEXT,
    direct_mention_hook TEXT,
    status TEXT DEFAULT 'available',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.warm_intro_paths
    ADD COLUMN IF NOT EXISTS target_lead_name TEXT,
    ADD COLUMN IF NOT EXISTS target_title TEXT,
    ADD COLUMN IF NOT EXISTS target_company TEXT,
    ADD COLUMN IF NOT EXISTS target_linkedin_url TEXT,
    ADD COLUMN IF NOT EXISTS connector_name TEXT,
    ADD COLUMN IF NOT EXISTS connector_type TEXT DEFAULT 'team_sender',
    ADD COLUMN IF NOT EXISTS shared_context TEXT,
    ADD COLUMN IF NOT EXISTS proximity_score INTEGER DEFAULT 88,
    ADD COLUMN IF NOT EXISTS intro_ask_script TEXT,
    ADD COLUMN IF NOT EXISTS direct_mention_hook TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'available',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.closed_lost_revivals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    company_name TEXT,
    contact_name TEXT,
    contact_title TEXT,
    deal_value NUMERIC(12, 2) DEFAULT 15000.00,
    lost_reason TEXT DEFAULT 'timing_budget',
    lost_days_ago INTEGER DEFAULT 120,
    revival_trigger_signal TEXT,
    readiness_score INTEGER DEFAULT 82,
    reengagement_script TEXT,
    status TEXT DEFAULT 'ready_to_revive',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.closed_lost_revivals
    ADD COLUMN IF NOT EXISTS company_name TEXT,
    ADD COLUMN IF NOT EXISTS contact_name TEXT,
    ADD COLUMN IF NOT EXISTS contact_title TEXT,
    ADD COLUMN IF NOT EXISTS deal_value NUMERIC(12, 2) DEFAULT 15000.00,
    ADD COLUMN IF NOT EXISTS lost_reason TEXT DEFAULT 'timing_budget',
    ADD COLUMN IF NOT EXISTS lost_days_ago INTEGER DEFAULT 120,
    ADD COLUMN IF NOT EXISTS revival_trigger_signal TEXT,
    ADD COLUMN IF NOT EXISTS readiness_score INTEGER DEFAULT 82,
    ADD COLUMN IF NOT EXISTS reengagement_script TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ready_to_revive',
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_champion_changes_ws ON public.champion_job_changes(workspace_id, new_company_icp_fit DESC);
CREATE INDEX IF NOT EXISTS idx_warm_intro_paths_ws ON public.warm_intro_paths(workspace_id, proximity_score DESC);
CREATE INDEX IF NOT EXISTS idx_closed_lost_revivals_ws ON public.closed_lost_revivals(workspace_id, readiness_score DESC);

-- =========================================================================================
-- 18. COMPETITIVE DISPLACEMENT & VENDOR TAKEOVER (HORIZON 35A)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.competitor_displacements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    competitor_name TEXT,
    prospect_name TEXT,
    prospect_title TEXT,
    prospect_company TEXT,
    prospect_linkedin_url TEXT,
    signal_source TEXT DEFAULT 'tech_stack_drop',
    signal_detail TEXT,
    estimated_contract_value NUMERIC(12, 2) DEFAULT 18000.00,
    urgency_score INTEGER DEFAULT 88,
    wedge_category TEXT DEFAULT 'reliability_ban_safety',
    displacement_script TEXT,
    status TEXT DEFAULT 'ready',
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.competitor_displacements
    ADD COLUMN IF NOT EXISTS competitor_name TEXT,
    ADD COLUMN IF NOT EXISTS prospect_name TEXT,
    ADD COLUMN IF NOT EXISTS prospect_title TEXT,
    ADD COLUMN IF NOT EXISTS prospect_company TEXT,
    ADD COLUMN IF NOT EXISTS prospect_linkedin_url TEXT,
    ADD COLUMN IF NOT EXISTS signal_source TEXT DEFAULT 'tech_stack_drop',
    ADD COLUMN IF NOT EXISTS signal_detail TEXT,
    ADD COLUMN IF NOT EXISTS estimated_contract_value NUMERIC(12, 2) DEFAULT 18000.00,
    ADD COLUMN IF NOT EXISTS urgency_score INTEGER DEFAULT 88,
    ADD COLUMN IF NOT EXISTS wedge_category TEXT DEFAULT 'reliability_ban_safety',
    ADD COLUMN IF NOT EXISTS displacement_script TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ready',
    ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.vendor_battlecards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    competitor_name TEXT,
    category TEXT DEFAULT 'LinkedIn Automation',
    their_weakness TEXT,
    our_unfair_advantage TEXT,
    kill_shot_question TEXT,
    migration_incentive TEXT,
    win_rate_pct INTEGER DEFAULT 74,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.vendor_battlecards
    ADD COLUMN IF NOT EXISTS competitor_name TEXT,
    ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'LinkedIn Automation',
    ADD COLUMN IF NOT EXISTS their_weakness TEXT,
    ADD COLUMN IF NOT EXISTS our_unfair_advantage TEXT,
    ADD COLUMN IF NOT EXISTS kill_shot_question TEXT,
    ADD COLUMN IF NOT EXISTS migration_incentive TEXT,
    ADD COLUMN IF NOT EXISTS win_rate_pct INTEGER DEFAULT 74,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_competitor_displacements_ws ON public.competitor_displacements(workspace_id, urgency_score DESC);
CREATE INDEX IF NOT EXISTS idx_vendor_battlecards_ws ON public.vendor_battlecards(workspace_id, competitor_name);

-- =========================================================================================
-- 19. AI CALENDAR CONCIERGE & MEETING BOOKING (HORIZON 34C)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.meeting_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    prospect_name TEXT,
    prospect_title TEXT,
    prospect_company TEXT,
    prospect_email TEXT,
    prospect_timezone TEXT DEFAULT 'America/New_York',
    assigned_rep_name TEXT DEFAULT 'Account Executive',
    assigned_rep_email TEXT,
    routing_rule_applied TEXT DEFAULT 'round_robin_weighted',
    proposed_slots JSONB DEFAULT '[]'::jsonb,
    confirmed_slot TIMESTAMPTZ,
    meeting_duration_mins INTEGER DEFAULT 30,
    meeting_link TEXT,
    booking_source TEXT DEFAULT 'in_thread_natural_language',
    show_probability INTEGER DEFAULT 88,
    pre_meeting_brief TEXT,
    no_show_rescue_status TEXT DEFAULT 'armed',
    status TEXT DEFAULT 'confirmed',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.meeting_bookings
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS prospect_name TEXT,
    ADD COLUMN IF NOT EXISTS prospect_title TEXT,
    ADD COLUMN IF NOT EXISTS prospect_company TEXT,
    ADD COLUMN IF NOT EXISTS prospect_email TEXT,
    ADD COLUMN IF NOT EXISTS prospect_timezone TEXT DEFAULT 'America/New_York',
    ADD COLUMN IF NOT EXISTS assigned_rep_name TEXT DEFAULT 'Account Executive',
    ADD COLUMN IF NOT EXISTS assigned_rep_email TEXT,
    ADD COLUMN IF NOT EXISTS routing_rule_applied TEXT DEFAULT 'round_robin_weighted',
    ADD COLUMN IF NOT EXISTS proposed_slots JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS confirmed_slot TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS meeting_duration_mins INTEGER DEFAULT 30,
    ADD COLUMN IF NOT EXISTS meeting_link TEXT,
    ADD COLUMN IF NOT EXISTS booking_source TEXT DEFAULT 'in_thread_natural_language',
    ADD COLUMN IF NOT EXISTS show_probability INTEGER DEFAULT 88,
    ADD COLUMN IF NOT EXISTS pre_meeting_brief TEXT,
    ADD COLUMN IF NOT EXISTS no_show_rescue_status TEXT DEFAULT 'armed',
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'confirmed',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.rep_calendar_availability (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    rep_name TEXT,
    rep_email TEXT,
    calendar_provider TEXT DEFAULT 'google_calendar',
    timezone TEXT DEFAULT 'America/New_York',
    round_robin_weight INTEGER DEFAULT 100,
    meetings_booked_this_week INTEGER DEFAULT 0,
    max_daily_meetings INTEGER DEFAULT 6,
    is_active BOOLEAN DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.rep_calendar_availability
    ADD COLUMN IF NOT EXISTS rep_name TEXT,
    ADD COLUMN IF NOT EXISTS rep_email TEXT,
    ADD COLUMN IF NOT EXISTS calendar_provider TEXT DEFAULT 'google_calendar',
    ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'America/New_York',
    ADD COLUMN IF NOT EXISTS round_robin_weight INTEGER DEFAULT 100,
    ADD COLUMN IF NOT EXISTS meetings_booked_this_week INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_daily_meetings INTEGER DEFAULT 6,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_meeting_bookings_ws ON public.meeting_bookings(workspace_id, confirmed_slot DESC);
CREATE INDEX IF NOT EXISTS idx_rep_calendar_ws ON public.rep_calendar_availability(workspace_id, is_active);

-- =========================================================================================
-- 20. MULTI-VENDOR WATERFALL ENRICHMENT & EMAIL WARMUP SWARM
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.waterfall_enrichment_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    full_name TEXT,
    company_name TEXT,
    company_domain TEXT,
    linkedin_url TEXT,
    work_email TEXT,
    email_verification_status TEXT DEFAULT 'verified_safe',
    direct_phone TEXT,
    winning_email_vendor TEXT,
    winning_phone_vendor TEXT,
    provider_trace JSONB DEFAULT '[]'::jsonb,
    credits_charged INTEGER DEFAULT 1,
    latency_ms INTEGER DEFAULT 640,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.waterfall_enrichment_runs
    ADD COLUMN IF NOT EXISTS lead_id UUID,
    ADD COLUMN IF NOT EXISTS full_name TEXT,
    ADD COLUMN IF NOT EXISTS company_name TEXT,
    ADD COLUMN IF NOT EXISTS company_domain TEXT,
    ADD COLUMN IF NOT EXISTS linkedin_url TEXT,
    ADD COLUMN IF NOT EXISTS work_email TEXT,
    ADD COLUMN IF NOT EXISTS email_verification_status TEXT DEFAULT 'verified_safe',
    ADD COLUMN IF NOT EXISTS direct_phone TEXT,
    ADD COLUMN IF NOT EXISTS winning_email_vendor TEXT,
    ADD COLUMN IF NOT EXISTS winning_phone_vendor TEXT,
    ADD COLUMN IF NOT EXISTS provider_trace JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS credits_charged INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS latency_ms INTEGER DEFAULT 640,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.vendor_enrichment_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    vendor_id TEXT,
    vendor_name TEXT,
    waterfall_priority INTEGER DEFAULT 1,
    data_type TEXT DEFAULT 'work_email',
    hit_rate_pct INTEGER DEFAULT 68,
    avg_latency_ms INTEGER DEFAULT 420,
    cost_credits INTEGER DEFAULT 1,
    is_enabled BOOLEAN DEFAULT true,
    byok_configured BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.vendor_enrichment_configs
    ADD COLUMN IF NOT EXISTS vendor_id TEXT,
    ADD COLUMN IF NOT EXISTS vendor_name TEXT,
    ADD COLUMN IF NOT EXISTS waterfall_priority INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS data_type TEXT DEFAULT 'work_email',
    ADD COLUMN IF NOT EXISTS hit_rate_pct INTEGER DEFAULT 68,
    ADD COLUMN IF NOT EXISTS avg_latency_ms INTEGER DEFAULT 420,
    ADD COLUMN IF NOT EXISTS cost_credits INTEGER DEFAULT 1,
    ADD COLUMN IF NOT EXISTS is_enabled BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS byok_configured BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_waterfall_runs_ws ON public.waterfall_enrichment_runs(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vendor_configs_ws ON public.vendor_enrichment_configs(workspace_id, waterfall_priority ASC);

CREATE TABLE IF NOT EXISTS public.warmup_mailboxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    email_address TEXT,
    domain TEXT,
    provider TEXT DEFAULT 'google_workspace',
    warmup_status TEXT DEFAULT 'active',
    deliverability_score INTEGER DEFAULT 94,
    daily_warmup_volume INTEGER DEFAULT 35,
    ramp_up_increment INTEGER DEFAULT 3,
    max_warmup_cap INTEGER DEFAULT 50,
    inbox_placement_pct NUMERIC(5, 2) DEFAULT 96.40,
    spam_rescued_last_7d INTEGER DEFAULT 14,
    spf_valid BOOLEAN DEFAULT true,
    dkim_valid BOOLEAN DEFAULT true,
    dmarc_policy TEXT DEFAULT 'p=quarantine',
    bimi_configured BOOLEAN DEFAULT false,
    blacklist_status TEXT DEFAULT 'clean',
    last_audit_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.warmup_mailboxes
    ADD COLUMN IF NOT EXISTS email_address TEXT,
    ADD COLUMN IF NOT EXISTS domain TEXT,
    ADD COLUMN IF NOT EXISTS provider TEXT DEFAULT 'google_workspace',
    ADD COLUMN IF NOT EXISTS warmup_status TEXT DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS deliverability_score INTEGER DEFAULT 94,
    ADD COLUMN IF NOT EXISTS daily_warmup_volume INTEGER DEFAULT 35,
    ADD COLUMN IF NOT EXISTS ramp_up_increment INTEGER DEFAULT 3,
    ADD COLUMN IF NOT EXISTS max_warmup_cap INTEGER DEFAULT 50,
    ADD COLUMN IF NOT EXISTS inbox_placement_pct NUMERIC(5, 2) DEFAULT 96.40,
    ADD COLUMN IF NOT EXISTS spam_rescued_last_7d INTEGER DEFAULT 14,
    ADD COLUMN IF NOT EXISTS spf_valid BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS dkim_valid BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS dmarc_policy TEXT DEFAULT 'p=quarantine',
    ADD COLUMN IF NOT EXISTS bimi_configured BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS blacklist_status TEXT DEFAULT 'clean',
    ADD COLUMN IF NOT EXISTS last_audit_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.mailbox_dns_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    domain TEXT,
    spf_record TEXT,
    dkim_selector TEXT DEFAULT 'google',
    dmarc_record TEXT,
    mx_provider TEXT DEFAULT 'Google Workspace',
    health_grade TEXT DEFAULT 'A+',
    recommendations JSONB DEFAULT '[]'::jsonb,
    audited_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.mailbox_dns_audits
    ADD COLUMN IF NOT EXISTS domain TEXT,
    ADD COLUMN IF NOT EXISTS spf_record TEXT,
    ADD COLUMN IF NOT EXISTS dkim_selector TEXT DEFAULT 'google',
    ADD COLUMN IF NOT EXISTS dmarc_record TEXT,
    ADD COLUMN IF NOT EXISTS mx_provider TEXT DEFAULT 'Google Workspace',
    ADD COLUMN IF NOT EXISTS health_grade TEXT DEFAULT 'A+',
    ADD COLUMN IF NOT EXISTS recommendations JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS audited_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_warmup_mailboxes_ws ON public.warmup_mailboxes(workspace_id, deliverability_score DESC);
CREATE INDEX IF NOT EXISTS idx_mailbox_dns_audits_ws ON public.mailbox_dns_audits(workspace_id, domain);

-- =========================================================================================
-- 21. BI-DIRECTIONAL CRM DEAL SYNC & ATTRIBUTION (HORIZON 33)
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.crm_account_sync_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    crm_provider TEXT DEFAULT 'hubspot',
    connection_status TEXT DEFAULT 'connected',
    bi_directional_enabled BOOLEAN DEFAULT true,
    auto_create_deals_on_positive_reply BOOLEAN DEFAULT true,
    auto_log_linkedin_messages BOOLEAN DEFAULT true,
    auto_pause_outbound_on_stage_change BOOLEAN DEFAULT true,
    stage_mapping JSONB DEFAULT '{}'::jsonb,
    field_mapping JSONB DEFAULT '[]'::jsonb,
    last_synced_at TIMESTAMPTZ DEFAULT NOW(),
    total_contacts_synced INTEGER DEFAULT 0,
    total_deals_attributed INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.crm_account_sync_mappings
    ADD COLUMN IF NOT EXISTS crm_provider TEXT DEFAULT 'hubspot',
    ADD COLUMN IF NOT EXISTS connection_status TEXT DEFAULT 'connected',
    ADD COLUMN IF NOT EXISTS bi_directional_enabled BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS auto_create_deals_on_positive_reply BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS auto_log_linkedin_messages BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS auto_pause_outbound_on_stage_change BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS stage_mapping JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS field_mapping JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS total_contacts_synced INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_deals_attributed INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.deal_attributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    crm_deal_id TEXT,
    deal_name TEXT,
    company_name TEXT,
    contact_name TEXT,
    deal_stage TEXT DEFAULT 'Appointment Scheduled',
    deal_amount NUMERIC(12, 2) DEFAULT 24000.00,
    attribution_model TEXT DEFAULT 'multi_touch_w_shaped',
    first_touch_channel TEXT DEFAULT 'LinkedIn Connection Note',
    converting_touch_channel TEXT DEFAULT 'AI Inbox Rebuttal',
    campaign_name TEXT,
    touchpoints_count INTEGER DEFAULT 5,
    touchpoint_timeline JSONB DEFAULT '[]'::jsonb,
    closed_won BOOLEAN DEFAULT false,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.deal_attributions
    ADD COLUMN IF NOT EXISTS crm_deal_id TEXT,
    ADD COLUMN IF NOT EXISTS deal_name TEXT,
    ADD COLUMN IF NOT EXISTS company_name TEXT,
    ADD COLUMN IF NOT EXISTS contact_name TEXT,
    ADD COLUMN IF NOT EXISTS deal_stage TEXT DEFAULT 'Appointment Scheduled',
    ADD COLUMN IF NOT EXISTS deal_amount NUMERIC(12, 2) DEFAULT 24000.00,
    ADD COLUMN IF NOT EXISTS attribution_model TEXT DEFAULT 'multi_touch_w_shaped',
    ADD COLUMN IF NOT EXISTS first_touch_channel TEXT DEFAULT 'LinkedIn Connection Note',
    ADD COLUMN IF NOT EXISTS converting_touch_channel TEXT DEFAULT 'AI Inbox Rebuttal',
    ADD COLUMN IF NOT EXISTS campaign_name TEXT,
    ADD COLUMN IF NOT EXISTS touchpoints_count INTEGER DEFAULT 5,
    ADD COLUMN IF NOT EXISTS touchpoint_timeline JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS closed_won BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.crm_sync_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    crm_provider TEXT DEFAULT 'hubspot',
    direction TEXT DEFAULT 'outbound_to_crm',
    entity_type TEXT DEFAULT 'deal_stage',
    record_name TEXT,
    action_summary TEXT,
    status TEXT DEFAULT 'success',
    latency_ms INTEGER DEFAULT 180,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.crm_sync_logs
    ADD COLUMN IF NOT EXISTS crm_provider TEXT DEFAULT 'hubspot',
    ADD COLUMN IF NOT EXISTS direction TEXT DEFAULT 'outbound_to_crm',
    ADD COLUMN IF NOT EXISTS entity_type TEXT DEFAULT 'deal_stage',
    ADD COLUMN IF NOT EXISTS record_name TEXT,
    ADD COLUMN IF NOT EXISTS action_summary TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'success',
    ADD COLUMN IF NOT EXISTS latency_ms INTEGER DEFAULT 180,
    ADD COLUMN IF NOT EXISTS synced_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_crm_mappings_ws ON public.crm_account_sync_mappings(workspace_id, crm_provider);
CREATE INDEX IF NOT EXISTS idx_deal_attributions_ws ON public.deal_attributions(workspace_id, deal_amount DESC);
CREATE INDEX IF NOT EXISTS idx_crm_sync_logs_ws ON public.crm_sync_logs(workspace_id, synced_at DESC);

-- =========================================================================================
-- 22. EMPLOYEE ADVOCACY, VIRAL PODS, ROI CERTIFICATES & AGENCY SUITE
-- =========================================================================================
CREATE TABLE IF NOT EXISTS public.advocacy_pods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    name TEXT,
    description TEXT DEFAULT '',
    auto_like_enabled BOOLEAN DEFAULT true,
    auto_comment_enabled BOOLEAN DEFAULT true,
    auto_repost_enabled BOOLEAN DEFAULT false,
    stagger_window_minutes INTEGER DEFAULT 45,
    persona_diversity_mode TEXT DEFAULT 'role_contextual',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.advocacy_pods
    ADD COLUMN IF NOT EXISTS name TEXT,
    ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS auto_like_enabled BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS auto_comment_enabled BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS auto_repost_enabled BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS stagger_window_minutes INTEGER DEFAULT 45,
    ADD COLUMN IF NOT EXISTS persona_diversity_mode TEXT DEFAULT 'role_contextual',
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.advocacy_pod_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pod_id UUID NOT NULL,
    workspace_id UUID NOT NULL,
    account_id TEXT NOT NULL,
    member_name TEXT,
    member_title TEXT DEFAULT 'Team Member',
    voice_style TEXT DEFAULT 'insightful_operator',
    daily_engagement_cap INTEGER DEFAULT 15,
    engagements_today INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(pod_id, account_id)
);

ALTER TABLE IF EXISTS public.advocacy_pod_members
    ADD COLUMN IF NOT EXISTS pod_id UUID,
    ADD COLUMN IF NOT EXISTS account_id TEXT,
    ADD COLUMN IF NOT EXISTS member_name TEXT,
    ADD COLUMN IF NOT EXISTS member_title TEXT DEFAULT 'Team Member',
    ADD COLUMN IF NOT EXISTS voice_style TEXT DEFAULT 'insightful_operator',
    ADD COLUMN IF NOT EXISTS daily_engagement_cap INTEGER DEFAULT 15,
    ADD COLUMN IF NOT EXISTS engagements_today INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.advocacy_post_boosts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    pod_id UUID NOT NULL,
    author_account_id TEXT,
    author_name TEXT,
    post_url TEXT,
    post_topic TEXT,
    post_excerpt TEXT DEFAULT '',
    status TEXT DEFAULT 'boosting',
    target_engagements INTEGER DEFAULT 10,
    completed_engagements INTEGER DEFAULT 0,
    estimated_reach_multiplier NUMERIC(5,2) DEFAULT 1.00,
    impressions_generated INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    golden_hour_deadline TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.advocacy_post_boosts
    ADD COLUMN IF NOT EXISTS pod_id UUID,
    ADD COLUMN IF NOT EXISTS author_account_id TEXT,
    ADD COLUMN IF NOT EXISTS author_name TEXT,
    ADD COLUMN IF NOT EXISTS post_url TEXT,
    ADD COLUMN IF NOT EXISTS post_topic TEXT,
    ADD COLUMN IF NOT EXISTS post_excerpt TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'boosting',
    ADD COLUMN IF NOT EXISTS target_engagements INTEGER DEFAULT 10,
    ADD COLUMN IF NOT EXISTS completed_engagements INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS estimated_reach_multiplier NUMERIC(5,2) DEFAULT 1.00,
    ADD COLUMN IF NOT EXISTS impressions_generated INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS likes_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS comments_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS golden_hour_deadline TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE TABLE IF NOT EXISTS public.advocacy_engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    post_boost_id UUID NOT NULL,
    account_id TEXT,
    action_type TEXT,
    reaction_type TEXT DEFAULT 'LIKE',
    comment_text TEXT DEFAULT '',
    scheduled_at TIMESTAMPTZ DEFAULT NOW(),
    executed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'queued',
    failure_reason TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE IF EXISTS public.advocacy_engagements
    ADD COLUMN IF NOT EXISTS post_boost_id UUID,
    ADD COLUMN IF NOT EXISTS account_id TEXT,
    ADD COLUMN IF NOT EXISTS action_type TEXT,
    ADD COLUMN IF NOT EXISTS reaction_type TEXT DEFAULT 'LIKE',
    ADD COLUMN IF NOT EXISTS comment_text TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'queued',
    ADD COLUMN IF NOT EXISTS failure_reason TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_advocacy_pods_ws ON public.advocacy_pods(workspace_id, is_active);
CREATE INDEX IF NOT EXISTS idx_advocacy_members_pod ON public.advocacy_pod_members(pod_id, is_active);
CREATE INDEX IF NOT EXISTS idx_advocacy_boosts_ws ON public.advocacy_post_boosts(workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_advocacy_engagements_boost ON public.advocacy_engagements(post_boost_id, status);

CREATE TABLE IF NOT EXISTS public.campaign_roi_certificates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token TEXT UNIQUE,
    verification_token TEXT,
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    campaign_display_name TEXT,
    agency_brand_name TEXT DEFAULT 'Ele-in Outbound Engine',
    agency_logo_url TEXT DEFAULT NULL,
    theme_color TEXT DEFAULT '#2563eb',
    anonymize_client BOOLEAN DEFAULT FALSE,
    metrics_snapshot JSONB DEFAULT '{}'::jsonb,
    views_count INTEGER DEFAULT 0,
    is_revoked BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMPTZ DEFAULT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.campaign_roi_certificates
    ADD COLUMN IF NOT EXISTS token TEXT,
    ADD COLUMN IF NOT EXISTS verification_token TEXT,
    ADD COLUMN IF NOT EXISTS campaign_display_name TEXT,
    ADD COLUMN IF NOT EXISTS agency_brand_name TEXT DEFAULT 'Ele-in Outbound Engine',
    ADD COLUMN IF NOT EXISTS agency_logo_url TEXT,
    ADD COLUMN IF NOT EXISTS theme_color TEXT DEFAULT '#2563eb',
    ADD COLUMN IF NOT EXISTS anonymize_client BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS metrics_snapshot JSONB DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS views_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_revoked BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_roi_certificates_token ON public.campaign_roi_certificates(token);
CREATE INDEX IF NOT EXISTS idx_roi_certificates_workspace ON public.campaign_roi_certificates(workspace_id, created_at DESC);

ALTER TABLE IF EXISTS public.agencies
    ADD COLUMN IF NOT EXISTS whitelabel_brand TEXT DEFAULT 'Ele-in Agency',
    ADD COLUMN IF NOT EXISTS whitelabel_domain TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS whitelabel_color TEXT DEFAULT '#2563eb',
    ADD COLUMN IF NOT EXISTS whitelabel_logo_url TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS whitelabel_enabled BOOLEAN DEFAULT true;

CREATE TABLE IF NOT EXISTS public.agency_credit_delegations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agency_id UUID NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
    from_workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    to_workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    actor_user_id UUID NOT NULL,
    amount INTEGER NOT NULL,
    direction TEXT NOT NULL,
    note TEXT,
    idempotency_key TEXT UNIQUE,
    from_balance_after INTEGER NOT NULL,
    to_balance_after INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.agency_credit_delegations
    ADD COLUMN IF NOT EXISTS agency_id UUID,
    ADD COLUMN IF NOT EXISTS from_workspace_id UUID,
    ADD COLUMN IF NOT EXISTS to_workspace_id UUID,
    ADD COLUMN IF NOT EXISTS actor_user_id UUID,
    ADD COLUMN IF NOT EXISTS amount INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS direction TEXT DEFAULT 'allocate',
    ADD COLUMN IF NOT EXISTS note TEXT,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
    ADD COLUMN IF NOT EXISTS from_balance_after INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS to_balance_after INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_agency_credit_delegations_agency ON public.agency_credit_delegations(agency_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.agency_billing_statements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    statement_number TEXT NOT NULL UNIQUE,
    agency_id UUID NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
    client_workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    client_name TEXT,
    period_start DATE,
    period_end DATE,
    retainer_fee_usd NUMERIC(10,2) DEFAULT 0.00,
    credits_allocated INTEGER DEFAULT 0,
    credits_consumed INTEGER DEFAULT 0,
    overdraft_credits INTEGER DEFAULT 0,
    overdraft_rate_usd NUMERIC(10,4) DEFAULT 0.0500,
    total_amount_usd NUMERIC(10,2) DEFAULT 0.00,
    currency TEXT DEFAULT 'USD',
    status TEXT DEFAULT 'draft',
    line_items JSONB DEFAULT '[]'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE IF EXISTS public.agency_billing_statements
    ADD COLUMN IF NOT EXISTS statement_number TEXT,
    ADD COLUMN IF NOT EXISTS agency_id UUID,
    ADD COLUMN IF NOT EXISTS client_workspace_id UUID,
    ADD COLUMN IF NOT EXISTS client_name TEXT,
    ADD COLUMN IF NOT EXISTS period_start DATE,
    ADD COLUMN IF NOT EXISTS period_end DATE,
    ADD COLUMN IF NOT EXISTS retainer_fee_usd NUMERIC(10,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS credits_allocated INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS credits_consumed INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS overdraft_credits INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS overdraft_rate_usd NUMERIC(10,4) DEFAULT 0.0500,
    ADD COLUMN IF NOT EXISTS total_amount_usd NUMERIC(10,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USD',
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS line_items JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS notes TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_agency_statements_agency ON public.agency_billing_statements(agency_id, created_at DESC);

-- =========================================================================================
-- 23. ATOMIC STORED PROCEDURES (RPC FUNCTIONS)
-- =========================================================================================

-- 23.1 Add Credits Safely (UUID overload returning JSONB)
CREATE OR REPLACE FUNCTION public.add_credits_safely(
    p_workspace_id UUID,
    p_credits INT,
    p_event_id TEXT,
    p_provider TEXT
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_current_balance INT;
    v_new_balance INT;
    v_already_processed BOOLEAN;
BEGIN
    SELECT data_cleaning_credits INTO v_current_balance
    FROM public.workspaces
    WHERE id = p_workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'balance', 0, 'reason', 'workspace_not_found');
    END IF;

    v_current_balance := COALESCE(v_current_balance, 0);

    SELECT EXISTS (
        SELECT 1 FROM public.billing_transactions WHERE provider_tx_id = p_event_id
    ) INTO v_already_processed;

    IF v_already_processed THEN
        RETURN jsonb_build_object(
            'success', true,
            'balance', v_current_balance,
            'already_processed', true,
            'reason', 'event_already_processed'
        );
    END IF;

    v_new_balance := v_current_balance + p_credits;

    UPDATE public.workspaces
    SET data_cleaning_credits = v_new_balance, updated_at = NOW()
    WHERE id = p_workspace_id;

    INSERT INTO public.billing_transactions (
        workspace_id, amount, currency, status, provider, provider_tx_id, metadata
    ) VALUES (
        p_workspace_id, p_credits::numeric, 'usd', 'succeeded', p_provider, p_event_id,
        jsonb_build_object('credits_added', p_credits)
    );

    RETURN jsonb_build_object(
        'success', true, 'balance', v_new_balance, 'added', p_credits, 'already_processed', false
    );
END;
$$;

-- 23.2 Deduct Credits Safely (UUID overload with Idempotency Ledger)
CREATE OR REPLACE FUNCTION public.deduct_credits_safely(
    p_workspace_id UUID,
    p_amount INT,
    p_action_type TEXT,
    p_idempotency_key TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_current_balance INT;
    v_new_balance INT;
    v_existing RECORD;
BEGIN
    IF p_amount < 0 THEN
        RAISE EXCEPTION 'Credit deduction amount must be non-negative (got %)', p_amount;
    END IF;

    IF p_amount = 0 THEN
        SELECT COALESCE(data_cleaning_credits, 0) INTO v_current_balance
        FROM public.workspaces WHERE id = p_workspace_id;
        RETURN jsonb_build_object('success', true, 'balance', COALESCE(v_current_balance, 0), 'deducted', 0, 'already_processed', false);
    END IF;

    SELECT data_cleaning_credits INTO v_current_balance
    FROM public.workspaces WHERE id = p_workspace_id FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'balance', 0, 'error', 'workspace_not_found');
    END IF;

    v_current_balance := COALESCE(v_current_balance, 0);

    IF p_idempotency_key IS NOT NULL AND length(trim(p_idempotency_key)) > 0 THEN
        SELECT amount, balance_after INTO v_existing
        FROM public.credit_deductions WHERE idempotency_key = p_idempotency_key;

        IF FOUND THEN
            RETURN jsonb_build_object('success', true, 'balance', v_current_balance, 'deducted', v_existing.amount, 'already_processed', true);
        END IF;
    END IF;

    IF v_current_balance < p_amount THEN
        RETURN jsonb_build_object(
            'success', false, 'balance', v_current_balance, 'required', p_amount,
            'shortfall', (p_amount - v_current_balance), 'error', 'insufficient_credits'
        );
    END IF;

    v_new_balance := v_current_balance - p_amount;

    UPDATE public.workspaces
    SET data_cleaning_credits = v_new_balance, updated_at = NOW()
    WHERE id = p_workspace_id;

    IF p_idempotency_key IS NOT NULL AND length(trim(p_idempotency_key)) > 0 THEN
        INSERT INTO public.credit_deductions (
            workspace_id, action_type, amount, balance_after, idempotency_key, metadata
        ) VALUES (
            p_workspace_id, p_action_type, p_amount, v_new_balance, p_idempotency_key, COALESCE(p_metadata, '{}'::jsonb)
        );
    END IF;

    RETURN jsonb_build_object('success', true, 'balance', v_new_balance, 'deducted', p_amount, 'already_processed', false);
END;
$$;

-- 23.3 Record Bayesian ICP Outcome (Matches existing live signature)
CREATE OR REPLACE FUNCTION public.record_bayesian_icp_outcome(
    p_workspace_id uuid,
    p_signal_name text,
    p_outcome text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_alpha integer;
    v_beta integer;
BEGIN
    INSERT INTO public.icp_signal_weights (workspace_id, signal_name, prior_alpha, prior_beta)
    VALUES (p_workspace_id, p_signal_name, 2, 2)
    ON CONFLICT (workspace_id, signal_name) DO NOTHING;

    SELECT prior_alpha, prior_beta INTO v_alpha, v_beta
    FROM public.icp_signal_weights
    WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;

    IF (COALESCE(v_alpha, 2) + COALESCE(v_beta, 2)) >= 200 THEN
        UPDATE public.icp_signal_weights
        SET prior_alpha = GREATEST(2, (prior_alpha * 0.5)::integer),
            prior_beta = GREATEST(2, (prior_beta * 0.5)::integer),
            updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    END IF;

    IF p_outcome = 'won' THEN
        UPDATE public.icp_signal_weights
        SET prior_alpha = prior_alpha + 1, updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    ELSIF p_outcome = 'lost' THEN
        UPDATE public.icp_signal_weights
        SET prior_beta = prior_beta + 1, updated_at = now()
        WHERE workspace_id = p_workspace_id AND signal_name = p_signal_name;
    END IF;
END;
$$;

-- =========================================================================================
-- 24. ROW-LEVEL SECURITY (RLS) ENFORCEMENT ACROSS ALL SESSION TABLES
-- =========================================================================================
ALTER TABLE IF EXISTS public.billing_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.checkout_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.credit_deductions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.credit_action_costs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.outbox_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.suppression_list ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.sender_pods ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.sender_pod_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.proxies ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.action_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.approval_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.webhook_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.lead_objections ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.knowledge_synthesis ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.knowledge_synthesis_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.knowledge_objections ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.icp_signal_weights ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.icp_feedback_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.social_signal_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.lead_social_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.lead_social_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.bandit_experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.copy_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.trigger_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.lead_prewarm_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.omnichannel_fallback_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.omnichannel_cascade_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.thought_leadership_posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.harvested_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.event_attendees ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.multimodal_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.target_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.account_committee_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.multithread_campaign_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.champion_job_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.warm_intro_paths ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.closed_lost_revivals ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.competitor_displacements ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.vendor_battlecards ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.meeting_bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.rep_calendar_availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.waterfall_enrichment_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.vendor_enrichment_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.warmup_mailboxes ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.mailbox_dns_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.crm_account_sync_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.deal_attributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.crm_sync_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.advocacy_pods ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.advocacy_pod_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.advocacy_post_boosts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.advocacy_engagements ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.campaign_roi_certificates ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.agency_credit_delegations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.agency_billing_statements ENABLE ROW LEVEL SECURITY;

-- Universal Idempotent Multi-Tenant Isolation Policy Generator
DO $$
DECLARE
    tbl TEXT;
    pol_name TEXT;
    session_tables TEXT[] := ARRAY[
        'billing_transactions', 'checkout_sessions', 'credit_deductions',
        'outbox_events', 'suppression_list', 'sender_pods', 'sender_pod_accounts',
        'proxies', 'action_log', 'approval_queue', 'webhook_endpoints',
        'webhook_deliveries', 'lead_objections', 'knowledge_synthesis',
        'knowledge_synthesis_drafts', 'knowledge_objections', 'icp_signal_weights',
        'icp_feedback_events', 'social_signal_cache', 'lead_social_posts',
        'lead_social_signals', 'bandit_experiments', 'copy_variants',
        'trigger_events', 'lead_prewarm_events', 'omnichannel_fallback_configs',
        'omnichannel_cascade_logs', 'thought_leadership_posts', 'harvested_events',
        'event_attendees', 'multimodal_assets', 'target_accounts',
        'account_committee_members', 'multithread_campaign_runs',
        'champion_job_changes', 'warm_intro_paths', 'closed_lost_revivals',
        'competitor_displacements', 'vendor_battlecards', 'meeting_bookings',
        'rep_calendar_availability', 'waterfall_enrichment_runs',
        'vendor_enrichment_configs', 'warmup_mailboxes', 'mailbox_dns_audits',
        'crm_account_sync_mappings', 'deal_attributions', 'crm_sync_logs',
        'advocacy_pods', 'advocacy_pod_members', 'advocacy_post_boosts',
        'advocacy_engagements', 'campaign_roi_certificates'
    ];
BEGIN
    FOREACH tbl IN ARRAY session_tables LOOP
        pol_name := tbl || '_ws_isolation_policy';
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = tbl AND policyname = pol_name
        ) THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR ALL USING (workspace_id::text IN (SELECT public.my_workspace_ids()::text) OR auth.role() = ''service_role'')',
                pol_name, tbl
            );
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'credit_action_costs' AND policyname = 'credit_action_costs_read_policy'
    ) THEN
        CREATE POLICY credit_action_costs_read_policy ON public.credit_action_costs
            FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'agency_credit_delegations' AND policyname = 'agency_credit_delegations_ws_policy'
    ) THEN
        CREATE POLICY agency_credit_delegations_ws_policy ON public.agency_credit_delegations
            FOR ALL USING (
                from_workspace_id::text IN (SELECT public.my_workspace_ids()::text)
                OR to_workspace_id::text IN (SELECT public.my_workspace_ids()::text)
                OR auth.role() = 'service_role'
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'public' AND tablename = 'agency_billing_statements' AND policyname = 'agency_billing_statements_ws_policy'
    ) THEN
        CREATE POLICY agency_billing_statements_ws_policy ON public.agency_billing_statements
            FOR ALL USING (
                client_workspace_id::text IN (SELECT public.my_workspace_ids()::text)
                OR auth.role() = 'service_role'
            );
    END IF;
END $$;

COMMIT;
