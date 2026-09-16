-- EXECUTION: NON-TRANSACTIONAL
CREATE INDEX CONCURRENTLY idx_ces_workspace_next_run ON public.campaign_execution_states (workspace_id, next_run_at ASC) WHERE status IN ('pending', 'running');
