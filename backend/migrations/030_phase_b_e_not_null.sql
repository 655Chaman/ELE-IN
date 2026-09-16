-- EXECUTION: TRANSACTIONAL

SET LOCAL lock_timeout = '2s';

ALTER TABLE public.campaign_execution_states
ALTER COLUMN workspace_id SET NOT NULL;

ALTER TABLE public.campaign_execution_states
DROP CONSTRAINT IF EXISTS chk_ces_workspace_id_not_null;
