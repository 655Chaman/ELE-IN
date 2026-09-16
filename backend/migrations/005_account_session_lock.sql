BEGIN;

-- Add a session lock column to accounts
-- NULL or past timestamp = available, future timestamp = locked by a worker
ALTER TABLE public.accounts 
    ADD COLUMN IF NOT EXISTS session_locked_until TIMESTAMPTZ DEFAULT NULL;

CREATE OR REPLACE FUNCTION public.try_acquire_account_lock(
    p_account_id uuid,
    p_lock_until timestamptz,
    p_now timestamptz
) RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows integer;
BEGIN
    UPDATE public.accounts
    SET session_locked_until = p_lock_until
    WHERE id = p_account_id
      AND (session_locked_until IS NULL OR session_locked_until < p_now);
    
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows > 0;
END;
$$;

COMMIT;
