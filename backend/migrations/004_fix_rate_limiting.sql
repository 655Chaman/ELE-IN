BEGIN;

-- Replace peek_daily_action_headroom to return INTEGER instead of BOOLEAN
-- and use the correct account-specific limits and warmup logic.

CREATE OR REPLACE FUNCTION public.get_account_action_limit(
    p_account_id uuid,
    p_action_type text
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_account       public.accounts%ROWTYPE;
    v_base_limit    integer;
    v_conn_limit    integer;
    v_msg_limit     integer;
    v_max_actions   integer;
    v_current_actions integer;
    v_days_active   integer;
BEGIN
    SELECT * INTO v_account FROM public.accounts WHERE id = p_account_id;
    IF NOT FOUND THEN RETURN 0; END IF;

    v_conn_limit := COALESCE(v_account.daily_connection_limit, 20);
    v_msg_limit  := COALESCE(v_account.daily_message_limit, 40);
    v_max_actions := v_conn_limit + v_msg_limit;

    -- Determine base limit for the requested action type
    IF p_action_type = 'connection_request' THEN
        v_base_limit := v_conn_limit;
    ELSIF p_action_type = 'message' OR p_action_type = 'inmail' THEN
        v_base_limit := v_msg_limit;
    ELSE
        -- Fallback to global config for things like view_profile
        SELECT daily_limit INTO v_base_limit FROM public.action_type_limits WHERE action_type = p_action_type;
        v_base_limit := COALESCE(v_base_limit, 20);
    END IF;

    -- Apply Warmup logic exactly matching the UI
    IF v_account.is_warmup AND v_account.warmup_start_date IS NOT NULL THEN
        v_days_active := GREATEST(0, CURRENT_DATE - v_account.warmup_start_date::date);
        -- Start at 15 actions, +5 every 3 days. Max out at their configured limits.
        v_current_actions := LEAST(15 + (v_days_active / 3) * 5, v_max_actions);
        
        IF p_action_type = 'connection_request' THEN
            v_base_limit := floor((v_current_actions::float * v_conn_limit) / v_max_actions)::integer;
        ELSIF p_action_type = 'message' OR p_action_type = 'inmail' THEN
            v_base_limit := v_current_actions - floor((v_current_actions::float * v_conn_limit) / v_max_actions)::integer;
        END IF;
    END IF;

    RETURN v_base_limit;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_action_headroom(
    p_account_id uuid,
    p_action_type text
) RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_limit integer;
    v_count integer;
BEGIN
    v_limit := public.get_account_action_limit(p_account_id, p_action_type);
    
    SELECT COALESCE(count, 0) INTO v_count
    FROM public.account_daily_action_counts
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = CURRENT_DATE;
      
    RETURN GREATEST(0, v_limit - COALESCE(v_count, 0));
END;
$$;

-- Fix try_consume_daily_action to use the new logic
CREATE OR REPLACE FUNCTION public.try_consume_daily_action(
    p_account_id  uuid,
    p_action_type text
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_limit integer;
    v_count integer;
BEGIN
    v_limit := public.get_account_action_limit(p_account_id, p_action_type);
    
    SELECT COALESCE(count, 0) INTO v_count
    FROM public.account_daily_action_counts
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND usage_date = CURRENT_DATE;
      
    IF COALESCE(v_count, 0) + 1 > v_limit THEN
        RETURN false;
    END IF;

    INSERT INTO public.account_daily_action_counts
        (account_id, action_type, usage_date, count)
    VALUES
        (p_account_id, p_action_type, CURRENT_DATE, 1)
    ON CONFLICT (account_id, action_type, usage_date)
    DO UPDATE SET count = public.account_daily_action_counts.count + 1;

    RETURN true;
END;
$$;

COMMIT;
