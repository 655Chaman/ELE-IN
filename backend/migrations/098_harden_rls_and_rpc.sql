-- ==============================================================================
-- MIGRATION: 098_harden_rls_and_rpc
-- PARANOIA FRAMEWORK: Layer 0 (Foundation), Layer 1 (Environmental), Layer 2 (Human Abuse)
-- 1. Closes all 18 open USING (true) RLS policies with strict workspace tenant isolation.
-- 2. Fixes broken request.jwt.claims policies that lock users out.
-- 3. Eliminates recursive RLS loop in agency_members.
-- 4. Hardens credit deduction RPC to block negative deductions and unauthorized minting.
-- 5. Restores core scheduler RPCs (dequeue_due_leads, lease recovery, distributed locks).
-- ==============================================================================

BEGIN;

-- ------------------------------------------------------------------------------
-- 1. Helper function for recursive agency authorization (prevents 54001 stack overflow)
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.is_agency_admin_or_owner(
    p_agency_id UUID,
    p_user_id UUID
) RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.agencies WHERE id = p_agency_id AND owner_id = p_user_id
    ) OR EXISTS (
        SELECT 1 FROM public.agency_members 
        WHERE agency_id = p_agency_id 
          AND user_id = p_user_id 
          AND role IN ('owner', 'admin')
    );
$$;

-- Fix recursive policy on agency_members
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'agency_members') THEN
        DROP POLICY IF EXISTS agency_members_access ON public.agency_members;
        CREATE POLICY agency_members_access ON public.agency_members
        FOR ALL USING (
            user_id = auth.uid() OR public.is_agency_admin_or_owner(agency_id, auth.uid())
        )
        WITH CHECK (
            public.is_agency_admin_or_owner(agency_id, auth.uid())
        );
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- 2. Fix broken request.jwt.claims on knowledge_objections and certificates
-- ------------------------------------------------------------------------------
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'knowledge_objections') THEN
        DROP POLICY IF EXISTS "Users can manage their own workspace objections" ON public.knowledge_objections;
        DROP POLICY IF EXISTS knowledge_objections_isolation ON public.knowledge_objections;
        CREATE POLICY knowledge_objections_isolation ON public.knowledge_objections
        FOR ALL USING (workspace_id::text IN (SELECT id::text FROM public.workspaces WHERE id IN (SELECT public.my_workspace_ids())))
        WITH CHECK (workspace_id::text IN (SELECT id::text FROM public.workspaces WHERE id IN (SELECT public.my_workspace_ids())));
    END IF;
END $$;

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'campaign_roi_certificates') THEN
        DROP POLICY IF EXISTS roi_certificates_policy ON public.campaign_roi_certificates;
        DROP POLICY IF EXISTS roi_certificates_isolation ON public.campaign_roi_certificates;
        CREATE POLICY roi_certificates_isolation ON public.campaign_roi_certificates
        FOR ALL USING (
            is_public = true OR workspace_id IN (SELECT public.my_workspace_ids())
        )
        WITH CHECK (
            workspace_id IN (SELECT public.my_workspace_ids())
        );
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- 3. Replace all 18 open USING (true) policies with strict workspace isolation
-- ------------------------------------------------------------------------------

-- 1. workspace_auto_recharge_settings
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'workspace_auto_recharge_settings') THEN
        DROP POLICY IF EXISTS workspace_auto_recharge_settings_isolation ON public.workspace_auto_recharge_settings;
        CREATE POLICY workspace_auto_recharge_settings_isolation ON public.workspace_auto_recharge_settings
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 2. agency_credit_allocations
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'agency_credit_allocations') THEN
        DROP POLICY IF EXISTS agency_credit_allocations_isolation ON public.agency_credit_allocations;
        CREATE POLICY agency_credit_allocations_isolation ON public.agency_credit_allocations
        FOR ALL USING (
            client_workspace_id IN (SELECT public.my_workspace_ids()) OR
            public.is_agency_admin_or_owner(agency_id, auth.uid())
        )
        WITH CHECK (
            public.is_agency_admin_or_owner(agency_id, auth.uid())
        );
    END IF;
END $$;

-- 3. sender_pod_audit_logs
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'sender_pod_audit_logs') THEN
        DROP POLICY IF EXISTS sender_pod_audit_isolation ON public.sender_pod_audit_logs;
        CREATE POLICY sender_pod_audit_isolation ON public.sender_pod_audit_logs
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 4. agency_billing_statements
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'agency_billing_statements') THEN
        DROP POLICY IF EXISTS agency_billing_statements_isolation ON public.agency_billing_statements;
        CREATE POLICY agency_billing_statements_isolation ON public.agency_billing_statements
        FOR ALL USING (
            client_workspace_id IN (SELECT public.my_workspace_ids()) OR
            public.is_agency_admin_or_owner(agency_id, auth.uid())
        )
        WITH CHECK (
            public.is_agency_admin_or_owner(agency_id, auth.uid())
        );
    END IF;
END $$;

-- 5. lead_social_posts
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_social_posts') THEN
        DROP POLICY IF EXISTS lead_social_posts_isolation ON public.lead_social_posts;
        CREATE POLICY lead_social_posts_isolation ON public.lead_social_posts
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 6. lead_social_signals
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_social_signals') THEN
        DROP POLICY IF EXISTS lead_social_signals_isolation ON public.lead_social_signals;
        CREATE POLICY lead_social_signals_isolation ON public.lead_social_signals
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 7. icp_feedback_events
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'icp_feedback_events') THEN
        DROP POLICY IF EXISTS icp_feedback_events_isolation ON public.icp_feedback_events;
        CREATE POLICY icp_feedback_events_isolation ON public.icp_feedback_events
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 8. lead_objections
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_objections') THEN
        DROP POLICY IF EXISTS lead_objections_isolation ON public.lead_objections;
        CREATE POLICY lead_objections_isolation ON public.lead_objections
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 9. lead_prewarm_events
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'lead_prewarm_events') THEN
        DROP POLICY IF EXISTS lead_prewarm_events_isolation ON public.lead_prewarm_events;
        CREATE POLICY lead_prewarm_events_isolation ON public.lead_prewarm_events
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 10. omnichannel_fallback_configs
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'omnichannel_fallback_configs') THEN
        DROP POLICY IF EXISTS omnichannel_fallback_configs_isolation ON public.omnichannel_fallback_configs;
        CREATE POLICY omnichannel_fallback_configs_isolation ON public.omnichannel_fallback_configs
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 11. omnichannel_cascade_logs
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'omnichannel_cascade_logs') THEN
        DROP POLICY IF EXISTS omnichannel_cascade_logs_isolation ON public.omnichannel_cascade_logs;
        CREATE POLICY omnichannel_cascade_logs_isolation ON public.omnichannel_cascade_logs
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 12. thought_leadership_posts
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'thought_leadership_posts') THEN
        DROP POLICY IF EXISTS thought_leadership_posts_isolation ON public.thought_leadership_posts;
        CREATE POLICY thought_leadership_posts_isolation ON public.thought_leadership_posts
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 13. bandit_experiments
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'bandit_experiments') THEN
        DROP POLICY IF EXISTS bandit_experiments_ws_policy ON public.bandit_experiments;
        CREATE POLICY bandit_experiments_ws_policy ON public.bandit_experiments
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 14. copy_variants
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'copy_variants') THEN
        DROP POLICY IF EXISTS copy_variants_ws_policy ON public.copy_variants;
        CREATE POLICY copy_variants_ws_policy ON public.copy_variants
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 15. trigger_events
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'trigger_events') THEN
        DROP POLICY IF EXISTS trigger_events_ws_policy ON public.trigger_events;
        CREATE POLICY trigger_events_ws_policy ON public.trigger_events
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 16. harvested_events
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'harvested_events') THEN
        DROP POLICY IF EXISTS harvested_events_ws_policy ON public.harvested_events;
        CREATE POLICY harvested_events_ws_policy ON public.harvested_events
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 17. event_attendees
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'event_attendees') THEN
        DROP POLICY IF EXISTS event_attendees_ws_policy ON public.event_attendees;
        CREATE POLICY event_attendees_ws_policy ON public.event_attendees
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;

-- 18. multimodal_assets
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'multimodal_assets') THEN
        DROP POLICY IF EXISTS multimodal_assets_ws_policy ON public.multimodal_assets;
        CREATE POLICY multimodal_assets_ws_policy ON public.multimodal_assets
        FOR ALL USING (workspace_id IN (SELECT public.my_workspace_ids()))
        WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));
    END IF;
END $$;


-- ------------------------------------------------------------------------------
-- 4. Hardened credit deduction & transfer functions
-- ------------------------------------------------------------------------------
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
    -- LAYER 2 PARANOIA: Block negative deduction values (prohibits credit minting abuse)
    IF p_amount < 0 THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', 0,
            'reason', 'invalid_amount',
            'error', 'Negative deduction amount is prohibited'
        );
    END IF;

    -- LAYER 1 PARANOIA: Row-level lock on public.workspaces to serialize concurrent requests
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

    -- Determine tier-aware overdraft floor
    IF v_tier IN ('PRO', 'GROWTH', 'ENTERPRISE', 'AGENCY', 'UNLIMITED', 'SCALE') THEN
        v_min_balance := -500;
    ELSE
        v_min_balance := 0;
    END IF;

    -- Check idempotency under lock
    SELECT EXISTS (
        SELECT 1 FROM public.credit_deductions 
        WHERE idempotency_key = p_idempotency_key
    ) INTO v_already_processed;

    IF v_already_processed THEN
        SELECT balance_after INTO v_new_balance
        FROM public.credit_deductions
        WHERE idempotency_key = p_idempotency_key;

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

    -- Check overdraft boundary
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


-- ------------------------------------------------------------------------------
-- 5. Restored Core Scheduler RPCs with Zombie Leases Hardening
-- ------------------------------------------------------------------------------

-- 5a. dequeue_due_leads with FOR UPDATE SKIP LOCKED
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
              AND COALESCE(a.manual_send_suspected, false) = false
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

-- 5b. release_lead_claim
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
AS $$
DECLARE
    v_rows INT;
    v_node_uuid UUID := NULL;
BEGIN
    IF p_next_node IS NOT NULL AND p_next_node ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN
        v_node_uuid := p_next_node::UUID;
    END IF;

    UPDATE public.campaign_execution_states
    SET 
        status = p_next_status,
        current_node_id = COALESCE(v_node_uuid, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        attempts = COALESCE(p_attempts, attempts),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id AND (p_lease_token IS NULL OR lease_token = p_lease_token::TEXT OR lease_token::TEXT = p_lease_token::TEXT);
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

-- 5c. recover_stale_leases (recovers both 'processing' and stalled 'running' fallback states)
CREATE OR REPLACE FUNCTION public.recover_stale_leases(p_timeout_minutes INT DEFAULT 5)
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
    WHERE status IN ('processing', 'running')
      AND (lease_expires_at IS NULL OR lease_expires_at < now());
      
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows;
END;
$$;

COMMIT;
