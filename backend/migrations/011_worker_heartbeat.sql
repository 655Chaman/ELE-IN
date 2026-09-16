CREATE TABLE IF NOT EXISTS public.worker_heartbeat (
    worker_id text NOT NULL,
    last_beat_at timestamp with time zone NOT NULL DEFAULT now(),
    tick_count bigint NOT NULL DEFAULT 0,
    last_tick_duration_ms integer,
    last_tick_leads_processed integer,
    status text NOT NULL DEFAULT 'alive',
    CONSTRAINT worker_heartbeat_pkey PRIMARY KEY (worker_id)
);

-- Seed the default worker row so upsert always hits an existing row
INSERT INTO public.worker_heartbeat (worker_id, status)
VALUES ('elein-daemon', 'starting')
ON CONFLICT (worker_id) DO NOTHING;
