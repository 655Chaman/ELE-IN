-- Migration 071: Compensating reversal for reserved daily action counts
CREATE OR REPLACE FUNCTION public.release_consumed_daily_action(
    p_account_id  uuid,
    p_action_type text
) RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE public.account_daily_action_counts
    SET count = GREATEST(0, count - 1)
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = CURRENT_DATE;
    RETURN true;
END;
$$;
