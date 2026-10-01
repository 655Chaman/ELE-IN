-- ⚠️  ORPHAN MIGRATION FILE — NOT TRACKED BY apply_migrations.py
-- This file lives outside the migrations/ directory and will NOT be applied automatically.
-- If this schema change is required, move this file into backend/migrations/ with a proper
-- sequential name and add it to the ordered list in backend/scripts/apply_migrations.py.
-- File: fix_jobs_rls.sql
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "processing_jobs_service_bypass" ON public.processing_jobs
    USING (auth.role() = 'service_role');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE POLICY "processing_jobs_workspace_isolation" ON public.processing_jobs FOR ALL
    USING (workspace_id IN (SELECT public.get_user_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.get_user_workspace_ids()));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
