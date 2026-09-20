BEGIN;

-- 1. campaign_accounts: Scoped via campaign ownership
ALTER TABLE public.campaign_accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS campaign_accounts_tenant_isolation ON public.campaign_accounts;
CREATE POLICY campaign_accounts_tenant_isolation ON public.campaign_accounts
    FOR ALL
    USING (
        campaign_id IN (
            SELECT id FROM public.campaigns WHERE workspace_id = public.get_my_workspace_id()
        )
    );

-- 2. processing_jobs: Direct workspace_id check
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS processing_jobs_tenant_isolation ON public.processing_jobs;
CREATE POLICY processing_jobs_tenant_isolation ON public.processing_jobs
    FOR ALL
    USING (workspace_id = public.get_my_workspace_id());

-- 3. worker_heartbeat: Read-only for any authenticated user
ALTER TABLE public.worker_heartbeat ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS worker_heartbeat_read ON public.worker_heartbeat;
CREATE POLICY worker_heartbeat_read ON public.worker_heartbeat
    FOR SELECT
    USING (auth.role() = 'authenticated');

COMMIT;
