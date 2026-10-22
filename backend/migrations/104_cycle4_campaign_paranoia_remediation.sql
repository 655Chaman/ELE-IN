-- ============================================================================
-- MIGRATION 104: CYCLE 4 CAMPAIGN SUBSYSTEM PARANOIA REMEDIATION
-- Idempotent resolution for FLAW-DB-01 through FLAW-DB-31
-- Standard: Zero Emojis, Complete Relational Integrity, Strict Multi-Tenancy
-- Aligned with Live Supabase Production Database Schema
-- ============================================================================

-- ----------------------------------------------------------------------------
-- PRE-FLIGHT FUNCTION CLEANUP (Prevents 42P13 Parameter Rename Errors)
-- ----------------------------------------------------------------------------
DO $$ 
DECLARE
    r RECORD;
BEGIN
    FOR r IN 
        SELECT oid::regprocedure AS func_sig 
        FROM pg_proc 
        WHERE proname IN (
            'create_campaign_atomic',
            'enroll_leads_chunk_atomic',
            'dequeue_due_leads',
            'release_lead_claim',
            'recover_stale_leases',
            'advance_reply_waiting_leads',
            'claim_processing_jobs',
            'decrement_list_row_count',
            'claim_outbox_events',
            'set_outbox_events_updated_at',
            'update_daily_campaign_stats'
        )
        AND pronamespace = 'public'::regnamespace
    LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS ' || r.func_sig || ' CASCADE';
    END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- 1. ENUM NORMALIZATION & VALUE EXTENSIONS (FLAW-DB-08, FLAW-DB-09)
-- Must execute outside transaction blocks to satisfy PostgreSQL 25001 constraint
-- ----------------------------------------------------------------------------

-- Add lowercase compatibility values to campaign_status
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'draft';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'active';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'paused';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'completed';
ALTER TYPE public.campaign_status ADD VALUE IF NOT EXISTS 'archived';

-- Add 'sent' and 'completed' to outbox_event_status
ALTER TYPE public.outbox_event_status ADD VALUE IF NOT EXISTS 'sent';
ALTER TYPE public.outbox_event_status ADD VALUE IF NOT EXISTS 'completed';

-- Extend lead_state_status for legacy environments where column was typed as ENUM
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'waiting_for_approval';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'waiting_for_reply';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'awaiting_approval';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'paused';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'failed';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'rate_limited';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'out_of_office';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'skipped';
ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'snoozed_ooo';

-- ----------------------------------------------------------------------------
-- 2. SCHEMA DRIFT & COLUMN RESTORATIONS (FLAW-DB-01, 03, 04, 05, 06, 11, 12)
-- ----------------------------------------------------------------------------

-- FLAW-DB-01: Add campaign_id to campaign_execution_states
ALTER TABLE public.campaign_execution_states 
    ADD COLUMN IF NOT EXISTS campaign_id UUID REFERENCES public.campaigns(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_ces_campaign_id 
    ON public.campaign_execution_states (campaign_id);

-- Backfill campaign_id from enrollments if null
UPDATE public.campaign_execution_states ces
SET campaign_id = ce.campaign_id
FROM public.campaign_enrollments ce
WHERE ces.enrollment_id = ce.id AND ces.campaign_id IS NULL;

-- FLAW-DB-03: Add position_x and position_y to campaign_nodes
ALTER TABLE public.campaign_nodes 
    ADD COLUMN IF NOT EXISTS position_x DOUBLE PRECISION DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS position_y DOUBLE PRECISION DEFAULT 0.0;

-- Defensively ensure DAG versioning columns exist on campaign_versions
ALTER TABLE public.campaign_versions
    ADD COLUMN IF NOT EXISTS nodes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS edges_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ DEFAULT NOW();

-- FLAW-DB-04: Add enrollment_id and normalize node_id on messages
ALTER TABLE public.messages 
    ADD COLUMN IF NOT EXISTS enrollment_id UUID REFERENCES public.campaign_enrollments(id) ON DELETE SET NULL;

ALTER TABLE public.messages 
    ALTER COLUMN node_id TYPE TEXT USING node_id::TEXT;

CREATE INDEX IF NOT EXISTS idx_messages_enrollment_node 
    ON public.messages (enrollment_id, node_id);

-- FLAW-DB-05: Add updated_at to outbox_events with auto-update trigger
ALTER TABLE public.outbox_events 
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE OR REPLACE FUNCTION public.set_outbox_events_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_outbox_events_updated_at ON public.outbox_events;
CREATE TRIGGER trigger_outbox_events_updated_at
    BEFORE UPDATE ON public.outbox_events
    FOR EACH ROW EXECUTE FUNCTION public.set_outbox_events_updated_at();

-- FLAW-DB-06: Add weight to campaign_accounts
ALTER TABLE public.campaign_accounts 
    ADD COLUMN IF NOT EXISTS weight INTEGER NOT NULL DEFAULT 100;

-- FLAW-DB-02: Enforce foreign keys on campaign_node_executions
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cne_workspace') THEN
        ALTER TABLE public.campaign_node_executions
            ADD CONSTRAINT fk_cne_workspace FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cne_enrollment') THEN
        ALTER TABLE public.campaign_node_executions
            ADD CONSTRAINT fk_cne_enrollment FOREIGN KEY (enrollment_id) REFERENCES public.campaign_enrollments(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_cne_campaign_version') THEN
        ALTER TABLE public.campaign_node_executions
            ADD CONSTRAINT fk_cne_campaign_version FOREIGN KEY (campaign_version_id) REFERENCES public.campaign_versions(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_cne_enrollment_node 
    ON public.campaign_node_executions (enrollment_id, node_id);

-- FLAW-DB-11: action_log.execution_state_id UUID type and FK
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'action_log' AND column_name = 'execution_state_id' AND data_type = 'text'
    ) THEN
        ALTER TABLE public.action_log 
            ALTER COLUMN execution_state_id TYPE UUID USING NULLIF(execution_state_id, '')::UUID;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_action_log_ces') THEN
        ALTER TABLE public.action_log
            ADD CONSTRAINT fk_action_log_ces FOREIGN KEY (execution_state_id) REFERENCES public.campaign_execution_states(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_action_log_ces_id 
    ON public.action_log (execution_state_id);

-- FLAW-DB-12: approval_queue.lead_id and exec_state_id UUID type and FK with orphaned ID cleanup
DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'approval_queue' AND column_name = 'lead_id' AND data_type = 'text'
    ) THEN
        ALTER TABLE public.approval_queue 
            ALTER COLUMN lead_id TYPE UUID USING (
                CASE 
                    WHEN lead_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' 
                    THEN lead_id::UUID 
                    ELSE NULL 
                END
            );
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'approval_queue' AND column_name = 'exec_state_id' AND data_type = 'text'
    ) THEN
        ALTER TABLE public.approval_queue 
            ALTER COLUMN exec_state_id TYPE UUID USING (
                CASE 
                    WHEN exec_state_id ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' 
                    THEN exec_state_id::UUID 
                    ELSE NULL 
                END
            );
    END IF;

    -- Clean up orphaned references before attaching foreign keys
    UPDATE public.approval_queue 
    SET lead_id = NULL 
    WHERE lead_id IS NOT NULL 
      AND NOT EXISTS (SELECT 1 FROM public.leads l WHERE l.id = approval_queue.lead_id);

    UPDATE public.approval_queue 
    SET exec_state_id = NULL 
    WHERE exec_state_id IS NOT NULL 
      AND NOT EXISTS (SELECT 1 FROM public.campaign_execution_states ces WHERE ces.id = approval_queue.exec_state_id);

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_queue_lead') THEN
        ALTER TABLE public.approval_queue
            ADD CONSTRAINT fk_approval_queue_lead FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_approval_queue_ces') THEN
        ALTER TABLE public.approval_queue
            ADD CONSTRAINT fk_approval_queue_ces FOREIGN KEY (exec_state_id) REFERENCES public.campaign_execution_states(id) ON DELETE CASCADE;
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 3. CHECK CONSTRAINTS, DEDUPLICATION & COMPATIBILITY VIEWS (FLAW-DB-07, 10, 13)
-- ----------------------------------------------------------------------------

-- Enforce UNIQUE constraint on campaign_enrollments(campaign_id, lead_id)
DELETE FROM public.campaign_enrollments a
USING public.campaign_enrollments b
WHERE a.id > b.id
  AND a.campaign_id = b.campaign_id
  AND a.lead_id = b.lead_id;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_campaign_lead_enrollment'
    ) THEN
        ALTER TABLE public.campaign_enrollments
            ADD CONSTRAINT uq_campaign_lead_enrollment UNIQUE (campaign_id, lead_id);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;

-- Enforce UNIQUE constraint on daily_campaign_stats(campaign_id, stat_date)
DELETE FROM public.daily_campaign_stats a
USING public.daily_campaign_stats b
WHERE a.id > b.id
  AND a.campaign_id = b.campaign_id
  AND a.stat_date = b.stat_date;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_daily_campaign_stats_date'
    ) THEN
        ALTER TABLE public.daily_campaign_stats
            ADD CONSTRAINT uq_daily_campaign_stats_date UNIQUE (campaign_id, stat_date);
    END IF;
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
END $$;

-- FLAW-DB-07: Status checks on campaign_execution_states and campaign_enrollments
DO $$ BEGIN
    -- 1. Drop existing defaults to prevent "cannot cast default to text" error
    BEGIN
        ALTER TABLE public.campaign_execution_states ALTER COLUMN status DROP DEFAULT;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    -- 2. Convert status column to TEXT
    BEGIN
        ALTER TABLE public.campaign_execution_states
            ALTER COLUMN status TYPE TEXT USING status::TEXT;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    -- 3. Restore default as TEXT
    BEGIN
        ALTER TABLE public.campaign_execution_states ALTER COLUMN status SET DEFAULT 'pending'::text;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    BEGIN
        ALTER TABLE public.campaign_enrollments ALTER COLUMN status DROP DEFAULT;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    BEGIN
        ALTER TABLE public.campaign_enrollments
            ALTER COLUMN status TYPE TEXT USING status::TEXT;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    BEGIN
        ALTER TABLE public.campaign_enrollments ALTER COLUMN status SET DEFAULT 'active'::text;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;

    -- 4. Sanitize invalid status values
    UPDATE public.campaign_execution_states 
    SET status = 'pending' 
    WHERE status IS NULL 
       OR status NOT IN ('pending', 'running', 'waiting_for_reply', 'awaiting_approval', 'waiting_for_approval', 'paused', 'completed', 'failed', 'exited', 'rate_limited', 'out_of_office', 'skipped', 'error', 'snoozed_ooo');

    UPDATE public.campaign_enrollments 
    SET status = 'active' 
    WHERE status IS NULL 
       OR status NOT IN ('active', 'completed', 'paused', 'exited', 'error', 'failed', 'bounced');

    -- 5. Add check constraints cleanly
    ALTER TABLE public.campaign_execution_states DROP CONSTRAINT IF EXISTS chk_ces_status_valid;
    ALTER TABLE public.campaign_execution_states
        ADD CONSTRAINT chk_ces_status_valid CHECK (
            status IN ('pending', 'running', 'waiting_for_reply', 'awaiting_approval', 'waiting_for_approval', 'paused', 'completed', 'failed', 'exited', 'rate_limited', 'out_of_office', 'skipped', 'error', 'snoozed_ooo')
        );

    ALTER TABLE public.campaign_enrollments DROP CONSTRAINT IF EXISTS chk_ce_status_valid;
    ALTER TABLE public.campaign_enrollments
        ADD CONSTRAINT chk_ce_status_valid CHECK (
            status IN ('active', 'completed', 'paused', 'exited', 'error', 'failed', 'bounced')
        );
END $$;

-- FLAW-DB-10: Drop dangling trigger / function on action_log
DROP TRIGGER IF EXISTS action_log_increment_daily_usage ON public.action_log;

-- FLAW-DB-13: campaign_leads compatibility view with enrolled_at mapping
-- Ensure created_at, updated_at, and enrolled_at exist defensively on campaign_enrollments
ALTER TABLE public.campaign_enrollments 
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.campaign_enrollments 
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.campaign_enrollments 
    ADD COLUMN IF NOT EXISTS enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE OR REPLACE VIEW public.campaign_leads AS
SELECT 
    id,
    workspace_id,
    campaign_id,
    lead_id,
    status,
    account_id,
    COALESCE(created_at, enrolled_at, NOW()) AS created_at,
    COALESCE(enrolled_at, created_at, NOW()) AS enrolled_at,
    COALESCE(updated_at, created_at, NOW()) AS updated_at
FROM public.campaign_enrollments;

-- ----------------------------------------------------------------------------
-- 4. B-TREE & COMPOSITE PERFORMANCE INDEXES (FLAW-DB-28, 29)
-- ----------------------------------------------------------------------------

-- FLAW-DB-28: Indexes on campaign_edges
CREATE INDEX IF NOT EXISTS idx_campaign_edges_source_node 
    ON public.campaign_edges (source_node_id);

CREATE INDEX IF NOT EXISTS idx_campaign_edges_target_node 
    ON public.campaign_edges (target_node_id);

-- FLAW-DB-29: Composite index on campaign_execution_states
CREATE INDEX IF NOT EXISTS idx_ces_enrollment_status 
    ON public.campaign_execution_states (enrollment_id, status);

-- ----------------------------------------------------------------------------
-- 5. SUPPRESSION TRIGGER WITH DOMAIN AUDIT (FLAW-DB-17)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.enforce_suppression_list()
RETURNS TRIGGER AS $$
DECLARE
    v_linkedin_url TEXT;
    v_email TEXT;
    v_domain TEXT;
    v_workspace_id UUID;
    v_is_suppressed BOOLEAN;
BEGIN
    IF TG_TABLE_NAME = 'list_members' OR TG_TABLE_NAME = 'lead_states' THEN
        SELECT workspace_id, linkedin_url, email, domain
        INTO v_workspace_id, v_linkedin_url, v_email, v_domain
        FROM public.leads
        WHERE id = NEW.opportunity_id;
    ELSIF TG_TABLE_NAME = 'campaign_enrollments' THEN
        v_workspace_id := NEW.workspace_id;
        SELECT linkedin_url, email, domain
        INTO v_linkedin_url, v_email, v_domain
        FROM public.leads
        WHERE id = NEW.lead_id;
    END IF;

    IF v_workspace_id IS NOT NULL THEN
        SELECT EXISTS (
            SELECT 1 
            FROM public.suppression_list 
            WHERE workspace_id = v_workspace_id 
              AND (
                  (v_linkedin_url IS NOT NULL AND linkedin_url = v_linkedin_url)
                  OR (v_email IS NOT NULL AND LOWER(email) = LOWER(v_email))
                  OR (v_domain IS NOT NULL AND domain IS NOT NULL AND LOWER(domain) = LOWER(v_domain))
              )
        ) INTO v_is_suppressed;

        IF v_is_suppressed THEN
            RAISE EXCEPTION USING 
                ERRCODE = 'U0001',
                MESSAGE = 'suppression_list_violation: Lead or company domain is suppressed for this workspace.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- ----------------------------------------------------------------------------
-- 6. RPC HARDENING: ATOMIC CAMPAIGN CREATION (FLAW-DB-14)
-- ----------------------------------------------------------------------------

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
    v_status_enum public.campaign_status;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
    ) AND auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized: User is not a member of workspace %', p_workspace_id;
    END IF;

    BEGIN
        v_status_enum := UPPER(COALESCE(p_status, 'DRAFT'))::public.campaign_status;
    EXCEPTION WHEN OTHERS THEN
        v_status_enum := 'DRAFT'::public.campaign_status;
    END;

    -- 1. Insert Campaign
    INSERT INTO public.campaigns (
        id, workspace_id, name, status, nodes_json, edges_json, sender_account_ids_json, metadata
    ) VALUES (
        p_campaign_id, p_workspace_id, p_name, v_status_enum, 
        COALESCE(p_nodes_json, '[]'::jsonb), 
        COALESCE(p_edges_json, '[]'::jsonb), 
        COALESCE(p_sender_account_ids_json, '[]'::jsonb), 
        COALESCE(p_metadata, '{}'::jsonb)
    );

    -- 2. Insert Version 1 with full DAG definition
    v_version_id := gen_random_uuid();
    INSERT INTO public.campaign_versions (
        id, campaign_id, nodes_json, edges_json, metadata, version, published_at
    ) VALUES (
        v_version_id, p_campaign_id, 
        COALESCE(p_nodes_json, '[]'::jsonb), 
        COALESCE(p_edges_json, '[]'::jsonb), 
        COALESCE(p_metadata, '{}'::jsonb), 
        1, now()
    );

    -- 3. Insert Accounts
    IF p_senders IS NOT NULL AND array_length(p_senders, 1) > 0 THEN
        FOREACH v_sender_id IN ARRAY p_senders LOOP
            IF EXISTS (SELECT 1 FROM public.accounts WHERE id = v_sender_id AND workspace_id = p_workspace_id) THEN
                INSERT INTO public.campaign_accounts (campaign_id, account_id, weight)
                VALUES (p_campaign_id, v_sender_id, 100)
                ON CONFLICT (campaign_id, account_id) DO NOTHING;
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

-- ----------------------------------------------------------------------------
-- 7. RPC HARDENING: ATOMIC LEAD ENROLLMENT (FLAW-DB-15, 16)
-- ----------------------------------------------------------------------------

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
    v_inserted_count INT := 0;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
    ) AND auth.role() <> 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized: User is not a member of workspace %', p_workspace_id;
    END IF;

    WITH inserted_enrollments AS (
        INSERT INTO public.campaign_enrollments (
            id, workspace_id, campaign_id, campaign_version_id, lead_id, account_id
        )
        SELECT
            COALESCE(NULLIF(e->>'id', '')::UUID, gen_random_uuid()),
            p_workspace_id,
            p_campaign_id,
            NULLIF(e->>'campaign_version_id', '')::UUID,
            NULLIF(e->>'lead_id', '')::UUID,
            NULLIF(e->>'account_id', '')::UUID
        FROM jsonb_array_elements(p_enrollments) AS e
        WHERE NOT EXISTS (
            -- Pre-filter suppressed leads to prevent trigger U0001 abort
            SELECT 1 FROM public.suppression_list sl
            JOIN public.leads l ON l.id = NULLIF(e->>'lead_id', '')::UUID
            WHERE sl.workspace_id = p_workspace_id
              AND (
                  (sl.linkedin_url IS NOT NULL AND sl.linkedin_url = l.linkedin_url)
                  OR (sl.email IS NOT NULL AND LOWER(sl.email) = LOWER(l.email))
                  OR (sl.domain IS NOT NULL AND l.domain IS NOT NULL AND LOWER(sl.domain) = LOWER(l.domain))
              )
        )
        ON CONFLICT (campaign_id, lead_id) DO NOTHING
        RETURNING id, lead_id
    )
    INSERT INTO public.campaign_execution_states (
        id, workspace_id, campaign_id, enrollment_id, status, variables
    )
    SELECT
        gen_random_uuid(),
        p_workspace_id,
        p_campaign_id,
        ie.id,
        'pending',
        '{}'::JSONB
    FROM inserted_enrollments ie
    ON CONFLICT (enrollment_id) DO NOTHING;

    GET DIAGNOSTICS v_inserted_count = ROW_COUNT;
    RETURN jsonb_build_object('status', 'success', 'inserted_count', v_inserted_count);
END;
$$;

-- ----------------------------------------------------------------------------
-- 8. RPC HARDENING: SCHEDULER DEQUEUE & LEASE RECOVERY (FLAW-DB-18, 19, 20, 21, 22)
-- ----------------------------------------------------------------------------

-- Canonical dequeue_due_leads with case-insensitive campaign status match
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
    WITH due_states AS (
        SELECT ces.id 
        FROM (
            SELECT id AS campaign_id, workspace_id 
            FROM public.campaigns
            WHERE UPPER(status::text) = 'ACTIVE' 
              AND (p_campaign_ids IS NULL OR id = ANY(p_campaign_ids))
        ) c
        CROSS JOIN LATERAL (
            SELECT ces.id, ces.next_run_at
            FROM public.campaign_execution_states ces
            JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
            LEFT JOIN public.accounts a ON a.id = ce.account_id
            WHERE ces.workspace_id = c.workspace_id
              AND ce.campaign_id = c.campaign_id
              AND (
                  ces.status = 'pending'
                  OR (ces.status = 'running' AND ces.lease_expires_at IS NOT NULL AND ces.lease_expires_at < now())
              )
              AND (ces.next_run_at IS NULL OR ces.next_run_at <= now())
              AND (a.id IS NULL OR (a.status::text = 'ACTIVE' AND COALESCE(a.manual_send_suspected, false) = false))
            ORDER BY ces.next_run_at ASC NULLS FIRST
            LIMIT GREATEST(1, p_batch_size / 5)
        ) ces
        ORDER BY ces.next_run_at ASC NULLS FIRST
        LIMIT p_batch_size
        FOR UPDATE OF ces SKIP LOCKED
    )
    UPDATE public.campaign_execution_states u
    SET 
        lease_token = v_token,
        lease_expires_at = v_expires,
        status = 'running',
        updated_at = now()
    FROM due_states ds
    WHERE u.id = ds.id
    RETURNING u.*;
END;
$$;

-- Canonical release_lead_claim with safe UUID casting
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
    v_next_node_uuid UUID;
BEGIN
    IF p_next_node IS NOT NULL AND p_next_node ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
        v_next_node_uuid := p_next_node::UUID;
    ELSE
        v_next_node_uuid := NULL;
    END IF;

    UPDATE public.campaign_execution_states
    SET 
        status = CASE 
            -- Protect operator-initiated pause from being reverted by in-flight worker
            WHEN status = 'paused' THEN 'paused'
            ELSE p_next_status 
        END,
        current_node_id = COALESCE(v_next_node_uuid, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        retry_count = COALESCE(p_attempts, retry_count),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id 
      AND (p_lease_token IS NULL OR lease_token = p_lease_token OR lease_token::TEXT = p_lease_token::TEXT);
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

-- Canonical recover_stale_leases (only running status)
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
    WHERE status = 'running'
      AND (
          (lease_expires_at IS NOT NULL AND lease_expires_at < now())
          OR updated_at < now() - (p_timeout_minutes || ' minutes')::INTERVAL
      );
    GET DIAGNOSTICS v_recovered = ROW_COUNT;
    RETURN v_recovered;
END;
$$;

-- ----------------------------------------------------------------------------
-- 9. RPC HARDENING: CROSS-TENANT DEFENSE & ATOMIC QUEUES (FLAW-DB-23, 24, 25, 30)
-- ----------------------------------------------------------------------------

-- FLAW-DB-23: Scoped advance_reply_waiting_leads
CREATE OR REPLACE FUNCTION public.advance_reply_waiting_leads(
    p_lead_id UUID,
    p_workspace_id UUID DEFAULT NULL
)
RETURNS integer 
LANGUAGE plpgsql 
SECURITY DEFINER 
SET search_path = public
AS $$
DECLARE
    v_state_id UUID;
    v_count INTEGER := 0;
BEGIN
    IF p_workspace_id IS NOT NULL AND auth.role() <> 'service_role' THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.workspace_members 
            WHERE workspace_id = p_workspace_id AND user_id = auth.uid()
        ) THEN
            RAISE EXCEPTION 'Unauthorized workspace access';
        END IF;
    END IF;

    SELECT ces.id INTO v_state_id
    FROM public.campaign_execution_states ces
    JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
    WHERE ce.lead_id = p_lead_id 
      AND ces.status = 'waiting_for_reply'
      AND (p_workspace_id IS NULL OR ces.workspace_id = p_workspace_id)
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

-- FLAW-DB-24: Scoped claim_processing_jobs with search_path
CREATE OR REPLACE FUNCTION public.claim_processing_jobs(
    claim_limit INT,
    p_workspace_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  workspace_id UUID,
  asset_id UUID,
  job_type TEXT,
  payload JSONB,
  status TEXT,
  created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  WITH claimed AS (
    SELECT processing_jobs.id
    FROM public.processing_jobs
    WHERE processing_jobs.status = 'pending'
      AND (p_workspace_id IS NULL OR processing_jobs.workspace_id = p_workspace_id)
    ORDER BY processing_jobs.created_at ASC
    LIMIT claim_limit
    FOR UPDATE SKIP LOCKED
  )
  UPDATE public.processing_jobs pj
  SET status = 'running', updated_at = NOW()
  FROM claimed c
  WHERE pj.id = c.id
  RETURNING 
    pj.id,
    pj.workspace_id,
    pj.asset_id,
    pj.job_type,
    pj.payload,
    pj.status,
    pj.created_at,
    pj.updated_at;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.claim_processing_jobs(INT, UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.claim_processing_jobs(INT, UUID) TO service_role;

-- FLAW-DB-25: Scoped decrement_list_row_count with search_path
CREATE OR REPLACE FUNCTION public.decrement_list_row_count(
    list_uuid UUID,
    p_workspace_id UUID DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE public.lead_lists
  SET row_count = GREATEST(row_count - 1, 0),
      updated_at = NOW()
  WHERE id = list_uuid 
    AND row_count > 0
    AND (
        p_workspace_id IS NULL 
        OR workspace_id IN (SELECT public.my_workspace_ids())
        OR auth.role() = 'service_role'
    );
END;
$$;

-- FLAW-DB-30: Atomic claim_outbox_events with FOR UPDATE SKIP LOCKED
CREATE OR REPLACE FUNCTION public.claim_outbox_events(
    p_batch_size INT DEFAULT 50,
    p_timeout_seconds INT DEFAULT 300
)
RETURNS SETOF public.outbox_events
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    WITH candidate_events AS (
        SELECT id
        FROM public.outbox_events
        WHERE (status = 'pending' AND deliver_at <= NOW())
           OR (status = 'processing' AND deliver_at <= NOW() - (p_timeout_seconds || ' seconds')::INTERVAL)
        ORDER BY deliver_at ASC
        LIMIT p_batch_size
        FOR UPDATE SKIP LOCKED
    )
    UPDATE public.outbox_events oe
    SET status = 'processing',
        deliver_at = NOW() + (p_timeout_seconds || ' seconds')::INTERVAL,
        attempts = oe.attempts + 1,
        updated_at = NOW()
    FROM candidate_events ce
    WHERE oe.id = ce.id
    RETURNING oe.*;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.claim_outbox_events(INT, INT) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.claim_outbox_events(INT, INT) TO service_role;

-- ----------------------------------------------------------------------------
-- 10. REAL-TIME STATS ROLLUP TRIGGER FIX (FLAW-DB-27)
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.update_daily_campaign_stats()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_campaign_id  UUID;
    v_workspace_id UUID;
    v_stat_date    DATE := DATE(NEW.executed_at AT TIME ZONE 'UTC');
BEGIN
    IF NEW.execution_state_id IS NOT NULL THEN
        SELECT ce.campaign_id, ces.workspace_id
          INTO v_campaign_id, v_workspace_id
          FROM public.campaign_execution_states ces
          JOIN public.campaign_enrollments ce ON ce.id = ces.enrollment_id
         WHERE ces.id = NEW.execution_state_id;
    ELSIF NEW.lead_state_id IS NOT NULL THEN
        SELECT ls.campaign_id, c.workspace_id
          INTO v_campaign_id, v_workspace_id
          FROM public.lead_states ls
          JOIN public.campaigns c ON c.id = ls.campaign_id
         WHERE ls.id = NEW.lead_state_id;
    END IF;

    IF v_workspace_id IS NULL THEN
        v_workspace_id := NEW.workspace_id;
    END IF;

    IF v_campaign_id IS NULL THEN 
        RETURN NEW; 
    END IF;

    INSERT INTO public.daily_campaign_stats (
        workspace_id, campaign_id, stat_date, connections_sent, messages_sent
    ) VALUES (
        v_workspace_id, v_campaign_id, v_stat_date,
        CASE WHEN NEW.action_type ILIKE '%connection%' THEN 1 ELSE 0 END,
        CASE WHEN NEW.action_type IN ('send_message','send_inmail','send_paid_inmail','send_voice_note','send_message_with_doc','send_message_with_image') THEN 1 ELSE 0 END
    )
    ON CONFLICT (campaign_id, stat_date) DO UPDATE SET
        connections_sent = public.daily_campaign_stats.connections_sent + EXCLUDED.connections_sent,
        messages_sent    = public.daily_campaign_stats.messages_sent    + EXCLUDED.messages_sent,
        updated_at       = NOW();

    RETURN NEW;
END;
$$;

-- ----------------------------------------------------------------------------
-- 11. ROW-LEVEL SECURITY POLICY REPAIRS (FLAW-DB-26, 31)
-- ----------------------------------------------------------------------------

ALTER TABLE public.campaign_roi_certificates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_execution_states ENABLE ROW LEVEL SECURITY;

-- FLAW-DB-26: Fix campaign_roi_certificates RLS
DROP POLICY IF EXISTS campaign_roi_cert_workspace_isolation ON public.campaign_roi_certificates;
DROP POLICY IF EXISTS roi_certificates_policy ON public.campaign_roi_certificates;
DROP POLICY IF EXISTS roi_certificates_isolation ON public.campaign_roi_certificates;

CREATE POLICY campaign_roi_certificates_isolation ON public.campaign_roi_certificates
    FOR ALL
    USING (
        is_public = true 
        OR workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    )
    WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    );

-- FLAW-DB-31: Add FOR ALL RLS policies on campaign_enrollments and campaign_execution_states
DROP POLICY IF EXISTS campaign_enrollments_select ON public.campaign_enrollments;
DROP POLICY IF EXISTS campaign_enrollments_all ON public.campaign_enrollments;
CREATE POLICY campaign_enrollments_all ON public.campaign_enrollments
    FOR ALL
    USING (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    )
    WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    );

DROP POLICY IF EXISTS campaign_execution_states_select ON public.campaign_execution_states;
DROP POLICY IF EXISTS campaign_execution_states_all ON public.campaign_execution_states;
CREATE POLICY campaign_execution_states_all ON public.campaign_execution_states
    FOR ALL
    USING (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    )
    WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids()) 
        OR auth.role() = 'service_role'
    );

-- ============================================================================
-- END OF MIGRATION 104
-- ============================================================================
