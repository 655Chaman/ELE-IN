-- =====================================================================
-- Phase 3: Performance, Fairness, and Isolation
-- =====================================================================

BEGIN;

-- 1. Performance: Fix full-table scan on the continuous execution queue polling
CREATE INDEX IF NOT EXISTS idx_ces_dequeue 
ON public.campaign_execution_states(next_run_at ASC NULLS FIRST) 
WHERE status IN ('pending', 'running');

-- 2. Observability: Add missing account attribution to execution tracking
ALTER TABLE public.campaign_node_executions
ADD COLUMN IF NOT EXISTS account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL;

-- Attempt to add account_id to campaign_events if it exists (Phase 2 created it)
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'campaign_events') THEN
        ALTER TABLE public.campaign_events ADD COLUMN IF NOT EXISTS account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL;
    END IF;
END $$;

-- 3. Fair-Share Scheduling: Replace the unfair FIFO dequeue with a workspace-partitioned bounded queue
-- By binding the inner lock to 5000 rows, we ensure bounded index scan latency.
-- By grouping by workspace_id and limiting to 5 per workspace, we prevent starvation.
CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
    p_batch_size integer DEFAULT 50
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
        SELECT ranked.id FROM (
            SELECT ces.id, ces.next_run_at,
                   row_number() OVER (PARTITION BY ce.workspace_id ORDER BY ces.next_run_at ASC NULLS FIRST) as rn
            FROM (
                SELECT id, enrollment_id, next_run_at
                FROM public.campaign_execution_states
                WHERE status IN ('pending', 'running')
                  AND (next_run_at IS NULL OR next_run_at <= now())
                ORDER BY next_run_at ASC NULLS FIRST
                LIMIT 5000
                FOR UPDATE SKIP LOCKED
            ) ces
            JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
            JOIN public.campaigns c ON c.id = ce.campaign_id
            WHERE c.status = 'ACTIVE'
        ) ranked
        WHERE rn <= GREATEST(1, p_batch_size / 5) -- Dynamic fair share based on batch size
        ORDER BY ranked.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
    )
    RETURNING *;
END;
$$;

COMMIT;
