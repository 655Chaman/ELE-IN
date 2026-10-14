-- Migration 095: Tier-Aware Atomic Credit Deduction RPC
-- Hardens deduct_credits_safely to strictly enforce tier-aware overdraft limits:
-- Free tier: Min allowed balance is 0 (zero overdraft).
-- Paid tiers (PRO, GROWTH, ENTERPRISE, AGENCY, UNLIMITED, SCALE): Min allowed balance is -500.

CREATE OR REPLACE FUNCTION public.deduct_credits_safely(
    p_workspace_id UUID,
    p_amount INT,
    p_action_type TEXT,
    p_idempotency_key TEXT,
    p_metadata JSONB DEFAULT '{}'::jsonb
) RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE
    v_current_balance INT;
    v_tier TEXT;
    v_min_balance INT := 0;
    v_actual_cost INT;
    v_new_balance INT;
    v_already_processed BOOLEAN;
BEGIN
    -- LAYER 1 PARANOIA: Row-level lock on public.workspaces first to serialize all requests
    SELECT data_cleaning_credits, COALESCE(tier::TEXT, 'FREE')
    INTO v_current_balance, v_tier
    FROM public.workspaces
    WHERE id = p_workspace_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', 0,
            'reason', 'workspace_not_found',
            'error', 'workspace_not_found'
        );
    END IF;

    v_current_balance := COALESCE(v_current_balance, 0);
    v_tier := UPPER(COALESCE(v_tier, 'FREE'));

    -- Determine tier-aware overdraft floor
    IF v_tier IN ('PRO', 'GROWTH', 'ENTERPRISE', 'AGENCY', 'UNLIMITED', 'SCALE') THEN
        v_min_balance := -500;
    ELSE
        v_min_balance := 0;
    END IF;

    -- Check idempotency under lock
    SELECT EXISTS (
        SELECT 1 FROM public.credit_deductions 
        WHERE idempotency_key = p_idempotency_key
    ) INTO v_already_processed;

    IF v_already_processed THEN
        SELECT balance_after INTO v_new_balance
        FROM public.credit_deductions
        WHERE idempotency_key = p_idempotency_key;

        RETURN jsonb_build_object(
            'success', true,
            'balance', v_new_balance,
            'reason', 'already_processed',
            'already_processed', true
        );
    END IF;

    -- Determine actual cost
    IF p_amount = 0 THEN
        SELECT credits INTO v_actual_cost
        FROM public.credit_action_costs
        WHERE action_type = p_action_type AND is_active = true;

        v_actual_cost := COALESCE(v_actual_cost, 0);
    ELSE
        v_actual_cost := p_amount;
    END IF;

    -- Check overdraft boundary
    v_new_balance := v_current_balance - v_actual_cost;
    IF v_new_balance < v_min_balance THEN
        RETURN jsonb_build_object(
            'success', false,
            'balance', v_current_balance,
            'reason', 'insufficient_credits',
            'error', 'insufficient_credits',
            'shortfall', (v_min_balance - v_new_balance),
            'min_allowed', v_min_balance
        );
    END IF;

    -- Deduct atomically
    UPDATE public.workspaces
    SET data_cleaning_credits = v_new_balance,
        updated_at = NOW()
    WHERE id = p_workspace_id;

    -- Record deduction log
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

COMMENT ON FUNCTION public.deduct_credits_safely IS 'Atomically deducts credits with FOR UPDATE locking and tier-aware overdraft floor enforcement (0 for Free, -500 for Paid).';
