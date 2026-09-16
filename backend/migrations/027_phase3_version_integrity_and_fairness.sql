BEGIN;

-- 1. CAMPAIGN/VERSION INTEGRITY (Blocker 2)
ALTER TABLE public.campaign_versions 
DROP CONSTRAINT IF EXISTS campaign_versions_id_campaign_id_key;

ALTER TABLE public.campaign_versions 
ADD CONSTRAINT campaign_versions_id_campaign_id_key UNIQUE (id, campaign_id);

ALTER TABLE public.campaign_enrollments
DROP CONSTRAINT IF EXISTS fk_enrollment_version_integrity;

ALTER TABLE public.campaign_enrollments
ADD CONSTRAINT fk_enrollment_version_integrity 
FOREIGN KEY (campaign_version_id, campaign_id) 
REFERENCES public.campaign_versions (id, campaign_id);


-- 2. FAIR SCHEDULING (Blocker 1)
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
        SELECT ranked.id FROM (
            SELECT ces.id, ces.next_run_at,
                   row_number() OVER (PARTITION BY ce.workspace_id ORDER BY ces.next_run_at ASC NULLS FIRST) as rn
            FROM public.campaign_execution_states ces
            JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
            WHERE ces.status IN ('pending', 'running')
              AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
              AND (p_campaign_ids IS NULL OR ce.campaign_id = ANY(p_campaign_ids))
        ) ranked
        WHERE rn <= GREATEST(1, p_batch_size / 5)
        ORDER BY ranked.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;

COMMIT;
