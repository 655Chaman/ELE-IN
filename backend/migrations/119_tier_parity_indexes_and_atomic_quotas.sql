-- ============================================================================
-- Migration 119: 10,000-Tenant Concurrency Composite Indexes & Atomic Quotas
-- ============================================================================
-- 1. Creates high-performance composite indexes across core tenant tables to
--    eliminate sequential table scans under 10k customer scale.
-- 2. Creates atomic stored procedures for campaign activation and account linking
--    using pg_advisory_xact_lock to eliminate TOCTOU race conditions permanently.

-- A. High-Performance 10k Tenant Composite Indexes
CREATE INDEX IF NOT EXISTS idx_campaigns_ws_status_created 
    ON public.campaigns (workspace_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_campaigns_ws_created 
    ON public.campaigns (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_accounts_ws_created 
    ON public.accounts (workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_accounts_ws_status 
    ON public.accounts (workspace_id, status);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_tier 
    ON public.workspaces (owner_id, tier);

CREATE INDEX IF NOT EXISTS idx_leads_ws_status_created 
    ON public.leads (workspace_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_leads_ws_list 
    ON public.leads (workspace_id, list_id);

CREATE INDEX IF NOT EXISTS idx_billing_txns_ws_status 
    ON public.billing_transactions (workspace_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workspace_audit_logs_ws_created 
    ON public.workspace_audit_logs (workspace_id, created_at DESC);


-- B. Stored Procedure: activate_campaign_safely (FLAW-SCALE-02 / Layer 0 & 1 Paranoia)
CREATE OR REPLACE FUNCTION public.activate_campaign_safely(
    p_workspace_id UUID,
    p_campaign_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_tier TEXT;
    v_max_campaigns INT := 1;
    v_active_count INT := 0;
    v_exists BOOLEAN := FALSE;
BEGIN
    -- Paranoia Layer 1: Transaction-level advisory lock serializes simultaneous activations per workspace
    PERFORM pg_advisory_xact_lock(hashtext('camp_act_' || p_workspace_id::text));

    -- Check campaign exists and belongs to workspace
    SELECT EXISTS(
        SELECT 1 FROM public.campaigns 
        WHERE id = p_campaign_id AND workspace_id = p_workspace_id
    ) INTO v_exists;

    IF NOT v_exists THEN
        RETURN jsonb_build_object('success', false, 'reason', 'campaign_not_found');
    END IF;

    -- Determine canonical tier and quota
    SELECT UPPER(COALESCE(tier, 'FREE')) INTO v_tier 
    FROM public.workspaces 
    WHERE id = p_workspace_id;

    IF v_tier IN ('PRO', 'GROWTH', 'STARTER') THEN
        v_max_campaigns := 20;
    ELSIF v_tier = 'AGENCY' THEN
        v_max_campaigns := 50;
    ELSIF v_tier IN ('ENTERPRISE', 'SCALE', 'UNLIMITED') THEN
        v_max_campaigns := 100;
    ELSE
        v_max_campaigns := 1;
    END IF;

    -- Count active campaigns excluding current
    SELECT count(*) INTO v_active_count
    FROM public.campaigns
    WHERE workspace_id = p_workspace_id 
      AND status = 'ACTIVE' 
      AND id != p_campaign_id;

    IF v_active_count >= v_max_campaigns THEN
        RETURN jsonb_build_object(
            'success', false,
            'reason', 'quota_exceeded',
            'tier', v_tier,
            'max_allowed', v_max_campaigns,
            'current_active', v_active_count
        );
    END IF;

    -- Atomically activate
    UPDATE public.campaigns
    SET status = 'ACTIVE', updated_at = NOW()
    WHERE id = p_campaign_id AND workspace_id = p_workspace_id;

    RETURN jsonb_build_object(
        'success', true,
        'status', 'ACTIVE',
        'tier', v_tier,
        'max_allowed', v_max_campaigns,
        'active_count', v_active_count + 1
    );
END;
$$;


-- C. Stored Procedure: check_and_reserve_account_slot (FLAW-SCALE-01 / Layer 0 & 1 Paranoia)
CREATE OR REPLACE FUNCTION public.check_and_reserve_account_slot(
    p_workspace_id UUID,
    p_account_id UUID DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_tier TEXT;
    v_max_accounts INT := 1;
    v_current_count INT := 0;
BEGIN
    -- Paranoia Layer 1: Transaction-level advisory lock serializes simultaneous account connections
    PERFORM pg_advisory_xact_lock(hashtext('acc_conn_' || p_workspace_id::text));

    SELECT UPPER(COALESCE(tier, 'FREE')) INTO v_tier 
    FROM public.workspaces 
    WHERE id = p_workspace_id;

    IF v_tier IN ('PRO', 'GROWTH', 'STARTER') THEN
        v_max_accounts := 5;
    ELSIF v_tier = 'AGENCY' THEN
        v_max_accounts := 15;
    ELSIF v_tier IN ('ENTERPRISE', 'SCALE', 'UNLIMITED') THEN
        v_max_accounts := 50;
    ELSE
        v_max_accounts := 1;
    END IF;

    SELECT count(*) INTO v_current_count
    FROM public.accounts
    WHERE workspace_id = p_workspace_id 
      AND (p_account_id IS NULL OR id != p_account_id)
      AND COALESCE(status, '') != 'DISCONNECTED';

    IF v_current_count >= v_max_accounts THEN
        RETURN jsonb_build_object(
            'allowed', false,
            'reason', 'quota_exceeded',
            'tier', v_tier,
            'max_allowed', v_max_accounts,
            'current_count', v_current_count
        );
    END IF;

    RETURN jsonb_build_object(
        'allowed', true,
        'tier', v_tier,
        'max_allowed', v_max_accounts,
        'current_count', v_current_count
    );
END;
$$;
