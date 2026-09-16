-- ============================================================
-- AI KNOWLEDGE BASE SCHEMA (Personas, Objections, Assets, Synthesis)
-- ============================================================

-- Create pgvector extension if not exists
CREATE EXTENSION IF NOT EXISTS vector;

-- Personas Table
CREATE TABLE IF NOT EXISTS public.personas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    pain_points JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Objections Table
CREATE TABLE IF NOT EXISTS public.objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    trigger TEXT NOT NULL,
    playbook TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Knowledge Assets Table (For UI reference)
CREATE TABLE IF NOT EXISTS public.knowledge_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'synced',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Vector Chunks Table (Using pgvector)
CREATE TABLE IF NOT EXISTS public.knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES public.knowledge_assets(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536), -- Assuming OpenAI ada-002 dimension
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Synthesis Table (One per workspace)
CREATE TABLE IF NOT EXISTS public.knowledge_synthesis (
    workspace_id UUID PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    core_value_prop TEXT,
    identified_tone JSONB DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================

ALTER TABLE public.personas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.objections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_synthesis ENABLE ROW LEVEL SECURITY;

-- Personas
CREATE POLICY personas_ws_read ON public.personas FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY personas_ws_insert ON public.personas FOR INSERT WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY personas_ws_update ON public.personas FOR UPDATE USING (workspace_id IN (SELECT public.my_workspace_ids())) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY personas_ws_delete ON public.personas FOR DELETE USING (workspace_id IN (SELECT public.my_workspace_ids()));

-- Objections
CREATE POLICY objections_ws_read ON public.objections FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY objections_ws_insert ON public.objections FOR INSERT WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY objections_ws_update ON public.objections FOR UPDATE USING (workspace_id IN (SELECT public.my_workspace_ids())) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY objections_ws_delete ON public.objections FOR DELETE USING (workspace_id IN (SELECT public.my_workspace_ids()));

-- Assets
CREATE POLICY assets_ws_read ON public.knowledge_assets FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY assets_ws_insert ON public.knowledge_assets FOR INSERT WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY assets_ws_update ON public.knowledge_assets FOR UPDATE USING (workspace_id IN (SELECT public.my_workspace_ids())) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY assets_ws_delete ON public.knowledge_assets FOR DELETE USING (workspace_id IN (SELECT public.my_workspace_ids()));

-- Chunks
CREATE POLICY chunks_ws_read ON public.knowledge_chunks FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY chunks_ws_insert ON public.knowledge_chunks FOR INSERT WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY chunks_ws_update ON public.knowledge_chunks FOR UPDATE USING (workspace_id IN (SELECT public.my_workspace_ids())) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY chunks_ws_delete ON public.knowledge_chunks FOR DELETE USING (workspace_id IN (SELECT public.my_workspace_ids()));

-- Synthesis
CREATE POLICY synthesis_ws_read ON public.knowledge_synthesis FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY synthesis_ws_insert ON public.knowledge_synthesis FOR INSERT WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY synthesis_ws_update ON public.knowledge_synthesis FOR UPDATE USING (workspace_id IN (SELECT public.my_workspace_ids())) WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
CREATE POLICY synthesis_ws_delete ON public.knowledge_synthesis FOR DELETE USING (workspace_id IN (SELECT public.my_workspace_ids()));

-- Defaults
ALTER TABLE public.personas ALTER COLUMN workspace_id SET DEFAULT public.get_my_workspace_id();
ALTER TABLE public.objections ALTER COLUMN workspace_id SET DEFAULT public.get_my_workspace_id();
ALTER TABLE public.knowledge_assets ALTER COLUMN workspace_id SET DEFAULT public.get_my_workspace_id();
ALTER TABLE public.knowledge_chunks ALTER COLUMN workspace_id SET DEFAULT public.get_my_workspace_id();

