-- EXECUTION: TRANSACTIONAL

SET LOCAL lock_timeout = '2s';

ALTER TABLE public.campaign_enrollments
ADD CONSTRAINT uq_campaign_enrollments_id_ws UNIQUE USING INDEX uq_campaign_enrollments_id_ws;

ALTER TABLE public.campaign_execution_states
ADD CONSTRAINT fk_ces_enrollment_ws FOREIGN KEY (enrollment_id, workspace_id) REFERENCES public.campaign_enrollments(id, workspace_id) ON UPDATE RESTRICT ON DELETE CASCADE NOT VALID;

ALTER TABLE public.campaign_execution_states
ADD CONSTRAINT chk_ces_workspace_id_not_null CHECK (workspace_id IS NOT NULL) NOT VALID;

ALTER TABLE public.campaign_execution_states
DROP CONSTRAINT IF EXISTS campaign_execution_states_enrollment_id_fkey;
