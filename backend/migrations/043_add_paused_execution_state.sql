BEGIN;

ALTER TYPE public.lead_state_status ADD VALUE IF NOT EXISTS 'paused';

COMMIT;
