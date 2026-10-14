BEGIN;

-- Add missing statuses to account_status ENUM
ALTER TYPE public.account_status ADD VALUE IF NOT EXISTS 'MANUAL_MODE';
ALTER TYPE public.account_status ADD VALUE IF NOT EXISTS 'SUSPENDED';
ALTER TYPE public.account_status ADD VALUE IF NOT EXISTS 'NEEDS_ATTENTION';
ALTER TYPE public.account_status ADD VALUE IF NOT EXISTS 'NEEDS_REVIEW';
ALTER TYPE public.account_status ADD VALUE IF NOT EXISTS 'DISABLED';

COMMIT;
