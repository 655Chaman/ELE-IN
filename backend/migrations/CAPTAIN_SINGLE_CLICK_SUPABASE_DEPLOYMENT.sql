-- =========================================================================================
-- ELE-IN: CAPTAIN MASTER SINGLE-CLICK SUPABASE DEPLOYMENT SCRIPT (REVISED)
-- =========================================================================================
-- Purpose: Complete, 100% idempotent database migration combining all session foundations,
-- campaign subsystem paranoia hardening, and leads data integrity repairs.
-- Includes pre-flight cleanup that prevents PostgreSQL error 42P13 (cannot change name of input parameter).
--
-- Instructions for Captain:
-- 1. Open your Supabase Dashboard: https://supabase.com/dashboard/project/_/sql
-- 2. Click 'New query' in the SQL Editor.
-- 3. Copy and paste this ENTIRE file into the editor.
-- 4. Click 'Run' (or press Cmd+Enter / Ctrl+Enter).
-- 5. Run the Verification Queries at the bottom to confirm 100% green status.
-- =========================================================================================

-- PRE-FLIGHT RPC CLEANUP: Safely drop any legacy overloads to prevent 42P13 parameter rename conflicts
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN 
        SELECT oid::regprocedure AS func_sig 
        FROM pg_proc 
        WHERE proname IN (
            'bulk_import_leads', 
            'bulk_import_leads_atomic', 
            'dequeue_due_leads',
            'release_lead_claim',
            'recover_stale_leases',
            'advance_reply_waiting_leads',
            'create_campaign_atomic',
            'enroll_leads_chunk_atomic',
            'add_credits_safely',
            'deduct_credits_safely',
            'record_bayesian_icp_outcome',
            'claim_processing_jobs',
            'decrement_list_row_count',
            'claim_outbox_events',
            'set_outbox_events_updated_at',
            'update_daily_campaign_stats'
        )
        AND pronamespace = 'public'::regnamespace
    LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS ' || r.func_sig || ' CASCADE';
    END LOOP;
END $$;



-- =========================================================================================
-- SECTION FROM: chat_session_complete_consolidated.sql
-- =========================================================================================

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
ALTER TYPE public.outbox_event_status ADD VALUE IF NOT EXISTS 'sent';
ALTER TYPE public.outbox_event_status ADD VALUE IF NOT EXISTS 'completed';
ALTER TYPE public.proxy_status ADD VALUE IF NOT EXISTS 'active';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'draft';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'active';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'paused';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'completed';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'archived';
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


-- =========================================================================================
-- SECTION FROM: 100_campaign_subsystem_paranoia_hardening.sql
-- =========================================================================================

-- ==============================================================================
-- Migration 100: Campaign Subsystem Paranoia Hardening
-- Resolves: VULN-16, VULN-17, VULN-18, VULN-19, DB-01 through DB-16
-- Applies the Three-Layer Logic Architecture (Paranoia Framework) across RLS, RPCs, 
-- Relational Cascades, Missing Indexes, and State Transitions.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Campaign Versions Row Level Security (VULN-19, DB-02)
-- ------------------------------------------------------------------------------
ALTER TABLE public.campaign_versions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    DROP POLICY IF EXISTS campaign_versions_tenant_isolation ON public.campaign_versions;
    CREATE POLICY campaign_versions_tenant_isolation ON public.campaign_versions
    FOR ALL USING (
        campaign_id IN (
            SELECT id FROM public.campaigns 
            WHERE workspace_id IN (SELECT public.my_workspace_ids())
        )
    )
    WITH CHECK (
        campaign_id IN (
            SELECT id FROM public.campaigns 
            WHERE workspace_id IN (SELECT public.my_workspace_ids())
        )
    );
END $$;


-- ------------------------------------------------------------------------------
-- 2. Campaign Accounts Tenant Check Hardening (DB-13)
-- Ensures both campaign_id AND account_id belong to the caller's workspace
-- ------------------------------------------------------------------------------
DO $$ BEGIN
    DROP POLICY IF EXISTS campaign_accounts_tenant_isolation ON public.campaign_accounts;
    DROP POLICY IF EXISTS campaign_accounts_isolation ON public.campaign_accounts;
    DROP POLICY IF EXISTS campaign_accounts_ws ON public.campaign_accounts;

    CREATE POLICY campaign_accounts_tenant_isolation ON public.campaign_accounts
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.campaigns c
            JOIN public.accounts a ON a.workspace_id = c.workspace_id
            WHERE c.id = campaign_accounts.campaign_id
              AND a.id = campaign_accounts.account_id
              AND c.workspace_id IN (SELECT public.my_workspace_ids())
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.campaigns c
            JOIN public.accounts a ON a.workspace_id = c.workspace_id
            WHERE c.id = campaign_accounts.campaign_id
              AND a.id = campaign_accounts.account_id
              AND c.workspace_id IN (SELECT public.my_workspace_ids())
        )
    );

    -- processing_jobs: Multi-workspace support (VULN-20)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'processing_jobs') THEN
        ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS processing_jobs_tenant_isolation ON public.processing_jobs;
        CREATE POLICY processing_jobs_tenant_isolation ON public.processing_jobs
        FOR ALL USING (
            workspace_id IN (SELECT public.my_workspace_ids())
        )
        WITH CHECK (
            workspace_id IN (SELECT public.my_workspace_ids())
        );
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- 3. Revoke Dangerous Public RPC Execution Privileges (VULN-16, VULN-17, VULN-18)
-- ------------------------------------------------------------------------------
DO $$ 
DECLARE
    r RECORD;
BEGIN
    -- Dynamically revoke EXECUTE on ALL overloads of sensitive RPCs from PUBLIC, anon, authenticated (VULN-16, VULN-17, VULN-18)
    FOR r IN 
        SELECT oid::regprocedure AS func_sig 
        FROM pg_proc 
        WHERE proname IN ('deduct_credits_safely', 'bulk_import_leads', 'get_user_id_by_email')
          AND pronamespace = 'public'::regnamespace
    LOOP
        EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || r.func_sig || ' FROM PUBLIC';
        EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || r.func_sig || ' FROM anon, authenticated';
        EXECUTE 'GRANT EXECUTE ON FUNCTION ' || r.func_sig || ' TO service_role';
    END LOOP;

    -- try_acquire_distributed_lock & release_distributed_lock
    FOR r IN 
        SELECT oid::regprocedure AS func_sig 
        FROM pg_proc 
        WHERE proname IN ('try_acquire_distributed_lock', 'release_distributed_lock')
          AND pronamespace = 'public'::regnamespace
    LOOP
        EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || r.func_sig || ' FROM PUBLIC, anon';
        EXECUTE 'GRANT EXECUTE ON FUNCTION ' || r.func_sig || ' TO authenticated, service_role';
    END LOOP;
END $$;


-- ------------------------------------------------------------------------------
-- 4. Relational Cascade Protections (DB-03, DB-24, DB-25)
-- Prevent account disconnection from destroying in-flight leads & campaign history
-- ------------------------------------------------------------------------------
ALTER TABLE public.campaign_enrollments ALTER COLUMN account_id DROP NOT NULL;

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'campaign_enrollments_account_id_fkey' 
          AND table_name = 'campaign_enrollments'
    ) THEN
        ALTER TABLE public.campaign_enrollments DROP CONSTRAINT campaign_enrollments_account_id_fkey;
    END IF;
    ALTER TABLE public.campaign_enrollments
        ADD CONSTRAINT campaign_enrollments_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE SET NULL;
END $$;

-- Preserve action_log audit trail when an account is deleted
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'action_log_account_id_fkey' 
          AND table_name = 'action_log'
    ) THEN
        ALTER TABLE public.action_log DROP CONSTRAINT action_log_account_id_fkey;
    END IF;
    ALTER TABLE public.action_log
        ADD CONSTRAINT action_log_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE SET NULL;
END $$;

-- Version integrity foreign key cascade
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_enrollment_version_integrity' 
          AND table_name = 'campaign_enrollments'
    ) THEN
        ALTER TABLE public.campaign_enrollments DROP CONSTRAINT fk_enrollment_version_integrity;
        ALTER TABLE public.campaign_enrollments
            ADD CONSTRAINT fk_enrollment_version_integrity
            FOREIGN KEY (campaign_version_id, campaign_id)
            REFERENCES public.campaign_versions (id, campaign_id) ON DELETE CASCADE;
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- 5. Missing Columns & Schema Reconciliations (DB-11, DB-18)
-- ------------------------------------------------------------------------------
-- Add lead_list_id column to campaigns table if missing
ALTER TABLE public.campaigns 
    ADD COLUMN IF NOT EXISTS lead_list_id UUID REFERENCES public.lead_lists(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_campaigns_lead_list_id ON public.campaigns(lead_list_id);

-- Add retry_count column to campaign_execution_states if missing
ALTER TABLE public.campaign_execution_states 
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;


-- ------------------------------------------------------------------------------
-- 6. Uniqueness & Concurrency Integrity (DB-04, DB-05)
-- ------------------------------------------------------------------------------
-- Enforce single enrollment per lead per campaign
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_campaign_lead_enrollment'
    ) THEN
        ALTER TABLE public.campaign_enrollments 
            ADD CONSTRAINT uq_campaign_lead_enrollment UNIQUE (campaign_id, lead_id);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;

-- Enforce single execution state per enrollment to prevent duplicate worker dispatches
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_ces_enrollment_id'
    ) THEN
        ALTER TABLE public.campaign_execution_states 
            ADD CONSTRAINT uq_ces_enrollment_id UNIQUE (enrollment_id);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;


-- ------------------------------------------------------------------------------
-- 7. High-Performance B-Tree Indexes for Scheduler & Webhooks (DB-06, DB-07, DB-15, DB-16)
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_campaign_status 
    ON public.campaign_enrollments (campaign_id, status);

CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_lead_id 
    ON public.campaign_enrollments (lead_id);

CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_account_id 
    ON public.campaign_enrollments (account_id);

CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_workspace_id 
    ON public.campaign_enrollments (workspace_id);

CREATE INDEX IF NOT EXISTS idx_ces_enrollment_id 
    ON public.campaign_execution_states (enrollment_id);

CREATE INDEX IF NOT EXISTS idx_campaigns_workspace_status 
    ON public.campaigns (workspace_id, status);

-- Replace partial index with predicate that covers both 'pending' and 'running'
DROP INDEX IF EXISTS public.idx_ces_next_run;
CREATE INDEX IF NOT EXISTS idx_ces_workspace_status_next_run 
    ON public.campaign_execution_states (workspace_id, next_run_at ASC NULLS FIRST) 
    WHERE status IN ('pending', 'running');


-- ------------------------------------------------------------------------------
-- 8. Hardened Queue Dequeue & Lead Progression RPCs (DB-08, DB-10, DB-20)
-- ------------------------------------------------------------------------------

-- 8a. dequeue_due_leads: Add FOR UPDATE OF ces SKIP LOCKED (eliminates accounts row deadlocks)
CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
    p_batch_size INT DEFAULT 50,
    p_campaign_ids UUID[] DEFAULT NULL,
    p_lease_seconds INT DEFAULT 300
) RETURNS SETOF public.campaign_execution_states
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_token UUID := gen_random_uuid();
    v_expires TIMESTAMPTZ := now() + (p_lease_seconds || ' seconds')::INTERVAL;
BEGIN
    RETURN QUERY
    UPDATE public.campaign_execution_states
    SET 
        lease_token = v_token,
        lease_expires_at = v_expires,
        status = 'running',
        updated_at = now()
    WHERE id IN (
        SELECT ces.id 
        FROM (
            SELECT DISTINCT workspace_id 
            FROM public.campaigns
            WHERE status = 'ACTIVE' 
              AND (p_campaign_ids IS NULL OR id = ANY(p_campaign_ids))
        ) w
        CROSS JOIN LATERAL (
            SELECT ces.id, ces.next_run_at
            FROM public.campaign_execution_states ces
            JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
            JOIN public.accounts a ON a.id = ce.account_id
            WHERE ces.workspace_id = w.workspace_id
              AND ces.status IN ('pending', 'running')
              AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
              AND a.status = 'ACTIVE'
              AND COALESCE(a.manual_send_suspected, false) = false
            ORDER BY ces.next_run_at ASC NULLS FIRST
            LIMIT GREATEST(1, p_batch_size / 5)
        ) ces
        ORDER BY ces.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE OF ces SKIP LOCKED
    )
    RETURNING *;
END;
$$;

-- 8b. release_lead_claim: Remove UUID regex, accept text node IDs, reconcile retry_count
CREATE OR REPLACE FUNCTION public.release_lead_claim(
    p_state_id UUID,
    p_lease_token UUID,
    p_next_status TEXT,
    p_next_node TEXT,
    p_next_run TIMESTAMPTZ,
    p_variables JSONB,
    p_error_reason TEXT,
    p_attempts INT
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = p_next_status,
        current_node_id = COALESCE(p_next_node, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        retry_count = COALESCE(p_attempts, retry_count),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id AND (p_lease_token IS NULL OR lease_token = p_lease_token::TEXT OR lease_token::TEXT = p_lease_token::TEXT);
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

-- 8c. recover_stale_leases: Harden with SECURITY DEFINER
CREATE OR REPLACE FUNCTION public.recover_stale_leases(p_timeout_minutes INT DEFAULT 5)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_recovered integer;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = 'pending',
        lease_token = NULL,
        lease_expires_at = NULL,
        next_run_at = now(),
        updated_at = now()
    WHERE (
        (lease_expires_at IS NOT NULL AND lease_expires_at < now())
        OR 
        (status = 'running' AND updated_at < now() - (p_timeout_minutes || ' minutes')::INTERVAL)
    );
    GET DIAGNOSTICS v_recovered = ROW_COUNT;
    RETURN v_recovered;
END;
$$;

-- 8d. advance_reply_waiting_leads: Order by ID with FOR UPDATE SKIP LOCKED to prevent lock inversion
CREATE OR REPLACE FUNCTION public.advance_reply_waiting_leads(p_lead_id uuid)
RETURNS integer 
LANGUAGE plpgsql 
SECURITY DEFINER 
SET search_path = public
AS $$
DECLARE
    v_state_id uuid;
    v_count integer := 0;
BEGIN
    SELECT ces.id INTO v_state_id
    FROM public.campaign_execution_states ces
    JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
    WHERE ce.lead_id = p_lead_id AND ces.status = 'waiting_for_reply'
    ORDER BY ces.id
    FOR UPDATE OF ces SKIP LOCKED
    LIMIT 1;

    IF v_state_id IS NOT NULL THEN
        UPDATE public.campaign_execution_states
        SET status = 'pending', next_run_at = now(),
            lease_token = NULL, lease_expires_at = NULL, updated_at = now()
        WHERE id = v_state_id;
        v_count := 1;
    END IF;

    RETURN v_count;
END; 
$$;

-- ------------------------------------------------------------------------------
-- 9. Multi-Tenant Workspace Resolution & Processing Jobs RLS (VULN-20)
-- Replaces single-workspace pinning with multi-workspace access check
-- ------------------------------------------------------------------------------
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    DROP POLICY IF EXISTS processing_jobs_tenant_isolation ON public.processing_jobs;
    CREATE POLICY processing_jobs_tenant_isolation ON public.processing_jobs
    FOR ALL USING (
        workspace_id IN (SELECT public.my_workspace_ids())
    )
    WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids())
    );
END $$;


-- ------------------------------------------------------------------------------
-- 10. Atomic Campaign Creation & Bulk Enrollment RPCs (API-01, API-02)
-- Wraps multi-table campaign creation & enrollment in ACID PostgreSQL transactions
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.create_campaign_atomic(
    p_campaign_id UUID,
    p_workspace_id UUID,
    p_name TEXT,
    p_status TEXT,
    p_nodes_json JSONB,
    p_edges_json JSONB,
    p_sender_account_ids_json JSONB,
    p_metadata JSONB,
    p_senders UUID[] DEFAULT '{}'::UUID[]
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_version_id UUID;
    v_sender_id UUID;
BEGIN
    -- Verify caller workspace membership
    IF NOT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
    ) AND auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized: User is not a member of workspace %', p_workspace_id;
    END IF;

    -- 1. Insert Campaign
    INSERT INTO public.campaigns (
        id, workspace_id, name, status, nodes_json, edges_json, sender_account_ids_json, metadata
    ) VALUES (
        p_campaign_id, p_workspace_id, p_name, p_status, p_nodes_json, p_edges_json, p_sender_account_ids_json, p_metadata
    );

    -- 2. Insert Version 1
    v_version_id := gen_random_uuid();
    INSERT INTO public.campaign_versions (id, campaign_id, version)
    VALUES (v_version_id, p_campaign_id, 1);

    -- 3. Insert Accounts
    IF p_senders IS NOT NULL AND array_length(p_senders, 1) > 0 THEN
        FOREACH v_sender_id IN ARRAY p_senders LOOP
            IF EXISTS (SELECT 1 FROM public.accounts WHERE id = v_sender_id AND workspace_id = p_workspace_id) THEN
                INSERT INTO public.campaign_accounts (campaign_id, account_id, weight)
                VALUES (p_campaign_id, v_sender_id, 100)
                ON CONFLICT DO NOTHING;
            END IF;
        END LOOP;
    END IF;

    RETURN jsonb_build_object(
        'campaign_id', p_campaign_id,
        'version_id', v_version_id,
        'status', 'success'
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.enroll_leads_chunk_atomic(
    p_workspace_id UUID,
    p_campaign_id UUID,
    p_enrollments JSONB,
    p_execution_states JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count INT := 0;
BEGIN
    -- Verify caller workspace membership
    IF NOT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
    ) AND auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized: User is not a member of workspace %', p_workspace_id;
    END IF;

    -- Upsert enrollments and execution states atomically
    INSERT INTO public.campaign_enrollments (id, workspace_id, campaign_id, campaign_version_id, lead_id, account_id)
    SELECT
        (e->>'id')::UUID,
        p_workspace_id,
        p_campaign_id,
        (e->>'campaign_version_id')::UUID,
        (e->>'lead_id')::UUID,
        (e->>'account_id')::UUID
    FROM jsonb_array_elements(p_enrollments) AS e
    ON CONFLICT (campaign_id, lead_id) DO NOTHING;

    INSERT INTO public.campaign_execution_states (id, workspace_id, campaign_id, enrollment_id, status, variables)
    SELECT
        (x->>'id')::UUID,
        p_workspace_id,
        p_campaign_id,
        (x->>'enrollment_id')::UUID,
        COALESCE(x->>'status', 'pending'),
        COALESCE(x->'variables', '{}'::JSONB)
    FROM jsonb_array_elements(p_execution_states) AS x
    ON CONFLICT (enrollment_id) DO NOTHING;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN jsonb_build_object('status', 'success', 'inserted_count', v_count);
END;
$$;


-- =========================================================================================
-- SECTION FROM: 101_leads_data_integrity_remediation.sql
-- =========================================================================================

-- ==============================================================================
-- MIGRATION: 101_leads_data_integrity_remediation.sql
-- Rigorously applied under the Three-Layer Logic Architecture (Paranoia Framework)
-- Fixes: RLS on list_members, Dropping Dangerous Cleanup Trigger, Schema Drift,
-- Foreign Keys, Indexes, Function Overloads, and Idempotent Atomic Ingestion.
-- ==============================================================================

BEGIN;

-- 1. DROP DANGEROUS CRM LEAD DELETION TRIGGER (VULN-LEAD-02)
DROP TRIGGER IF EXISTS trigger_cleanup_orphaned_leads ON public.list_members;
DROP FUNCTION IF EXISTS public.cleanup_orphaned_leads();

-- 2. HARDEN list_members WITH WORKSPACE_ID AND ROW LEVEL SECURITY (VULN-LEAD-01)
ALTER TABLE public.list_members
    ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE;

-- Backfill workspace_id from parent lead_lists
UPDATE public.list_members lm
SET workspace_id = l.workspace_id
FROM public.lead_lists l
WHERE lm.list_id = l.id AND lm.workspace_id IS NULL;

-- In case any orphaned list_members have no parent list, clean them
DELETE FROM public.list_members WHERE workspace_id IS NULL;

ALTER TABLE public.list_members ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.list_members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS list_members_isolation ON public.list_members;
CREATE POLICY list_members_isolation ON public.list_members
    FOR ALL
    USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
    WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_list_members_ws ON public.list_members (workspace_id);
CREATE INDEX IF NOT EXISTS idx_list_members_list_lead ON public.list_members (list_id, opportunity_id);

-- 3. RESOLVE LEADS TABLE SCHEMA DRIFT (VULN-LEAD-06, VULN-LEAD-07)
ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS is_open_profile BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS last_social_retargeted_at TIMESTAMPTZ DEFAULT NULL;

-- 4. RESOLVE CAMPAIGN VERSIONS ORDERING COLUMN (VULN-LEAD-09)
ALTER TABLE public.campaign_versions
    ADD COLUMN IF NOT EXISTS version INTEGER DEFAULT 1;

-- 5. RESOLVE OPEN USING (true) RLS POLICIES (VULN-LEAD-12)
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_social_posts') THEN
        DROP POLICY IF EXISTS lead_social_posts_isolation ON public.lead_social_posts;
        CREATE POLICY lead_social_posts_isolation ON public.lead_social_posts
            FOR ALL
            USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;

    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_social_signals') THEN
        DROP POLICY IF EXISTS lead_social_signals_isolation ON public.lead_social_signals;
        CREATE POLICY lead_social_signals_isolation ON public.lead_social_signals
            FOR ALL
            USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;

    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_objections') THEN
        DROP POLICY IF EXISTS lead_objections_isolation ON public.lead_objections;
        CREATE POLICY lead_objections_isolation ON public.lead_objections
            FOR ALL
            USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
            WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;

-- 6. ADD PERFORMANCE INDEXES FOR CLEANUP, SUPPRESSION & INTENT (VULN-LEAD-10, VULN-LEAD-11)
CREATE INDEX IF NOT EXISTS idx_approval_queue_lead_id 
    ON public.approval_queue (lead_id);

CREATE INDEX IF NOT EXISTS idx_messages_lead_id 
    ON public.messages (lead_id);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_social_posts') THEN
        CREATE INDEX IF NOT EXISTS idx_lead_social_posts_lookup 
            ON public.lead_social_posts (workspace_id, lead_id, post_date DESC);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_leads_social_intent_feed 
    ON public.leads (workspace_id, social_intent_score DESC, last_social_scan_at DESC)
    WHERE social_intent_score > 0;

CREATE INDEX IF NOT EXISTS idx_suppression_composite_lookup 
    ON public.suppression_list (workspace_id, linkedin_url, email, domain);

-- 7. REMOVE AMBIGUOUS FUNCTION OVERLOADS (VULN-LEAD-15)
DROP FUNCTION IF EXISTS public.dequeue_due_leads(integer, uuid[]);

-- 8. ATOMIC BULK IMPORT RPC (VULN-LEAD-13)
CREATE OR REPLACE FUNCTION public.bulk_import_leads_atomic(
    p_workspace_id UUID,
    p_list_id UUID,
    p_leads JSONB,
    p_timezone TEXT DEFAULT 'UTC'
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_item JSONB;
    v_lead_id UUID;
    v_linkedin TEXT;
    v_email TEXT;
    v_inserted INT := 0;
    v_updated INT := 0;
BEGIN
    -- Layer 1 Paranoia: Acquire advisory transaction lock on list to eliminate concurrent write races
    PERFORM pg_advisory_xact_lock(hashtext(p_list_id::text));

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_leads)
    LOOP
        v_linkedin := NULLIF(LOWER(TRIM(v_item->>'linkedin_url')), '');
        v_email := NULLIF(LOWER(TRIM(v_item->>'email')), '');
        v_lead_id := NULL;

        -- Seek existing lead by canonical identity
        IF v_linkedin IS NOT NULL THEN
            SELECT id INTO v_lead_id FROM public.leads
            WHERE workspace_id = p_workspace_id AND LOWER(TRIM(linkedin_url)) = v_linkedin
            LIMIT 1;
        END IF;

        IF v_lead_id IS NULL AND v_email IS NOT NULL THEN
            SELECT id INTO v_lead_id FROM public.leads
            WHERE workspace_id = p_workspace_id AND LOWER(TRIM(email)) = v_email
            LIMIT 1;
        END IF;

        IF v_lead_id IS NOT NULL THEN
            -- Merge existing lead
            UPDATE public.leads
            SET first_name = COALESCE(NULLIF(v_item->>'first_name', ''), first_name),
                last_name = COALESCE(NULLIF(v_item->>'last_name', ''), last_name),
                company_name = COALESCE(NULLIF(v_item->>'company_name', ''), company_name),
                job_title = COALESCE(NULLIF(v_item->>'job_title', ''), job_title),
                location = COALESCE(NULLIF(v_item->>'location', ''), location),
                timezone = COALESCE(NULLIF(v_item->>'timezone', ''), timezone, p_timezone),
                is_open_profile = COALESCE((v_item->>'is_open_profile')::boolean, is_open_profile),
                updated_at = NOW()
            WHERE id = v_lead_id;
            v_updated := v_updated + 1;
        ELSE
            -- Insert new lead
            v_lead_id := gen_random_uuid();
            INSERT INTO public.leads (
                id, workspace_id, first_name, last_name, linkedin_url, company_name, email,
                domain, job_title, location, timezone, is_open_profile, status
            ) VALUES (
                v_lead_id, p_workspace_id,
                v_item->>'first_name', v_item->>'last_name', v_linkedin, v_item->>'company_name',
                v_email, v_item->>'domain', v_item->>'job_title', v_item->>'location',
                COALESCE(v_item->>'timezone', p_timezone),
                COALESCE((v_item->>'is_open_profile')::boolean, false),
                'extracted'
            );
            v_inserted := v_inserted + 1;
        END IF;

        -- Bind to list_members
        INSERT INTO public.list_members (id, workspace_id, list_id, opportunity_id)
        VALUES (gen_random_uuid(), p_workspace_id, p_list_id, v_lead_id)
        ON CONFLICT (list_id, opportunity_id) DO NOTHING;
    END LOOP;

    -- Update row count
    UPDATE public.lead_lists
    SET row_count = (SELECT COUNT(*) FROM public.list_members WHERE list_id = p_list_id),
        updated_at = NOW()
    WHERE id = p_list_id;

    RETURN jsonb_build_object(
        'success', true,
        'inserted_count', v_inserted,
        'updated_count', v_updated,
        'total_processed', v_inserted + v_updated
    );
END;
$$;

COMMIT;


-- =========================================================================================
-- SECTION FROM: 102_leads_storage_and_schema_drift.sql
-- =========================================================================================

-- ==============================================================================
-- MIGRATION: 102_leads_storage_and_schema_drift.sql
-- Rigorously applied under the Three-Layer Logic Architecture (Paranoia Framework)
-- Fixes:
-- 1. Missing EmailShield hygiene columns on leads table (Layer 0 Foundational)
-- 2. Multi-tenancy isolation and RLS on lead_tags with workspace_id (Layer 1 Security)
-- 3. Promoted lead_list_id on campaigns table for robust deletion guards (Layer 1 & 2)
-- 4. Canonical unique index on suppression_list domain vector (Layer 2 Paranoia)
-- 5. Exception-safe suppression handling in bulk_import_leads_atomic RPC
-- ==============================================================================

BEGIN;

-- 1. ADD MISSING EMAIL SHIELD HYGIENE COLUMNS TO LEADS TABLE
ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS quarantine_reason TEXT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS email_classification TEXT DEFAULT 'CORPORATE',
    ADD COLUMN IF NOT EXISTS is_role_based BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_disposable BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS deliverability_risk TEXT DEFAULT 'SAFE';

-- 2. HARDEN LEAD_TAGS WITH WORKSPACE_ID AND ROW LEVEL SECURITY
ALTER TABLE public.lead_tags
    ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE;

-- Backfill workspace_id from parent leads
UPDATE public.lead_tags lt
SET workspace_id = l.workspace_id
FROM public.leads l
WHERE lt.lead_id = l.id AND lt.workspace_id IS NULL;

-- Remove any dangling orphaned tags without parent lead
DELETE FROM public.lead_tags WHERE workspace_id IS NULL;

ALTER TABLE public.lead_tags ALTER COLUMN workspace_id SET NOT NULL;
ALTER TABLE public.lead_tags ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lead_tags_ws_all ON public.lead_tags;
CREATE POLICY lead_tags_ws_all ON public.lead_tags
    FOR ALL
    USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role')
    WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_lead_tags_ws_tag 
    ON public.lead_tags (workspace_id, tag);

-- 3. PROMOTE lead_list_id COLUMN ON CAMPAIGNS TABLE
ALTER TABLE public.campaigns
    ADD COLUMN IF NOT EXISTS lead_list_id UUID REFERENCES public.lead_lists(id) ON DELETE SET NULL;

-- Backfill from metadata JSONB where present
DO $$
BEGIN
    UPDATE public.campaigns
    SET lead_list_id = (metadata->>'lead_list_id')::uuid
    WHERE lead_list_id IS NULL 
      AND metadata IS NOT NULL 
      AND metadata ? 'lead_list_id'
      AND metadata->>'lead_list_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
EXCEPTION WHEN OTHERS THEN
    -- Ignore unparseable historical UUIDs in metadata
    NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_campaigns_lead_list_id 
    ON public.campaigns (lead_list_id);

-- 4. HARDEN SUPPRESSION_LIST WITH CANONICAL DOMAIN UNIQUE INDEX
CREATE UNIQUE INDEX IF NOT EXISTS uq_suppression_domain_canonical
    ON public.suppression_list (workspace_id, LOWER(TRIM(domain)))
    WHERE domain IS NOT NULL AND TRIM(domain) != '';

-- 5. UPGRADE bulk_import_leads_atomic RPC WITH EXCEPTION-SAFE SUPPRESSION HANDLING AND METADATA MERGE
-- Drop any legacy overloads first to avoid PostgreSQL 42P13 parameter rename conflicts
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN 
        SELECT oid::regprocedure AS func_sig 
        FROM pg_proc 
        WHERE proname IN ('bulk_import_leads', 'bulk_import_leads_atomic')
          AND pronamespace = 'public'::regnamespace
    LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS ' || r.func_sig || ' CASCADE';
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.bulk_import_leads_atomic(
    p_workspace_id UUID,
    p_list_id UUID,
    p_leads JSONB,
    p_location TEXT DEFAULT NULL,
    p_timezone TEXT DEFAULT 'UTC'
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_item JSONB;
    v_lead_id UUID;
    v_linkedin TEXT;
    v_email TEXT;
    v_inserted INT := 0;
    v_updated INT := 0;
BEGIN
    -- Layer 1 Paranoia: Advisory transaction lock on list to serialize concurrent ingestions
    PERFORM pg_advisory_xact_lock(hashtext(p_list_id::text));

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_leads)
    LOOP
        v_linkedin := NULLIF(LOWER(TRIM(v_item->>'linkedin_url')), '');
        v_email := NULLIF(LOWER(TRIM(v_item->>'email')), '');
        v_lead_id := NULL;

        -- Seek existing lead by canonical identity
        IF v_linkedin IS NOT NULL THEN
            SELECT id INTO v_lead_id FROM public.leads
            WHERE workspace_id = p_workspace_id AND LOWER(TRIM(linkedin_url)) = v_linkedin
            LIMIT 1;
        END IF;

        IF v_lead_id IS NULL AND v_email IS NOT NULL THEN
            SELECT id INTO v_lead_id FROM public.leads
            WHERE workspace_id = p_workspace_id AND LOWER(TRIM(email)) = v_email
            LIMIT 1;
        END IF;

        IF v_lead_id IS NOT NULL THEN
            -- Merge existing lead
            UPDATE public.leads
            SET first_name = COALESCE(NULLIF(v_item->>'first_name', ''), first_name),
                last_name = COALESCE(NULLIF(v_item->>'last_name', ''), last_name),
                company_name = COALESCE(NULLIF(v_item->>'company_name', ''), company_name),
                job_title = COALESCE(NULLIF(v_item->>'job_title', ''), job_title),
                location = COALESCE(NULLIF(v_item->>'location', ''), location, p_location),
                domain = COALESCE(NULLIF(v_item->>'domain', ''), domain),
                timezone = COALESCE(NULLIF(v_item->>'timezone', ''), timezone, p_timezone),
                is_open_profile = COALESCE((v_item->>'is_open_profile')::boolean, is_open_profile),
                quarantine_reason = COALESCE(NULLIF(v_item->>'quarantine_reason', ''), quarantine_reason),
                email_classification = COALESCE(NULLIF(v_item->>'email_classification', ''), email_classification),
                is_role_based = COALESCE((v_item->>'is_role_based')::boolean, is_role_based),
                is_disposable = COALESCE((v_item->>'is_disposable')::boolean, is_disposable),
                deliverability_risk = COALESCE(NULLIF(v_item->>'deliverability_risk', ''), deliverability_risk),
                metadata = CASE 
                    WHEN v_item ? 'metadata' AND jsonb_typeof(v_item->'metadata') = 'object' 
                    THEN COALESCE(metadata, '{}'::jsonb) || (v_item->'metadata')
                    ELSE metadata
                END,
                updated_at = NOW()
            WHERE id = v_lead_id;
            v_updated := v_updated + 1;
        ELSE
            -- Insert new lead
            v_lead_id := gen_random_uuid();
            INSERT INTO public.leads (
                id, workspace_id, first_name, last_name, linkedin_url, company_name, email,
                domain, job_title, location, timezone, is_open_profile,
                quarantine_reason, email_classification, is_role_based, is_disposable, deliverability_risk,
                metadata, status
            ) VALUES (
                v_lead_id, p_workspace_id,
                v_item->>'first_name', v_item->>'last_name', v_linkedin, v_item->>'company_name',
                v_email, v_item->>'domain', v_item->>'job_title', COALESCE(NULLIF(v_item->>'location', ''), p_location),
                COALESCE(v_item->>'timezone', p_timezone),
                COALESCE((v_item->>'is_open_profile')::boolean, false),
                v_item->>'quarantine_reason',
                COALESCE(v_item->>'email_classification', 'CORPORATE'),
                COALESCE((v_item->>'is_role_based')::boolean, false),
                COALESCE((v_item->>'is_disposable')::boolean, false),
                COALESCE(v_item->>'deliverability_risk', 'SAFE'),
                COALESCE(v_item->'metadata', '{}'::jsonb),
                COALESCE(v_item->>'status', 'extracted')
            );
            v_inserted := v_inserted + 1;
        END IF;

        -- Bind to list_members (safely handling suppression trigger rejection)
        BEGIN
            INSERT INTO public.list_members (id, workspace_id, list_id, opportunity_id)
            VALUES (gen_random_uuid(), p_workspace_id, p_list_id, v_lead_id)
            ON CONFLICT (list_id, opportunity_id) DO NOTHING;
        EXCEPTION WHEN SQLSTATE 'U0001' THEN
            -- Lead is suppressed, skip adding to active list without aborting bulk import
            NULL;
        END;
    END LOOP;

    -- Update list row count atomically
    UPDATE public.lead_lists
    SET row_count = (SELECT COUNT(*) FROM public.list_members WHERE list_id = p_list_id),
        updated_at = NOW()
    WHERE id = p_list_id;

    RETURN jsonb_build_object(
        'success', true,
        'inserted_count', v_inserted,
        'updated_count', v_updated,
        'total_processed', v_inserted + v_updated
    );
END;
$$;

-- 6. Canonical delegation wrapper from bulk_import_leads to bulk_import_leads_atomic
-- Matches exact historical parameter order (p_list_id, p_workspace_id, p_leads, p_location, p_timezone)
CREATE OR REPLACE FUNCTION public.bulk_import_leads(
    p_list_id UUID,
    p_workspace_id UUID,
    p_leads JSONB,
    p_location TEXT DEFAULT NULL,
    p_timezone TEXT DEFAULT 'UTC'
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN public.bulk_import_leads_atomic(
        p_workspace_id => p_workspace_id,
        p_list_id => p_list_id,
        p_leads => p_leads,
        p_location => p_location,
        p_timezone => p_timezone
    );
END;
$$;

COMMIT;


-- =========================================================================================
-- CAPTAIN VERIFICATION SUITE: RUN THESE SELECT QUERIES AFTER DEPLOYMENT
-- =========================================================================================

-- Verification 1: Verify core RPC functions exist and are registered
SELECT proname, prosecdef 
FROM pg_proc 
WHERE proname IN (
    'my_workspace_ids',
    'dequeue_due_leads', 
    'release_lead_claim', 
    'advance_reply_waiting',
    'create_campaign_atomic', 
    'enroll_leads_chunk_atomic',
    'bulk_import_leads',
    'bulk_import_leads_atomic'
)
ORDER BY proname;

-- Verification 2: Verify RLS is enabled on all campaign and lead tables
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
  AND tablename IN (
    'campaigns', 
    'campaign_versions', 
    'campaign_accounts', 
    'campaign_enrollments', 
    'campaign_execution_states', 
    'list_members', 
    'leads', 
    'lead_tags'
)
ORDER BY tablename;

-- Verification 3: Verify critical composite indexes are present
SELECT indexname, tablename 
FROM pg_indexes 
WHERE schemaname = 'public' 
  AND indexname IN (
    'idx_ces_workspace_status_next_run',
    'idx_campaigns_lead_list_id',
    'idx_list_members_ws',
    'idx_lead_tags_ws_tag',
    'uq_suppression_domain_canonical'
)
ORDER BY indexname;


-- ============================================================================
-- MIGRATION STAGE 5: WORKSPACE CLOUD BLUEPRINTS SYNC (MIGRATION 103)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.workspace_blueprints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    version TEXT NOT NULL DEFAULT '1.0.0',
    schema_version TEXT NOT NULL DEFAULT 'elein-blueprint-v1',
    branding JSONB NOT NULL DEFAULT '{}'::jsonb,
    sequence_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    stats JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_workspace_blueprints_ws_updated ON public.workspace_blueprints(workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_workspace_blueprints_ws_name ON public.workspace_blueprints(workspace_id, name);

ALTER TABLE public.workspace_blueprints ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS workspace_blueprints_tenant_isolation ON public.workspace_blueprints;
CREATE POLICY workspace_blueprints_tenant_isolation ON public.workspace_blueprints
    FOR ALL
    USING (
        workspace_id IN (
            SELECT workspace_id FROM public.workspace_members
            WHERE user_id = auth.uid()
        )
        OR is_public = true
    )
    WITH CHECK (
        workspace_id IN (
            SELECT workspace_id FROM public.workspace_members
            WHERE user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS workspace_blueprints_service_role ON public.workspace_blueprints;
CREATE POLICY workspace_blueprints_service_role ON public.workspace_blueprints
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
-- ============================================================================
-- ============================================================================
-- ============================================================================
-- ============================================================================
-- MIGRATION 104: CYCLE 4 CAMPAIGN SUBSYSTEM PARANOIA REMEDIATION
-- Idempotent resolution for FLAW-DB-01 through FLAW-DB-31
-- Standard: Zero Emojis, Complete Relational Integrity, Strict Multi-Tenancy
-- Aligned with Live Supabase Production Database Schema
-- ============================================================================

-- ----------------------------------------------------------------------------
-- PRE-FLIGHT FUNCTION CLEANUP (Prevents 42P13 Parameter Rename Errors)
-- ----------------------------------------------------------------------------
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN 
        SELECT oid::regprocedure AS func_sig 
        FROM pg_proc 
        WHERE proname IN (
            'create_campaign_atomic',
            'enroll_leads_chunk_atomic',
            'dequeue_due_leads',
            'release_lead_claim',
            'recover_stale_leases',
            'advance_reply_waiting_leads',
            'claim_processing_jobs',
            'decrement_list_row_count',
            'claim_outbox_events',
            'set_outbox_events_updated_at',
            'update_daily_campaign_stats'
        )
        AND pronamespace = 'public'::regnamespace
    LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS ' || r.func_sig || ' CASCADE';
    END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- 1. ENUM NORMALIZATION & VALUE EXTENSIONS (FLAW-DB-08, FLAW-DB-09)
-- lead_state_status enum is permanently superseded by standard TEXT column
-- with chk_ces_status_valid check constraint in Section 3.
-- Zero ALTER TYPE ... ADD VALUE statements are used, guaranteeing complete
-- immunity to PostgreSQL 55P04 (unsafe new enum value) and 25001 transaction errors.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- 2. SCHEMA DRIFT & COLUMN RESTORATIONS (FLAW-DB-01, 03, 04, 05, 06, 11, 12)
-- ----------------------------------------------------------------------------

-- FLAW-DB-01: Add campaign_id to campaign_execution_states
ALTER TABLE public.campaign_execution_states 
    ADD COLUMN IF NOT EXISTS campaign_id UUID REFERENCES public.campaigns(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_ces_campaign_id 
    ON public.campaign_execution_states (campaign_id);

-- Backfill campaign_id from enrollments if null
UPDATE public.campaign_execution_states ces
SET campaign_id = ce.campaign_id
FROM public.campaign_enrollments ce
WHERE ces.enrollment_id = ce.id AND ces.campaign_id IS NULL;

-- FLAW-DB-03: Add position_x and position_y to campaign_nodes
ALTER TABLE public.campaign_nodes 
    ADD COLUMN IF NOT EXISTS position_x DOUBLE PRECISION DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS position_y DOUBLE PRECISION DEFAULT 0.0;

-- Defensively ensure DAG versioning columns exist on campaign_versions
ALTER TABLE public.campaign_versions
    ADD COLUMN IF NOT EXISTS nodes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS edges_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ DEFAULT NOW();

-- FLAW-DB-04: Add enrollment_id and normalize node_id on messages
ALTER TABLE public.messages 
    ADD COLUMN IF NOT EXISTS enrollment_id UUID REFERENCES public.campaign_enrollments(id) ON DELETE SET NULL;

ALTER TABLE public.messages 
    ALTER COLUMN node_id TYPE TEXT USING node_id::TEXT;

CREATE INDEX IF NOT EXISTS idx_messages_enrollment_node 
    ON public.messages (enrollment_id, node_id);

-- FLAW-DB-05: Add updated_at to outbox_events with auto-update trigger
ALTER TABLE public.outbox_events 
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE OR REPLACE FUNCTION public.set_outbox_events_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_outbox_events_updated_at ON public.outbox_events;
CREATE TRIGGER trigger_outbox_events_updated_at
    BEFORE UPDATE ON public.outbox_events
    FOR EACH ROW EXECUTE FUNCTION public.set_outbox_events_updated_at();

-- FLAW-DB-06: Add weight to campaign_accounts
ALTER TABLE public.campaign_accounts 
    ADD COLUMN IF NOT EXISTS weight INTEGER NOT NULL DEFAULT 100;

-- FLAW-DB-02: Enforce foreign keys on campaign_node_executions
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cne_workspace') THEN
        ALTER TABLE public.campaign_node_executions
            ADD CONSTRAINT fk_cne_workspace FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cne_enrollment') THEN
        ALTER TABLE public.campaign_node_executions
            ADD CONSTRAINT fk_cne_enrollment FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cne_campaign_version') THEN
        ALTER TABLE public.campaign_node_executions
            ADD CONSTRAINT fk_cne_campaign_version FOREIGN KEY (campaign_version_id) REFERENCES public.campaign_versions(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_cne_enrollment_node 
    ON public.campaign_node_executions (enrollment_id, node_id);

-- FLAW-DB-11: action_log.execution_state_id UUID type and FK
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'action_log' AND column_name = 'execution_state_id' AND data_type = 'text'
    ) THEN
        ALTER TABLE public.action_log 
            ALTER COLUMN execution_state_id TYPE UUID USING (
                CASE 
                    WHEN execution_state_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' 
                    THEN execution_state_id::UUID 
                    ELSE NULL 
                END
            );
    END IF;
END $$;

UPDATE public.action_log 
SET execution_state_id = NULL 
WHERE execution_state_id IS NOT NULL 
  AND NOT EXISTS (SELECT 1 FROM public.campaign_execution_states ces WHERE ces.id = action_log.execution_state_id);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_action_log_ces') THEN
        ALTER TABLE public.action_log
            ADD CONSTRAINT fk_action_log_ces FOREIGN KEY (execution_state_id) REFERENCES public.campaign_execution_states(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_action_log_ces_id 
    ON public.action_log (execution_state_id);

-- FLAW-DB-12: approval_queue.lead_id and exec_state_id UUID type and FK with orphaned ID cleanup
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'approval_queue' AND column_name = 'lead_id' AND data_type = 'text'
    ) THEN
        ALTER TABLE public.approval_queue 
            ALTER COLUMN lead_id TYPE UUID USING (
                CASE 
                    WHEN lead_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' 
                    THEN lead_id::UUID 
                    ELSE NULL 
                END
            );
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'approval_queue' AND column_name = 'exec_state_id' AND data_type = 'text'
    ) THEN
        ALTER TABLE public.approval_queue 
            ALTER COLUMN exec_state_id TYPE UUID USING (
                CASE 
                    WHEN exec_state_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' 
                    THEN exec_state_id::UUID 
                    ELSE NULL 
                END
            );
    END IF;
END $$;

-- Clean up orphaned references after columns are guaranteed UUID in catalog
UPDATE public.approval_queue 
SET lead_id = NULL 
WHERE lead_id IS NOT NULL 
  AND NOT EXISTS (SELECT 1 FROM public.leads l WHERE l.id = approval_queue.lead_id);

UPDATE public.approval_queue 
SET exec_state_id = NULL 
WHERE exec_state_id IS NOT NULL 
  AND NOT EXISTS (SELECT 1 FROM public.campaign_execution_states ces WHERE ces.id = approval_queue.exec_state_id);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_queue_lead') THEN
        ALTER TABLE public.approval_queue
            ADD CONSTRAINT fk_approval_queue_lead FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_queue_ces') THEN
        ALTER TABLE public.approval_queue
            ADD CONSTRAINT fk_approval_queue_ces FOREIGN KEY (exec_state_id) REFERENCES public.campaign_execution_states(id) ON DELETE CASCADE;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 3. CHECK CONSTRAINTS, DEDUPLICATION & COMPATIBILITY VIEWS (FLAW-DB-07, 10, 13)
-- ----------------------------------------------------------------------------

-- Enforce UNIQUE constraint on campaign_enrollments(campaign_id, lead_id)
DELETE FROM public.campaign_enrollments a
USING public.campaign_enrollments b
WHERE a.id > b.id
  AND a.campaign_id = b.campaign_id
  AND a.lead_id = b.lead_id;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_campaign_lead_enrollment'
    ) THEN
        ALTER TABLE public.campaign_enrollments
            ADD CONSTRAINT uq_campaign_lead_enrollment UNIQUE (campaign_id, lead_id);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;

-- Enforce UNIQUE constraint on daily_campaign_stats(campaign_id, stat_date)
DELETE FROM public.daily_campaign_stats a
USING public.daily_campaign_stats b
WHERE a.id > b.id
  AND a.campaign_id = b.campaign_id
  AND a.stat_date = b.stat_date;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_daily_campaign_stats_date'
    ) THEN
        ALTER TABLE public.daily_campaign_stats
            ADD CONSTRAINT uq_daily_campaign_stats_date UNIQUE (campaign_id, stat_date);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;

-- FLAW-DB-07: Status checks on campaign_execution_states and campaign_enrollments
-- Executed directly as top-level DDL & DML statements (outside PL/pgSQL function)
-- to ensure status column is committed as TEXT before running value sanitization queries.

-- Drop any dependent views before column type conversion
DROP VIEW IF EXISTS public.campaign_leads CASCADE;

-- Drop trigger dependencies on campaign_execution_states.status (prevents 0A000 trigger dependency error)
DROP TRIGGER IF EXISTS execution_state_transition_guard ON public.campaign_execution_states CASCADE;

DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN 
        SELECT DISTINCT t.tgname, c.relname 
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' 
          AND c.relname IN ('campaign_execution_states', 'campaign_enrollments')
          AND NOT t.tgisinternal
          AND (
              t.tgname ILIKE '%transition%'
              OR t.tgname ILIKE '%status%'
              OR t.tgname ILIKE '%guard%'
              OR EXISTS (
                  SELECT 1 FROM pg_depend d
                  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.refobjsubid
                  WHERE d.objid = t.oid AND a.attname = 'status'
              )
          )
    LOOP
        EXECUTE 'DROP TRIGGER IF EXISTS ' || quote_ident(r.tgname) || ' ON public.' || quote_ident(r.relname) || ' CASCADE';
    END LOOP;
END $$;

-- 1. Drop existing defaults to prevent "cannot cast default to text" error
ALTER TABLE public.campaign_execution_states ALTER COLUMN status DROP DEFAULT;
ALTER TABLE public.campaign_enrollments ALTER COLUMN status DROP DEFAULT;

-- 2. Convert status columns directly to TEXT
ALTER TABLE public.campaign_execution_states ALTER COLUMN status TYPE TEXT USING status::TEXT;
ALTER TABLE public.campaign_enrollments ALTER COLUMN status TYPE TEXT USING status::TEXT;

-- 3. Restore defaults as TEXT
ALTER TABLE public.campaign_execution_states ALTER COLUMN status SET DEFAULT 'pending';
ALTER TABLE public.campaign_enrollments ALTER COLUMN status SET DEFAULT 'active';

-- 4. Sanitize invalid status values now that column is confirmed TEXT in the catalog
UPDATE public.campaign_execution_states 
SET status = 'pending' 
WHERE status IS NULL 
   OR status NOT IN ('pending', 'running', 'waiting_for_reply', 'awaiting_approval', 'waiting_for_approval', 'paused', 'completed', 'failed', 'exited', 'rate_limited', 'out_of_office', 'skipped', 'error', 'snoozed_ooo');

UPDATE public.campaign_enrollments 
SET status = 'active' 
WHERE status IS NULL 
   OR status NOT IN ('active', 'completed', 'paused', 'exited', 'error', 'failed', 'bounced');

-- 5. Add check constraints cleanly
ALTER TABLE public.campaign_execution_states DROP CONSTRAINT IF EXISTS chk_ces_status_valid;
ALTER TABLE public.campaign_execution_states
    ADD CONSTRAINT chk_ces_status_valid CHECK (
        status IN ('pending', 'running', 'waiting_for_reply', 'awaiting_approval', 'waiting_for_approval', 'paused', 'completed', 'failed', 'exited', 'rate_limited', 'out_of_office', 'skipped', 'error', 'snoozed_ooo')
    );

ALTER TABLE public.campaign_enrollments DROP CONSTRAINT IF EXISTS chk_ce_status_valid;
ALTER TABLE public.campaign_enrollments
    ADD CONSTRAINT chk_ce_status_valid CHECK (
        status IN ('active', 'completed', 'paused', 'exited', 'error', 'failed', 'bounced')
    );

-- FLAW-DB-10: Drop dangling trigger / function on action_log
DROP TRIGGER IF EXISTS action_log_increment_daily_usage ON public.action_log;

-- FLAW-DB-13: campaign_leads compatibility view with enrolled_at mapping
-- Ensure created_at, updated_at, and enrolled_at exist defensively on campaign_enrollments
ALTER TABLE public.campaign_enrollments 
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.campaign_enrollments 
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.campaign_enrollments 
    ADD COLUMN IF NOT EXISTS enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE OR REPLACE VIEW public.campaign_leads AS
SELECT 
    id,
    workspace_id,
    campaign_id,
    lead_id,
    status,
    account_id,
    COALESCE(created_at, enrolled_at, NOW()) AS created_at,
    COALESCE(enrolled_at, created_at, NOW()) AS enrolled_at,
    COALESCE(updated_at, created_at, NOW()) AS updated_at
FROM public.campaign_enrollments;

-- ----------------------------------------------------------------------------
-- 4. B-TREE & COMPOSITE PERFORMANCE INDEXES (FLAW-DB-28, 29)
-- ----------------------------------------------------------------------------

-- FLAW-DB-28: Indexes on campaign_edges
CREATE INDEX IF NOT EXISTS idx_campaign_edges_source_node 
    ON public.campaign_edges (source_node_id);

CREATE INDEX IF NOT EXISTS idx_campaign_edges_target_node 
    ON public.campaign_edges (target_node_id);

-- FLAW-DB-29: Composite index on campaign_execution_states
CREATE INDEX IF NOT EXISTS idx_ces_enrollment_status 
    ON public.campaign_execution_states (enrollment_id, status);

-- ----------------------------------------------------------------------------
-- 5. SUPPRESSION TRIGGER WITH DOMAIN AUDIT (FLAW-DB-17)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.enforce_suppression_list()
RETURNS TRIGGER AS $$
DECLARE
    v_linkedin_url TEXT;
    v_email TEXT;
    v_domain TEXT;
    v_workspace_id UUID;
    v_is_suppressed BOOLEAN;
BEGIN
    IF TG_TABLE_NAME = 'list_members' OR TG_TABLE_NAME = 'lead_states' THEN
        SELECT workspace_id, linkedin_url, email, domain
        INTO v_workspace_id, v_linkedin_url, v_email, v_domain
        FROM public.leads
        WHERE id = NEW.opportunity_id;
    ELSIF TG_TABLE_NAME = 'campaign_enrollments' THEN
        v_workspace_id := NEW.workspace_id;
        SELECT linkedin_url, email, domain
        INTO v_linkedin_url, v_email, v_domain
        FROM public.leads
        WHERE id = NEW.lead_id;
    END IF;

    IF v_workspace_id IS NOT NULL THEN
        SELECT EXISTS (
            SELECT 1 
            FROM public.suppression_list 
            WHERE workspace_id = v_workspace_id 
              AND (
                  (v_linkedin_url IS NOT NULL AND linkedin_url = v_linkedin_url)
                  OR (v_email IS NOT NULL AND LOWER(email) = LOWER(v_email))
                  OR (v_domain IS NOT NULL AND domain IS NOT NULL AND LOWER(domain) = LOWER(v_domain))
              )
        ) INTO v_is_suppressed;

        IF v_is_suppressed THEN
            RAISE EXCEPTION USING 
                ERRCODE = 'U0001',
                MESSAGE = 'suppression_list_violation: Lead or company domain is suppressed for this workspace.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- ----------------------------------------------------------------------------
-- 6. RPC HARDENING: ATOMIC CAMPAIGN CREATION (FLAW-DB-14)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.create_campaign_atomic(
    p_campaign_id UUID,
    p_workspace_id UUID,
    p_name TEXT,
    p_status TEXT,
    p_nodes_json JSONB,
    p_edges_json JSONB,
    p_sender_account_ids_json JSONB,
    p_metadata JSONB,
    p_senders UUID[] DEFAULT '{}'::UUID[]
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_version_id UUID;
    v_sender_id UUID;
    v_status_enum public.campaign_status;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
    ) AND auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized: User is not a member of workspace %', p_workspace_id;
    END IF;

    BEGIN
        v_status_enum := UPPER(COALESCE(p_status, 'DRAFT'))::public.campaign_status;
    EXCEPTION WHEN OTHERS THEN
        v_status_enum := 'DRAFT'::public.campaign_status;
    END;

    -- 1. Insert Campaign
    INSERT INTO public.campaigns (
        id, workspace_id, name, status, nodes_json, edges_json, sender_account_ids_json, metadata
    ) VALUES (
        p_campaign_id, p_workspace_id, p_name, v_status_enum, 
        COALESCE(p_nodes_json, '[]'::jsonb), 
        COALESCE(p_edges_json, '[]'::jsonb), 
        COALESCE(p_sender_account_ids_json, '[]'::jsonb), 
        COALESCE(p_metadata, '{}'::jsonb)
    );

    -- 2. Insert Version 1 with full DAG definition
    v_version_id := gen_random_uuid();
    INSERT INTO public.campaign_versions (
        id, campaign_id, nodes_json, edges_json, metadata, version, published_at
    ) VALUES (
        v_version_id, p_campaign_id, 
        COALESCE(p_nodes_json, '[]'::jsonb), 
        COALESCE(p_edges_json, '[]'::jsonb), 
        COALESCE(p_metadata, '{}'::jsonb), 
        1, now()
    );

    -- 3. Insert Accounts
    IF p_senders IS NOT NULL AND array_length(p_senders, 1) > 0 THEN
        FOREACH v_sender_id IN ARRAY p_senders LOOP
            IF EXISTS (SELECT 1 FROM public.accounts WHERE id = v_sender_id AND workspace_id = p_workspace_id) THEN
                INSERT INTO public.campaign_accounts (campaign_id, account_id, weight)
                VALUES (p_campaign_id, v_sender_id, 100)
                ON CONFLICT (campaign_id, account_id) DO NOTHING;
            END IF;
        END LOOP;
    END IF;

    RETURN jsonb_build_object(
        'campaign_id', p_campaign_id,
        'version_id', v_version_id,
        'status', 'success'
    );
END;
$$;

-- ----------------------------------------------------------------------------
-- 7. RPC HARDENING: ATOMIC LEAD ENROLLMENT (FLAW-DB-15, 16)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.enroll_leads_chunk_atomic(
    p_workspace_id UUID,
    p_campaign_id UUID,
    p_enrollments JSONB,
    p_execution_states JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_inserted_count INT := 0;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
    ) AND auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized: User is not a member of workspace %', p_workspace_id;
    END IF;

    WITH inserted_enrollments AS (
        INSERT INTO public.campaign_enrollments (
            id, workspace_id, campaign_id, campaign_version_id, lead_id, account_id
        )
        SELECT
            COALESCE(NULLIF(e->>'id', '')::UUID, gen_random_uuid()),
            p_workspace_id,
            p_campaign_id,
            NULLIF(e->>'campaign_version_id', '')::UUID,
            NULLIF(e->>'lead_id', '')::UUID,
            NULLIF(e->>'account_id', '')::UUID
        FROM jsonb_array_elements(p_enrollments) AS e
        WHERE NOT EXISTS (
            -- Pre-filter suppressed leads to prevent trigger U0001 abort
            SELECT 1 FROM public.suppression_list sl
            JOIN public.leads l ON l.id = NULLIF(e->>'lead_id', '')::UUID
            WHERE sl.workspace_id = p_workspace_id
              AND (
                  (sl.linkedin_url IS NOT NULL AND sl.linkedin_url = l.linkedin_url)
                  OR (sl.email IS NOT NULL AND LOWER(sl.email) = LOWER(l.email))
                  OR (sl.domain IS NOT NULL AND l.domain IS NOT NULL AND LOWER(sl.domain) = LOWER(l.domain))
              )
        )
        ON CONFLICT (campaign_id, lead_id) DO NOTHING
        RETURNING id, lead_id
    )
    INSERT INTO public.campaign_execution_states (
        id, workspace_id, campaign_id, enrollment_id, status, variables
    )
    SELECT
        gen_random_uuid(),
        p_workspace_id,
        p_campaign_id,
        ie.id,
        'pending',
        '{}'::JSONB
    FROM inserted_enrollments ie
    ON CONFLICT (enrollment_id) DO NOTHING;

    GET DIAGNOSTICS v_inserted_count = ROW_COUNT;
    RETURN jsonb_build_object('status', 'success', 'inserted_count', v_inserted_count);
END;
$$;

-- ----------------------------------------------------------------------------
-- 8. RPC HARDENING: SCHEDULER DEQUEUE & LEASE RECOVERY (FLAW-DB-18, 19, 20, 21, 22)
-- ----------------------------------------------------------------------------

-- Canonical dequeue_due_leads with case-insensitive campaign status match
CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
    p_batch_size INT DEFAULT 50,
    p_campaign_ids UUID[] DEFAULT NULL,
    p_lease_seconds INT DEFAULT 300
) RETURNS SETOF public.campaign_execution_states
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_token UUID := gen_random_uuid();
    v_expires TIMESTAMPTZ := now() + (p_lease_seconds || ' seconds')::INTERVAL;
BEGIN
    RETURN QUERY
    WITH due_states AS (
        SELECT ces.id 
        FROM (
            SELECT id AS campaign_id, workspace_id 
            FROM public.campaigns
            WHERE UPPER(status::text) = 'ACTIVE' 
              AND (p_campaign_ids IS NULL OR id = ANY(p_campaign_ids))
        ) c
        CROSS JOIN LATERAL (
            SELECT ces.id, ces.next_run_at
            FROM public.campaign_execution_states ces
            JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
            LEFT JOIN public.accounts a ON a.id = ce.account_id
            WHERE ces.workspace_id = c.workspace_id
              AND ce.campaign_id = c.campaign_id
              AND (
                  ces.status = 'pending'
                  OR (ces.status = 'running' AND ces.lease_expires_at IS NOT NULL AND ces.lease_expires_at < now())
              )
              AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
              AND (a.id IS NULL OR (a.status::text = 'ACTIVE' AND COALESCE(a.manual_send_suspected, false) = false))
            ORDER BY ces.next_run_at ASC NULLS FIRST
            LIMIT GREATEST(1, p_batch_size / 5)
        ) ces
        ORDER BY ces.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE OF ces SKIP LOCKED
    )
    UPDATE public.campaign_execution_states u
    SET 
        lease_token = v_token,
        lease_expires_at = v_expires,
        status = 'running',
        updated_at = now()
    FROM due_states ds
    WHERE u.id = ds.id
    RETURNING u.*;
END;
$$;

-- Canonical release_lead_claim with safe UUID casting
CREATE OR REPLACE FUNCTION public.release_lead_claim(
    p_state_id UUID,
    p_lease_token UUID,
    p_next_status TEXT,
    p_next_node TEXT,
    p_next_run TIMESTAMPTZ,
    p_variables JSONB,
    p_error_reason TEXT,
    p_attempts INT
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_rows INT;
    v_next_node_uuid UUID;
BEGIN
    IF p_next_node IS NOT NULL AND p_next_node ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
        v_next_node_uuid := p_next_node::UUID;
    ELSE
        v_next_node_uuid := NULL;
    END IF;

    UPDATE public.campaign_execution_states
    SET 
        status = CASE 
            -- Protect operator-initiated pause from being reverted by in-flight worker
            WHEN status = 'paused' THEN 'paused'
            ELSE p_next_status 
        END,
        current_node_id = COALESCE(v_next_node_uuid, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        retry_count = COALESCE(p_attempts, retry_count),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id 
      AND (p_lease_token IS NULL OR lease_token = p_lease_token OR lease_token::TEXT = p_lease_token::TEXT);
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

-- Canonical recover_stale_leases (only running status)
CREATE OR REPLACE FUNCTION public.recover_stale_leases(p_timeout_minutes INT DEFAULT 5)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_recovered integer;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = 'pending',
        lease_token = NULL,
        lease_expires_at = NULL,
        next_run_at = now(),
        updated_at = now()
    WHERE status = 'running'
      AND (
          (lease_expires_at IS NOT NULL AND lease_expires_at < now())
          OR updated_at < now() - (p_timeout_minutes || ' minutes')::INTERVAL
      );
    GET DIAGNOSTICS v_recovered = ROW_COUNT;
    RETURN v_recovered;
END;
$$;

-- ----------------------------------------------------------------------------
-- 9. RPC HARDENING: CROSS-TENANT DEFENSE & ATOMIC QUEUES (FLAW-DB-23, 24, 25, 30)
-- ----------------------------------------------------------------------------

-- FLAW-DB-23: Scoped advance_reply_waiting_leads
CREATE OR REPLACE FUNCTION public.advance_reply_waiting_leads(
    p_lead_id UUID,
    p_workspace_id UUID DEFAULT NULL
)
RETURNS integer 
LANGUAGE plpgsql 
SECURITY DEFINER 
SET search_path = public
AS $$
DECLARE
    v_state_id UUID;
    v_count INTEGER := 0;
BEGIN
    IF p_workspace_id IS NOT NULL AND auth.role() <> 'service_role' THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.workspace_members 
            WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
        ) THEN
            RAISE EXCEPTION 'Unauthorized workspace access';
        END IF;
    END IF;

    SELECT ces.id INTO v_state_id
    FROM public.campaign_execution_states ces
    JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
    WHERE ce.lead_id = p_lead_id 
      AND ces.status = 'waiting_for_reply'
      AND (p_workspace_id IS NULL OR ces.workspace_id = p_workspace_id)
    ORDER BY ces.id
    FOR UPDATE OF ces SKIP LOCKED
    LIMIT 1;

    IF v_state_id IS NOT NULL THEN
        UPDATE public.campaign_execution_states
        SET status = 'pending', next_run_at = now(),
            lease_token = NULL, lease_expires_at = NULL, updated_at = now()
        WHERE id = v_state_id;
        v_count := 1;
    END IF;

    RETURN v_count;
END; 
$$;

-- FLAW-DB-24: Scoped claim_processing_jobs with search_path
CREATE OR REPLACE FUNCTION public.claim_processing_jobs(
    claim_limit INT,
    p_workspace_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  workspace_id UUID,
  asset_id UUID,
  job_type TEXT,
  payload JSONB,
  status TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  WITH claimed AS (
    SELECT processing_jobs.id
    FROM public.processing_jobs
    WHERE processing_jobs.status = 'pending'
      AND (p_workspace_id IS NULL OR processing_jobs.workspace_id = p_workspace_id)
    ORDER BY processing_jobs.created_at ASC
    LIMIT claim_limit
    FOR UPDATE SKIP LOCKED
  )
  UPDATE public.processing_jobs pj
  SET status = 'running', updated_at = NOW()
  FROM claimed c
  WHERE pj.id = c.id
  RETURNING 
    pj.id,
    pj.workspace_id,
    pj.asset_id,
    pj.job_type,
    pj.payload,
    pj.status,
    pj.created_at,
    pj.updated_at;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.claim_processing_jobs(INT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.claim_processing_jobs(INT, UUID) TO service_role;

-- FLAW-DB-25: Scoped decrement_list_row_count with search_path
CREATE OR REPLACE FUNCTION public.decrement_list_row_count(
    list_uuid UUID,
    p_workspace_id UUID DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE public.lead_lists
  SET row_count = GREATEST(row_count - 1, 0),
      updated_at = NOW()
  WHERE id = list_uuid 
    AND row_count > 0
    AND (
        p_workspace_id IS NULL 
        OR workspace_id IN (SELECT public.my_workspace_ids())
        OR auth.role() = 'service_role'
    );
END;
$$;

-- FLAW-DB-30: Atomic claim_outbox_events with FOR UPDATE SKIP LOCKED
CREATE OR REPLACE FUNCTION public.claim_outbox_events(
    p_batch_size INT DEFAULT 50,
    p_timeout_seconds INT DEFAULT 300
)
RETURNS SETOF public.outbox_events
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    WITH candidate_events AS (
        SELECT id
        FROM public.outbox_events
        WHERE (status = 'pending' AND deliver_at <= NOW())
           OR (status = 'processing' AND deliver_at <= NOW() - (p_timeout_seconds || ' seconds')::INTERVAL)
        ORDER BY deliver_at ASC
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE public.outbox_events oe
    SET status = 'processing',
        deliver_at = NOW() + (p_timeout_seconds || ' seconds')::INTERVAL,
        attempts = oe.attempts + 1,
        updated_at = NOW()
    FROM candidate_events ce
    WHERE oe.id = ce.id
    RETURNING oe.*;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.claim_outbox_events(INT, INT) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.claim_outbox_events(INT, INT) TO service_role;

-- ----------------------------------------------------------------------------
-- 10. REAL-TIME STATS ROLLUP TRIGGER FIX (FLAW-DB-27)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.update_daily_campaign_stats()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_campaign_id  UUID;
    v_workspace_id UUID;
    v_stat_date    DATE := DATE(NEW.executed_at AT TIME ZONE 'UTC');
BEGIN
    IF NEW.execution_state_id IS NOT NULL THEN
        SELECT ce.campaign_id, ces.workspace_id
          INTO v_campaign_id, v_workspace_id
          FROM public.campaign_execution_states ces
          JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
         WHERE ces.id = NEW.execution_state_id;
    ELSIF NEW.lead_state_id IS NOT NULL THEN
        SELECT ls.campaign_id, c.workspace_id
          INTO v_campaign_id, v_workspace_id
          FROM public.lead_states ls
          JOIN public.campaigns c ON c.id = ls.campaign_id
         WHERE ls.id = NEW.lead_state_id;
    END IF;

    IF v_workspace_id IS NULL THEN
        v_workspace_id := NEW.workspace_id;
    END IF;

    IF v_campaign_id IS NULL THEN 
        RETURN NEW; 
    END IF;

    INSERT INTO public.daily_campaign_stats (
        workspace_id, campaign_id, stat_date, connections_sent, messages_sent
    ) VALUES (
        v_workspace_id, v_campaign_id, v_stat_date,
        CASE WHEN NEW.action_type ILIKE '%connection%' THEN 1 ELSE 0 END,
        CASE WHEN NEW.action_type IN ('send_message','send_inmail','send_paid_inmail','send_voice_note','send_message_with_doc','send_message_with_image') THEN 1 ELSE 0 END
    )
    ON CONFLICT (campaign_id, stat_date) DO UPDATE SET
        connections_sent = public.daily_campaign_stats.connections_sent + EXCLUDED.connections_sent,
        messages_sent    = public.daily_campaign_stats.messages_sent    + EXCLUDED.messages_sent,
        updated_at       = NOW();

    RETURN NEW;
END;
$$;

-- ----------------------------------------------------------------------------
-- 11. ROW-LEVEL SECURITY POLICY REPAIRS (FLAW-DB-26, 31)
-- ----------------------------------------------------------------------------

ALTER TABLE public.campaign_roi_certificates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_execution_states ENABLE ROW LEVEL SECURITY;

-- FLAW-DB-26: Fix campaign_roi_certificates RLS
DROP POLICY IF EXISTS campaign_roi_cert_workspace_isolation ON public.campaign_roi_certificates;
DROP POLICY IF EXISTS roi_certificates_policy ON public.campaign_roi_certificates;
DROP POLICY IF EXISTS roi_certificates_isolation ON public.campaign_roi_certificates;

CREATE POLICY campaign_roi_certificates_isolation ON public.campaign_roi_certificates
    FOR ALL
    USING (
        is_public = true 
        OR workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    )
    WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    );

-- FLAW-DB-31: Add FOR ALL RLS policies on campaign_enrollments and campaign_execution_states
DROP POLICY IF EXISTS campaign_enrollments_select ON public.campaign_enrollments;
DROP POLICY IF EXISTS campaign_enrollments_all ON public.campaign_enrollments;
CREATE POLICY campaign_enrollments_all ON public.campaign_enrollments
    FOR ALL
    USING (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    )
    WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    );

DROP POLICY IF EXISTS campaign_execution_states_select ON public.campaign_execution_states;
DROP POLICY IF EXISTS campaign_execution_states_all ON public.campaign_execution_states;
CREATE POLICY campaign_execution_states_all ON public.campaign_execution_states
    FOR ALL
    USING (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    )
    WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    );

-- ============================================================================
-- END OF MIGRATION 104
-- ============================================================================
