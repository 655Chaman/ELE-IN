-- ==============================================================================
-- Migration 070: Personas columns, knowledge_assets raw_text, and objections unification
-- ==============================================================================

-- 1. Ensure personas table has target_titles, value_prop, tone_tweaks
ALTER TABLE public.personas 
ADD COLUMN IF NOT EXISTS value_prop TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS target_titles JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS tone_tweaks TEXT DEFAULT '';

-- 2. Ensure knowledge_assets table has raw_text column for text retries
ALTER TABLE public.knowledge_assets
ADD COLUMN IF NOT EXISTS raw_text TEXT;

-- 3. Ensure knowledge_objections table exists with correct schema and indices
CREATE TABLE IF NOT EXISTS public.knowledge_objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id VARCHAR NOT NULL,
    trigger TEXT NOT NULL,
    playbook TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_objections_workspace ON public.knowledge_objections(workspace_id);

-- Enable RLS
ALTER TABLE public.knowledge_objections ENABLE ROW LEVEL SECURITY;

-- Add RLS policy if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'knowledge_objections' AND policyname = 'Users can manage their own workspace objections'
    ) THEN
        CREATE POLICY "Users can manage their own workspace objections"
        ON public.knowledge_objections
        FOR ALL
        USING (workspace_id = current_setting('request.jwt.claims', true)::json->>'workspace_id')
        WITH CHECK (workspace_id = current_setting('request.jwt.claims', true)::json->>'workspace_id');
    END IF;
END $$;

-- 4. Sync legacy objections to knowledge_objections if any exist
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'objections') THEN
        INSERT INTO public.knowledge_objections (id, workspace_id, trigger, playbook, created_at)
        SELECT id, workspace_id::text, trigger, playbook, created_at 
        FROM public.objections
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;
