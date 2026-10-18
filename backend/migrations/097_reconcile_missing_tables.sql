-- ==============================================================================
-- MIGRATION: 097_reconcile_missing_tables
-- PARANOIA FRAMEWORK: Layer 0 (Foundation) & Layer 1 (Environmental Reliability)
-- Reconciles 8 phantom tables queried throughout codebase that were missing DDL.
-- Includes RLS enablement and workspace tenant isolation policies.
-- ==============================================================================

BEGIN;

-- 1. campaign_events (Orchestrator telemetry and MCP stats)
CREATE TABLE IF NOT EXISTS public.campaign_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID NOT NULL REFERENCES public.campaigns(id) ON DELETE CASCADE,
    enrollment_id UUID REFERENCES public.campaign_enrollments(id) ON DELETE CASCADE,
    account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
    node_id TEXT,
    event_type TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Environmental Hardening: If campaign_events already existed from prior schema, ensure all indexed columns exist
ALTER TABLE public.campaign_events ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE;
ALTER TABLE public.campaign_events ADD COLUMN IF NOT EXISTS campaign_id UUID REFERENCES public.campaigns(id) ON DELETE CASCADE;
ALTER TABLE public.campaign_events ADD COLUMN IF NOT EXISTS enrollment_id UUID REFERENCES public.campaign_enrollments(id) ON DELETE CASCADE;
ALTER TABLE public.campaign_events ADD COLUMN IF NOT EXISTS account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL;
ALTER TABLE public.campaign_events ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE public.campaign_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_campaign_events_ws_camp ON public.campaign_events(workspace_id, campaign_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_campaign_events_enrollment ON public.campaign_events(enrollment_id);
CREATE INDEX IF NOT EXISTS idx_campaign_events_account ON public.campaign_events(account_id);

ALTER TABLE public.campaign_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'campaign_events' AND policyname = 'campaign_events_isolation') THEN
        CREATE POLICY campaign_events_isolation ON public.campaign_events
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;


-- 2. campaign_nodes (Relational execution graph nodes)
CREATE TABLE IF NOT EXISTS public.campaign_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_version_id UUID NOT NULL REFERENCES public.campaign_versions(id) ON DELETE CASCADE,
    node_key TEXT,
    node_type TEXT NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    ui_position JSONB NOT NULL DEFAULT '{"x": 0, "y": 0}'::jsonb,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Environmental Hardening: If campaign_nodes already existed from prior schema, ensure campaign_id and ui_position exist
ALTER TABLE public.campaign_nodes ADD COLUMN IF NOT EXISTS campaign_id UUID REFERENCES public.campaigns(id) ON DELETE CASCADE;
ALTER TABLE public.campaign_nodes ADD COLUMN IF NOT EXISTS ui_position JSONB NOT NULL DEFAULT '{"x": 0, "y": 0}'::jsonb;
ALTER TABLE public.campaign_nodes ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE public.campaign_nodes cn
SET campaign_id = cv.campaign_id
FROM public.campaign_versions cv
WHERE cn.campaign_version_id = cv.id AND cn.campaign_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_campaign_nodes_version ON public.campaign_nodes(campaign_version_id);
CREATE INDEX IF NOT EXISTS idx_campaign_nodes_campaign ON public.campaign_nodes(campaign_id);

ALTER TABLE public.campaign_nodes ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'campaign_nodes' AND policyname = 'campaign_nodes_isolation') THEN
        CREATE POLICY campaign_nodes_isolation ON public.campaign_nodes
        FOR ALL USING (
            campaign_version_id IN (
                SELECT cv.id FROM public.campaign_versions cv
                JOIN public.campaigns c ON c.id = cv.campaign_id
                WHERE c.workspace_id IN (SELECT public.my_workspace_ids())
            )
        )
        WITH CHECK (
            campaign_version_id IN (
                SELECT cv.id FROM public.campaign_versions cv
                JOIN public.campaigns c ON c.id = cv.campaign_id
                WHERE c.workspace_id IN (SELECT public.my_workspace_ids())
            )
        );
    END IF;
END $$;


-- 3. campaign_edges (Relational execution graph edges)
CREATE TABLE IF NOT EXISTS public.campaign_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_version_id UUID NOT NULL REFERENCES public.campaign_versions(id) ON DELETE CASCADE,
    source_node_id UUID NOT NULL REFERENCES public.campaign_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES public.campaign_nodes(id) ON DELETE CASCADE,
    source_handle TEXT,
    target_handle TEXT,
    condition TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Environmental Hardening: If campaign_edges already existed, ensure condition and created_at columns exist
ALTER TABLE public.campaign_edges ADD COLUMN IF NOT EXISTS condition TEXT;
ALTER TABLE public.campaign_edges ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_campaign_edges_version ON public.campaign_edges(campaign_version_id);

ALTER TABLE public.campaign_edges ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'campaign_edges' AND policyname = 'campaign_edges_isolation') THEN
        CREATE POLICY campaign_edges_isolation ON public.campaign_edges
        FOR ALL USING (
            campaign_version_id IN (
                SELECT cv.id FROM public.campaign_versions cv
                JOIN public.campaigns c ON c.id = cv.campaign_id
                WHERE c.workspace_id IN (SELECT public.my_workspace_ids())
            )
        )
        WITH CHECK (
            campaign_version_id IN (
                SELECT cv.id FROM public.campaign_versions cv
                JOIN public.campaigns c ON c.id = cv.campaign_id
                WHERE c.workspace_id IN (SELECT public.my_workspace_ids())
            )
        );
    END IF;
END $$;


-- 4. system_api_keys (Failover key pool & DEK vault storage)
CREATE TABLE IF NOT EXISTS public.system_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE,
    api_key TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'nvidia',
    service TEXT NOT NULL DEFAULT 'ai',
    status TEXT NOT NULL DEFAULT 'active',
    secret_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.system_api_keys ADD COLUMN IF NOT EXISTS service TEXT NOT NULL DEFAULT 'ai';
ALTER TABLE public.system_api_keys ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';

CREATE INDEX IF NOT EXISTS idx_system_api_keys_lookup ON public.system_api_keys(service, status);

ALTER TABLE public.system_api_keys ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'system_api_keys' AND policyname = 'system_api_keys_isolation') THEN
        CREATE POLICY system_api_keys_isolation ON public.system_api_keys
        FOR ALL USING (
            workspace_id IS NULL OR workspace_id IN (SELECT public.my_workspace_ids())
        )
        WITH CHECK (
            workspace_id IS NULL OR workspace_id IN (SELECT public.my_workspace_ids())
        );
    END IF;
END $$;


-- 5. email_events (Multichannel intent triggers, cold email opened/clicked/bounced)
CREATE TABLE IF NOT EXISTS public.email_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES public.leads(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    link_url TEXT,
    error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.email_events ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE;
ALTER TABLE public.email_events ADD COLUMN IF NOT EXISTS lead_id UUID REFERENCES public.leads(id) ON DELETE CASCADE;
ALTER TABLE public.email_events ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'sent';

CREATE INDEX IF NOT EXISTS idx_email_events_lead ON public.email_events(workspace_id, lead_id, event_type);

ALTER TABLE public.email_events ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'email_events' AND policyname = 'email_events_isolation') THEN
        CREATE POLICY email_events_isolation ON public.email_events
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;


-- 6. workspace_settings (Webhook verification secrets & global workspace configs)
CREATE TABLE IF NOT EXISTS public.workspace_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL UNIQUE REFERENCES public.workspaces(id) ON DELETE CASCADE,
    booking_webhook_secret TEXT,
    webhook_signing_secret TEXT,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.workspace_settings ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES public.workspaces(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_workspace_settings_ws ON public.workspace_settings(workspace_id);

ALTER TABLE public.workspace_settings ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'workspace_settings' AND policyname = 'workspace_settings_isolation') THEN
        CREATE POLICY workspace_settings_isolation ON public.workspace_settings
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;


-- 7. Compatibility Views (Bridge legacy table names to current schema)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_views WHERE viewname = 'account_action_limits') AND
       NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'account_action_limits') THEN
        CREATE OR REPLACE VIEW public.account_action_limits AS 
        SELECT 
            account_id,
            action_type,
            custom_limit AS daily_limit,
            custom_limit,
            expires_at,
            created_at
        FROM public.account_limit_overrides;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_views WHERE viewname = 'campaign_leads') AND
       NOT EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'campaign_leads') THEN
        CREATE OR REPLACE VIEW public.campaign_leads AS
        SELECT 
            id,
            campaign_id,
            lead_id,
            status,
            account_id,
            enrolled_at AS created_at,
            enrolled_at
        FROM public.campaign_enrollments;
    END IF;
END $$;


-- 8. ai_reply_approvals RLS hardening (Fix missing RLS from 049)
ALTER TABLE public.ai_reply_approvals ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'ai_reply_approvals' AND policyname = 'ai_reply_approvals_isolation') THEN
        CREATE POLICY ai_reply_approvals_isolation ON public.ai_reply_approvals
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

COMMIT;
