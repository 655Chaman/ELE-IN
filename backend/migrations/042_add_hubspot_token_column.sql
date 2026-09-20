BEGIN;

ALTER TABLE public.workspaces ADD COLUMN IF NOT EXISTS hubspot_token TEXT;

COMMIT;
