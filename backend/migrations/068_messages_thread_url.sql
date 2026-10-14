-- Paranoia Framework: Add thread_url to prevent name collision messaging errors.
BEGIN;

ALTER TABLE public.messages ADD COLUMN thread_url TEXT;
ALTER TABLE public.approval_queue ADD COLUMN thread_url TEXT;

COMMIT;
