BEGIN;

-- Add a hard ceiling inside the limit function so that no matter what
-- is stored in the database, it cannot exceed the global safety limits.

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

    -- SAFETY CEILINGS: Hard cap the user-configured limits to prevent instant bans.
    -- Never allow more than 30 connections/day or 60 messages/day, 
    -- regardless of what the user set.
    v_conn_limit := LEAST(COALESCE(v_account.daily_connection_limit, 20), 30);
    v_msg_limit  := LEAST(COALESCE(v_account.daily_message_limit, 40), 60);
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

-- Also update existing rows in the DB to reflect the new truth so the UI doesn't show 500
UPDATE public.accounts
SET 
    daily_connection_limit = LEAST(daily_connection_limit, 30),
    daily_message_limit = LEAST(daily_message_limit, 60);

COMMIT;
