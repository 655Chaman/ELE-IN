-- ==============================================================================
-- MIGRATION: 100_leads_module_hardening.sql
-- Rigorously applied under the Three-Layer Logic Architecture (Paranoia Framework)
-- Fixes: Data Integrity, Constraints, Cascades, Indexes, and Worker Concurrency
-- ==============================================================================

-- 1. ADD MISSING ENUM VALUES (Idempotent)
DO $$ BEGIN
    ALTER TYPE public.lead_status ADD VALUE IF NOT EXISTS 'suppressed';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TYPE public.lead_status ADD VALUE IF NOT EXISTS 'bounced';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 2. REPAIR LEADS UNIQUE CONSTRAINTS FOR EMAIL-ONLY IMPORTS (SCH-01 & CRIT-11)
-- Drop restrictive NOT NULL and raw bitwise unique constraints
ALTER TABLE public.leads ALTER COLUMN linkedin_url DROP NOT NULL;
ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_workspace_id_linkedin_url_key;
ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS uq_leads_workspace_linkedin;
ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_workspace_linkedin_key;
DROP INDEX IF EXISTS leads_workspace_linkedin_url_uniq;

-- Convert empty strings to NULL to avoid '' = '' collisions in PostgreSQL
UPDATE public.leads SET linkedin_url = NULL WHERE TRIM(linkedin_url) = '';
UPDATE public.leads SET email = LOWER(TRIM(email)) WHERE email IS NOT NULL;

-- Enforce lowercase canonical unique index on linkedin_url (ignoring NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_workspace_linkedin_canonical
    ON public.leads (workspace_id, LOWER(TRIM(linkedin_url)))
    WHERE linkedin_url IS NOT NULL AND TRIM(linkedin_url) != '';

-- Enforce lowercase canonical unique index on email (ignoring NULLs)
CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_workspace_email_canonical
    ON public.leads (workspace_id, LOWER(TRIM(email)))
    WHERE email IS NOT NULL AND TRIM(email) != '';

-- Check constraint: Lead must have at least a LinkedIn URL or Email
ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS chk_lead_identity;
ALTER TABLE public.leads ADD CONSTRAINT chk_lead_identity 
    CHECK ((linkedin_url IS NOT NULL AND TRIM(linkedin_url) != '') OR (email IS NOT NULL AND TRIM(email) != ''));

-- 3. REPAIR cleanup_orphaned_leads TRIGGER (SAFE DELETION WITH ACTIVE STATE GUARD)
CREATE INDEX IF NOT EXISTS idx_list_members_opp_id 
    ON public.list_members (opportunity_id);

CREATE OR REPLACE FUNCTION public.cleanup_orphaned_leads()
RETURNS TRIGGER AS $$
DECLARE
    v_has_other_lists BOOLEAN;
    v_has_active_campaigns BOOLEAN;
    v_has_messages BOOLEAN;
    v_has_pending_approvals BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM public.list_members 
        WHERE opportunity_id = OLD.opportunity_id
    ) INTO v_has_other_lists;

    IF v_has_other_lists THEN
        RETURN OLD;
    END IF;

    -- Check if lead has active campaign enrollments
    SELECT EXISTS (
        SELECT 1 FROM public.campaign_execution_states ces
        JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
        WHERE ce.lead_id = OLD.opportunity_id
          AND ces.status IN ('pending', 'running', 'waiting_for_reply', 'awaiting_approval', 'snoozed_ooo')
    ) INTO v_has_active_campaigns;

    IF v_has_active_campaigns THEN
        RETURN OLD;
    END IF;

    -- Check if lead has message history
    SELECT EXISTS (
        SELECT 1 FROM public.messages
        WHERE lead_id = OLD.opportunity_id
    ) INTO v_has_messages;

    IF v_has_messages THEN
        RETURN OLD;
    END IF;

    -- Check if lead has pending approvals
    SELECT EXISTS (
        SELECT 1 FROM public.approval_queue
        WHERE lead_id = OLD.opportunity_id::text
    ) INTO v_has_pending_approvals;

    IF v_has_pending_approvals THEN
        RETURN OLD;
    END IF;

    DELETE FROM public.leads WHERE id = OLD.opportunity_id;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS trigger_cleanup_orphaned_leads ON public.list_members;
CREATE TRIGGER trigger_cleanup_orphaned_leads
    AFTER DELETE ON public.list_members
    FOR EACH ROW EXECUTE FUNCTION public.cleanup_orphaned_leads();

-- 4. REPAIR APPROVAL QUEUE SCHEMA DRIFT (SCH-03)
ALTER TABLE public.approval_queue
    ADD COLUMN IF NOT EXISTS thread_messages_json JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS intent TEXT,
    ADD COLUMN IF NOT EXISTS heat_score NUMERIC DEFAULT 50.0,
    ADD COLUMN IF NOT EXISTS node_id TEXT,
    ADD COLUMN IF NOT EXISTS enrollment_id UUID,
    ADD COLUMN IF NOT EXISTS campaign_id UUID;

-- 5. ATOMIC & SAFE DEQUEUE RPC (CON-02: PREVENTS DEADLOCKS & RACE CONDITIONS)
CREATE OR REPLACE FUNCTION public.dequeue_due_leads(
    p_worker_id TEXT,
    p_batch_size INT DEFAULT 10,
    p_lease_duration_seconds INT DEFAULT 300
)
RETURNS TABLE (
    execution_state_id UUID,
    enrollment_id UUID,
    workspace_id UUID,
    lead_id UUID,
    campaign_id UUID,
    account_id UUID,
    current_node_id TEXT,
    variables JSONB,
    lease_token TEXT
) LANGUAGE plpgsql AS $$
DECLARE
    v_token TEXT := p_worker_id || ':' || gen_random_uuid()::text;
    v_expires_at TIMESTAMPTZ := NOW() + (p_lease_duration_seconds || ' seconds')::interval;
BEGIN
    RETURN QUERY
    WITH due_candidates AS (
        SELECT ces.id
        FROM public.campaign_execution_states ces
        WHERE (
            (ces.status = 'pending' AND (ces.next_run_at IS NULL OR ces.next_run_at <= NOW()))
            OR (ces.status = 'running' AND ces.lease_expires_at < NOW())
        )
        ORDER BY ces.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE OF ces SKIP LOCKED
    ),
    claimed AS (
        UPDATE public.campaign_execution_states ces
        SET status = 'running',
            lease_token = v_token,
            lease_expires_at = v_expires_at,
            updated_at = NOW()
        FROM due_candidates dc
        WHERE ces.id = dc.id
        RETURNING ces.id, ces.enrollment_id, ces.workspace_id, ces.current_node_id, ces.variables, ces.lease_token
    )
    SELECT 
        c.id AS execution_state_id,
        c.enrollment_id,
        c.workspace_id,
        ce.lead_id,
        ce.campaign_id,
        ce.account_id,
        c.current_node_id,
        c.variables,
        c.lease_token
    FROM claimed c
    JOIN public.campaign_enrollments ce ON ce.id = c.enrollment_id;
END;
$$;

-- 6. ATOMIC RELEASE CLAIM RPC (STOPS WORKER OVERWRITE RACE CONDITIONS)
CREATE OR REPLACE FUNCTION public.release_lead_execution_claim(
    p_execution_state_id UUID,
    p_lease_token TEXT,
    p_next_status TEXT,
    p_next_node_id TEXT,
    p_next_run_at TIMESTAMPTZ,
    p_variables JSONB,
    p_error_reason TEXT DEFAULT NULL
)
RETURNS BOOLEAN LANGUAGE plpgsql AS $$
DECLARE
    v_updated_rows INT;
BEGIN
    UPDATE public.campaign_execution_states
    SET status = p_next_status,
        current_node_id = p_next_node_id,
        next_run_at = p_next_run_at,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = NOW()
    WHERE id = p_execution_state_id 
      AND lease_token = p_lease_token
      AND status = 'running';

    GET DIAGNOSTICS v_updated_rows = ROW_COUNT;
    RETURN v_updated_rows > 0;
END;
$$;

-- 7. ATOMIC BULK ENROLLMENT RPC (CON-01: TRANSACTIONAL INTEGRITY)
CREATE OR REPLACE FUNCTION public.bulk_enroll_leads_safely(
    p_campaign_id UUID,
    p_workspace_id UUID,
    p_version_id UUID,
    p_enrollments JSONB
)
RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE
    v_enrolled_count INT := 0;
    v_item JSONB;
    v_enr_id UUID;
    v_exec_id UUID;
BEGIN
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_enrollments)
    LOOP
        v_enr_id := gen_random_uuid();
        v_exec_id := gen_random_uuid();

        INSERT INTO public.campaign_enrollments (
            id, workspace_id, campaign_id, campaign_version_id, lead_id, account_id, status
        ) VALUES (
            v_enr_id,
            p_workspace_id,
            p_campaign_id,
            p_version_id,
            (v_item->>'lead_id')::uuid,
            (v_item->>'account_id')::uuid,
            'active'
        )
        ON CONFLICT (campaign_id, lead_id) DO NOTHING;

        IF FOUND THEN
            INSERT INTO public.campaign_execution_states (
                id, workspace_id, enrollment_id, status, variables
            ) VALUES (
                v_exec_id,
                p_workspace_id,
                v_enr_id,
                'pending',
                '{}'::jsonb
            );
            v_enrolled_count := v_enrolled_count + 1;
        END IF;
    END LOOP;

    RETURN jsonb_build_object('success', true, 'enrolled_count', v_enrolled_count);
END;
$$;

-- 8. COMPREHENSIVE PERFORMANCE INDEXES (PERF-01, PERF-02, CRIT-13, CRIT-14)
CREATE INDEX IF NOT EXISTS idx_list_members_opp_id 
    ON public.list_members (opportunity_id);

CREATE INDEX IF NOT EXISTS idx_ces_enrollment_id 
    ON public.campaign_execution_states (enrollment_id);

CREATE INDEX IF NOT EXISTS idx_ces_enrollment_status 
    ON public.campaign_execution_states (enrollment_id, status);

CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_ws_lead 
    ON public.campaign_enrollments (workspace_id, lead_id);

CREATE INDEX IF NOT EXISTS idx_campaign_enrollments_lead_id 
    ON public.campaign_enrollments (lead_id);

CREATE INDEX IF NOT EXISTS idx_messages_ws_created 
    ON public.messages (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_lead_acc 
    ON public.messages (workspace_id, lead_id, account_id);

CREATE INDEX IF NOT EXISTS idx_messages_account_inbound 
    ON public.messages (account_id, direction, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_thread_url 
    ON public.messages (workspace_id, thread_url) 
    WHERE thread_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_leads_ws_created 
    ON public.leads (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_leads_ws_status 
    ON public.leads (workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_leads_ws_domain 
    ON public.leads (workspace_id, domain) 
    WHERE domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_leads_metadata_gin 
    ON public.leads USING GIN (metadata);

CREATE INDEX IF NOT EXISTS idx_lead_social_signals_lead_ws 
    ON public.lead_social_signals (workspace_id, lead_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_suppression_ws_value 
    ON public.suppression_list (workspace_id, value);
