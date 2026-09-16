-- ⚠️  ORPHAN MIGRATION FILE — NOT TRACKED BY apply_migrations.py
-- This file lives outside the migrations/ directory and will NOT be applied automatically.
-- If this schema change is required, move this file into backend/migrations/ with a proper
-- sequential name and add it to the ordered list in backend/scripts/apply_migrations.py.
-- File: phase_9_objections.sql
-- NOTE: The ON DELETE CASCADE on workspace_id means that deleting a workspace 
-- instantly and silently deletes ALL its objection playbooks. 
-- This cascading behavior is intentional for data hygiene.

CREATE TABLE IF NOT EXISTS public.knowledge_objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    trigger VARCHAR(500) NOT NULL,
    playbook VARCHAR(5000) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_knowledge_objections_workspace ON public.knowledge_objections(workspace_id);

-- Enable RLS
ALTER TABLE public.knowledge_objections ENABLE ROW LEVEL SECURITY;

-- Updated at trigger function (if not already exists in public)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.updated_at = now();
   RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for knowledge_objections
DROP TRIGGER IF EXISTS update_knowledge_objections_updated_at ON public.knowledge_objections;
CREATE TRIGGER update_knowledge_objections_updated_at
BEFORE UPDATE ON public.knowledge_objections
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Allow SELECT
DROP POLICY IF EXISTS "Users can view objections in their workspaces" ON public.knowledge_objections;
DO $$
BEGIN
    CREATE POLICY "Users can view objections in their workspaces"
        ON public.knowledge_objections FOR SELECT
        USING (workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        ));
EXCEPTION WHEN DUPLICATE_OBJECT THEN NULL;
END;
$$;

-- Allow INSERT, UPDATE, DELETE
DROP POLICY IF EXISTS "Users can manage objections in their workspaces" ON public.knowledge_objections;
DO $$
BEGIN
    CREATE POLICY "Users can manage objections in their workspaces"
        ON public.knowledge_objections FOR ALL
        USING (workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        ))
        WITH CHECK (workspace_id IN (
            SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
        ));
EXCEPTION WHEN DUPLICATE_OBJECT THEN NULL;
END;
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_objections TO authenticated;
