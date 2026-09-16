CREATE TABLE IF NOT EXISTS public.processing_jobs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  asset_id     UUID,
  job_type     TEXT NOT NULL,  -- 'url', 'text', 'pdf', 'csv'
  status       TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'running', 'done', 'failed'
  payload      JSONB NOT NULL DEFAULT '{}',
  error_msg    TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS processing_jobs_status_idx ON public.processing_jobs (status, created_at);
