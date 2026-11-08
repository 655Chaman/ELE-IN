-- Migration 121: Fix PostgreSQL 0A000 Error on Window Functions FOR UPDATE in dequeue_due_leads_v2
-- EPF Paranoia Layer 0 & 1: Separate prioritization CTE from locking CTE.
-- PostgreSQL forbids FOR UPDATE directly on queries with window functions.

BEGIN;

CREATE OR REPLACE FUNCTION public.dequeue_due_leads_v2(
    p_batch_size INT DEFAULT 500,
    p_max_per_campaign INT DEFAULT 10,
    p_lease_seconds INT DEFAULT 300
) RETURNS SETOF public.campaign_execution_states
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_token UUID := gen_random_uuid();
    v_expires TIMESTAMPTZ := now() + (p_lease_seconds || ' seconds')::INTERVAL;
BEGIN
    RETURN QUERY
    WITH prioritized AS (
        SELECT ces.id,
               ROW_NUMBER() OVER (
                   PARTITION BY ce.campaign_id 
                   ORDER BY ces.next_run_at ASC NULLS FIRST
               ) as rank
        FROM public.campaign_execution_states ces
        JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
        JOIN public.campaigns c ON c.id = ce.campaign_id
        WHERE ces.status = 'pending'
          AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
          AND UPPER(c.status::text) = 'ACTIVE'
    ),
    selected AS (
        SELECT ces.id
        FROM public.campaign_execution_states ces
        JOIN prioritized p ON p.id = ces.id
        WHERE p.rank <= p_max_per_campaign
        ORDER BY p.rank ASC
        LIMIT p_batch_size
        FOR UPDATE OF ces SKIP LOCKED
    )
    UPDATE public.campaign_execution_states u
    SET status = 'running',
        lease_token = v_token,
        lease_expires_at = v_expires,
        updated_at = now()
    FROM selected s
    WHERE u.id = s.id
    RETURNING u.*;
END;
$$;

GRANT EXECUTE ON FUNCTION public.dequeue_due_leads_v2(INT, INT, INT) TO authenticated, service_role;

COMMIT;
