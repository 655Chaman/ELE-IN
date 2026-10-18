-- ==============================================================================
-- Migration 100: Campaign Subsystem Paranoia Hardening
-- Resolves: VULN-16, VULN-17, VULN-18, VULN-19, DB-01 through DB-16
-- Applies the Three-Layer Logic Architecture (Paranoia Framework) across RLS, RPCs, 
-- Relational Cascades, Missing Indexes, and State Transitions.
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- 1. Campaign Versions Row Level Security (VULN-19, DB-02)
-- ------------------------------------------------------------------------------
ALTER TABLE public.campaign_versions ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    DROP POLICY IF EXISTS campaign_versions_tenant_isolation ON public.campaign_versions;
    CREATE POLICY campaign_versions_tenant_isolation ON public.campaign_versions
    FOR ALL USING (
        campaign_id IN (
            SELECT id FROM public.campaigns 
            WHERE workspace_id IN (SELECT public.my_workspace_ids())
        )
    )
    WITH CHECK (
        campaign_id IN (
            SELECT id FROM public.campaigns 
            WHERE workspace_id IN (SELECT public.my_workspace_ids())
        )
    );
END $$;


-- ------------------------------------------------------------------------------
-- 2. Campaign Accounts Tenant Check Hardening (DB-13)
-- Ensures both campaign_id AND account_id belong to the caller's workspace
-- ------------------------------------------------------------------------------
DO $$ BEGIN
    DROP POLICY IF EXISTS campaign_accounts_tenant_isolation ON public.campaign_accounts;
    DROP POLICY IF EXISTS campaign_accounts_isolation ON public.campaign_accounts;
    DROP POLICY IF EXISTS campaign_accounts_ws ON public.campaign_accounts;

    CREATE POLICY campaign_accounts_tenant_isolation ON public.campaign_accounts
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM public.campaigns c
            JOIN public.accounts a ON a.workspace_id = c.workspace_id
            WHERE c.id = campaign_accounts.campaign_id
              AND a.id = campaign_accounts.account_id
              AND c.workspace_id IN (SELECT public.my_workspace_ids())
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.campaigns c
            JOIN public.accounts a ON a.workspace_id = c.workspace_id
            WHERE c.id = campaign_accounts.campaign_id
              AND a.id = campaign_accounts.account_id
              AND c.workspace_id IN (SELECT public.my_workspace_ids())
        )
    );

    -- processing_jobs: Multi-workspace support (VULN-20)
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'processing_jobs') THEN
        ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS processing_jobs_tenant_isolation ON public.processing_jobs;
        CREATE POLICY processing_jobs_tenant_isolation ON public.processing_jobs
        FOR ALL USING (
            workspace_id IN (SELECT public.my_workspace_ids())
        )
        WITH CHECK (
            workspace_id IN (SELECT public.my_workspace_ids())
        );
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- 3. Revoke Dangerous Public RPC Execution Privileges (VULN-16, VULN-17, VULN-18)
-- ------------------------------------------------------------------------------
DO $$ 
DECLARE
    r RECORD;
BEGIN
    -- Dynamically revoke EXECUTE on ALL overloads of sensitive RPCs from PUBLIC, anon, authenticated (VULN-16, VULN-17, VULN-18)
    FOR r IN 
        SELECT oid::regprocedure AS func_sig 
        FROM pg_proc 
        WHERE proname IN ('deduct_credits_safely', 'bulk_import_leads', 'get_user_id_by_email')
          AND pronamespace = 'public'::regnamespace
    LOOP
        EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || r.func_sig || ' FROM PUBLIC';
        EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || r.func_sig || ' FROM anon, authenticated';
        EXECUTE 'GRANT EXECUTE ON FUNCTION ' || r.func_sig || ' TO service_role';
    END LOOP;

    -- try_acquire_distributed_lock & release_distributed_lock
    FOR r IN 
        SELECT oid::regprocedure AS func_sig 
        FROM pg_proc 
        WHERE proname IN ('try_acquire_distributed_lock', 'release_distributed_lock')
          AND pronamespace = 'public'::regnamespace
    LOOP
        EXECUTE 'REVOKE EXECUTE ON FUNCTION ' || r.func_sig || ' FROM PUBLIC, anon';
        EXECUTE 'GRANT EXECUTE ON FUNCTION ' || r.func_sig || ' TO authenticated, service_role';
    END LOOP;
END $$;


-- ------------------------------------------------------------------------------
-- 4. Relational Cascade Protections (DB-03, DB-24, DB-25)
-- Prevent account disconnection from destroying in-flight leads & campaign history
-- ------------------------------------------------------------------------------
ALTER TABLE public.campaign_enrollments ALTER COLUMN account_id DROP NOT NULL;

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'campaign_enrollments_account_id_fkey' 
          AND table_name = 'campaign_enrollments'
    ) THEN
        ALTER TABLE public.campaign_enrollments DROP CONSTRAINT campaign_enrollments_account_id_fkey;
    END IF;
    ALTER TABLE public.campaign_enrollments
        ADD CONSTRAINT campaign_enrollments_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE SET NULL;
END $$;

-- Preserve action_log audit trail when an account is deleted
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'action_log_account_id_fkey' 
          AND table_name = 'action_log'
    ) THEN
        ALTER TABLE public.action_log DROP CONSTRAINT action_log_account_id_fkey;
    END IF;
    ALTER TABLE public.action_log
        ADD CONSTRAINT action_log_account_id_fkey
        FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE SET NULL;
END $$;

-- Version integrity foreign key cascade
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'fk_enrollment_version_integrity' 
          AND table_name = 'campaign_enrollments'
    ) THEN
        ALTER TABLE public.campaign_enrollments DROP CONSTRAINT fk_enrollment_version_integrity;
        ALTER TABLE public.campaign_enrollments
            ADD CONSTRAINT fk_enrollment_version_integrity
            FOREIGN KEY (campaign_version_id, campaign_id)
            REFERENCES public.campaign_versions (id, campaign_id) ON DELETE CASCADE;
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- 5. Missing Columns & Schema Reconciliations (DB-11, DB-18)
-- ------------------------------------------------------------------------------
-- Add lead_list_id column to campaigns table if missing
ALTER TABLE public.campaigns 
    ADD COLUMN IF NOT EXISTS lead_list_id UUID REFERENCES public.lead_lists(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_campaigns_lead_list_id ON public.campaigns(lead_list_id);

-- Add retry_count column to campaign_execution_states if missing
ALTER TABLE public.campaign_execution_states 
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;


-- ------------------------------------------------------------------------------
-- 6. Uniqueness & Concurrency Integrity (DB-04, DB-05)
-- ------------------------------------------------------------------------------
-- Enforce single enrollment per lead per campaign
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_campaign_lead_enrollment'
    ) THEN
        ALTER TABLE public.campaign_enrollments 
            ADD CONSTRAINT uq_campaign_lead_enrollment UNIQUE (campaign_id, lead_id);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;

-- Enforce single execution state per enrollment to prevent duplicate worker dispatches
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_ces_enrollment_id'
    ) THEN
        ALTER TABLE public.campaign_execution_states 
            ADD CONSTRAINT uq_ces_enrollment_id UNIQUE (enrollment_id);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;


-- ------------------------------------------------------------------------------
-- 7. High-Performance B-Tree Indexes for Scheduler & Webhooks (DB-06, DB-07, DB-15, DB-16)
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_campaign_status 
    ON public.campaign_enrollments (campaign_id, status);

CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_lead_id 
    ON public.campaign_enrollments (lead_id);

CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_account_id 
    ON public.campaign_enrollments (account_id);

CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_workspace_id 
    ON public.campaign_enrollments (workspace_id);

CREATE INDEX IF NOT EXISTS idx_ces_enrollment_id 
    ON public.campaign_execution_states (enrollment_id);

CREATE INDEX IF NOT EXISTS idx_campaigns_workspace_status 
    ON public.campaigns (workspace_id, status);

-- Replace partial index with predicate that covers both 'pending' and 'running'
DROP INDEX IF EXISTS public.idx_ces_next_run;
CREATE INDEX IF NOT EXISTS idx_ces_workspace_status_next_run 
    ON public.campaign_execution_states (workspace_id, next_run_at ASC NULLS FIRST) 
    WHERE status IN ('pending', 'running');


-- ------------------------------------------------------------------------------
-- 8. Hardened Queue Dequeue & Lead Progression RPCs (DB-08, DB-10, DB-20)
-- ------------------------------------------------------------------------------

-- 8a. dequeue_due_leads: Add FOR UPDATE OF ces SKIP LOCKED (eliminates accounts row deadlocks)
CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
    p_batch_size INT DEFAULT 50,
    p_campaign_ids UUID[] DEFAULT NULL,
    p_lease_seconds INT DEFAULT 300
) RETURNS SETOF public.campaign_execution_states
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_token UUID := gen_random_uuid();
    v_expires TIMESTAMPTZ := now() + (p_lease_seconds || ' seconds')::INTERVAL;
BEGIN
    RETURN QUERY
    UPDATE public.campaign_execution_states
    SET 
        lease_token = v_token,
        lease_expires_at = v_expires,
        status = 'running',
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
              AND COALESCE(a.manual_send_suspected, false) = false
            ORDER BY ces.next_run_at ASC NULLS FIRST
            LIMIT GREATEST(1, p_batch_size / 5)
        ) ces
        ORDER BY ces.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE OF ces SKIP LOCKED
    )
    RETURNING *;
END;
$$;

-- 8b. release_lead_claim: Remove UUID regex, accept text node IDs, reconcile retry_count
CREATE OR REPLACE FUNCTION public.release_lead_claim(
    p_state_id UUID,
    p_lease_token UUID,
    p_next_status TEXT,
    p_next_node TEXT,
    p_next_run TIMESTAMPTZ,
    p_variables JSONB,
    p_error_reason TEXT,
    p_attempts INT
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_rows INT;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = p_next_status,
        current_node_id = COALESCE(p_next_node, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        retry_count = COALESCE(p_attempts, retry_count),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id AND (p_lease_token IS NULL OR lease_token = p_lease_token::TEXT OR lease_token::TEXT = p_lease_token::TEXT);
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

-- 8c. recover_stale_leases: Harden with SECURITY DEFINER
CREATE OR REPLACE FUNCTION public.recover_stale_leases(p_timeout_minutes INT DEFAULT 5)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_recovered integer;
BEGIN
    UPDATE public.campaign_execution_states
    SET 
        status = 'pending',
        lease_token = NULL,
        lease_expires_at = NULL,
        next_run_at = now(),
        updated_at = now()
    WHERE (
        (lease_expires_at IS NOT NULL AND lease_expires_at < now())
        OR 
        (status = 'running' AND updated_at < now() - (p_timeout_minutes || ' minutes')::INTERVAL)
    );
    GET DIAGNOSTICS v_recovered = ROW_COUNT;
    RETURN v_recovered;
END;
$$;

-- 8d. advance_reply_waiting_leads: Order by ID with FOR UPDATE SKIP LOCKED to prevent lock inversion
CREATE OR REPLACE FUNCTION public.advance_reply_waiting_leads(p_lead_id uuid)
RETURNS integer 
LANGUAGE plpgsql 
SECURITY DEFINER 
SET search_path = public
AS $$
DECLARE
    v_state_id uuid;
    v_count integer := 0;
BEGIN
    SELECT ces.id INTO v_state_id
    FROM public.campaign_execution_states ces
    JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
    WHERE ce.lead_id = p_lead_id AND ces.status = 'waiting_for_reply'
    ORDER BY ces.id
    FOR UPDATE OF ces SKIP LOCKED
    LIMIT 1;

    IF v_state_id IS NOT NULL THEN
        UPDATE public.campaign_execution_states
        SET status = 'pending', next_run_at = now(),
            lease_token = NULL, lease_expires_at = NULL, updated_at = now()
        WHERE id = v_state_id;
        v_count := 1;
    END IF;

    RETURN v_count;
END; 
$$;

-- ------------------------------------------------------------------------------
-- 9. Multi-Tenant Workspace Resolution & Processing Jobs RLS (VULN-20)
-- Replaces single-workspace pinning with multi-workspace access check
-- ------------------------------------------------------------------------------
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    DROP POLICY IF EXISTS processing_jobs_tenant_isolation ON public.processing_jobs;
    CREATE POLICY processing_jobs_tenant_isolation ON public.processing_jobs
    FOR ALL USING (
        workspace_id IN (SELECT public.my_workspace_ids())
    )
    WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids())
    );
END $$;


-- ------------------------------------------------------------------------------
-- 10. Atomic Campaign Creation & Bulk Enrollment RPCs (API-01, API-02)
-- Wraps multi-table campaign creation & enrollment in ACID PostgreSQL transactions
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.create_campaign_atomic(
    p_campaign_id UUID,
    p_workspace_id UUID,
    p_name TEXT,
    p_status TEXT,
    p_nodes_json JSONB,
    p_edges_json JSONB,
    p_sender_account_ids_json JSONB,
    p_metadata JSONB,
    p_senders UUID[] DEFAULT '{}'::UUID[]
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_version_id UUID;
    v_sender_id UUID;
BEGIN
    -- Verify caller workspace membership
    IF NOT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
    ) AND auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized: User is not a member of workspace %', p_workspace_id;
    END IF;

    -- 1. Insert Campaign
    INSERT INTO public.campaigns (
        id, workspace_id, name, status, nodes_json, edges_json, sender_account_ids_json, metadata
    ) VALUES (
        p_campaign_id, p_workspace_id, p_name, p_status, p_nodes_json, p_edges_json, p_sender_account_ids_json, p_metadata
    );

    -- 2. Insert Version 1
    v_version_id := gen_random_uuid();
    INSERT INTO public.campaign_versions (id, campaign_id, version)
    VALUES (v_version_id, p_campaign_id, 1);

    -- 3. Insert Accounts
    IF p_senders IS NOT NULL AND array_length(p_senders, 1) > 0 THEN
        FOREACH v_sender_id IN ARRAY p_senders LOOP
            IF EXISTS (SELECT 1 FROM public.accounts WHERE id = v_sender_id AND workspace_id = p_workspace_id) THEN
                INSERT INTO public.campaign_accounts (campaign_id, account_id, weight)
                VALUES (p_campaign_id, v_sender_id, 100)
                ON CONFLICT DO NOTHING;
            END IF;
        END LOOP;
    END IF;

    RETURN jsonb_build_object(
        'campaign_id', p_campaign_id,
        'version_id', v_version_id,
        'status', 'success'
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.enroll_leads_chunk_atomic(
    p_workspace_id UUID,
    p_campaign_id UUID,
    p_enrollments JSONB,
    p_execution_states JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_count INT := 0;
BEGIN
    -- Verify caller workspace membership
    IF NOT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
    ) AND auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized: User is not a member of workspace %', p_workspace_id;
    END IF;

    -- Upsert enrollments and execution states atomically
    INSERT INTO public.campaign_enrollments (id, workspace_id, campaign_id, campaign_version_id, lead_id, account_id)
    SELECT
        (e->>'id')::UUID,
        p_workspace_id,
        p_campaign_id,
        (e->>'campaign_version_id')::UUID,
        (e->>'lead_id')::UUID,
        (e->>'account_id')::UUID
    FROM jsonb_array_elements(p_enrollments) AS e
    ON CONFLICT (campaign_id, lead_id) DO NOTHING;

    INSERT INTO public.campaign_execution_states (id, workspace_id, campaign_id, enrollment_id, status, variables)
    SELECT
        (x->>'id')::UUID,
        p_workspace_id,
        p_campaign_id,
        (x->>'enrollment_id')::UUID,
        COALESCE(x->>'status', 'pending'),
        COALESCE(x->'variables', '{}'::JSONB)
    FROM jsonb_array_elements(p_execution_states) AS x
    ON CONFLICT (enrollment_id) DO NOTHING;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN jsonb_build_object('status', 'success', 'inserted_count', v_count);
END;
$$;
