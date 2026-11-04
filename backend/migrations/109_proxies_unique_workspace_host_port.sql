-- Migration 109: Proxy Pool Workspace Host Port Unique Constraint & Index Hardening
-- Paranoia Layer 0 & 1: Supports PostgREST upsert on (workspace_id, host, port) and ensures clean tenant isolation.

BEGIN;

-- 1. Deduplicate any existing duplicate entries per workspace before applying unique index
DELETE FROM public.proxies a
USING public.proxies b
WHERE a.id > b.id
  AND a.host = b.host
  AND a.port = b.port
  AND (
    (a.workspace_id = b.workspace_id)
    OR (a.workspace_id IS NULL AND b.workspace_id IS NULL)
  );

-- 2. Create unique index for workspace-dedicated proxies
CREATE UNIQUE INDEX IF NOT EXISTS uq_proxies_workspace_host_port
ON public.proxies (workspace_id, host, port)
WHERE workspace_id IS NOT NULL;

-- 3. Create unique index for system-shared proxies (workspace_id IS NULL)
CREATE UNIQUE INDEX IF NOT EXISTS uq_proxies_system_host_port
ON public.proxies (host, port)
WHERE workspace_id IS NULL;

-- 4. Add the explicit table constraint for workspace proxies to support on_conflict="workspace_id,host,port"
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_proxies_workspace_host_port_constraint'
    ) THEN
        ALTER TABLE public.proxies
        ADD CONSTRAINT uq_proxies_workspace_host_port_constraint
        UNIQUE (workspace_id, host, port);
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Notice: table constraint creation skipped or deferred: %', SQLERRM;
END $$;

COMMIT;
