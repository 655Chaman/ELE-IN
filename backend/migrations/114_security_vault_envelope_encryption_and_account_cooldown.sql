-- Migration 114: Security Vault Envelope Encryption, Audit Logging, & Account Rate Limit Cooldown
-- Pillar 7: Security Vault & Envelope Encryption Engine

CREATE TABLE IF NOT EXISTS workspace_deks (
    workspace_id TEXT PRIMARY KEY,
    wrapped_dek TEXT NOT NULL,
    key_version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rotated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS encryption_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    key_version INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'success',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_encryption_audit_ws_time 
    ON encryption_audit_log(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS account_rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    period_date DATE NOT NULL DEFAULT CURRENT_DATE,
    period_hour INT NOT NULL DEFAULT EXTRACT(HOUR FROM now())::INT,
    conn_requests_daily INT NOT NULL DEFAULT 0,
    messages_daily INT NOT NULL DEFAULT 0,
    conn_requests_hourly INT NOT NULL DEFAULT 0,
    messages_hourly INT NOT NULL DEFAULT 0,
    cooldown_until TIMESTAMPTZ,
    cooldown_reason TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_account_rate_period UNIQUE (account_id, period_date, period_hour)
);

CREATE INDEX IF NOT EXISTS idx_account_rate_limits_cooldown 
    ON account_rate_limits(account_id, cooldown_until)
    WHERE cooldown_until IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_account_rate_limits_ws 
    ON account_rate_limits(workspace_id);

-- Enable Row Level Security (RLS) across newly created tables
ALTER TABLE workspace_deks ENABLE ROW LEVEL SECURITY;
ALTER TABLE encryption_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_rate_limits ENABLE ROW LEVEL SECURITY;

-- Idempotent RLS policy creation
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'workspace_deks' AND policyname = 'workspace_deks_tenant_isolation'
    ) THEN
        CREATE POLICY workspace_deks_tenant_isolation ON workspace_deks
            FOR ALL
            USING (workspace_id IN (SELECT get_user_workspace_ids()))
            WITH CHECK (workspace_id IN (SELECT get_user_workspace_ids()));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'encryption_audit_log' AND policyname = 'encryption_audit_tenant_isolation'
    ) THEN
        CREATE POLICY encryption_audit_tenant_isolation ON encryption_audit_log
            FOR ALL
            USING (workspace_id IN (SELECT get_user_workspace_ids()))
            WITH CHECK (workspace_id IN (SELECT get_user_workspace_ids()));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'account_rate_limits' AND policyname = 'account_rate_limits_tenant_isolation'
    ) THEN
        CREATE POLICY account_rate_limits_tenant_isolation ON account_rate_limits
            FOR ALL
            USING (workspace_id IN (SELECT get_user_workspace_ids()))
            WITH CHECK (workspace_id IN (SELECT get_user_workspace_ids()));
    END IF;
END $$;
