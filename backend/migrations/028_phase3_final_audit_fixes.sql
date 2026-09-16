BEGIN;

-- Area 5: Relational Integrity Fixes
ALTER TABLE public.campaign_node_executions 
ADD CONSTRAINT fk_cne_version_node
FOREIGN KEY (node_id) REFERENCES public.campaign_nodes(id);

ALTER TABLE public.accounts
DROP CONSTRAINT IF EXISTS accounts_id_workspace_id_key;

ALTER TABLE public.accounts
ADD CONSTRAINT accounts_id_workspace_id_key UNIQUE (id, workspace_id);

ALTER TABLE public.campaign_node_executions
ADD CONSTRAINT fk_cne_workspace_account
FOREIGN KEY (account_id, workspace_id) REFERENCES public.accounts(id, workspace_id);

-- Area 1: Scheduler Scalability
ALTER TABLE public.campaign_execution_states 
ADD COLUMN IF NOT EXISTS workspace_id UUID;

-- Backfill workspace_id for existing rows
UPDATE public.campaign_execution_states ces
SET workspace_id = ce.workspace_id
FROM public.campaign_enrollments ce
WHERE ces.enrollment_id = ce.id AND ces.workspace_id IS NULL;

-- Make workspace_id required for future inserts
ALTER TABLE public.campaign_execution_states 
ALTER COLUMN workspace_id SET NOT NULL;

-- Add a multi-tenant execution queue index
CREATE INDEX IF NOT EXISTS idx_ces_workspace_status_next_run 
ON public.campaign_execution_states (workspace_id, status, next_run_at ASC NULLS FIRST)
WHERE status IN ('pending', 'running');

-- Replace the unscalable window function query with an O(1) LATERAL partition
CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
    p_batch_size integer DEFAULT 50,
    p_campaign_ids uuid[] DEFAULT NULL
)
RETURNS SETOF public.campaign_execution_states
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.campaign_execution_states
    SET
        status     = 'processing',
        lease_token = gen_random_uuid(),
        lease_expires_at = now() + interval '5 minutes',
        updated_at = now()
    WHERE id IN (
        SELECT ces.id 
        FROM (
            SELECT DISTINCT workspace_id 
            FROM public.campaigns
            WHERE status = 'ACTIVE' 
              AND (p_campaign_ids IS NULL OR id = ANY(p_campaign_ids))
        ) w
        CROSS JOIN LATERAL (
            SELECT id, next_run_at
            FROM public.campaign_execution_states
            WHERE workspace_id = w.workspace_id
              AND status IN ('pending', 'running')
              AND (next_run_at IS NULL OR next_run_at <= now())
            ORDER BY next_run_at ASC NULLS FIRST
            LIMIT GREATEST(1, p_batch_size / 5)
        ) ces
        ORDER BY ces.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;

COMMIT;
