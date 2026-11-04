-- ==============================================================================
-- MIGRATION: 999_fix_get_account_action_limit_and_partitions.sql
-- Fixes:
-- 1. get_account_action_limit PL/pgSQL variable reference bug (v_warmup_start_date)
-- 2. campaign_events DEFAULT partition to prevent range partition errors
-- 3. accounts missing columns (execution_channel, timezone)
-- ==============================================================================

BEGIN;

-- 1. Fix get_account_action_limit function
CREATE OR REPLACE FUNCTION public.get_account_action_limit(p_account_id uuid, p_action_type text)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_override_limit integer;
    v_global_limit integer;
    v_is_warmup boolean;
    v_warmup_start_date timestamptz;
    v_warmup_limit integer;
BEGIN
    SELECT custom_limit INTO v_override_limit
    FROM public.account_limit_overrides
    WHERE account_id = p_account_id
      AND action_type = p_action_type
      AND (expires_at IS NULL OR expires_at > now());

    IF v_override_limit IS NOT NULL THEN
        RETURN v_override_limit;
    END IF;

    SELECT daily_limit INTO v_global_limit
    FROM public.action_type_limits
    WHERE action_type = p_action_type;

    IF v_global_limit IS NULL THEN
        RETURN 20;
    END IF;

    SELECT is_warmup, warmup_start_date INTO v_is_warmup, v_warmup_start_date
    FROM public.accounts
    WHERE id = p_account_id;

    IF v_is_warmup = true AND v_warmup_start_date IS NOT NULL AND p_action_type IN ('connection_request', 'message', 'inmail') THEN
        v_warmup_limit := 15 + ( GREATEST(0, (CURRENT_DATE - v_warmup_start_date::date)) / 3 ) * 5;
        RETURN LEAST(v_warmup_limit, v_global_limit);
    END IF;

    RETURN v_global_limit;
END;
$$;

GRANT EXECUTE ON FUNCTION public.get_account_action_limit(uuid, text) TO authenticated, service_role;

-- 2. Add missing columns to accounts
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS execution_channel VARCHAR(20) DEFAULT 'CLOUD';
ALTER TABLE public.accounts ADD COLUMN IF NOT EXISTS timezone TEXT DEFAULT 'UTC';

-- 3. Ensure campaign_events has default partition if partitioned
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_partitioned_table pt
        JOIN pg_class c ON pt.partrelid = c.oid
        WHERE c.relname = 'campaign_events'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_inherits i
            JOIN pg_class c ON i.inhrelid = c.oid
            WHERE c.relname = 'campaign_events_default'
        ) THEN
            EXECUTE 'CREATE TABLE IF NOT EXISTS public.campaign_events_default PARTITION OF public.campaign_events DEFAULT;';
        END IF;
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Partition check notice: %', SQLERRM;
END $$;

COMMIT;
