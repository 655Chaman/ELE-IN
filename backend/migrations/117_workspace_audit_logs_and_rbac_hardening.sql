-- ==============================================================================
-- MIGRATION: 117_workspace_audit_logs_and_rbac_hardening.sql
-- SUBSYSTEM: Core Security, Enterprise RBAC & Tamper-Evident Audit Trail (Phase T)
-- ARCHITECTURE: Three-Layer Logic Architecture (Paranoia Framework)
-- ==============================================================================

BEGIN;

-- ------------------------------------------------------------------------------
-- 1. LAYER 0: TABLE DEFINITION & RELATIONAL FOUNDATION
-- ------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.workspace_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL DEFAULT 'unknown',
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'SUCCESS',
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address VARCHAR(45) NOT NULL DEFAULT 'internal',
    user_agent TEXT NOT NULL DEFAULT 'internal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- ------------------------------------------------------------------------------
-- 2. LAYER 1: PERFORMANCE INDEXING & CONCURRENCY OPTIMIZATION
-- ------------------------------------------------------------------------------

-- High-performance query indexing for workspace audit dashboards
CREATE INDEX IF NOT EXISTS idx_workspace_audit_logs_ws_created
    ON public.workspace_audit_logs (workspace_id, created_at DESC);

-- Actor activity tracking index
CREATE INDEX IF NOT EXISTS idx_workspace_audit_logs_actor_created
    ON public.workspace_audit_logs (actor_id, created_at DESC);

-- High-severity / action filter index
CREATE INDEX IF NOT EXISTS idx_workspace_audit_logs_action_status
    ON public.workspace_audit_logs (workspace_id, action, status);

-- ------------------------------------------------------------------------------
-- 3. LAYER 1 & 2: CONSTRAINTS & DATA INTEGRITY
-- ------------------------------------------------------------------------------

-- Status integrity constraint
ALTER TABLE public.workspace_audit_logs
    DROP CONSTRAINT IF EXISTS chk_audit_status,
    ADD CONSTRAINT chk_audit_status
        CHECK (status IN ('SUCCESS', 'DENIED', 'FAILED', 'WARNING', 'ABORTED'));

-- Role bounds constraint
ALTER TABLE public.workspace_audit_logs
    DROP CONSTRAINT IF EXISTS chk_audit_role,
    ADD CONSTRAINT chk_audit_role
        CHECK (actor_role IN ('owner', 'admin', 'manager', 'sender', 'analyst', 'system', 'unknown'));

-- ------------------------------------------------------------------------------
-- 4. LAYER 2: IMMUTABILITY & TAMPER-RESISTANCE (ANTI-EXFILTRATION / ZERO-ALTERATION)
-- ------------------------------------------------------------------------------

-- Immutability trigger function to prevent altering historical audit records
CREATE OR REPLACE FUNCTION public.fn_prevent_audit_log_tampering()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'Audit log entries are strictly immutable and cannot be updated.';
    ELSIF TG_OP = 'DELETE' THEN
        -- Allow cascade deletions only when parent workspace is explicitly removed
        IF current_setting('elein.allow_workspace_cascade', true) IS NULL THEN
            RAISE EXCEPTION 'Audit log entries cannot be manually deleted.';
        END IF;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_audit_log_tampering ON public.workspace_audit_logs;
CREATE TRIGGER trg_prevent_audit_log_tampering
    BEFORE UPDATE OR DELETE ON public.workspace_audit_logs
    FOR EACH ROW
    EXECUTE FUNCTION public.fn_prevent_audit_log_tampering();

-- ------------------------------------------------------------------------------
-- 5. LAYER 1 & 2: ROW-LEVEL SECURITY (RLS) POLICIES
-- ------------------------------------------------------------------------------

ALTER TABLE public.workspace_audit_logs ENABLE ROW LEVEL SECURITY;

-- Select Policy: Only workspace Owners and Admins can view audit logs
DROP POLICY IF EXISTS "Admins and Owners can view workspace audit logs" ON public.workspace_audit_logs;
CREATE POLICY "Admins and Owners can view workspace audit logs"
    ON public.workspace_audit_logs
    FOR SELECT
    USING (
        workspace_id IN (
            SELECT wm.workspace_id
            FROM public.workspace_members wm
            WHERE wm.user_id = auth.uid()::text
              AND wm.role IN ('owner', 'admin')
        )
        OR
        workspace_id IN (
            SELECT w.id
            FROM public.workspaces w
            WHERE w.owner_id = auth.uid()::text
        )
    );

-- Insert Policy: Authenticated users can insert audit logs for their workspaces
DROP POLICY IF EXISTS "Members can insert workspace audit logs" ON public.workspace_audit_logs;
CREATE POLICY "Members can insert workspace audit logs"
    ON public.workspace_audit_logs
    FOR INSERT
    WITH CHECK (
        workspace_id IN (
            SELECT wm.workspace_id
            FROM public.workspace_members wm
            WHERE wm.user_id = auth.uid()::text
        )
        OR
        workspace_id IN (
            SELECT w.id
            FROM public.workspaces w
            WHERE w.owner_id = auth.uid()::text
        )
    );

COMMIT;
