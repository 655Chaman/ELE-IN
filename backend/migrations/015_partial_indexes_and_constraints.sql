BEGIN;

-- 1. Optimize the scheduler index to be a partial index (smaller, faster)
DROP INDEX IF EXISTS public.idx_accounts_workspace_status;
CREATE INDEX idx_accounts_workspace_status ON public.accounts (workspace_id, status) WHERE status = 'ACTIVE';

-- 2. Enforce proxy exclusivity. Shared proxies cause cascading LinkedIn bans.
CREATE UNIQUE INDEX uq_proxy_single_account ON public.accounts (proxy_id) WHERE proxy_id IS NOT NULL;

COMMIT;
