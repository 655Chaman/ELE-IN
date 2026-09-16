-- EXECUTION: TRANSACTIONAL

ALTER TABLE public.campaign_execution_states VALIDATE CONSTRAINT fk_ces_enrollment_ws;
ALTER TABLE public.campaign_execution_states VALIDATE CONSTRAINT chk_ces_workspace_id_not_null;
