-- ==============================================================================
-- MIGRATION: 066_credit_system_core
-- PARANOIA FRAMEWORK: Layer 0 & Layer 1
-- Adds atomic credit system to prevent double-spending and infinite consumption
-- ==============================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- 0. Ensure the core credit balance column actually exists
-- ---------------------------------------------------------------------
ALTER TABLE public.workspaces 
ADD COLUMN IF NOT EXISTS data_cleaning_credits INT NOT NULL DEFAULT 0;

-- ---------------------------------------------------------------------
-- A. credit_deductions table
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.credit_deductions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    action_type       TEXT NOT NULL,
    amount            INT NOT NULL,
    balance_after     INT NOT NULL,
    idempotency_key   TEXT UNIQUE NOT NULL,
    metadata          JSONB DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS credit_deductions_workspace_created_idx ON public.credit_deductions(workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS credit_deductions_workspace_action_idx ON public.credit_deductions(workspace_id, action_type);
-- Unique constraint implicitly creates an index on idempotency_key

ALTER TABLE public.credit_deductions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view their own workspace credit deductions" ON public.credit_deductions;
CREATE POLICY "Users can view their own workspace credit deductions"
    ON public.credit_deductions FOR SELECT
    USING (workspace_id IN (SELECT public.my_workspace_ids()));

COMMENT ON COLUMN public.credit_deductions.amount IS 'The number of credits deducted for this action.';
COMMENT ON COLUMN public.credit_deductions.balance_after IS 'The remaining credit balance immediately after this deduction.';
COMMENT ON COLUMN public.credit_deductions.idempotency_key IS 'Unique key to prevent duplicate processing of the same action.';

-- ---------------------------------------------------------------------
-- B. credit_action_costs table
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.credit_action_costs (
    action_type   TEXT PRIMARY KEY,
    credits       INT NOT NULL,
    description   TEXT,
    category      TEXT NOT NULL DEFAULT 'general',
    is_active     BOOLEAN NOT NULL DEFAULT true,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.credit_action_costs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Anyone can view active credit costs" ON public.credit_action_costs;
CREATE POLICY "Anyone can view active credit costs"
    ON public.credit_action_costs FOR SELECT
    USING (true);

INSERT INTO public.credit_action_costs (action_type, credits, category, description) VALUES
('ai_reply_draft', 5, 'ai', 'AI Reply Draft'),
('ai_intent_classify', 2, 'ai', 'AI Intent Classification'),
('ai_copywriting', 1, 'ai', 'AI Copywriting per lead'),
('ai_coaching', 1, 'ai', 'AI Coaching'),
('ai_scoring', 1, 'ai', 'AI Scoring'),
('ai_funnel_analysis', 3, 'ai', 'AI Funnel Analysis'),
('rag_embed', 2, 'ai', 'RAG Embedding per document'),
('apollo_enrich', 5, 'enrichment', 'Apollo Enrichment per lead'),
('clearbit_tech_stack', 4, 'enrichment', 'Clearbit Tech Stack'),
('crunchbase_funding', 3, 'enrichment', 'Crunchbase Funding'),
('zerobounce_verify', 1, 'enrichment', 'ZeroBounce Verify'),
('apify_scrape', 50, 'enrichment', 'Apify Scrape per run'),
('sendgrid_email', 1, 'email', 'SendGrid Email'),
('data_hygiene', 1, 'general', 'Data Hygiene per 100 leads')
ON CONFLICT (action_type) DO UPDATE SET 
    credits = EXCLUDED.credits,
    category = EXCLUDED.category,
    description = EXCLUDED.description;

-- ---------------------------------------------------------------------
-- C. deduct_credits_safely RPC
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.deduct_credits_safely(
    p_workspace_id    UUID,
    p_amount          INT,
    p_action_type     TEXT,
    p_idempotency_key TEXT,
    p_metadata        JSONB DEFAULT '{}'::jsonb
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_actual_cost INT;
    v_current_balance INT;
    v_new_balance INT;
    v_already_processed BOOLEAN;
BEGIN
    -- LAYER 1 PARANOIA: Lock the workspace FIRST to serialize all requests
    -- If we check idempotency before locking, two concurrent requests can both pass the check
    -- and hit a Unique Violation crash on the insert.
    SELECT data_cleaning_credits INTO v_current_balance
    FROM public.workspaces
    WHERE id = p_workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', 0,
            'reason', 'workspace_not_found'
        );
    END IF;
    
    v_current_balance := COALESCE(v_current_balance, 0);

    -- Now that we hold the lock, check idempotency (100% race-condition free)
    SELECT EXISTS (
        SELECT 1 FROM public.credit_deductions 
        WHERE idempotency_key = p_idempotency_key
    ) INTO v_already_processed;

    IF v_already_processed THEN
        SELECT balance_after INTO v_new_balance FROM public.credit_deductions WHERE idempotency_key = p_idempotency_key;
        RETURN jsonb_build_object(
            'success', true,
            'balance', v_new_balance,
            'reason', 'already_processed'
        );
    END IF;

    -- Look up the credit cost if amount is 0 (dynamic lookup)
    IF p_amount = 0 THEN
        SELECT credits INTO v_actual_cost
        FROM public.credit_action_costs
        WHERE action_type = p_action_type AND is_active = true;
        
        v_actual_cost := COALESCE(v_actual_cost, 0);
    ELSE
        v_actual_cost := p_amount;
    END IF;

    -- Check balance (allow overdraft down to -500 for UX grace period)
    v_new_balance := v_current_balance - v_actual_cost;
    IF v_new_balance < -500 THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', v_current_balance,
            'reason', 'insufficient_credits'
        );
    END IF;

    -- Deduct atomically
    UPDATE public.workspaces
    SET data_cleaning_credits = v_new_balance
    WHERE id = p_workspace_id;

    -- Record the deduction log
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

COMMENT ON FUNCTION public.deduct_credits_safely IS 'Atomically deducts credits from a workspace with proper FOR UPDATE locking prior to idempotency checks.';

-- ---------------------------------------------------------------------
-- D. get_credit_balance RPC
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_credit_balance(
    p_workspace_id UUID
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_balance INT;
    v_tier TEXT;
    v_usage JSONB;
BEGIN
    SELECT data_cleaning_credits, tier::TEXT INTO v_balance, v_tier
    FROM public.workspaces WHERE id = p_workspace_id;
    
    v_balance := COALESCE(v_balance, 0);

    SELECT COALESCE(jsonb_object_agg(action_type, total_amount), '{}'::jsonb) INTO v_usage
    FROM (
        SELECT action_type, SUM(amount) as total_amount
        FROM public.credit_deductions
        WHERE workspace_id = p_workspace_id
          AND date_trunc('month', created_at) = date_trunc('month', NOW())
        GROUP BY action_type
    ) sub;

    RETURN jsonb_build_object(
        'balance', v_balance,
        'tier', COALESCE(v_tier, 'free'),
        'usage_this_month', v_usage
    );
END;
$$;

-- ---------------------------------------------------------------------
-- E. get_credit_cost RPC
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.get_credit_cost(
    p_action_type TEXT
) RETURNS INT
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_cost INT;
BEGIN
    SELECT credits INTO v_cost FROM public.credit_action_costs WHERE action_type = p_action_type;
    RETURN COALESCE(v_cost, 0);
END;
$$;

-- ---------------------------------------------------------------------
-- F. Seed existing workspaces with 500 free credits
-- ---------------------------------------------------------------------
UPDATE public.workspaces 
SET data_cleaning_credits = GREATEST(COALESCE(data_cleaning_credits, 0), 500);

-- ---------------------------------------------------------------------
-- G. Trigger to seed NEW workspaces (Cleaned: BEFORE INSERT instead of AFTER)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.trg_seed_workspace_credits_before()
RETURNS trigger AS $$
BEGIN
    NEW.data_cleaning_credits := GREATEST(COALESCE(NEW.data_cleaning_credits, 0), 500);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_workspace_created_seed_credits ON public.workspaces;
CREATE TRIGGER on_workspace_created_seed_credits
BEFORE INSERT ON public.workspaces
FOR EACH ROW
EXECUTE FUNCTION public.trg_seed_workspace_credits_before();

-- ---------------------------------------------------------------------
-- H. credit_usage_summary view
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW public.credit_usage_summary AS
SELECT 
    workspace_id,
    date_trunc('month', created_at) AS month,
    action_type,
    SUM(amount) AS total_credits_used,
    COUNT(id) AS action_count
FROM public.credit_deductions
GROUP BY workspace_id, date_trunc('month', created_at), action_type;

COMMIT;
