-- EXECUTION: NON-TRANSACTIONAL
CREATE INDEX CONCURRENTLY idx_workspaces_queue_poll ON public.workspaces (last_queue_poll_at ASC, id ASC);
