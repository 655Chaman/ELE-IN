BEGIN;

ALTER TABLE public.campaign_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_enrollments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_execution_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campaign_node_executions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS campaign_accounts_select ON public.campaign_accounts;
CREATE POLICY campaign_accounts_select ON public.campaign_accounts
FOR SELECT
TO authenticated
USING (
    campaign_id IN (
        SELECT id FROM public.campaigns 
        WHERE workspace_id IN (SELECT public.my_workspace_ids())
    )
);

DROP POLICY IF EXISTS campaign_enrollments_select ON public.campaign_enrollments;
CREATE POLICY campaign_enrollments_select ON public.campaign_enrollments
FOR SELECT
TO authenticated
USING (
    workspace_id IN (SELECT public.my_workspace_ids())
);

DROP POLICY IF EXISTS campaign_execution_states_select ON public.campaign_execution_states;
CREATE POLICY campaign_execution_states_select ON public.campaign_execution_states
FOR SELECT
TO authenticated
USING (
    workspace_id IN (SELECT public.my_workspace_ids())
);

COMMIT;
