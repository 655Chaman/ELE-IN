-- Migration 086: Account-Based Marketing (ABM) Buying Committees & Multithreading Orchestration
-- Description: Enables target account mapping, buying committee role archetypes, role-differentiated messaging, and account heat scores.
-- Paranoia Framework: Idempotent DDL with IF NOT EXISTS, RLS policies, and defensive defaults.

CREATE TABLE IF NOT EXISTS public.target_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    company_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'tier_1' CHECK (tier IN ('tier_1', 'tier_2', 'tier_3')),
    employee_count INT DEFAULT 250,
    industry TEXT DEFAULT 'Software & Technology',
    account_heat_score INT NOT NULL DEFAULT 10,
    stage TEXT NOT NULL DEFAULT 'discovery' CHECK (stage IN ('discovery', 'multithreaded', 'consensus_building', 'opportunity')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.account_committee_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES public.target_accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    lead_id UUID,
    prospect_name TEXT NOT NULL,
    title TEXT NOT NULL,
    email TEXT,
    linkedin_url TEXT,
    role_archetype TEXT NOT NULL DEFAULT 'champion' CHECK (role_archetype IN ('economic_buyer', 'champion', 'technical_evaluator', 'end_user')),
    status TEXT NOT NULL DEFAULT 'uncontacted' CHECK (status IN ('uncontacted', 'engaged', 'replied', 'meeting_booked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.account_committee_members ADD COLUMN IF NOT EXISTS email TEXT;

CREATE TABLE IF NOT EXISTS public.multithread_campaign_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES public.target_accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    campaign_id UUID,
    committee_size INT NOT NULL DEFAULT 3,
    staggered_interval_hours INT NOT NULL DEFAULT 4,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
    launched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid querying
CREATE INDEX IF NOT EXISTS idx_target_accounts_ws ON public.target_accounts(workspace_id, domain);
CREATE INDEX IF NOT EXISTS idx_committee_members_acc ON public.account_committee_members(account_id, role_archetype);
CREATE INDEX IF NOT EXISTS idx_multithread_runs_ws ON public.multithread_campaign_runs(workspace_id, account_id);

-- Row-Level Security
ALTER TABLE public.target_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_committee_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.multithread_campaign_runs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'target_accounts' AND policyname = 'target_accounts_ws_policy') THEN
        CREATE POLICY target_accounts_ws_policy ON public.target_accounts FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'account_committee_members' AND policyname = 'account_committee_members_ws_policy') THEN
        CREATE POLICY account_committee_members_ws_policy ON public.account_committee_members FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'multithread_campaign_runs' AND policyname = 'multithread_campaign_runs_ws_policy') THEN
        CREATE POLICY multithread_campaign_runs_ws_policy ON public.multithread_campaign_runs FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR auth.role() = 'service_role');
    END IF;
END $$;
