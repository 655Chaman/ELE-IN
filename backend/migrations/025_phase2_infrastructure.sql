BEGIN;

-- 1. campaign_node_executions
CREATE TABLE IF NOT EXISTS public.campaign_node_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'running', -- running, success, failed
    node_id TEXT NOT NULL,
    workspace_id UUID,
    enrollment_id UUID,
    campaign_version_id UUID,
    node_type TEXT,
    attempt INT,
    error_code TEXT,
    output_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_campaign_node_executions_idemp ON public.campaign_node_executions(idempotency_key);

-- 2. campaign_execution_states lease columns
ALTER TABLE public.campaign_execution_states
ADD COLUMN IF NOT EXISTS lease_token UUID,
ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

-- 3. accounts session lock ownership
ALTER TABLE public.accounts
ADD COLUMN IF NOT EXISTS session_lock_worker_id TEXT;

-- 4. Campaign Lease RPCs
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
        FROM public.campaign_execution_states ces
        WHERE ces.status IN ('pending', 'running')
          AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
          AND (p_campaign_ids IS NULL OR EXISTS (
              SELECT 1 FROM public.campaign_enrollments ce
              WHERE ce.id = ces.enrollment_id
                AND ce.campaign_id = ANY(p_campaign_ids)
          ))
        ORDER BY ces.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    RETURNING *;
END;
$$;

CREATE OR REPLACE FUNCTION public.renew_lead_lease(
    p_state_id UUID,
    p_lease_token UUID,
    p_extra_seconds INT
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.campaign_execution_states
    SET lease_expires_at = now() + (p_extra_seconds || ' seconds')::interval
    WHERE id = p_state_id AND lease_token = p_lease_token;
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

CREATE OR REPLACE FUNCTION public.release_lead_claim(
    p_state_id UUID,
    p_lease_token UUID,
    p_next_status TEXT,
    p_next_node UUID,
    p_next_run TIMESTAMPTZ,
    p_variables JSONB,
    p_error_reason TEXT,
    p_attempts INT
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = p_next_status::public.lead_state_status,
        current_node_id = COALESCE(p_next_node, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        attempts = COALESCE(p_attempts, attempts),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id AND lease_token = p_lease_token;
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

CREATE OR REPLACE FUNCTION public.recover_stale_leases(p_timeout_minutes INT)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = 'pending',
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE status = 'processing' 
      AND (lease_expires_at IS NULL OR lease_expires_at < now());
      
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END;
$$;

-- 5. Account Lock RPCs
DROP FUNCTION IF EXISTS public.try_acquire_account_lock(uuid, timestamptz, timestamptz);

CREATE OR REPLACE FUNCTION public.try_acquire_account_lock(
    p_account_id UUID,
    p_duration_seconds INT,
    p_worker_id TEXT
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows integer;
BEGIN
    UPDATE public.accounts
    SET session_locked_until = now() + (p_duration_seconds || ' seconds')::interval,
        session_lock_worker_id = p_worker_id
    WHERE id = p_account_id
      AND (session_locked_until IS NULL OR session_locked_until < now() OR session_lock_worker_id = p_worker_id);
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

CREATE OR REPLACE FUNCTION public.renew_account_lock(
    p_account_id UUID,
    p_worker_id TEXT,
    p_extra_seconds INT
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.accounts
    SET session_locked_until = now() + (p_extra_seconds || ' seconds')::interval
    WHERE id = p_account_id AND session_lock_worker_id = p_worker_id;
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

CREATE OR REPLACE FUNCTION public.release_account_lock(
    p_account_id UUID,
    p_worker_id TEXT
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.accounts
    SET session_locked_until = NULL,
        session_lock_worker_id = NULL
    WHERE id = p_account_id AND session_lock_worker_id = p_worker_id;
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

COMMIT;
