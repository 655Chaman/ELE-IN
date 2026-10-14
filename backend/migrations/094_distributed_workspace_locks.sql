-- ==============================================================================
-- MIGRATION: 094_distributed_workspace_locks
-- PARANOIA FRAMEWORK: Layer 0 & Layer 1
-- Adds atomic distributed workspace locks across multiple Uvicorn workers and pods
-- ==============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.processing_locks (
    lock_name TEXT PRIMARY KEY,
    locked_until TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01 00:00:00+00'
);

CREATE OR REPLACE FUNCTION public.try_acquire_distributed_lock(
    p_lock_name TEXT,
    p_ttl_seconds INT DEFAULT 60
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    v_acquired BOOLEAN := FALSE;
BEGIN
    INSERT INTO public.processing_locks (lock_name, locked_until)
    VALUES (p_lock_name, now() + (p_ttl_seconds || ' seconds')::interval)
    ON CONFLICT (lock_name) DO UPDATE
    SET locked_until = now() + (p_ttl_seconds || ' seconds')::interval
    WHERE processing_locks.locked_until <= now()
    RETURNING true INTO v_acquired;

    RETURN COALESCE(v_acquired, false);
END;
$$;

CREATE OR REPLACE FUNCTION public.release_distributed_lock(
    p_lock_name TEXT
) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE public.processing_locks
    SET locked_until = '1970-01-01 00:00:00+00'
    WHERE lock_name = p_lock_name;
END;
$$;

COMMIT;
