BEGIN;

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
            SELECT ces.id, ces.next_run_at
            FROM public.campaign_execution_states ces
            JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
            JOIN public.accounts a ON a.id = ce.account_id
            WHERE ces.workspace_id = w.workspace_id
              AND ces.status IN ('pending', 'running')
              AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
              AND a.status = 'ACTIVE'
              AND a.manual_mode_enabled = FALSE
            ORDER BY ces.next_run_at ASC NULLS FIRST
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
