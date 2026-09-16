-- 014_gdpr_cascades.sql
-- Enforce ON DELETE CASCADE for all PII tables on workspace_id
ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_workspace_id_fkey;
ALTER TABLE public.leads ADD CONSTRAINT leads_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;

ALTER TABLE public.messages DROP CONSTRAINT IF EXISTS messages_workspace_id_fkey;
ALTER TABLE public.messages ADD CONSTRAINT messages_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;

ALTER TABLE public.accounts DROP CONSTRAINT IF EXISTS accounts_workspace_id_fkey;
ALTER TABLE public.accounts ADD CONSTRAINT accounts_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;

ALTER TABLE public.action_log DROP CONSTRAINT IF EXISTS action_log_workspace_id_fkey;
ALTER TABLE public.action_log ADD CONSTRAINT action_log_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;

ALTER TABLE public.campaigns DROP CONSTRAINT IF EXISTS campaigns_workspace_id_fkey;
ALTER TABLE public.campaigns ADD CONSTRAINT campaigns_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;

ALTER TABLE public.lead_lists DROP CONSTRAINT IF EXISTS lead_lists_workspace_id_fkey;
ALTER TABLE public.lead_lists ADD CONSTRAINT lead_lists_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;

ALTER TABLE public.approval_queue DROP CONSTRAINT IF EXISTS approval_queue_workspace_id_fkey;
ALTER TABLE public.approval_queue ADD CONSTRAINT approval_queue_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;

ALTER TABLE public.outbox_events DROP CONSTRAINT IF EXISTS outbox_events_workspace_id_fkey;
ALTER TABLE public.outbox_events ADD CONSTRAINT outbox_events_workspace_id_fkey FOREIGN KEY (workspace_id) REFERENCES public.workspaces(id) ON DELETE CASCADE;
