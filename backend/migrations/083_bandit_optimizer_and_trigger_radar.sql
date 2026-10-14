-- Migration 083: Thompson Sampling Multi-Armed Bandit Copy Optimizer & Trigger Radar Events
-- Description: Enables autonomous Bayesian copy variant selection (MAB), genetic copy mutation, and career/funding trigger radar events.
-- Paranoia Framework: Idempotent DDL with IF NOT EXISTS, RLS policies, and defensive defaults.

CREATE TABLE IF NOT EXISTS public.bandit_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    campaign_id UUID,
    node_id TEXT,
    name TEXT NOT NULL DEFAULT 'Dynamic Copy Bandit',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
    exploration_factor NUMERIC NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.copy_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID REFERENCES public.bandit_experiments(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL,
    name TEXT NOT NULL,
    template_text TEXT NOT NULL,
    arm_type TEXT NOT NULL DEFAULT 'full_message' CHECK (arm_type IN ('hook', 'value_prop', 'cta', 'full_message')),
    alpha_param NUMERIC NOT NULL DEFAULT 1.0, -- Prior success count
    beta_param NUMERIC NOT NULL DEFAULT 1.0,  -- Prior failure count
    impressions INT NOT NULL DEFAULT 0,
    positive_replies INT NOT NULL DEFAULT 0,
    objections INT NOT NULL DEFAULT 0,
    unsubscribes INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'degraded', 'retired')),
    parent_variant_id UUID,
    generation INT NOT NULL DEFAULT 1,
    mutation_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.trigger_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    lead_id UUID,
    prospect_name TEXT NOT NULL,
    company_name TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('NEW_ROLE', 'PROMOTION', 'FUNDING_ROUND', 'HIRING_SURGE')),
    event_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'ENROLLED', 'DISMISSED')),
    generated_icebreaker TEXT,
    enrolled_campaign_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indices for rapid querying
CREATE INDEX IF NOT EXISTS idx_bandit_experiments_ws ON public.bandit_experiments(workspace_id, campaign_id);
CREATE INDEX IF NOT EXISTS idx_copy_variants_exp ON public.copy_variants(experiment_id, status);
CREATE INDEX IF NOT EXISTS idx_trigger_events_ws_status ON public.trigger_events(workspace_id, status);

-- Row-Level Security
ALTER TABLE public.bandit_experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.copy_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trigger_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'bandit_experiments' AND policyname = 'bandit_experiments_ws_policy') THEN
        CREATE POLICY bandit_experiments_ws_policy ON public.bandit_experiments FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'copy_variants' AND policyname = 'copy_variants_ws_policy') THEN
        CREATE POLICY copy_variants_ws_policy ON public.copy_variants FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'trigger_events' AND policyname = 'trigger_events_ws_policy') THEN
        CREATE POLICY trigger_events_ws_policy ON public.trigger_events FOR ALL USING (workspace_id = auth.uid() OR auth.role() = 'service_role');
    END IF;
END $$;
