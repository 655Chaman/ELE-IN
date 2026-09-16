-- Removes duplicate unique constraints created by 001, 016, 017. Keeps only uq_leads_workspace_linkedin as the canonical constraint.

DROP INDEX IF EXISTS leads_workspace_linkedin_url_uniq;
ALTER TABLE public.leads DROP CONSTRAINT IF EXISTS leads_workspace_linkedin_key;

ALTER TABLE public.leads
  DROP CONSTRAINT IF EXISTS uq_leads_workspace_linkedin;
ALTER TABLE public.leads
  ADD CONSTRAINT uq_leads_workspace_linkedin UNIQUE (workspace_id, linkedin_url);
