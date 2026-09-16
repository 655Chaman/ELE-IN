-- EXECUTION: NON-TRANSACTIONAL
CREATE UNIQUE INDEX CONCURRENTLY uq_campaign_enrollments_id_ws ON public.campaign_enrollments (id, workspace_id);
