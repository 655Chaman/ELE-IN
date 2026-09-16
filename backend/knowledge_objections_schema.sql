-- ⚠️  ORPHAN MIGRATION FILE — NOT TRACKED BY apply_migrations.py
-- This file lives outside the migrations/ directory and will NOT be applied automatically.
-- If this schema change is required, move this file into backend/migrations/ with a proper
-- sequential name and add it to the ordered list in backend/scripts/apply_migrations.py.
-- File: knowledge_objections_schema.sql
CREATE TABLE IF NOT EXISTS public.knowledge_objections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id VARCHAR NOT NULL,
    trigger TEXT NOT NULL,
    playbook TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE public.knowledge_objections ENABLE ROW LEVEL SECURITY;

-- Add policies
CREATE POLICY "Users can manage their own workspace objections"
ON public.knowledge_objections
FOR ALL
USING (workspace_id = current_setting('request.jwt.claims', true)::json->>'workspace_id')
WITH CHECK (workspace_id = current_setting('request.jwt.claims', true)::json->>'workspace_id');
