-- Migration 103: Workspace Cloud Blueprints Sync
-- Enables agencies and enterprise teams to save, sync, and share
-- Make.com / n8n style workflow blueprints across workspace team members.

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

-- Indexes for high-performance retrieval and unique name querying per tenant
CREATE INDEX IF NOT EXISTS idx_workspace_blueprints_ws_updated ON public.workspace_blueprints(workspace_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_workspace_blueprints_ws_name ON public.workspace_blueprints(workspace_id, name);

-- Row Level Security (RLS) Multi-Tenant Hardening
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

-- Service Role full bypass for background workers and service client
DROP POLICY IF EXISTS workspace_blueprints_service_role ON public.workspace_blueprints;
CREATE POLICY workspace_blueprints_service_role ON public.workspace_blueprints
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
