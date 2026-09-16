-- 1. Create the new join table for Campaigns <-> Accounts
CREATE TABLE IF NOT EXISTS campaign_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(campaign_id, account_id)
);

-- 2. Migrate existing data from JSON to the new table
DO $$
DECLARE
    camp RECORD;
    acc_id UUID;
BEGIN
    FOR camp IN SELECT id, sender_account_ids_json FROM campaigns WHERE sender_account_ids_json IS NOT NULL AND sender_account_ids_json != 'null'::jsonb LOOP
        -- Extract JSON array elements and cast to text, then UUID
        FOR acc_id IN SELECT jsonb_array_elements_text(camp.sender_account_ids_json::jsonb)::UUID LOOP
            BEGIN
                INSERT INTO campaign_accounts (campaign_id, account_id)
                VALUES (camp.id, acc_id)
                ON CONFLICT DO NOTHING;
            EXCEPTION WHEN OTHERS THEN
                -- If account doesn't exist (violates FK), ignore it
                NULL;
            END;
        END LOOP;
    END LOOP;
END $$;

-- 3. Add UNIQUE constraint to prevent duplicate outreach
-- First, deduplicate lead_states if there are any violators
DELETE FROM lead_states
WHERE id IN (
    SELECT id FROM (
        SELECT id, row_number() OVER (PARTITION BY campaign_id, opportunity_id ORDER BY created_at DESC) as rnum
        FROM lead_states
    ) t WHERE t.rnum > 1
);

ALTER TABLE lead_states ADD CONSTRAINT lead_states_campaign_opp_unique UNIQUE (campaign_id, opportunity_id);

-- 4. Add partial index for the scheduler
CREATE INDEX IF NOT EXISTS idx_lead_states_pending_next_run
ON lead_states (next_run_at ASC)
WHERE status = 'pending';
