-- Description: Creates the worker_heartbeat table for Phase 8 Observability

BEGIN;

CREATE TABLE IF NOT EXISTS public.worker_heartbeat (
    worker_id TEXT PRIMARY KEY,
    last_beat_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    last_tick_duration_ms INTEGER,
    last_tick_leads_processed INTEGER
);

ALTER TABLE public.worker_heartbeat ENABLE ROW LEVEL SECURITY;

-- Service role bypass
DROP POLICY IF EXISTS "worker_heartbeat_service_bypass" ON public.worker_heartbeat;
CREATE POLICY "worker_heartbeat_service_bypass" ON public.worker_heartbeat USING (auth.role() = 'service_role');

COMMIT;
