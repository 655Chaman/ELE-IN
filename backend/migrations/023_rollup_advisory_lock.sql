-- PARANOIA LAYER 1: ENVIRONMENTAL
-- Advisory locks over PostgREST connection pools are unsafe because acquire and release may hit different pooled connections.
-- We use a table-based singleton lock with check-and-set semantics for a fully atomic, stateless-safe locking mechanism.

CREATE TABLE IF NOT EXISTS processing_locks (
    lock_name text PRIMARY KEY,
    locked_until timestamp with time zone
);

INSERT INTO processing_locks (lock_name, locked_until) 
VALUES ('dashboard_rollup', '1970-01-01 00:00:00+00') 
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION try_acquire_rollup_lock()
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE
    v_updated boolean;
BEGIN
    UPDATE processing_locks
    SET locked_until = now() + interval '2 hours'
    WHERE lock_name = 'dashboard_rollup'
      AND locked_until <= now()
    RETURNING true INTO v_updated;

    RETURN coalesce(v_updated, false);
END;
$$;

CREATE OR REPLACE FUNCTION release_rollup_lock()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    UPDATE processing_locks
    SET locked_until = '1970-01-01 00:00:00+00'
    WHERE lock_name = 'dashboard_rollup';
END;
$$;
