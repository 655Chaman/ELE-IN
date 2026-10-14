-- Migration 077: Proxy Quarantine & Sticky Geo-Affinity
BEGIN;

ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS quarantined_until TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE public.proxies ADD COLUMN IF NOT EXISTS quarantine_reason TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_proxies_quarantined ON public.proxies(status, quarantined_until);

COMMIT;
