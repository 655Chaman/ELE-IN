-- Migration 078: Sender Pod Load Balancing, Fleet Failover & Quarantine
-- Designed under the Three-Layer Logic Architecture (Paranoia Framework)

-- 1. Account Pod Quarantine & Eligibility Columns
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS quarantine_reason TEXT DEFAULT NULL;
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS is_pod_eligible BOOLEAN DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_accounts_quarantined_until ON public.accounts(quarantined_until);
CREATE INDEX IF NOT EXISTS idx_accounts_pod_eligible ON public.accounts(is_pod_eligible, status);

-- 2. Campaign Pod Load Balancing & Failover Settings
ALTER TABLE public.campaigns ADD COLUMN IF NOT EXISTS pod_dispatch_strategy TEXT DEFAULT 'CAPACITY_WEIGHTED';
ALTER TABLE public.campaigns ADD COLUMN IF NOT EXISTS pod_failover_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE public.campaigns ADD COLUMN IF NOT EXISTS pod_emergency_paused BOOLEAN DEFAULT FALSE;

-- 3. Campaign Accounts Custom Weighting
ALTER TABLE public.campaign_accounts ADD COLUMN IF NOT EXISTS weight INTEGER DEFAULT 100;
ALTER TABLE public.campaign_accounts ADD COLUMN IF NOT EXISTS is_primary BOOLEAN DEFAULT FALSE;

-- 4. Pod Audit Trail (Layer 1 Environmental & Layer 2 Human Error Auditing)
CREATE TABLE IF NOT EXISTS public.sender_pod_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES public.campaigns(id) ON DELETE SET NULL,
    account_id UUID REFERENCES public.accounts(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL, -- 'DISPATCH', 'FAILOVER', 'QUARANTINE', 'RELEASE', 'EMERGENCY_PAUSE', 'REBALANCE'
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pod_audit_workspace_created ON public.sender_pod_audit_logs(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pod_audit_campaign ON public.sender_pod_audit_logs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_pod_audit_account ON public.sender_pod_audit_logs(account_id);

-- Enable RLS on audit logs
ALTER TABLE public.sender_pod_audit_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS sender_pod_audit_isolation ON public.sender_pod_audit_logs;
CREATE POLICY sender_pod_audit_isolation ON public.sender_pod_audit_logs
    FOR ALL
    USING (workspace_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'workspace_id')::UUID)
    WITH CHECK (workspace_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'workspace_id')::UUID);
