-- ==============================================================================
-- MIGRATION: 119_scale_and_tier_security_patch
-- PARANOIA FRAMEWORK: Layer 0, Layer 1 & Layer 2
-- Fixes:
--   1. FLAW-01: Creates processing_locks and try_acquire_distributed_lock RPC.
--   2. FLAW-02: Adds unique composite index on credit_deductions(workspace_id, idempotency_key).
--   3. FLAW-03: Hardens RLS on campaign_lead_sender_locks to prevent cross-tenant leaks.
--   4. FLAW-18: Hardens deduct_credits_safely with strict tier-aware overdraft floors.
--   5. FLAW-06 & FLAW-07: Adds dequeue_due_leads_v2 multi-tenant fair scheduling RPC.
--   6. Adds scheduler partial index on campaign_execution_states(status, next_run_at).
-- ==============================================================================

BEGIN;

-- 1. Index idempotency_key to prevent multi-million row table scans during credit deductions
CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_deductions_ws_idemp 
    ON public.credit_deductions(workspace_id, idempotency_key);

-- 2. Index campaign execution states for instant due-lead retrieval
CREATE INDEX IF NOT EXISTS idx_ces_due_scheduler 
    ON public.campaign_execution_states(status, next_run_at) 
    WHERE status = 'pending';

-- 3. Distributed Lock Table and RPCs (FLAW-01)
CREATE TABLE IF NOT EXISTS public.processing_locks (
    lock_name TEXT PRIMARY KEY,
    locked_until TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01 00:00:00+00'
);

CREATE OR REPLACE FUNCTION public.try_acquire_distributed_lock(
    p_lock_name TEXT,
    p_ttl_seconds INT DEFAULT 60
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_acquired BOOLEAN := FALSE;
BEGIN
    INSERT INTO public.processing_locks (lock_name, locked_until)
    VALUES (p_lock_name, now() + (p_ttl_seconds || ' seconds')::interval)
    ON CONFLICT (lock_name) DO UPDATE
    SET locked_until = now() + (p_ttl_seconds || ' seconds')::interval
    WHERE processing_locks.locked_until <= now()
    RETURNING true INTO v_acquired;

    RETURN COALESCE(v_acquired, false);
END;
$$;

CREATE OR REPLACE FUNCTION public.release_distributed_lock(
    p_lock_name TEXT
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE public.processing_locks
    SET locked_until = '1970-01-01 00:00:00+00'
    WHERE lock_name = p_lock_name;
END;
$$;

GRANT ALL ON TABLE public.processing_locks TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.try_acquire_distributed_lock(TEXT, INT) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.release_distributed_lock(TEXT) TO authenticated, service_role;

-- 4. Fix critical cross-tenant data leak on campaign_lead_sender_locks (FLAW-03)
DROP POLICY IF EXISTS campaign_lead_sender_locks_workspace_isolation ON public.campaign_lead_sender_locks;
CREATE POLICY campaign_lead_sender_locks_workspace_isolation ON public.campaign_lead_sender_locks
    FOR ALL
    TO authenticated
    USING (workspace_id IN (SELECT public.my_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));

-- 5. Safe sender locks constraint using NULLS NOT DISTINCT (FLAW-21)
CREATE UNIQUE INDEX IF NOT EXISTS uq_campaign_lead_sender_nulls_not_distinct 
    ON public.campaign_lead_sender_locks(workspace_id, campaign_id, lead_id) NULLS NOT DISTINCT;

-- 6. Tier-aware atomic credit deduction with strict overdraft floor (FLAW-18)
CREATE OR REPLACE FUNCTION public.deduct_credits_safely(
    p_workspace_id UUID,
    p_amount INT,
    p_action_type TEXT,
    p_idempotency_key TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_current_balance INT;
    v_tier TEXT;
    v_min_balance INT := 0;
    v_actual_cost INT;
    v_new_balance INT;
    v_already_processed BOOLEAN;
BEGIN
    -- LAYER 1 PARANOIA: Row-level lock on public.workspaces first to serialize all requests
    SELECT data_cleaning_credits, COALESCE(tier::TEXT, 'FREE')
    INTO v_current_balance, v_tier
    FROM public.workspaces
    WHERE id = p_workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', 0,
            'reason', 'workspace_not_found',
            'error', 'workspace_not_found'
        );
    END IF;

    v_current_balance := COALESCE(v_current_balance, 0);
    v_tier := UPPER(COALESCE(v_tier, 'FREE'));

    -- Determine tier-aware overdraft floor: Free is 0, Paid is -500
    IF v_tier IN ('PRO', 'GROWTH', 'ENTERPRISE', 'AGENCY', 'UNLIMITED', 'SCALE') THEN
        v_min_balance := -500;
    ELSE
        v_min_balance := 0;
    END IF;

    -- Check idempotency under lock using indexed (workspace_id, idempotency_key)
    SELECT EXISTS (
        SELECT 1 FROM public.credit_deductions 
        WHERE workspace_id = p_workspace_id AND idempotency_key = p_idempotency_key
    ) INTO v_already_processed;

    IF v_already_processed THEN
        SELECT balance_after INTO v_new_balance
        FROM public.credit_deductions
        WHERE workspace_id = p_workspace_id AND idempotency_key = p_idempotency_key;

        RETURN jsonb_build_object(
            'success', true,
            'balance', v_new_balance,
            'reason', 'already_processed',
            'already_processed', true
        );
    END IF;

    -- Determine actual cost
    IF p_amount = 0 THEN
        SELECT credits INTO v_actual_cost
        FROM public.credit_action_costs
        WHERE action_type = p_action_type AND is_active = true;

        v_actual_cost := COALESCE(v_actual_cost, 0);
    ELSE
        v_actual_cost := p_amount;
    END IF;

    -- Check overdraft boundary against tier-specific floor
    v_new_balance := v_current_balance - v_actual_cost;
    IF v_new_balance < v_min_balance THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', v_current_balance,
            'reason', 'insufficient_credits',
            'error', 'insufficient_credits',
            'shortfall', (v_min_balance - v_new_balance),
            'min_allowed', v_min_balance
        );
    END IF;

    -- Deduct atomically
    UPDATE public.workspaces
    SET data_cleaning_credits = v_new_balance,
        updated_at = NOW()
    WHERE id = p_workspace_id;

    -- Record deduction log
    INSERT INTO public.credit_deductions (
        workspace_id, action_type, amount, balance_after, idempotency_key, metadata
    ) VALUES (
        p_workspace_id, p_action_type, v_actual_cost, v_new_balance, p_idempotency_key, p_metadata
    );

    RETURN jsonb_build_object(
        'success', true,
        'balance', v_new_balance,
        'reason', 'ok'
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.deduct_credits_safely(UUID, INT, TEXT, TEXT, JSONB) TO authenticated, service_role;

-- 7. Multi-Tenant Fair Scheduling Dispatcher (FLAW-06 & FLAW-07)
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
        FOR UPDATE OF ces SKIP LOCKED
    ),
    selected AS (
        SELECT id FROM prioritized WHERE rank <= p_max_per_campaign LIMIT p_batch_size
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
