-- ⚠️  ORPHAN MIGRATION FILE — NOT TRACKED BY apply_migrations.py
-- This file lives outside the migrations/ directory and will NOT be applied automatically.
-- If this schema change is required, move this file into backend/migrations/ with a proper
-- sequential name and add it to the ordered list in backend/scripts/apply_migrations.py.
-- File: phase_4_synthesis.sql
CREATE TABLE IF NOT EXISTS public.knowledge_synthesis_drafts (
    workspace_id uuid PRIMARY KEY REFERENCES public.workspaces(id) ON DELETE CASCADE,
    core_value_prop text,
    identified_tone text[],
    target_customer_profile text,
    key_differentiators text[],
    proof_points text[],
    primary_pain_points_solved text[],
    status text DEFAULT 'pending_review',
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now()),
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now())
);

-- Enable RLS for drafts so the frontend can query it directly
ALTER TABLE public.knowledge_synthesis_drafts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view synthesis drafts in their workspaces"
    ON public.knowledge_synthesis_drafts FOR SELECT
    USING (workspace_id IN (
        SELECT workspace_id FROM public.workspace_members WHERE user_id = auth.uid()
    ));

ALTER TABLE public.knowledge_synthesis_drafts ADD COLUMN IF NOT EXISTS generated_from_vector_count INT DEFAULT 0;
