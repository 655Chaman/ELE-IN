BEGIN;

CREATE OR REPLACE FUNCTION public.try_consume_daily_action(
    p_account_id  uuid,
    p_action_type text
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_limit integer;
    v_rows_updated integer;
BEGIN
    v_limit := public.get_account_action_limit(p_account_id, p_action_type);

    -- Attempt an atomic upsert that only succeeds if count < limit.
    -- The WHERE clause on DO UPDATE makes this a single atomic conditional increment.
    -- If the row doesn't exist yet, the INSERT sets count=1 (always allowed if limit >= 1).
    -- If the row exists and count >= limit, DO UPDATE is skipped, 0 rows are affected.
    WITH upsert AS (
        INSERT INTO public.account_daily_action_counts
            (account_id, action_type, usage_date, count)
        VALUES
            (p_account_id, p_action_type, CURRENT_DATE, 1)
        ON CONFLICT (account_id, action_type, usage_date)
        DO UPDATE
            SET count = public.account_daily_action_counts.count + 1
            WHERE public.account_daily_action_counts.count < v_limit
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_rows_updated FROM upsert;

    RETURN v_rows_updated > 0;
END;
$$;

COMMIT;
