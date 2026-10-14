-- Migration 087: Autonomous Champion Job-Change Boomerang Tracker, Warm Intro Graph & Closed-Lost Deal Revival Engine
-- Description: Creates tables for tracking past customer/champion job changes, mutual connection warm intro bridges, and closed-lost deal resurrections.
-- Paranoia Framework: Fully idempotent DDL with IF NOT EXISTS, composite indices, and tenant RLS policies.

CREATE TABLE IF NOT EXISTS public.champion_job_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    prospect_name TEXT NOT NULL,
    linkedin_url TEXT,
    previous_company TEXT NOT NULL,
    previous_title TEXT NOT NULL,
    new_company TEXT NOT NULL,
    new_title TEXT NOT NULL,
    new_domain TEXT,
    relationship_type TEXT NOT NULL DEFAULT 'former_champion' CHECK (relationship_type IN ('past_customer', 'former_champion', 'closed_lost_contact', 'power_user')),
    days_in_new_role INT NOT NULL DEFAULT 14,
    buying_window_score INT NOT NULL DEFAULT 85,
    is_internal_promotion BOOLEAN NOT NULL DEFAULT FALSE,
    playbook_message TEXT,
    status TEXT NOT NULL DEFAULT 'detected' CHECK (status IN ('detected', 'playbook_drafted', 'enrolled', 'converted')),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.warm_intro_paths (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    target_prospect_name TEXT NOT NULL,
    target_company TEXT NOT NULL,
    target_title TEXT NOT NULL,
    connector_name TEXT NOT NULL,
    connector_role TEXT NOT NULL,
    bridge_type TEXT NOT NULL DEFAULT 'shared_alumni' CHECK (bridge_type IN ('shared_alumni', 'mutual_connection', 'shared_investor', 'board_member')),
    overlap_context TEXT NOT NULL,
    warmth_score INT NOT NULL DEFAULT 88,
    intro_request_draft TEXT,
    direct_bridge_draft TEXT,
    status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available', 'requested', 'introduced', 'replied')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.closed_lost_revivals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    prospect_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    title TEXT NOT NULL,
    lost_reason TEXT NOT NULL DEFAULT 'bad_timing' CHECK (lost_reason IN ('budget_freeze', 'missing_feature', 'bad_timing', 'competitor_chosen', 'ghosted_no_decision')),
    days_since_lost INT NOT NULL DEFAULT 120,
    original_deal_value NUMERIC NOT NULL DEFAULT 25000,
    revival_trigger TEXT,
    revival_score INT NOT NULL DEFAULT 80,
    resurrection_message TEXT,
    status TEXT NOT NULL DEFAULT 'ready_to_revive' CHECK (status IN ('ready_to_revive', 'revival_sent', 're_engaged', 'pipeline_restored')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for fast filtering
CREATE INDEX IF NOT EXISTS idx_champion_job_changes_ws ON public.champion_job_changes(workspace_id, buying_window_score DESC);
CREATE INDEX IF NOT EXISTS idx_warm_intro_paths_ws ON public.warm_intro_paths(workspace_id, warmth_score DESC);
CREATE INDEX IF NOT EXISTS idx_closed_lost_revivals_ws ON public.closed_lost_revivals(workspace_id, revival_score DESC);

-- Enable Row-Level Security
ALTER TABLE public.champion_job_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.warm_intro_paths ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.closed_lost_revivals ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'champion_job_changes' AND policyname = 'champion_job_changes_ws_policy') THEN
        CREATE POLICY champion_job_changes_ws_policy ON public.champion_job_changes FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'warm_intro_paths' AND policyname = 'warm_intro_paths_ws_policy') THEN
        CREATE POLICY warm_intro_paths_ws_policy ON public.warm_intro_paths FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'closed_lost_revivals' AND policyname = 'closed_lost_revivals_ws_policy') THEN
        CREATE POLICY closed_lost_revivals_ws_policy ON public.closed_lost_revivals FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()) OR workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
