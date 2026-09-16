CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
    p_batch_size integer DEFAULT 50,
    p_campaign_ids uuid[] DEFAULT NULL
)
RETURNS SETOF public.lead_states
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    UPDATE public.lead_states
    SET
        status     = 'processing',
        updated_at = now()
    WHERE id IN (
        SELECT id
        FROM public.lead_states
        WHERE status IN ('pending', 'running')
          AND (next_run_at IS NULL OR next_run_at <= now())
          AND (p_campaign_ids IS NULL OR campaign_id = ANY(p_campaign_ids))
        ORDER BY next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;
