-- Migration 111: Campaign Lead Sender Locks & DAG State Engine Hardening
-- Pillar 3: Multi-Sender Pod Balancing, Thread Affinity, & State Engine Hardening

CREATE TABLE IF NOT EXISTS campaign_lead_sender_locks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id TEXT NOT NULL,
    campaign_id TEXT,
    lead_id TEXT NOT NULL,
    account_id TEXT,
    inbox_id TEXT,
    locked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_campaign_lead_sender UNIQUE (workspace_id, campaign_id, lead_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_lead_sender_locks_lead 
    ON campaign_lead_sender_locks(workspace_id, lead_id);

CREATE INDEX IF NOT EXISTS idx_campaign_lead_sender_locks_account 
    ON campaign_lead_sender_locks(account_id);

CREATE INDEX IF NOT EXISTS idx_campaign_lead_sender_locks_inbox 
    ON campaign_lead_sender_locks(inbox_id);

-- Ensure RLS is active
ALTER TABLE campaign_lead_sender_locks ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'campaign_lead_sender_locks' 
        AND policyname = 'campaign_lead_sender_locks_workspace_isolation'
    ) THEN
        CREATE POLICY campaign_lead_sender_locks_workspace_isolation ON campaign_lead_sender_locks
            FOR ALL
            USING (workspace_id = current_setting('app.current_workspace_id', true) OR current_setting('app.current_workspace_id', true) IS NULL);
    END IF;
END $$;
