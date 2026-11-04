-- ==============================================================================
-- MIGRATION: 116_settings_and_workspace_paranoia_hardening.sql
-- SUBSYSTEM: Settings, Workspaces, Members, Audit Logs, and Security Locks
-- ARCHITECTURE: Three-Layer Logic Architecture (Paranoia Framework)
-- ==============================================================================

BEGIN;

-- ------------------------------------------------------------------------------
-- 1. LAYER 1: FIX CRITICAL INDEXES & FOREIGN KEY PERFORMANCE BOTTLENECKS
-- ------------------------------------------------------------------------------

-- 1a. The #1 Global RLS Bottleneck: Index workspace_members(user_id) for public.my_workspace_ids()
CREATE INDEX IF NOT EXISTS idx_workspace_members_user_id 
    ON public.workspace_members(user_id);

-- 1b. Unindexed foreign keys causing table locks during deletion/cascade
CREATE INDEX IF NOT EXISTS idx_workspace_members_invited_by 
    ON public.workspace_members(invited_by) 
    WHERE invited_by IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_id 
    ON public.workspaces(owner_id);

CREATE INDEX IF NOT EXISTS idx_workspaces_agency_id 
    ON public.workspaces(agency_id) 
    WHERE agency_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workspace_invites_ws 
    ON public.workspace_invites(workspace_id);

CREATE INDEX IF NOT EXISTS idx_workspace_invites_invited_by 
    ON public.workspace_invites(invited_by);

-- 1c. Partial unique index for active pending invites (fixes RACE-01)
DROP INDEX IF EXISTS public.uq_pending_invite_active;
ALTER TABLE public.workspace_invites DROP CONSTRAINT IF EXISTS uq_pending_invite;
CREATE UNIQUE INDEX IF NOT EXISTS uq_pending_invite_active 
    ON public.workspace_invites (workspace_id, lower(trim(email))) 
    WHERE status = 'pending';

-- 1d. Partial unique index for active superadmin grants (fixes RACE-02)
CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_grants_active_user 
    ON public.admin_grants (user_id) 
    WHERE revoked_at IS NULL;


-- ------------------------------------------------------------------------------
-- 2. LAYER 0 & 2: CHECK CONSTRAINTS & DATA BOUNDS
-- ------------------------------------------------------------------------------

-- Pre-sanitize legacy dirty data in workspace_sending_defaults to prevent constraint abort
UPDATE public.workspace_sending_defaults 
SET default_working_hours_start = '08:00:00', default_working_hours_end = '18:00:00'
WHERE default_working_hours_start IS NULL 
   OR default_working_hours_end IS NULL 
   OR default_working_hours_start >= default_working_hours_end;

UPDATE public.workspace_sending_defaults
SET default_daily_connection_limit = LEAST(GREATEST(COALESCE(default_daily_connection_limit, 20), 0), 250),
    default_daily_message_limit = LEAST(GREATEST(COALESCE(default_daily_message_limit, 40), 0), 500),
    default_warmup_target_days = LEAST(GREATEST(COALESCE(default_warmup_target_days, 14), 0), 180);

-- 2a. workspace_sending_defaults bounds
ALTER TABLE public.workspace_sending_defaults
    DROP CONSTRAINT IF EXISTS chk_ws_sending_conn_limit,
    ADD CONSTRAINT chk_ws_sending_conn_limit 
        CHECK (default_daily_connection_limit >= 0 AND default_daily_connection_limit <= 250);

ALTER TABLE public.workspace_sending_defaults
    DROP CONSTRAINT IF EXISTS chk_ws_sending_msg_limit,
    ADD CONSTRAINT chk_ws_sending_msg_limit 
        CHECK (default_daily_message_limit >= 0 AND default_daily_message_limit <= 500);

ALTER TABLE public.workspace_sending_defaults
    DROP CONSTRAINT IF EXISTS chk_ws_sending_warmup_days,
    ADD CONSTRAINT chk_ws_sending_warmup_days 
        CHECK (default_warmup_target_days >= 0 AND default_warmup_target_days <= 180);

ALTER TABLE public.workspace_sending_defaults
    DROP CONSTRAINT IF EXISTS chk_ws_sending_working_hours,
    ADD CONSTRAINT chk_ws_sending_working_hours 
        CHECK (default_working_hours_start < default_working_hours_end);

-- 2b. workspace_ai_settings bounds
DO $$ 
BEGIN 
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'workspace_ai_settings') THEN
        UPDATE public.workspace_ai_settings 
        SET temperature = LEAST(GREATEST(COALESCE(temperature, 0.7), 0.0), 2.0),
            max_tokens_budget = LEAST(GREATEST(COALESCE(max_tokens_budget, 100000), 1000), 100000000)
        WHERE temperature < 0.0 OR temperature > 2.0 OR max_tokens_budget < 1000 OR max_tokens_budget > 100000000;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'workspace_auto_recharge_settings') THEN
        UPDATE public.workspace_auto_recharge_settings
        SET threshold_credits = LEAST(GREATEST(COALESCE(threshold_credits, 100), 10), 10000),
            max_monthly_recharges = LEAST(GREATEST(COALESCE(max_monthly_recharges, 5), 1), 50),
            recharges_this_month = GREATEST(COALESCE(recharges_this_month, 0), 0)
        WHERE threshold_credits < 10 OR threshold_credits > 10000 OR max_monthly_recharges < 1 OR max_monthly_recharges > 50 OR recharges_this_month < 0;
    END IF;
END $$;

ALTER TABLE public.workspace_ai_settings
    DROP CONSTRAINT IF EXISTS chk_ws_ai_temperature,
    ADD CONSTRAINT chk_ws_ai_temperature 
        CHECK (temperature >= 0.0 AND temperature <= 2.0);

ALTER TABLE public.workspace_ai_settings
    DROP CONSTRAINT IF EXISTS chk_ws_ai_tokens_budget,
    ADD CONSTRAINT chk_ws_ai_tokens_budget 
        CHECK (max_tokens_budget >= 1000 AND max_tokens_budget <= 100000000);

ALTER TABLE public.workspace_ai_settings
    DROP CONSTRAINT IF EXISTS chk_ws_ai_byok_provider,
    ADD CONSTRAINT chk_ws_ai_byok_provider 
        CHECK (byok_provider IS NULL OR byok_provider IN ('openai', 'anthropic', 'deepseek', 'groq', 'openrouter', 'gemini', 'nvidia', 'moonshot'));

-- 2c. workspace_auto_recharge_settings bounds
ALTER TABLE public.workspace_auto_recharge_settings
    DROP CONSTRAINT IF EXISTS chk_auto_recharge_threshold,
    ADD CONSTRAINT chk_auto_recharge_threshold 
        CHECK (threshold_credits >= 10 AND threshold_credits <= 10000);

ALTER TABLE public.workspace_auto_recharge_settings
    DROP CONSTRAINT IF EXISTS chk_auto_recharge_max_monthly,
    ADD CONSTRAINT chk_auto_recharge_max_monthly 
        CHECK (max_monthly_recharges >= 1 AND max_monthly_recharges <= 50);

ALTER TABLE public.workspace_auto_recharge_settings
    DROP CONSTRAINT IF EXISTS chk_auto_recharge_counter,
    ADD CONSTRAINT chk_auto_recharge_counter 
        CHECK (recharges_this_month >= 0);

ALTER TABLE public.workspace_auto_recharge_settings
    DROP CONSTRAINT IF EXISTS chk_auto_recharge_package,
    ADD CONSTRAINT chk_auto_recharge_package 
        CHECK (recharge_package_id IN ('credits_1000', 'credits_5000'));

-- 2d. workspace_invites status & email format bounds
ALTER TABLE public.workspace_invites
    DROP CONSTRAINT IF EXISTS chk_ws_invite_status,
    ADD CONSTRAINT chk_ws_invite_status 
        CHECK (status IN ('pending', 'accepted', 'revoked', 'expired'));

ALTER TABLE public.workspace_invites
    DROP CONSTRAINT IF EXISTS chk_ws_invite_expiry,
    ADD CONSTRAINT chk_ws_invite_expiry 
        CHECK (expires_at > created_at);

-- 2e. workspaces status, confidence, and temperature bounds
ALTER TABLE public.workspaces
    DROP CONSTRAINT IF EXISTS chk_workspaces_status,
    ADD CONSTRAINT chk_workspaces_status 
        CHECK (status IN ('active', 'suspended', 'deletion_pending', 'pending_deletion', 'purged'));

ALTER TABLE public.workspaces
    DROP CONSTRAINT IF EXISTS chk_workspaces_ai_confidence,
    ADD CONSTRAINT chk_workspaces_ai_confidence 
        CHECK (ai_reply_confidence_threshold IS NULL OR (ai_reply_confidence_threshold >= 0.0 AND ai_reply_confidence_threshold <= 1.0));

-- 2f. notification_preferences channel bounds
ALTER TABLE public.notification_preferences
    DROP CONSTRAINT IF EXISTS chk_notif_pref_channel,
    ADD CONSTRAINT chk_notif_pref_channel 
        CHECK (channel IN ('email', 'in_app', 'slack', 'webhook', 'sms'));

-- 2g. admin_grants temporal bounds
ALTER TABLE public.admin_grants
    DROP CONSTRAINT IF EXISTS chk_admin_grants_temporal,
    ADD CONSTRAINT chk_admin_grants_temporal 
        CHECK (revoked_at IS NULL OR revoked_at >= granted_at);


-- ------------------------------------------------------------------------------
-- 3. LAYER 2: HARDEN ROW-LEVEL SECURITY (RLS) POLICIES
-- ------------------------------------------------------------------------------

-- Helper function: verify if caller is admin or owner of workspace
CREATE OR REPLACE FUNCTION public.is_workspace_admin_or_owner(
    p_workspace_id UUID,
    p_user_id UUID DEFAULT auth.uid()
) RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.workspaces 
        WHERE id = p_workspace_id AND owner_id = p_user_id
    ) OR EXISTS (
        SELECT 1 FROM public.workspace_members 
        WHERE workspace_id = p_workspace_id 
          AND user_id = p_user_id 
          AND role IN ('owner', 'admin')
    );
$$;

-- 3a. Close RLS-01: workspace_ai_settings
ALTER TABLE public.workspace_ai_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_ai_settings_workspace_isolation ON public.workspace_ai_settings;
DROP POLICY IF EXISTS workspace_ai_settings_select ON public.workspace_ai_settings;
DROP POLICY IF EXISTS workspace_ai_settings_modify ON public.workspace_ai_settings;

CREATE POLICY workspace_ai_settings_select ON public.workspace_ai_settings
    FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));

CREATE POLICY workspace_ai_settings_modify ON public.workspace_ai_settings
    FOR ALL 
    USING (public.is_workspace_admin_or_owner(workspace_id, auth.uid()))
    WITH CHECK (public.is_workspace_admin_or_owner(workspace_id, auth.uid()));

-- 3b. Close RLS-02: workspace_blueprints (Prevent cross-workspace deletion)
ALTER TABLE public.workspace_blueprints ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_blueprints_tenant_isolation ON public.workspace_blueprints;
DROP POLICY IF EXISTS workspace_blueprints_select ON public.workspace_blueprints;
DROP POLICY IF EXISTS workspace_blueprints_insert ON public.workspace_blueprints;
DROP POLICY IF EXISTS workspace_blueprints_update ON public.workspace_blueprints;
DROP POLICY IF EXISTS workspace_blueprints_delete ON public.workspace_blueprints;

CREATE POLICY workspace_blueprints_select ON public.workspace_blueprints
    FOR SELECT USING (
        workspace_id IN (SELECT public.my_workspace_ids()) OR is_public = true
    );

CREATE POLICY workspace_blueprints_insert ON public.workspace_blueprints
    FOR INSERT WITH CHECK (
        workspace_id IN (SELECT public.my_workspace_ids())
    );

CREATE POLICY workspace_blueprints_update ON public.workspace_blueprints
    FOR UPDATE 
    USING (workspace_id IN (SELECT public.my_workspace_ids()))
    WITH CHECK (workspace_id IN (SELECT public.my_workspace_ids()));

CREATE POLICY workspace_blueprints_delete ON public.workspace_blueprints
    FOR DELETE USING (
        workspace_id IN (SELECT public.my_workspace_ids())
    );

-- 3c. Close RLS-03: workspace_members (Prevent role self-elevation)
ALTER TABLE public.workspace_members ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "workspace_members_self_or_owner" ON public.workspace_members;
DROP POLICY IF EXISTS "workspace_members_workspace_isolation" ON public.workspace_members;
DROP POLICY IF EXISTS workspace_members_select ON public.workspace_members;
DROP POLICY IF EXISTS workspace_members_insert ON public.workspace_members;
DROP POLICY IF EXISTS workspace_members_update ON public.workspace_members;
DROP POLICY IF EXISTS workspace_members_delete ON public.workspace_members;

-- Members can see teammates in their workspaces
CREATE POLICY workspace_members_select ON public.workspace_members
    FOR SELECT USING (
        workspace_id IN (SELECT public.my_workspace_ids())
    );

-- Only owners and admins can add members
CREATE POLICY workspace_members_insert ON public.workspace_members
    FOR INSERT WITH CHECK (
        public.is_workspace_admin_or_owner(workspace_id, auth.uid())
    );

-- Only owners and admins can update member roles
CREATE POLICY workspace_members_update ON public.workspace_members
    FOR UPDATE 
    USING (public.is_workspace_admin_or_owner(workspace_id, auth.uid()))
    WITH CHECK (public.is_workspace_admin_or_owner(workspace_id, auth.uid()));

-- Owners/admins can remove members; members can leave themselves
CREATE POLICY workspace_members_delete ON public.workspace_members
    FOR DELETE USING (
        user_id = auth.uid() OR public.is_workspace_admin_or_owner(workspace_id, auth.uid())
    );

-- Hard Layer 2 trigger: Disallow non-owners from modifying roles
CREATE OR REPLACE FUNCTION public.trg_guard_member_role_escalation()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF OLD.role IS DISTINCT FROM NEW.role THEN
        -- Verify that executing user is an owner of the workspace
        IF NOT EXISTS (
            SELECT 1 FROM public.workspaces 
            WHERE id = OLD.workspace_id AND owner_id = auth.uid()
        ) AND NOT EXISTS (
            SELECT 1 FROM public.workspace_members 
            WHERE workspace_id = OLD.workspace_id AND user_id = auth.uid() AND role = 'owner'
        ) AND (auth.role() != 'service_role') THEN
            RAISE EXCEPTION 'Privilege escalation blocked: Only workspace owners can change member roles';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_block_member_role_escalation ON public.workspace_members;
CREATE TRIGGER trg_block_member_role_escalation
    BEFORE UPDATE ON public.workspace_members
    FOR EACH ROW EXECUTE FUNCTION public.trg_guard_member_role_escalation();

-- 3d. Close RLS-04: workspace_deks (Master encryption key protection)
ALTER TABLE public.workspace_deks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_deks_tenant_isolation ON public.workspace_deks;
DROP POLICY IF EXISTS workspace_deks_select ON public.workspace_deks;
DROP POLICY IF EXISTS workspace_deks_modify ON public.workspace_deks;

CREATE POLICY workspace_deks_select ON public.workspace_deks
    FOR SELECT USING (
        public.is_workspace_admin_or_owner(workspace_id::uuid, auth.uid())
    );

CREATE POLICY workspace_deks_modify ON public.workspace_deks
    FOR ALL 
    USING (public.is_workspace_admin_or_owner(workspace_id::uuid, auth.uid()))
    WITH CHECK (public.is_workspace_admin_or_owner(workspace_id::uuid, auth.uid()));

-- 3e. Close RLS-05: workspace_invites
ALTER TABLE public.workspace_invites ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_invites_ws ON public.workspace_invites;
DROP POLICY IF EXISTS workspace_invites_select ON public.workspace_invites;
DROP POLICY IF EXISTS workspace_invites_admin ON public.workspace_invites;

CREATE POLICY workspace_invites_select ON public.workspace_invites
    FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));

CREATE POLICY workspace_invites_admin ON public.workspace_invites
    FOR ALL 
    USING (public.is_workspace_admin_or_owner(workspace_id, auth.uid()))
    WITH CHECK (public.is_workspace_admin_or_owner(workspace_id, auth.uid()));

-- 3f. Close RLS-06: notification_preferences
ALTER TABLE public.notification_preferences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS notification_preferences_ws ON public.notification_preferences;
CREATE POLICY notification_preferences_ws ON public.notification_preferences
    FOR ALL 
    USING (user_id = auth.uid() AND workspace_id IN (SELECT public.my_workspace_ids()))
    WITH CHECK (user_id = auth.uid() AND workspace_id IN (SELECT public.my_workspace_ids()));

-- 3g. Close RLS-07: workspace_settings
ALTER TABLE public.workspace_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspace_settings_isolation ON public.workspace_settings;
DROP POLICY IF EXISTS workspace_settings_select ON public.workspace_settings;
DROP POLICY IF EXISTS workspace_settings_modify ON public.workspace_settings;

CREATE POLICY workspace_settings_select ON public.workspace_settings
    FOR SELECT USING (workspace_id IN (SELECT public.my_workspace_ids()));

CREATE POLICY workspace_settings_modify ON public.workspace_settings
    FOR ALL 
    USING (public.is_workspace_admin_or_owner(workspace_id, auth.uid()))
    WITH CHECK (public.is_workspace_admin_or_owner(workspace_id, auth.uid()));

-- 3h. Close RLS-08: workspaces
ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS workspaces_member ON public.workspaces;
DROP POLICY IF EXISTS workspaces_select ON public.workspaces;
DROP POLICY IF EXISTS workspaces_update ON public.workspaces;
DROP POLICY IF EXISTS workspaces_delete ON public.workspaces;

CREATE POLICY workspaces_select ON public.workspaces
    FOR SELECT USING (id IN (SELECT public.my_workspace_ids()));

CREATE POLICY workspaces_update ON public.workspaces
    FOR UPDATE 
    USING (public.is_workspace_admin_or_owner(id, auth.uid()))
    WITH CHECK (public.is_workspace_admin_or_owner(id, auth.uid()));

CREATE POLICY workspaces_delete ON public.workspaces
    FOR DELETE USING (owner_id = auth.uid());

-- 3i. Close RLS-09: audit_log (Admin-only read access)
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS audit_log_ws_read ON public.audit_log;
CREATE POLICY audit_log_ws_read ON public.audit_log
    FOR SELECT USING (
        public.is_workspace_admin_or_owner(workspace_id, auth.uid())
    );

-- 3j. Close RPC-01: processing_locks table & RPC hardening
ALTER TABLE public.processing_locks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS processing_locks_service_role ON public.processing_locks;
CREATE POLICY processing_locks_service_role ON public.processing_locks
    FOR ALL TO service_role
    USING (true) WITH CHECK (true);

-- Harden try_acquire_distributed_lock
CREATE OR REPLACE FUNCTION public.try_acquire_distributed_lock(
    p_lock_name TEXT,
    p_ttl_seconds INT DEFAULT 60
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_acquired BOOLEAN := FALSE;
    v_safe_ttl INT;
    v_safe_lock TEXT;
BEGIN
    v_safe_lock := substr(trim(coalesce(p_lock_name, 'default_lock')), 1, 128);
    v_safe_ttl := greatest(1, least(86400, coalesce(p_ttl_seconds, 60)));

    INSERT INTO public.processing_locks (lock_name, locked_until)
    VALUES (v_safe_lock, now() + (v_safe_ttl || ' seconds')::interval)
    ON CONFLICT (lock_name) DO UPDATE
    SET locked_until = now() + (v_safe_ttl || ' seconds')::interval
    WHERE processing_locks.locked_until <= now()
    RETURNING true INTO v_acquired;

    RETURN COALESCE(v_acquired, false);
END;
$$;

-- Harden release_distributed_lock
CREATE OR REPLACE FUNCTION public.release_distributed_lock(
    p_lock_name TEXT
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    UPDATE public.processing_locks
    SET locked_until = '1970-01-01 00:00:00+00'
    WHERE lock_name = substr(trim(coalesce(p_lock_name, '')), 1, 128);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.try_acquire_distributed_lock(TEXT, INT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.release_distributed_lock(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.try_acquire_distributed_lock(TEXT, INT) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.release_distributed_lock(TEXT) TO authenticated, service_role;


-- ------------------------------------------------------------------------------
-- 4. LAYER 2: AUDIT LOG IMMUTABILITY & DEDICATED SECURITY AUDIT VAULT
-- ------------------------------------------------------------------------------

-- 4a. Close AUD-01: Add immutable append-only trigger to audit_log
CREATE OR REPLACE FUNCTION public.trg_block_audit_log_tampering()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'Audit log entries are tamper-resistant and immutable. UPDATE or DELETE operations are strictly prohibited.';
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_log_immutability ON public.audit_log;
CREATE TRIGGER trg_audit_log_immutability
    BEFORE UPDATE OR DELETE ON public.audit_log
    FOR EACH ROW EXECUTE FUNCTION public.trg_block_audit_log_tampering();

-- 4b. Close AUD-02 & AUD-03: Create tamper-resistant surviving Security Audit Vault
CREATE TABLE IF NOT EXISTS public.workspace_security_audit_vault (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    actor_id UUID,
    actor_email TEXT,
    event_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_security_vault_ws 
    ON public.workspace_security_audit_vault(workspace_id, created_at DESC);

ALTER TABLE public.workspace_security_audit_vault ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS security_audit_vault_select ON public.workspace_security_audit_vault;
CREATE POLICY security_audit_vault_select ON public.workspace_security_audit_vault
    FOR SELECT USING (
        public.is_workspace_admin_or_owner(workspace_id, auth.uid())
    );

DROP TRIGGER IF EXISTS trg_security_vault_immutability ON public.workspace_security_audit_vault;
CREATE TRIGGER trg_security_vault_immutability
    BEFORE UPDATE OR DELETE ON public.workspace_security_audit_vault
    FOR EACH ROW EXECUTE FUNCTION public.trg_block_audit_log_tampering();

-- 4c. Workspace Deletion Tombstone Trigger (Guarantees audit survival on purge)
CREATE OR REPLACE FUNCTION public.trg_workspace_deletion_tombstone()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_actor_email TEXT;
BEGIN
    SELECT email INTO v_actor_email FROM auth.users WHERE id = auth.uid();
    
    INSERT INTO public.workspace_security_audit_vault (
        workspace_id,
        actor_id,
        actor_email,
        event_type,
        target_type,
        target_id,
        details
    ) VALUES (
        OLD.id,
        auth.uid(),
        v_actor_email,
        'workspace.permanently_deleted',
        'workspace',
        OLD.id::text,
        jsonb_build_object(
            'workspace_name', OLD.name,
            'owner_id', OLD.owner_id,
            'tier', OLD.tier,
            'credits_at_deletion', OLD.data_cleaning_credits,
            'deleted_at', now()
        )
    );
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_workspace_audit_tombstone ON public.workspaces;
CREATE TRIGGER trg_workspace_audit_tombstone
    BEFORE DELETE ON public.workspaces
    FOR EACH ROW EXECUTE FUNCTION public.trg_workspace_deletion_tombstone();

COMMIT;
