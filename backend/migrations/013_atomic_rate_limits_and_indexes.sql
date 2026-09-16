BEGIN;

-- 1. Create the missing index for worker scheduler lookups
CREATE INDEX IF NOT EXISTS idx_accounts_workspace_status ON public.accounts(workspace_id, status);

-- 2. Fix try_consume_daily_action to be strictly atomic and immune to race conditions
CREATE OR REPLACE FUNCTION public.try_consume_daily_action(
    p_account_id  uuid,
    p_action_type text
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_limit integer;
    v_new_count integer;
BEGIN
    v_limit := public.get_account_action_limit(p_account_id, p_action_type);
    
    -- Step 1: Ensure the daily row exists (starts at 0)
    INSERT INTO public.account_daily_action_counts (account_id, action_type, usage_date, count)
    VALUES (p_account_id, p_action_type, CURRENT_DATE, 0)
    ON CONFLICT (account_id, action_type, usage_date) DO NOTHING;

    -- Step 2: Atomically increment ONLY if it remains under the limit
    UPDATE public.account_daily_action_counts
    SET count = count + 1
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = CURRENT_DATE
      AND count < v_limit
    RETURNING count INTO v_new_count;

    -- Step 3: If v_new_count is NULL, the WHERE clause (count < limit) failed
    IF v_new_count IS NULL THEN
        RETURN false;
    END IF;

    RETURN true;
END;
$$;

COMMIT;
