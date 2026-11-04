-- ==============================================================================
-- Migration 121: Institutional Tier-1 Scale, Schema Integrity & RPC Reconciliation
-- Scope: Fix string node ID advancement, column sync, metadata, and missing FK indexes
-- Standard: Three-Layer Logic Architecture (Paranoia Framework: Layers 0, 1, 2)
-- ==============================================================================

BEGIN;

-- ------------------------------------------------------------------------------
-- 1.0 WORKSPACES: Ensure metadata JSONB exists & Harden Tier Checks
-- ------------------------------------------------------------------------------
ALTER TABLE public.workspaces 
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Convert tier to flexible TEXT with CHECK constraint to support all institutional tiers
DO $$ 
BEGIN
    -- Check if column exists and is enum
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
          AND table_name = 'workspaces' 
          AND column_name = 'tier' 
          AND data_type = 'USER-DEFINED'
    ) THEN
        ALTER TABLE public.workspaces ALTER COLUMN tier TYPE TEXT USING tier::TEXT;
    END IF;
END $$;

ALTER TABLE public.workspaces DROP CONSTRAINT IF EXISTS chk_workspaces_tier;
ALTER TABLE public.workspaces ADD CONSTRAINT chk_workspaces_tier 
    CHECK (UPPER(tier) IN ('FREE', 'STARTER', 'PRO', 'GROWTH', 'ENTERPRISE', 'VIP', 'AGENCY', 'UNLIMITED', 'SCALE'));

-- ------------------------------------------------------------------------------
-- 2.0 CAMPAIGN NODE EXECUTIONS: Reconcile Missing Relational Columns
-- ------------------------------------------------------------------------------
ALTER TABLE public.campaign_node_executions 
    ADD COLUMN IF NOT EXISTS account_id TEXT;

ALTER TABLE public.campaign_node_executions 
    ADD COLUMN IF NOT EXISTS campaign_id UUID REFERENCES public.campaigns(id) ON DELETE CASCADE;

ALTER TABLE public.campaign_node_executions 
    ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '5 minutes');

ALTER TABLE public.campaign_node_executions 
    ADD COLUMN IF NOT EXISTS worker_id UUID;

-- ------------------------------------------------------------------------------
-- 3.0 ACCOUNTS: Reconcile Channel & Timezone Columns
-- ------------------------------------------------------------------------------
ALTER TABLE public.accounts 
    ADD COLUMN IF NOT EXISTS execution_channel VARCHAR(20) DEFAULT 'CLOUD';

ALTER TABLE public.accounts 
    ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC';

-- ------------------------------------------------------------------------------
-- 4.0 CAMPAIGN EXECUTION STATES: attempts & retry_count Bi-Directional Sync
-- ------------------------------------------------------------------------------
ALTER TABLE public.campaign_execution_states 
    ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;

ALTER TABLE public.campaign_execution_states 
    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION public.sync_campaign_execution_attempts()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.attempts IS DISTINCT FROM OLD.attempts THEN
        NEW.retry_count = NEW.attempts;
    ELSIF NEW.retry_count IS DISTINCT FROM OLD.retry_count THEN
        NEW.attempts = NEW.retry_count;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_attempts ON public.campaign_execution_states;
CREATE TRIGGER trg_sync_attempts
    BEFORE INSERT OR UPDATE ON public.campaign_execution_states
    FOR EACH ROW EXECUTE FUNCTION public.sync_campaign_execution_attempts();

-- ------------------------------------------------------------------------------
-- 5.0 RPC RECONCILIATION: release_lead_claim (Support String Node IDs & attempts)
-- ------------------------------------------------------------------------------
-- This version eliminates the strict UUID regex that silenced text slug node IDs (e.g. 'node_1')
CREATE OR REPLACE FUNCTION public.release_lead_claim(
    p_state_id UUID,
    p_lease_token UUID,
    p_next_status TEXT,
    p_next_node TEXT,
    p_next_run TIMESTAMPTZ,
    p_variables JSONB,
    p_error_reason TEXT,
    p_attempts INT,
    p_workspace_id UUID DEFAULT NULL
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
        status = CASE 
            -- Protect operator-initiated pause from being reverted by in-flight worker
            WHEN status = 'paused' THEN 'paused'
            ELSE p_next_status 
        END,
        current_node_id = COALESCE(p_next_node, current_node_id),
        next_run_at = p_next_run,
        variables = COALESCE(p_variables, variables),
        error_reason = p_error_reason,
        attempts = COALESCE(p_attempts, attempts),
        retry_count = COALESCE(p_attempts, retry_count),
        lease_token = NULL,
        lease_expires_at = NULL,
        updated_at = now()
    WHERE id = p_state_id 
      AND (p_workspace_id IS NULL OR workspace_id = p_workspace_id)
      AND (p_lease_token IS NULL OR lease_token = p_lease_token::TEXT OR lease_token::TEXT = p_lease_token::TEXT);
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

GRANT EXECUTE ON FUNCTION public.release_lead_claim(UUID, UUID, TEXT, TEXT, TIMESTAMPTZ, JSONB, TEXT, INT, UUID) TO authenticated, service_role;

-- Overload for backwards compatibility without p_workspace_id
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
BEGIN
    RETURN public.release_lead_claim(
        p_state_id,
        p_lease_token,
        p_next_status,
        p_next_node,
        p_next_run,
        p_variables,
        p_error_reason,
        p_attempts,
        NULL
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.release_lead_claim(UUID, UUID, TEXT, TEXT, TIMESTAMPTZ, JSONB, TEXT, INT) TO authenticated, service_role;

-- ------------------------------------------------------------------------------
-- 6.0 RPC RECONCILIATION: check_and_reserve_account_slot (Support All Tiers)
-- ------------------------------------------------------------------------------
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
    PERFORM pg_advisory_xact_lock(hashtext('acc_conn_' || p_workspace_id::text));

    SELECT UPPER(COALESCE(tier, 'FREE')) INTO v_tier 
    FROM public.workspaces 
    WHERE id = p_workspace_id;

    IF v_tier IN ('PRO', 'GROWTH') THEN
        v_max_accounts := 5;
    ELSIF v_tier = 'STARTER' THEN
        v_max_accounts := 2;
    ELSIF v_tier = 'AGENCY' THEN
        v_max_accounts := 15;
    ELSIF v_tier IN ('ENTERPRISE', 'VIP', 'SCALE', 'UNLIMITED') THEN
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
            'reason', 'ACCOUNT_LIMIT_REACHED',
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

GRANT EXECUTE ON FUNCTION public.check_and_reserve_account_slot(UUID, UUID) TO authenticated, service_role;

-- ------------------------------------------------------------------------------
-- 7.0 MISSING FOREIGN KEY INDEXES (Eliminate Cascade ExclusiveLocks)
-- ------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_accounts_proxy_id 
    ON public.accounts(proxy_id) WHERE proxy_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cne_workspace_id 
    ON public.campaign_node_executions(workspace_id);

CREATE INDEX IF NOT EXISTS idx_cne_campaign_ver 
    ON public.campaign_node_executions(campaign_version_id);

CREATE INDEX IF NOT EXISTS idx_cne_campaign_id 
    ON public.campaign_node_executions(campaign_id);

CREATE INDEX IF NOT EXISTS idx_messages_account_id 
    ON public.messages(account_id);

CREATE INDEX IF NOT EXISTS idx_ces_workspace_id_full 
    ON public.campaign_execution_states(workspace_id);

CREATE INDEX IF NOT EXISTS idx_workspace_members_user_ws 
    ON public.workspace_members(user_id, workspace_id);

COMMIT;
