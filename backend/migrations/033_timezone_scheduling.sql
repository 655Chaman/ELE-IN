-- Migration: 033_timezone_scheduling
-- Description: Phase 1 of Lead-Local Timezone Scheduling (Additive only)

ALTER TABLE public.leads ADD COLUMN IF NOT EXISTS timezone TEXT;

CREATE TABLE IF NOT EXISTS public.location_timezone_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    normalized_location TEXT UNIQUE NOT NULL,
    iana_timezone TEXT,
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('resolved', 'ambiguous', 'unresolved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index on resolution_status to support efficient querying of unresolved/ambiguous entries
CREATE INDEX IF NOT EXISTS idx_location_timezone_cache_status
ON public.location_timezone_cache(resolution_status);
