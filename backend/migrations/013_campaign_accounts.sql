-- LAYER 0: FOUNDATIONAL MIGRATION
CREATE TABLE IF NOT EXISTS campaign_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(campaign_id, account_id)
);

-- INDEXES FOR FAST LOOKUPS (The hottest queries)
CREATE INDEX IF NOT EXISTS idx_campaign_accounts_campaign_id ON campaign_accounts(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_accounts_account_id ON campaign_accounts(account_id);

-- UNIQUE CONSTRAINT (To prevent duplicate outreach)
ALTER TABLE lead_states DROP CONSTRAINT IF EXISTS lead_states_campaign_opp_unique;
ALTER TABLE lead_states ADD CONSTRAINT lead_states_campaign_opp_unique UNIQUE (campaign_id, opportunity_id);

-- PARTIAL INDEX (For the Orchestrator's hottest query)
CREATE INDEX IF NOT EXISTS idx_lead_states_pending_next_run 
ON lead_states (next_run_at ASC) 
WHERE status = 'pending';

-- LAYER 1: ENVIRONMENTAL PARANOIA (Idempotent Data Migration)
-- We safely copy existing JSON arrays into the relational table without breaking anything.
DO $$
DECLARE
    camp RECORD;
    acc_id UUID;
BEGIN
    FOR camp IN SELECT id, sender_account_ids_json FROM campaigns WHERE sender_account_ids_json IS NOT NULL AND sender_account_ids_json != 'null'::jsonb LOOP
        FOR acc_id IN SELECT jsonb_array_elements_text(camp.sender_account_ids_json::jsonb)::UUID LOOP
            BEGIN
                INSERT INTO campaign_accounts (campaign_id, account_id)
                VALUES (camp.id, acc_id)
                ON CONFLICT DO NOTHING;
            EXCEPTION WHEN OTHERS THEN
                -- If the account was deleted (ghost account), Postgres drops it here safely.
                NULL;
            END;
        END LOOP;
    END LOOP;
END $$;
