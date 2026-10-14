-- Migration 072: Timezone-aware daily action consumption and reversal
CREATE OR REPLACE FUNCTION public.try_consume_daily_action(
    p_account_id  uuid,
    p_action_type text,
    p_usage_date  date DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_limit integer;
    v_new_count integer;
    v_date date;
BEGIN
    v_date := COALESCE(p_usage_date, CURRENT_DATE);
    v_limit := public.get_account_action_limit(p_account_id, p_action_type);
    
    -- Step 1: Ensure the daily row exists (starts at 0)
    INSERT INTO public.account_daily_action_counts (account_id, action_type, usage_date, count)
    VALUES (p_account_id, p_action_type, v_date, 0)
    ON CONFLICT (account_id, action_type, usage_date) DO NOTHING;

    -- Step 2: Atomically increment ONLY if it remains under the limit
    UPDATE public.account_daily_action_counts
    SET count = count + 1
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = v_date
      AND count < v_limit
    RETURNING count INTO v_new_count;

    -- Step 3: If v_new_count is NULL, the WHERE clause (count < limit) failed
    IF v_new_count IS NULL THEN
        RETURN false;
    END IF;

    RETURN true;
END;
$$;

CREATE OR REPLACE FUNCTION public.release_consumed_daily_action(
    p_account_id  uuid,
    p_action_type text,
    p_usage_date  date DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_date date;
BEGIN
    v_date := COALESCE(p_usage_date, CURRENT_DATE);
    UPDATE public.account_daily_action_counts
    SET count = GREATEST(0, count - 1)
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = v_date;
    RETURN true;
END;
$$;
