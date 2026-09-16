-- EXECUTION: TRANSACTIONAL

SET LOCAL lock_timeout = '2s';

ALTER TABLE public.campaign_execution_states
ADD COLUMN IF NOT EXISTS workspace_id UUID;

ALTER TABLE public.workspaces
ADD COLUMN IF NOT EXISTS last_queue_poll_at TIMESTAMPTZ NOT NULL DEFAULT '-infinity'::timestamptz;
