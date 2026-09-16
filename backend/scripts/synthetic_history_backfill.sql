BEGIN;

DO $$
DECLARE
    acc RECORD;
    v_date date;
    v_days_active int;
    v_conn_limit int;
    v_msg_limit int;
    v_conns_sent int;
    v_msgs_sent int;
BEGIN
    -- Loop through all currently active accounts
    FOR acc IN SELECT id, created_at, is_warmup, warmup_start_date FROM public.accounts WHERE status = 'ACTIVE'
    LOOP
        -- Start from the day they were created (or warmup started)
        v_date := COALESCE(acc.warmup_start_date, acc.created_at)::date;
        
        -- Generate rows up until today
        WHILE v_date <= CURRENT_DATE LOOP
            v_days_active := GREATEST(0, v_date - COALESCE(acc.warmup_start_date, acc.created_at)::date);
            
            IF acc.is_warmup THEN
                v_conn_limit := 15 + (v_days_active / 3) * 5;
                v_msg_limit := 15 + (v_days_active / 3) * 5;
            ELSE
                v_conn_limit := 40;
                v_msg_limit := 40;
            END IF;

            -- Simulate a realistic workload: Sending ~80% to 95% of their daily limit
            v_conns_sent := (v_conn_limit * (0.8 + (random() * 0.15)))::int;
            v_msgs_sent := (v_msg_limit * (0.8 + (random() * 0.15)))::int;

            -- Insert simulated connection history
            INSERT INTO public.account_daily_action_counts (account_id, action_type, usage_date, count)
            VALUES (acc.id, 'connection_request', v_date, v_conns_sent)
            ON CONFLICT (account_id, action_type, usage_date) DO NOTHING;

            -- Insert simulated message history
            INSERT INTO public.account_daily_action_counts (account_id, action_type, usage_date, count)
            VALUES (acc.id, 'message', v_date, v_msgs_sent)
            ON CONFLICT (account_id, action_type, usage_date) DO NOTHING;

            -- Move to the next day
            v_date := v_date + INTERVAL '1 day';
        END LOOP;
    END LOOP;
END $$;

COMMIT;
